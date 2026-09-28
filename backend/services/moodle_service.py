# backend/services/moodle_service.py
"""
Moodle integration via REST web services (read-only functions only).

Functions used (all must be added to the external service in
Site administration > Server > Web services > External services):
  core_webservice_get_site_info       connectivity + list of allowed functions
  core_course_get_courses             course list
  core_enrol_get_enrolled_users       students per course (+ lastcourseaccess)
  mod_assign_get_assignments          assignments and due dates
  mod_assign_get_submissions          submission status per student
  gradereport_user_get_grade_items    quiz / course-total grades per student

A function that is not enabled simply switches off the matching capability
(e.g. no quiz data) — nothing is fabricated.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config import settings
from domain import AssignmentStatus, LMSData, QuizResult
from services.base import ERROR, NOT_CONFIGURED, OK, UNAVAILABLE, SourceError, SourceResult


MAX_PARALLEL_CALLS = 6  # concurrent per-course requests (Moodle's bundled Apache handles these fine)


class MoodleFunctionError(Exception):
    pass


class MoodleClient:
    def __init__(self, url: str, token: str, timeout: float, read_timeout: Optional[float] = None):
        self.url = url
        self.token = token
        # Connecting must be quick (a stopped Moodle is reported fast), but bulk calls such as
        # mod_assign_get_submissions legitimately take several seconds - longer on a cold start.
        self.client = httpx.Client(timeout=httpx.Timeout(read_timeout or timeout, connect=timeout))

    def close(self):
        self.client.close()

    def call(self, function: str, **params: Any) -> Any:
        data: dict[str, Any] = {"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json"}
        for key, value in params.items():
            if isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    data[f"{key}[{i}]"] = item
            else:
                data[key] = value
        try:
            res = self.client.post(self.url, data=data)
        except httpx.ReadTimeout:
            raise SourceError(UNAVAILABLE, f"Moodle is reachable but did not answer {function} in time (ReadTimeout).")
        except httpx.HTTPError as exc:
            raise SourceError(UNAVAILABLE, f"Moodle is not reachable ({exc.__class__.__name__}).")
        if res.status_code == 404:
            raise SourceError(UNAVAILABLE, "Moodle web service endpoint not found (HTTP 404). "
                                           "Is Moodle installed at MOODLE_API_URL?")
        try:
            body = res.json()
        except ValueError:
            raise SourceError(ERROR, f"Moodle returned a non-JSON response (HTTP {res.status_code}).")
        if isinstance(body, dict) and body.get("exception"):
            code = body.get("errorcode", "")
            if code in {"invalidtoken", "servicenotavailable"}:
                raise SourceError(ERROR, f"Moodle rejected the token ({code}).")
            raise MoodleFunctionError(f"{function}: {code or body.get('message')}")
        return body


@dataclass
class MoodleStudent:
    moodle_id: int
    username: Optional[str]
    idnumber: Optional[str]
    email: Optional[str]
    fullname: str
    lms: LMSData = field(default_factory=LMSData)


def check_moodle() -> dict:
    if not settings.MOODLE_API_URL or not settings.MOODLE_API_TOKEN:
        return {"status": NOT_CONFIGURED, "message": "MOODLE_API_URL / MOODLE_API_TOKEN not set."}
    client = MoodleClient(settings.MOODLE_API_URL, settings.MOODLE_API_TOKEN, 5)
    try:
        info = client.call("core_webservice_get_site_info")
        return {"status": OK, "message": f"Connected to '{info.get('sitename', 'Moodle')}'.",
                "functions": sorted(f.get("name") for f in info.get("functions", []))}
    except SourceError as exc:
        return {"status": exc.status, "message": exc.message}
    except MoodleFunctionError as exc:
        return {"status": ERROR, "message": str(exc)}
    finally:
        client.close()


def fetch_moodle() -> SourceResult:
    if not settings.MOODLE_API_URL or not settings.MOODLE_API_TOKEN:
        return SourceResult("moodle", NOT_CONFIGURED, "MOODLE_API_URL / MOODLE_API_TOKEN not set.")
    client = MoodleClient(settings.MOODLE_API_URL, settings.MOODLE_API_TOKEN,
                          settings.EXTERNAL_TIMEOUT_SECONDS, settings.MOODLE_READ_TIMEOUT_SECONDS)
    try:
        return _collect(client)
    except SourceError as exc:
        return SourceResult("moodle", exc.status, exc.message)
    finally:
        client.close()


def _per_course(client: MoodleClient, function: str, courses: list[dict]) -> dict[int, Any]:
    """Calls a per-course function for every course concurrently (the calls are independent;
    sequentially they took ~60 s for 18 courses). Returns {course_id: response | MoodleFunctionError}.
    A SourceError (Moodle down / token rejected) propagates and fails the whole fetch, as before."""
    def one(cid: int):
        try:
            return client.call(function, courseid=cid)
        except MoodleFunctionError as exc:
            return exc

    ids = [c["id"] for c in courses]
    if not ids:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_CALLS, len(ids))) as pool:
        return dict(zip(ids, pool.map(one, ids)))


def _collect(client: MoodleClient) -> SourceResult:
    now = datetime.now(timezone.utc)
    notes: dict[str, str] = {}
    try:
        info = client.call("core_webservice_get_site_info")
    except MoodleFunctionError as exc:
        return SourceResult("moodle", ERROR, str(exc))
    allowed = {f.get("name") for f in info.get("functions", [])}

    def can(fn: str) -> bool:
        if allowed and fn not in allowed:
            notes[fn] = "not enabled in the Moodle external service"
            return False
        return True

    if not can("core_course_get_courses") or not can("core_enrol_get_enrolled_users"):
        return SourceResult("moodle", ERROR, "Moodle service must allow core_course_get_courses and "
                                             "core_enrol_get_enrolled_users.", details={"functions": notes})

    courses = [c for c in client.call("core_course_get_courses") if c.get("format") != "site" and c.get("id") != 1]
    course_code = {c["id"]: (c.get("shortname") or c.get("fullname") or str(c["id"])).replace(" ", "").upper()
                   for c in courses}

    students: dict[int, MoodleStudent] = {}
    last_access: dict[int, int] = {}
    engagement_ok = False
    enrolled = _per_course(client, "core_enrol_get_enrolled_users", courses)
    for c in courses:
        users = enrolled[c["id"]]
        if isinstance(users, MoodleFunctionError):
            notes[f"enrolled_users:{c['id']}"] = str(users)
            continue
        for u in users:
            roles = {r.get("shortname") for r in u.get("roles", [])}
            if roles and "student" not in roles:
                continue
            st = students.setdefault(u["id"], MoodleStudent(
                moodle_id=u["id"], username=u.get("username"), idnumber=(u.get("idnumber") or None),
                email=u.get("email"), fullname=u.get("fullname") or u.get("username") or f"Moodle user {u['id']}",
            ))
            st.lms.courses.append(course_code[c["id"]])
            if "lastcourseaccess" in u or "lastaccess" in u:
                engagement_ok = True
                ts = u.get("lastcourseaccess") or 0
                last_access[u["id"]] = max(last_access.get(u["id"], 0), ts)

    # ---- assignments & submissions ---------------------------------------
    assignments_ok = False
    if courses and can("mod_assign_get_assignments") and can("mod_assign_get_submissions"):
        try:
            # includenotenrolledcourses: the API account views courses via capabilities, it is not enrolled in them
            assign_resp = client.call("mod_assign_get_assignments", courseids=[c["id"] for c in courses],
                                      includenotenrolledcourses=1)
            assigns = [(course_code.get(ac["id"], str(ac["id"])), a)
                       for ac in assign_resp.get("courses", []) for a in ac.get("assignments", [])]
            submitted: dict[int, set[int]] = {}
            if assigns:
                sub_resp = client.call("mod_assign_get_submissions", assignmentids=[a["id"] for _, a in assigns])
                for block in sub_resp.get("assignments", []):
                    submitted[block["assignmentid"]] = {
                        s["userid"] for s in block.get("submissions", []) if s.get("status") == "submitted"
                    }
            assignments_ok = True
            for st in students.values():
                for code, a in assigns:
                    if code not in st.lms.courses or a.get("nosubmissions"):
                        continue
                    due = a.get("duedate") or 0
                    if st.moodle_id in submitted.get(a["id"], set()):
                        status = "submitted"
                    elif due and due < now.timestamp():
                        status = "missed"
                    else:
                        status = "pending"
                    st.lms.assignments.append(AssignmentStatus(
                        course=code, name=a.get("name", "Assignment"),
                        due_date=datetime.fromtimestamp(due, timezone.utc).date().isoformat() if due else None,
                        status=status,
                    ))
        except MoodleFunctionError as exc:
            notes["assignments"] = str(exc)

    # ---- grades (quizzes + course totals) ---------------------------------
    grades_ok = False
    if courses and can("gradereport_user_get_grade_items"):
        grade_reports = _per_course(client, "gradereport_user_get_grade_items", courses)
        for c in courses:
            resp = grade_reports[c["id"]]
            if isinstance(resp, MoodleFunctionError):
                notes[f"grades:{c['id']}"] = str(resp)
                continue
            grades_ok = True
            for ug in resp.get("usergrades", []):
                st = students.get(ug.get("userid"))
                if not st:
                    continue
                for item in ug.get("gradeitems", []):
                    raw, gmax = item.get("graderaw"), item.get("grademax")
                    pct = round(raw / gmax * 100, 1) if raw is not None and gmax else None
                    if item.get("itemmodule") == "quiz":
                        st.lms.quizzes.append(QuizResult(course=course_code[c["id"]],
                                                         name=item.get("itemname") or "Quiz", percent=pct))
                    elif item.get("itemtype") == "course":
                        st.lms.course_grades[course_code[c["id"]]] = pct

    for st in students.values():
        st.lms.available = True
        st.lms.moodle_user_id = st.moodle_id
        st.lms.capabilities = {"engagement": engagement_ok, "assignments": assignments_ok, "quizzes": grades_ok}
        ts = last_access.get(st.moodle_id)
        if ts:
            dt = datetime.fromtimestamp(ts, timezone.utc)
            st.lms.last_access = dt.isoformat(timespec="minutes")
            st.lms.days_since_last_access = (now - dt).days
        # ts == 0 => never accessed: days_since_last_access stays None

    details = {"site": info.get("sitename"), "courses": len(courses),
               "capabilities": {"engagement": engagement_ok, "assignments": assignments_ok, "quizzes": grades_ok},
               "notes": notes}
    return SourceResult("moodle", OK, f"Retrieved {len(students)} student(s) across {len(courses)} Moodle course(s).",
                        list(students.values()), details)
