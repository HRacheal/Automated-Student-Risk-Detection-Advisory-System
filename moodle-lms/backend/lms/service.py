"""
Student-scoped view of Moodle. Every method runs with the signed-in student's own Moodle
token, so the data is exactly what Moodle lets that student see. Nothing here invents
values: when Moodle has no value (no grade yet, no completion tracking...) the field is
None and the UI says so.
"""
import asyncio
import html
import re
import time
from typing import Any, Optional
from urllib.parse import quote

from . import quiz_html
from .config import settings
from .moodle import MoodleClient, MoodleError
from .sessions import Session

SHORT_TTL = 60        # activity state (submissions, attempts, completion)
LONG_TTL = 600        # structure (course list, contacts, assignment settings)
DAY = 86400


class NotFound(Exception):
    pass


def _now() -> int:
    return int(time.time())


def _title(course: dict) -> tuple[str, Optional[str]]:
    """'DSA3010 Machine Learning Foundations (Fall 2026)' -> ('Machine Learning Foundations', 'Fall 2026')."""
    name = course.get("fullname") or course.get("displayname") or course.get("shortname") or ""
    short = course.get("shortname") or ""
    if short and name.startswith(short):
        name = name[len(short):].strip(" -:")
    term = None
    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", name)
    if m:
        name, term = m.group(1), m.group(2)
    return name or short, term


def _plain(value: Optional[str]) -> str:
    return quiz_html.html_to_text(value) if value else ""


def file_link(url: Optional[str]) -> Optional[str]:
    """Moodle file URLs are only served through our /api/files proxy (which adds the token server-side)."""
    return f"/api/files?url={quote(url, safe='')}" if url else None


class StudentLMS:
    def __init__(self, session: Session, moodle: MoodleClient):
        self.s = session
        self.m = moodle
        self._sem = asyncio.Semaphore(settings.MOODLE_PARALLEL_CALLS)

    async def call(self, function: str, **params: Any) -> Any:
        async with self._sem:
            return await self.m.call(self.s.token, function, **params)

    async def gather(self, *aws):
        return await asyncio.gather(*aws)

    # ------------------------------------------------------------------ courses
    async def _raw_courses(self) -> list[dict]:
        return await self.s.cached("courses", SHORT_TTL, lambda: self.call(
            "core_enrol_get_users_courses", userid=self.s.moodle_userid, returnusercount=0))

    async def course_ids(self) -> list[int]:
        return [c["id"] for c in await self._raw_courses()]

    async def require_course(self, course_id: int) -> dict:
        for c in await self._raw_courses():
            if c["id"] == course_id:
                return c
        raise NotFound("You are not enrolled in this course.")

    async def _contacts(self) -> dict[int, list[str]]:
        async def load():
            ids = await self.course_ids()
            if not ids:
                return {}
            res = await self.call("core_course_get_courses_by_field", field="ids", value=",".join(map(str, ids)))
            return {c["id"]: [p.get("fullname") for p in c.get("contacts", [])] for c in res.get("courses", [])}
        return await self.s.cached("contacts", LONG_TTL, load)

    def _course_summary(self, c: dict, contacts: dict[int, list[str]]) -> dict:
        title, term = _title(c)
        progress = c.get("progress")
        return {
            "id": c["id"], "code": c.get("shortname"), "title": title, "term": term, "fullname": c.get("fullname"),
            "summary": _plain(c.get("summary")),
            "instructors": contacts.get(c["id"], []),
            "progress": round(progress, 1) if isinstance(progress, (int, float)) and c.get("enablecompletion") else None,
            "completed": bool(c.get("completed")),
            "completion_enabled": bool(c.get("enablecompletion")),
            "last_access": c.get("lastaccess") or None,
            "start_date": c.get("startdate") or None, "end_date": c.get("enddate") or None,
        }

    async def courses(self) -> list[dict]:
        raw, contacts = await self.gather(self._raw_courses(), self._contacts())
        return sorted((self._course_summary(c, contacts) for c in raw), key=lambda c: c["code"] or "")

    async def contents(self, course_id: int) -> list[dict]:
        await self.require_course(course_id)
        return await self.s.cached(f"contents:{course_id}", SHORT_TTL,
                                   lambda: self.call("core_course_get_contents", courseid=course_id))

    # ------------------------------------------------------------------ assignments
    async def _assign_index(self) -> dict[int, dict]:
        """cmid -> assignment settings (from mod_assign_get_assignments)."""
        async def load():
            ids = await self.course_ids()
            if not ids:
                return {}
            res = await self.call("mod_assign_get_assignments", courseids=ids)
            out = {}
            for course in res.get("courses", []):
                for a in course.get("assignments", []):
                    a["_course_code"] = course.get("shortname")
                    out[a["cmid"]] = a
            return out
        return await self.s.cached("assign_index", LONG_TTL, load)

    async def _submission_status(self, assign_id: int) -> dict:
        return await self.s.cached(f"substatus:{assign_id}", SHORT_TTL,
                                   lambda: self.call("mod_assign_get_submission_status", assignid=assign_id))

    @staticmethod
    def _configs(a: dict) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for cfg in a.get("configs", []):
            if cfg.get("subtype") == "assignsubmission":
                out.setdefault(cfg["plugin"], {})[cfg["name"]] = cfg["value"]
        return out

    def _assignment_view(self, a: dict, st: dict, detail: bool = False) -> dict:
        now = _now()
        last = st.get("lastattempt") or {}
        sub = last.get("submission") or (last.get("teamsubmission") if a.get("teamsubmission") else None) or {}
        cfg = self._configs(a)
        due = a.get("duedate") or 0
        extension = last.get("extensionduedate") or 0
        effective_due = max(due, extension) if extension else due
        cutoff = a.get("cutoffdate") or 0
        status = sub.get("status") or "new"
        submitted = status == "submitted"
        submitted_at = sub.get("timemodified") if submitted else None
        late_by = (submitted_at - effective_due) if (submitted and effective_due and submitted_at > effective_due) else 0
        opens = a.get("allowsubmissionsfromdate") or 0

        feedback = st.get("feedback") or {}
        grade_display = html.unescape(feedback.get("gradefordisplay") or "").replace("\xa0", " ").strip() or None
        comments = []
        for plugin in feedback.get("plugins", []) or []:
            for ef in plugin.get("editorfields", []) or []:
                txt = _plain(ef.get("text"))
                if txt:
                    comments.append(txt)

        if submitted:
            state = "submitted"
        elif status == "draft":
            state = "draft"
        elif cutoff and now > cutoff:
            state = "closed"         # past the cut-off: Moodle no longer accepts it
        elif effective_due and now > effective_due:
            state = "overdue"        # late submissions still accepted until the cut-off
        elif opens and now < opens:
            state = "not_open"
        else:
            state = "open"

        view = {
            "cmid": a["cmid"], "id": a["id"], "course_id": a["course"], "course_code": a.get("_course_code"),
            "name": a.get("name"), "due_date": due or None, "extension_due_date": extension or None,
            "cutoff_date": cutoff or None, "opens": opens or None, "max_grade": a.get("grade"),
            "state": state, "submission_status": status, "submitted_at": submitted_at,
            "late": bool(late_by), "late_by_seconds": late_by or None,
            "grading_status": last.get("gradingstatus"), "graded": bool(last.get("graded")),
            "grade": grade_display, "graded_at": feedback.get("gradeddate"), "feedback": comments,
            "can_edit": bool(last.get("canedit")) and state not in {"closed", "not_open"},
            "can_submit_for_grading": bool(last.get("cansubmit")),
            "requires_submit_for_grading": bool(a.get("submissiondrafts")),
            "submissions_enabled": bool(last.get("submissionsenabled", True)) and not a.get("nosubmissions"),
            "locked": bool(last.get("locked")),
        }
        if detail:
            files, text = [], ""
            for plugin in sub.get("plugins", []) or []:
                if plugin.get("type") == "file":
                    for area in plugin.get("fileareas", []) or []:
                        for f in area.get("files", []) or []:
                            files.append({"filename": f.get("filename"), "size": f.get("filesize"),
                                          "mimetype": f.get("mimetype"), "modified": f.get("timemodified"),
                                          "url": file_link(f.get("fileurl"))})
                if plugin.get("type") == "onlinetext":
                    for ef in plugin.get("editorfields", []) or []:
                        text = _plain(ef.get("text"))
            max_bytes = int(cfg.get("file", {}).get("maxsubmissionsizebytes") or 0) or None
            intro_files = [{"filename": f.get("filename"), "size": f.get("filesize"), "url": file_link(f.get("fileurl"))}
                           for f in (a.get("introattachments") or []) + (a.get("introfiles") or [])]
            view.update({
                "description": _plain(a.get("intro")),
                "attachments": intro_files,
                "file_submissions": cfg.get("file", {}).get("enabled") == "1",
                "max_files": int(cfg.get("file", {}).get("maxfilesubmissions") or 0) or None,
                "max_bytes": max_bytes,
                "accepted_types": cfg.get("file", {}).get("filetypeslist") or None,
                "online_text": cfg.get("onlinetext", {}).get("enabled") == "1",
                "submitted_files": files, "submitted_text": text,
                "submission_created": sub.get("timecreated"), "submission_modified": sub.get("timemodified"),
                "staged_files": self.s.draft_files.get(a["cmid"], []),
                "grading_due_date": a.get("gradingduedate") or None,
            })
        return view

    async def assignments(self, course_id: Optional[int] = None) -> list[dict]:
        index = await self._assign_index()
        items = [a for a in index.values() if course_id is None or a["course"] == course_id]
        statuses = await self.gather(*(self._submission_status(a["id"]) for a in items))
        views = [self._assignment_view(a, st) for a, st in zip(items, statuses)]
        return sorted(views, key=lambda v: (v["due_date"] or 2**40, v["course_code"] or "", v["name"] or ""))

    async def _assignment(self, cmid: int) -> dict:
        a = (await self._assign_index()).get(cmid)
        if not a:
            raise NotFound("Assignment not found in your courses.")
        return a

    async def assignment(self, cmid: int, log_view: bool = True) -> dict:
        a = await self._assignment(cmid)
        st = await self._submission_status(a["id"])
        if log_view:
            try:   # records the view in Moodle's logs (real engagement, seen by My Coach)
                await self.call("mod_assign_view_submission_status", assignid=a["id"])
            except MoodleError:
                pass
        view = self._assignment_view(a, st, detail=True)
        course = await self.require_course(a["course"])
        view["course_title"] = _title(course)[0]
        return view

    async def stage_file(self, cmid: int, filename: str, content: bytes) -> dict:
        a = await self._assignment(cmid)
        view = self._assignment_view(a, await self._submission_status(a["id"]), detail=True)
        if not view["file_submissions"]:
            raise MoodleError("filesnotenabled", "This assignment does not accept file submissions.")
        if not view["can_edit"]:
            raise MoodleError("submissionclosed", "This assignment is not accepting submissions.")
        staged = self.s.draft_files.get(cmid, [])
        if view["max_files"] and len(staged) >= view["max_files"]:
            raise MoodleError("toomanyfiles", f"You can upload at most {view['max_files']} file(s).")
        if view["max_bytes"] and len(content) > view["max_bytes"]:
            raise MoodleError("filetoobig", "The file is larger than this assignment allows.")
        if any(f["filename"] == filename for f in staged):
            raise MoodleError("duplicatefile", "A file with this name is already staged.")
        stored = await self.m.upload_draft(self.s.token, filename, content, self.s.drafts.get(cmid, 0))
        self.s.drafts[cmid] = int(stored[0]["itemid"])
        staged = staged + [{"filename": stored[0].get("filename", filename), "size": len(content)}]
        self.s.draft_files[cmid] = staged
        return {"staged_files": staged}

    def clear_staged(self, cmid: int) -> None:
        self.s.drafts.pop(cmid, None)
        self.s.draft_files.pop(cmid, None)

    async def submit(self, cmid: int, text: Optional[str]) -> dict:
        a = await self._assignment(cmid)
        self.s.invalidate(f"substatus:{a['id']}")
        current = self._assignment_view(a, await self._submission_status(a["id"]), detail=True)
        if not current["can_edit"]:
            raise MoodleError("submissionclosed", "This assignment is not accepting submissions.")
        plugindata: dict[str, Any] = {}
        if cmid in self.s.drafts:
            plugindata["files_filemanager"] = self.s.drafts[cmid]
        if current["online_text"]:
            # Always resend the text: omitting it would blank a previous online-text answer.
            body = current["submitted_text"] if text is None else text
            paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in body.split("\n") if p.strip())
            plugindata["onlinetext_editor"] = {"text": paragraphs, "format": 1, "itemid": 0}
        if "files_filemanager" not in plugindata and not (text or "").strip():
            raise MoodleError("submissionempty", "Upload a file (or enter text) before submitting.")

        warnings = await self.call("mod_assign_save_submission", assignmentid=a["id"], plugindata=plugindata)
        if warnings:
            raise MoodleError("couldnotsavesubmission", "; ".join(w.get("message", "") for w in warnings))
        if a.get("submissiondrafts"):
            warnings = await self.call("mod_assign_submit_for_grading", assignmentid=a["id"], acceptsubmissionstatement=1)
            if warnings:
                raise MoodleError("couldnotsubmitforgrading", "; ".join(w.get("message", "") for w in warnings))
        self.clear_staged(cmid)
        self.s.invalidate("substatus:", "contents:", "courses", "grades:", "activity")
        return await self.assignment(cmid, log_view=False)

    # ------------------------------------------------------------------ quizzes
    async def _quiz_index(self) -> dict[int, dict]:
        async def load():
            ids = await self.course_ids()
            if not ids:
                return {}
            res = await self.call("mod_quiz_get_quizzes_by_courses", courseids=ids)
            codes = {c["id"]: c.get("shortname") for c in await self._raw_courses()}
            out = {}
            for q in res.get("quizzes", []):
                q["_course_code"] = codes.get(q["course"])
                out[q["coursemodule"]] = q
            return out
        return await self.s.cached("quiz_index", LONG_TTL, load)

    async def _attempts(self, quiz_id: int) -> list[dict]:
        res = await self.s.cached(f"attempts:{quiz_id}", SHORT_TTL, lambda: self.call(
            "mod_quiz_get_user_attempts", quizid=quiz_id, status="all", includepreviews=0))
        return res.get("attempts", [])

    async def _best(self, quiz_id: int) -> dict:
        return await self.s.cached(f"best:{quiz_id}", SHORT_TTL,
                                   lambda: self.call("mod_quiz_get_user_best_grade", quizid=quiz_id))

    @staticmethod
    def _scaled(q: dict, sumgrades: Optional[float]) -> Optional[float]:
        if sumgrades is None or not q.get("sumgrades"):
            return None
        return round(sumgrades / q["sumgrades"] * q.get("grade", 0), 2)

    def _quiz_view(self, q: dict, attempts: list[dict], best: dict) -> dict:
        now = _now()
        opens, closes = q.get("timeopen") or 0, q.get("timeclose") or 0
        finished = [t for t in attempts if t.get("state") in {"finished", "abandoned"}]
        in_progress = next((t for t in attempts if t.get("state") in {"inprogress", "overdue"}), None)
        allowed = q.get("attempts") or 0   # 0 = unlimited
        if in_progress:
            state = "in_progress"
        elif opens and now < opens:
            state = "not_open"
        elif closes and now > closes:
            state = "closed" if not finished else "completed"
        elif allowed and len(finished) >= allowed:
            state = "completed"
        elif finished:
            state = "attempted"
        else:
            state = "open"
        grade = best.get("grade") if best.get("hasgrade") else None
        return {
            "cmid": q["coursemodule"], "id": q["id"], "course_id": q["course"], "course_code": q.get("_course_code"),
            "name": q.get("name"), "opens": opens or None, "closes": closes or None,
            "time_limit": q.get("timelimit") or None, "attempts_allowed": allowed or None,
            "attempts_used": len(finished), "max_grade": q.get("grade"),
            "grade": round(grade, 2) if grade is not None else None,
            "state": state, "in_progress_attempt": in_progress["id"] if in_progress else None,
            "last_finished": max((t.get("timefinish") or 0 for t in finished), default=0) or None,
        }

    async def quizzes(self, course_id: Optional[int] = None) -> list[dict]:
        index = await self._quiz_index()
        items = [q for q in index.values() if course_id is None or q["course"] == course_id]
        attempts = await self.gather(*(self._attempts(q["id"]) for q in items))
        bests = await self.gather(*(self._best(q["id"]) for q in items))
        views = [self._quiz_view(q, at, b) for q, at, b in zip(items, attempts, bests)]
        return sorted(views, key=lambda v: (v["closes"] or 2**40, v["course_code"] or "", v["name"] or ""))

    async def _quiz(self, cmid: int) -> dict:
        q = (await self._quiz_index()).get(cmid)
        if not q:
            raise NotFound("Quiz not found in your courses.")
        return q

    async def quiz(self, cmid: int) -> dict:
        q = await self._quiz(cmid)
        attempts, best, access = await self.gather(
            self._attempts(q["id"]), self._best(q["id"]),
            self.call("mod_quiz_get_quiz_access_information", quizid=q["id"]))
        attempt_access = await self.call("mod_quiz_get_attempt_access_information", quizid=q["id"])
        try:
            await self.call("mod_quiz_view_quiz", quizid=q["id"])
        except MoodleError:
            pass
        view = self._quiz_view(q, attempts, best)
        feedback = ""
        if view["grade"] is not None:
            try:
                fb = await self.call("mod_quiz_get_quiz_feedback_for_grade", quizid=q["id"], grade=view["grade"])
                feedback = _plain(fb.get("feedbacktext"))
            except MoodleError:
                pass
        course = await self.require_course(q["course"])
        view.update({
            "course_title": _title(course)[0],
            "description": _plain(q.get("intro")),
            "grade_method": {1: "Highest grade", 2: "Average grade", 3: "First attempt", 4: "Last attempt"}.get(q.get("grademethod")),
            "rules": access.get("accessrules", []),
            "can_attempt": bool(access.get("canattempt")),
            "can_review": bool(access.get("canreviewmyattempts")),
            "prevent_access": access.get("preventaccessreasons", []),
            "prevent_new_attempt": attempt_access.get("preventnewattemptreasons", []),
            "overall_feedback": feedback,
            "attempts": [{
                "id": t["id"], "number": t.get("attempt"), "state": t.get("state"),
                "started": t.get("timestart") or None, "finished": t.get("timefinish") or None,
                "grade": self._scaled(q, t.get("sumgrades")),
            } for t in sorted(attempts, key=lambda t: t.get("attempt") or 0)],
        })
        return view

    async def start_attempt(self, cmid: int) -> dict:
        q = await self._quiz(cmid)
        self.s.invalidate(f"attempts:{q['id']}")
        existing = next((t for t in await self._attempts(q["id"]) if t.get("state") in {"inprogress", "overdue"}), None)
        if existing:
            return {"attempt_id": existing["id"], "resumed": True}
        res = await self.call("mod_quiz_start_attempt", quizid=q["id"], preflightdata=[], forcenew=0)
        self.s.invalidate(f"attempts:{q['id']}", "activity")
        return {"attempt_id": res["attempt"]["id"], "resumed": False}

    async def _quiz_for_attempt(self, attempt_id: int, quiz_id: int) -> dict:
        for q in (await self._quiz_index()).values():
            if q["id"] == quiz_id:
                return q
        raise NotFound("Quiz not found in your courses.")

    async def attempt_page(self, attempt_id: int, page: int) -> dict:
        res = await self.call("mod_quiz_get_attempt_data", attemptid=attempt_id, page=page, preflightdata=[])
        attempt = res.get("attempt", {})
        if attempt.get("userid") != self.s.moodle_userid:
            raise NotFound("Attempt not found.")
        q = await self._quiz_for_attempt(attempt_id, attempt.get("quiz"))
        try:
            await self.call("mod_quiz_view_attempt", attemptid=attempt_id, page=page, preflightdata=[])
        except MoodleError:
            pass
        layout = [p for p in (attempt.get("layout") or "").split(",")]
        pages = max(1, layout.count("0"))
        questions = [quiz_html.parse_question(x) for x in res.get("questions", [])]
        return {
            "attempt_id": attempt_id, "quiz_cmid": q["coursemodule"], "quiz_name": q.get("name"),
            "course_code": q.get("_course_code"), "state": attempt.get("state"),
            "page": page, "pages": pages, "next_page": res.get("nextpage"),
            "time_limit": q.get("timelimit") or None, "started": attempt.get("timestart"),
            "messages": res.get("messages", []),
            "questions": [{k: v for k, v in qq.items() if k != "hidden"} for qq in questions],
            "_parsed": questions,
        }

    async def save_attempt_page(self, attempt_id: int, page: int, answers: dict, finish: bool) -> dict:
        current = await self.attempt_page(attempt_id, page)
        data = quiz_html.build_submission(current["_parsed"], answers)
        res = await self.call("mod_quiz_process_attempt", attemptid=attempt_id, data=data,
                              finishattempt=1 if finish else 0, timeup=0, preflightdata=[])
        q = await self._quiz(current["quiz_cmid"])
        self.s.invalidate(f"attempts:{q['id']}", f"best:{q['id']}", "contents:", "courses", "grades:", "activity")
        return {"state": res.get("state"), "warnings": res.get("warnings", [])}

    async def finish_attempt(self, attempt_id: int) -> dict:
        info = await self.call("mod_quiz_get_attempt_data", attemptid=attempt_id, page=0, preflightdata=[])
        attempt = info.get("attempt", {})
        if attempt.get("userid") != self.s.moodle_userid:
            raise NotFound("Attempt not found.")
        out = await self.call("mod_quiz_process_attempt", attemptid=attempt_id, data=quiz_html.FINISH_ONLY,
                              finishattempt=1, timeup=0, preflightdata=[])
        quiz_id = attempt.get("quiz")
        self.s.invalidate(f"attempts:{quiz_id}", f"best:{quiz_id}", "contents:", "courses", "grades:")
        return {"state": out.get("state"), "warnings": out.get("warnings", [])}

    async def attempt_summary(self, attempt_id: int) -> dict:
        res = await self.call("mod_quiz_get_attempt_summary", attemptid=attempt_id, preflightdata=[])
        return {"questions": [{"slot": x.get("slot"), "number": x.get("questionnumber") or x.get("number"),
                               "status": x.get("status"), "page": x.get("page"),
                               "answered": x.get("stateclass") not in {"notyetanswered", "invalidanswer"}}
                              for x in res.get("questions", [])]}

    async def attempt_review(self, attempt_id: int) -> dict:
        res = await self.call("mod_quiz_get_attempt_review", attemptid=attempt_id, page=-1)
        attempt = res.get("attempt", {})
        if attempt.get("userid") != self.s.moodle_userid:
            raise NotFound("Attempt not found.")
        try:
            await self.call("mod_quiz_view_attempt_review", attemptid=attempt_id)
        except MoodleError:
            pass
        q = await self._quiz_for_attempt(attempt_id, attempt.get("quiz"))
        grade = res.get("grade")
        try:
            grade = float(grade) if grade not in (None, "") else None
        except (TypeError, ValueError):
            grade = None
        questions = [quiz_html.parse_question(x) for x in res.get("questions", [])]
        return {
            "attempt_id": attempt_id, "quiz_cmid": q["coursemodule"], "quiz_name": q.get("name"),
            "course_code": q.get("_course_code"), "state": attempt.get("state"),
            "started": attempt.get("timestart"), "finished": attempt.get("timefinish"),
            "grade": grade, "max_grade": q.get("grade"),
            "additional": [{"title": _plain(d.get("title")), "content": _plain(d.get("content"))}
                           for d in res.get("additionaldata", [])],
            "questions": [{k: v for k, v in qq.items() if k != "hidden"} for qq in questions],
        }

    # ------------------------------------------------------------------ grades
    async def grades(self, course_id: int) -> dict:
        course = await self.require_course(course_id)
        res = await self.s.cached(f"grades:{course_id}", SHORT_TTL, lambda: self.call(
            "gradereport_user_get_grade_items", courseid=course_id, userid=self.s.moodle_userid))
        items, total = [], None
        for ug in res.get("usergrades", []):
            if ug.get("userid") != self.s.moodle_userid:
                continue
            for it in ug.get("gradeitems", []):
                pct = html.unescape(it.get("percentageformatted") or "").strip()
                entry = {
                    "id": it.get("id"), "name": it.get("itemname"), "type": it.get("itemtype"),
                    "module": it.get("itemmodule"), "cmid": it.get("cmid"),
                    "grade": it.get("graderaw"), "grade_formatted": html.unescape(it.get("gradeformatted") or "").strip() or None,
                    "grade_max": it.get("grademax"), "grade_min": it.get("grademin"),
                    "percentage": None if pct in {"", "-"} else pct,
                    "range": html.unescape(it.get("rangeformatted") or "").strip() or None,
                    "weight": html.unescape(it.get("weightformatted") or "").strip() or None,
                    "graded_at": it.get("gradedategraded"),
                    "hidden": bool(it.get("gradeishidden")),
                    "feedback": _plain(it.get("feedback")),
                }
                if it.get("gradeishidden"):
                    entry.update(grade=None, grade_formatted=None, percentage=None)
                if it.get("itemtype") == "course":
                    total = entry
                elif it.get("itemtype") != "category":
                    items.append(entry)
        title, term = _title(course)
        return {"course_id": course_id, "course_code": course.get("shortname"), "course_title": title,
                "items": items, "course_total": total,
                "progress": round(course["progress"], 1) if isinstance(course.get("progress"), (int, float)) else None}

    async def all_grades(self) -> list[dict]:
        return list(await self.gather(*(self.grades(cid) for cid in await self.course_ids())))

    # ------------------------------------------------------------------ progress / completion
    async def course_progress(self, course_id: int) -> dict:
        course, sections = await self.gather(self.require_course(course_id), self.contents(course_id))
        activities = []
        for sec in sections:
            for mod in sec.get("modules", []):
                if not mod.get("uservisible", True):
                    continue
                cd = mod.get("completiondata") or {}
                activities.append({
                    "cmid": mod["id"], "name": mod.get("name"), "module": mod.get("modname"),
                    "section": sec.get("name"), "tracked": bool(cd.get("hascompletion")),
                    "completed": cd.get("state") in (1, 2) if cd.get("hascompletion") else None,
                    "completed_at": cd.get("timecompleted") or None,
                    "rules": [d.get("rulevalue", {}).get("description") for d in cd.get("details", []) or []],
                })
        tracked = [a for a in activities if a["tracked"]]
        done = [a for a in tracked if a["completed"]]
        by_type: dict[str, dict[str, int]] = {}
        for a in tracked:
            t = by_type.setdefault(a["module"], {"total": 0, "completed": 0})
            t["total"] += 1
            t["completed"] += 1 if a["completed"] else 0
        progress = course.get("progress")
        title, _ = _title(course)
        return {
            "course_id": course_id, "course_code": course.get("shortname"), "course_title": title,
            "completion_enabled": bool(course.get("enablecompletion")),
            # Moodle's own percentage (the one shown on the Moodle dashboard)
            "percentage": round(progress, 1) if isinstance(progress, (int, float)) else None,
            "completed": len(done), "tracked": len(tracked), "remaining": len(tracked) - len(done),
            "by_type": by_type, "last_access": course.get("lastaccess") or None,
            "activities": activities,
        }

    async def course_detail(self, course_id: int) -> dict:
        course = await self.require_course(course_id)
        try:   # logs the course view in Moodle (updates the student's real last-access)
            await self.call("core_course_view_course", courseid=course_id)
        except MoodleError:
            pass
        contacts, sections, assigns, quizzes, progress = await self.gather(
            self._contacts(), self.contents(course_id), self.assignments(course_id),
            self.quizzes(course_id), self.course_progress(course_id))
        assign_by_cm = {a["cmid"]: a for a in assigns}
        quiz_by_cm = {q["cmid"]: q for q in quizzes}
        out_sections = []
        for sec in sections:
            if not sec.get("uservisible", True):
                continue
            modules = []
            for mod in sec.get("modules", []):
                if not mod.get("uservisible", True):
                    continue
                cd = mod.get("completiondata") or {}
                entry = {
                    "cmid": mod["id"], "name": mod.get("name"), "module": mod.get("modname"),
                    "module_label": mod.get("modplural"), "description": _plain(mod.get("description")),
                    "dates": [{"label": d.get("label"), "timestamp": d.get("timestamp")} for d in mod.get("dates", [])],
                    "completion": {"tracked": bool(cd.get("hascompletion")),
                                   "completed": cd.get("state") in (1, 2) if cd.get("hascompletion") else None,
                                   "manual": cd.get("hascompletion") and not cd.get("isautomatic")},
                    "moodle_url": mod.get("url"),
                    "files": [{"filename": c.get("filename"), "size": c.get("filesize"),
                               "url": file_link(c.get("fileurl")) if c.get("type") == "file" else c.get("fileurl")}
                              for c in mod.get("contents", []) or [] if c.get("type") in {"file", "url"}],
                }
                if mod["id"] in assign_by_cm:
                    entry["assignment"] = assign_by_cm[mod["id"]]
                if mod["id"] in quiz_by_cm:
                    entry["quiz"] = quiz_by_cm[mod["id"]]
                modules.append(entry)
            out_sections.append({"id": sec["id"], "number": sec.get("section"), "name": sec.get("name"),
                                 "summary": _plain(sec.get("summary")), "modules": modules})
        summary = self._course_summary(course, contacts)
        return {**summary, "sections": out_sections, "assignments": assigns, "quizzes": quizzes, "progress_detail": progress}

    async def set_manual_completion(self, cmid: int, completed: bool) -> None:
        await self.call("core_completion_update_activity_completion_status_manually", cmid=cmid, completed=completed)
        self.s.invalidate("contents:", "courses", "activity")

    # ------------------------------------------------------------------ calendar
    async def calendar(self, start: int, end: int) -> list[dict]:
        ids = await self.course_ids()
        if not ids:
            return []
        res = await self.call("core_calendar_get_calendar_events",
                              events={"courseids": ids},
                              options={"userevents": 1, "siteevents": 1, "timestart": start, "timeend": end,
                                       "ignorehidden": 1})
        codes = {c["id"]: c.get("shortname") for c in await self._raw_courses()}
        assign_by_instance = {a["id"]: a for a in (await self._assign_index()).values()}
        quiz_by_instance = {q["id"]: q for q in (await self._quiz_index()).values()}
        out = []
        for e in res.get("events", []):
            link = None
            if e.get("modulename") == "assign" and e.get("instance") in assign_by_instance:
                link = f"/assignments/{assign_by_instance[e['instance']]['cmid']}"
            elif e.get("modulename") == "quiz" and e.get("instance") in quiz_by_instance:
                link = f"/quizzes/{quiz_by_instance[e['instance']]['coursemodule']}"
            out.append({
                "id": e["id"], "name": e.get("name"), "description": _plain(e.get("description")),
                "course_id": e.get("courseid") or None, "course_code": codes.get(e.get("courseid")),
                "module": e.get("modulename") or None, "event_type": e.get("eventtype"),
                "start": e.get("timestart"), "duration": e.get("timeduration") or 0, "link": link,
            })
        return sorted(out, key=lambda e: e["start"] or 0)

    # ------------------------------------------------------------------ activity / notifications
    async def _grade_items_all(self) -> list[dict]:
        out = []
        for g in await self.all_grades():
            for it in g["items"]:
                out.append({**it, "course_code": g["course_code"], "course_id": g["course_id"]})
        return out

    async def recent_activity(self, limit: int = 40) -> list[dict]:
        courses, assigns, quizzes, grade_items = await self.gather(
            self._raw_courses(), self.assignments(), self.quizzes(), self._grade_items_all())
        quiz_attempts = await self.gather(*(self._attempts(q["id"]) for q in quizzes))
        contents = await self.gather(*(self.contents(c["id"]) for c in courses))
        now = _now()
        events: list[dict] = []

        def add(kind, title, course_code, name, ts, status, link=None):
            if ts:
                events.append({"type": kind, "title": title, "course_code": course_code, "activity": name,
                               "timestamp": ts, "status": status, "link": link})

        for a in assigns:
            link = f"/assignments/{a['cmid']}"
            if a["submitted_at"]:
                add("assignment_submitted", "Assignment submitted", a["course_code"], a["name"], a["submitted_at"],
                    "Late" if a["late"] else "On time", link)
            if a["state"] in {"overdue", "closed"} and a["due_date"] and a["due_date"] < now:
                add("assignment_overdue", "Assignment overdue" if a["state"] == "overdue" else "Assignment missed",
                    a["course_code"], a["name"], a["due_date"],
                    "Late submission still accepted" if a["state"] == "overdue" else "Not submitted", link)
        for q, attempts in zip(quizzes, quiz_attempts):
            for t in attempts:
                if t.get("state") == "finished":
                    add("quiz_completed", "Quiz completed", q["course_code"], q["name"], t.get("timefinish"),
                        "Finished", f"/quizzes/{q['cmid']}")
                elif t.get("state") in {"inprogress", "overdue"}:
                    add("quiz_started", "Quiz attempt started", q["course_code"], q["name"], t.get("timestart"),
                        "In progress", f"/quizzes/{q['cmid']}")
        for it in grade_items:
            if it["graded_at"] and it["grade"] is not None:
                link = f"/assignments/{it['cmid']}" if it["module"] == "assign" else (
                    f"/quizzes/{it['cmid']}" if it["module"] == "quiz" else "/grades")
                add("grade_received", "Grade received", it["course_code"], it["name"], it["graded_at"],
                    it["percentage"] or it["grade_formatted"], link)
        for c, sections in zip(courses, contents):
            add("course_accessed", "Course accessed", c.get("shortname"), _title(c)[0], c.get("lastaccess"),
                "Visited", f"/courses/{c['id']}")
            for sec in sections:
                for mod in sec.get("modules", []):
                    cd = mod.get("completiondata") or {}
                    # submissions / quiz attempts already appear above; this adds the other activities
                    if cd.get("state") in (1, 2) and mod.get("modname") not in {"assign", "quiz"}:
                        add("activity_completed", "Activity completed", c.get("shortname"), mod.get("name"),
                            cd.get("timecompleted"), "Completed", f"/courses/{c['id']}")
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    async def upcoming(self, horizon_days: int = 21) -> dict:
        assigns, quizzes = await self.gather(self.assignments(), self.quizzes())
        now = _now()
        upcoming, overdue = [], []
        for a in assigns:
            entry = {"kind": "assignment", "cmid": a["cmid"], "name": a["name"], "course_code": a["course_code"],
                     "course_id": a["course_id"], "due": a["extension_due_date"] or a["due_date"],
                     "state": a["state"], "link": f"/assignments/{a['cmid']}", "cutoff": a["cutoff_date"]}
            if a["state"] in {"open", "draft"} and entry["due"] and entry["due"] <= now + horizon_days * DAY:
                upcoming.append(entry)
            elif a["state"] == "overdue":
                overdue.append(entry)
        for q in quizzes:
            if q["state"] in {"open", "in_progress", "not_open"} and q["closes"] \
                    and now <= q["closes"] <= now + horizon_days * DAY:
                upcoming.append({"kind": "quiz", "cmid": q["cmid"], "name": q["name"], "course_code": q["course_code"],
                                 "course_id": q["course_id"], "due": q["closes"], "opens": q["opens"],
                                 "state": q["state"], "link": f"/quizzes/{q['cmid']}"})
        upcoming.sort(key=lambda e: e["due"])
        overdue.sort(key=lambda e: e["due"])
        return {"upcoming": upcoming, "overdue": overdue}

    async def moodle_notifications(self) -> list[dict]:
        try:
            res = await self.call("message_popup_get_popup_notifications", useridto=self.s.moodle_userid,
                                  newestfirst=1, limit=30, offset=0)
        except MoodleError:
            return []
        return [{
            "id": f"moodle-{n['id']}", "moodle_id": n["id"], "source": "moodle", "type": n.get("eventtype") or "moodle",
            "title": n.get("subject"), "body": _plain(n.get("smallmessage") or n.get("fullmessage")),
            "course_code": None, "timestamp": n.get("timecreated"), "read": bool(n.get("read")), "link": None,
        } for n in res.get("notifications", [])]

    async def announcements(self) -> list[dict]:
        ids = await self.course_ids()
        if not ids:
            return []
        try:
            forums = await self.s.cached("forums", LONG_TTL, lambda: self.call("mod_forum_get_forums_by_courses", courseids=ids))
        except MoodleError:
            return []
        codes = {c["id"]: c.get("shortname") for c in await self._raw_courses()}
        news = [f for f in forums if f.get("type") == "news"]
        out = []
        for f in news:
            try:
                res = await self.call("mod_forum_get_forum_discussions", forumid=f["id"], sortorder=-1, page=0, perpage=5)
            except MoodleError:
                continue
            for d in res.get("discussions", []):
                out.append({"id": f"announcement-{d['id']}", "source": "moodle", "type": "announcement",
                            "title": d.get("name"), "body": _plain(d.get("message")),
                            "course_code": codes.get(f.get("course")), "timestamp": d.get("timemodified") or d.get("created"),
                            "read": True, "link": f"/courses/{f.get('course')}"})
        return out

    async def notifications(self) -> list[dict]:
        """Moodle's own notifications + announcements, plus reminders computed from the student's REAL
        Moodle dates and statuses (clearly labelled source='reminder')."""
        moodle, news, up, assigns, quizzes, grade_items = await self.gather(
            self.moodle_notifications(), self.announcements(), self.upcoming(horizon_days=3),
            self.assignments(), self.quizzes(), self._grade_items_all())
        now = _now()
        out = list(moodle) + list(news)
        for e in up["upcoming"]:
            kind = "Assignment" if e["kind"] == "assignment" else "Quiz"
            out.append({"id": f"due-{e['kind']}-{e['cmid']}", "source": "reminder", "type": "due_soon",
                        "title": f"{kind} due soon: {e['name']}",
                        "body": f"{e['course_code']} - {'due' if e['kind'] == 'assignment' else 'closes'} soon.",
                        "course_code": e["course_code"], "timestamp": e["due"], "read": False, "link": e["link"]})
        for e in up["overdue"]:
            out.append({"id": f"overdue-{e['cmid']}", "source": "reminder", "type": "overdue",
                        "title": f"Overdue: {e['name']}",
                        "body": f"{e['course_code']} - not submitted. Late submissions are accepted until the cut-off date.",
                        "course_code": e["course_code"], "timestamp": e["due"], "read": False, "link": e["link"],
                        "cutoff": e.get("cutoff")})
        for a in assigns:
            if a["submitted_at"] and a["submitted_at"] >= now - 7 * DAY:
                out.append({"id": f"submitted-{a['cmid']}-{a['submitted_at']}", "source": "reminder", "type": "submitted",
                            "title": f"Assignment submitted: {a['name']}", "body": f"{a['course_code']} - submission received"
                            + (" (late)." if a["late"] else "."), "course_code": a["course_code"],
                            "timestamp": a["submitted_at"], "read": True, "link": f"/assignments/{a['cmid']}"})
        for it in grade_items:
            if it["graded_at"] and it["graded_at"] >= now - 14 * DAY and it["grade"] is not None:
                label = "Quiz result available" if it["module"] == "quiz" else "Grade released"
                link = f"/quizzes/{it['cmid']}" if it["module"] == "quiz" else (
                    f"/assignments/{it['cmid']}" if it["module"] == "assign" else "/grades")
                out.append({"id": f"grade-{it['id']}-{it['graded_at']}", "source": "reminder",
                            "type": "quiz_result" if it["module"] == "quiz" else "grade_released",
                            "title": f"{label}: {it['name']}",
                            "body": f"{it['course_code']} - {it['percentage'] or it['grade_formatted']}",
                            "course_code": it["course_code"], "timestamp": it["graded_at"], "read": True, "link": link})
        out.sort(key=lambda n: n["timestamp"] or 0, reverse=True)
        return out

    async def mark_notification_read(self, moodle_id: int) -> None:
        await self.call("core_message_mark_notification_read", notificationid=moodle_id, timeread=_now())

    # ------------------------------------------------------------------ profile
    async def profile(self) -> dict:
        users = await self.s.cached("profile", LONG_TTL, lambda: self.call(
            "core_user_get_users_by_field", field="id", values=[self.s.moodle_userid]))
        u = users[0] if users else {}
        courses = await self.courses()
        return {
            "fullname": u.get("fullname") or self.s.fullname, "student_id": self.s.student_id,
            "username": u.get("username") or self.s.username, "email": u.get("email"),
            "department": u.get("department") or None, "institution": u.get("institution") or None,
            "first_access": u.get("firstaccess") or None, "last_access": u.get("lastaccess") or None,
            "courses": [{"id": c["id"], "code": c["code"], "title": c["title"], "term": c["term"]} for c in courses],
        }

    async def dashboard(self) -> dict:
        courses, up, activity, notes = await self.gather(
            self.courses(), self.upcoming(), self.recent_activity(15), self.notifications())
        progresses = await self.gather(*(self.course_progress(c["id"]) for c in courses))
        by_course_next: dict[int, dict] = {}
        for e in up["overdue"] + up["upcoming"]:
            by_course_next.setdefault(e["course_id"], e)
        by_course_last: dict[str, dict] = {}
        for e in activity:
            by_course_last.setdefault(e["course_code"], e)
        cards = []
        for c, p in zip(courses, progresses):
            cards.append({**c, "completed_activities": p["completed"], "tracked_activities": p["tracked"],
                          "next_activity": by_course_next.get(c["id"]),
                          "last_activity": by_course_last.get(c["code"])})
        tracked = sum(p["tracked"] for p in progresses)
        done = sum(p["completed"] for p in progresses)
        pct = [c["progress"] for c in courses if c["progress"] is not None]
        return {
            "courses": cards, "upcoming": up["upcoming"], "overdue": up["overdue"],
            "recent_activity": activity, "notifications": notes[:8],
            "unread_notifications": sum(1 for n in notes if not n["read"]),
            "progress": {"completed": done, "tracked": tracked,
                         "average_course_progress": round(sum(pct) / len(pct), 1) if pct else None},
        }
