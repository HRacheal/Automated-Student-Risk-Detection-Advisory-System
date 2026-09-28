# backend/services/rosario_service.py
"""
RosarioSIS integration via the REST_API plugin (read-only GET requests).

Auth flow (plugins/REST_API/README.md):
  POST auth.php  usertoken=<ROSARIO_API_TOKEN>   ->  {"access_token": "<JWT>"}
  GET  api.php/records/<table>  with header  X-Authorization: Bearer <JWT>

Only whitelisted fields are copied out of RosarioSIS (e.g. password hashes in
the `students` table are never read into the application).
"""
import re
from datetime import date, datetime
from typing import Any, Optional

import httpx

from config import settings
from domain import (
    INCOMPLETE_LETTERS,
    LETTER_POINTS,
    WITHDRAWAL_LETTERS,
    CourseEnrollment,
    CourseGrade,
    FinancialData,
    StudentRecord,
    compute_gpas,
    standing_from_units,
)
from services.base import ERROR, NOT_CONFIGURED, OK, UNAVAILABLE, SourceError, SourceResult

PAGE_SIZE = 1000  # plugin caps pages at 1000 records
MAJOR_FIELD_RE = re.compile(r"\b(declared\s+major|major|program(me)?|degree|course of study)\b", re.I)
HOLD_FIELD_RE = re.compile(r"\bhold", re.I)


def _d(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _f(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


class RosarioClient:
    def __init__(self, api_url: str, token: str, timeout: float):
        self.api_url = api_url.rstrip("/")
        self.auth_url = self.api_url.rsplit("/", 1)[0] + "/auth.php"
        self.token = token
        self.client = httpx.Client(timeout=timeout)
        self._access_token: Optional[str] = None

    def close(self):
        self.client.close()

    def authenticate(self) -> None:
        try:
            res = self.client.post(self.auth_url, data={"usertoken": self.token})
        except httpx.HTTPError as exc:
            raise SourceError(UNAVAILABLE, f"RosarioSIS is not reachable ({exc.__class__.__name__}).")
        try:
            body = res.json()
        except ValueError:
            raise SourceError(ERROR, f"RosarioSIS auth returned a non-JSON response (HTTP {res.status_code}).")
        token = body.get("access_token") if isinstance(body, dict) else None
        if not token:
            raise SourceError(ERROR, "RosarioSIS rejected the API user token (check REST_API plugin is "
                                     "active and ROSARIO_API_TOKEN is valid).")
        self._access_token = token

    def records(self, table: str, **filters: str) -> list[dict]:
        """GET every page of records/<table>. Raises KeyError if the table is not exposed."""
        if not self._access_token:
            self.authenticate()
        rows: list[dict] = []
        page = 1
        while True:
            params: dict[str, Any] = {"page": f"{page},{PAGE_SIZE}"}
            if filters:
                params["filter"] = [f"{k},eq,{v}" for k, v in filters.items()]
            try:
                res = self.client.get(
                    f"{self.api_url}/records/{table}",
                    params=params,
                    headers={"X-Authorization": f"Bearer {self._access_token}"},
                )
            except httpx.HTTPError as exc:
                raise SourceError(UNAVAILABLE, f"RosarioSIS request failed ({exc.__class__.__name__}).")
            try:
                body = res.json()
            except ValueError:
                raise SourceError(ERROR, f"RosarioSIS returned a non-JSON response for {table}.")
            if isinstance(body, dict) and "code" in body and "records" not in body:
                if body.get("code") == 1001:  # table not found / not exposed
                    raise KeyError(table)
                raise SourceError(ERROR, f"RosarioSIS error for {table}: {body.get('message')}")
            batch = body.get("records", []) if isinstance(body, dict) else []
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
            page += 1


def fetch_rosario() -> SourceResult:
    if not settings.ROSARIO_API_URL or not settings.ROSARIO_API_TOKEN:
        return SourceResult("rosario", NOT_CONFIGURED, "ROSARIO_API_URL / ROSARIO_API_TOKEN not set.")
    client = RosarioClient(settings.ROSARIO_API_URL, settings.ROSARIO_API_TOKEN,
                           settings.EXTERNAL_TIMEOUT_SECONDS)
    try:
        client.authenticate()
        return _build_records(client)
    except SourceError as exc:
        return SourceResult("rosario", exc.status, exc.message)
    finally:
        client.close()


def check_rosario() -> dict:
    """Lightweight connectivity check used by /api/integrations/status."""
    if not settings.ROSARIO_API_URL or not settings.ROSARIO_API_TOKEN:
        return {"status": NOT_CONFIGURED, "message": "ROSARIO_API_URL / ROSARIO_API_TOKEN not set."}
    client = RosarioClient(settings.ROSARIO_API_URL, settings.ROSARIO_API_TOKEN, 5)
    try:
        client.authenticate()
        schools = client.records("schools")
        return {"status": OK, "message": f"Authenticated. {len(schools)} school record(s) visible."}
    except SourceError as exc:
        return {"status": exc.status, "message": exc.message}
    except KeyError:
        return {"status": OK, "message": "Authenticated."}
    finally:
        client.close()


def _build_records(client: RosarioClient) -> SourceResult:
    today = date.today()
    tables: dict[str, str] = {}

    # Fetched SEQUENTIALLY on purpose: the plugin's PHP-CRUD-API file cache
    # (in the Windows TEMP dir) races under concurrent requests and injects PHP
    # warnings into the JSON response.
    wanted = ["students", "custom_fields", "student_enrollment", "student_enrollment_codes",
              "school_gradelevels", "schools", "school_marking_periods", "history_marking_periods",
              "schedule", "courses", "course_periods", "student_report_card_grades",
              "billing_fees", "billing_payments"]

    def fetch(table: str) -> Optional[list[dict]]:
        try:
            return client.records(table)
        except KeyError:
            return None

    fetched = {table: fetch(table) for table in wanted}

    def load(table: str) -> Optional[list[dict]]:
        rows = fetched.get(table)
        tables[table] = f"{len(rows)} rows" if rows is not None else "not exposed by API"
        return rows

    students_raw = load("students") or []
    custom_fields = load("custom_fields") or []
    enrollment = load("student_enrollment")
    enrollment_codes = {r["id"]: r for r in (load("student_enrollment_codes") or [])}
    grade_levels = {r["id"]: r for r in (load("school_gradelevels") or [])}
    schools = {r["id"]: r for r in (load("schools") or [])}
    mps_rows = (load("school_marking_periods") or []) + (load("history_marking_periods") or [])
    schedule = load("schedule")
    courses = {r["course_id"]: r for r in (load("courses") or [])}
    course_periods = {r["course_period_id"]: r for r in (load("course_periods") or [])}
    report_grades = load("student_report_card_grades")
    fees = load("billing_fees")
    payments = load("billing_payments")

    # --- custom student fields (major / hold) ------------------------------
    major_col = hold_col = None
    for cf in custom_fields:
        title = str(cf.get("title") or "")
        if major_col is None and MAJOR_FIELD_RE.search(title):
            major_col = f"custom_{cf['id']}"
        elif hold_col is None and HOLD_FIELD_RE.search(title):
            hold_col = f"custom_{cf['id']}"

    # --- marking periods / current term -----------------------------------
    mps: dict[Any, dict] = {}
    for r in mps_rows:
        mp_id = r.get("marking_period_id")
        start = _d(r.get("start_date")) or _d(r.get("post_end_date"))
        mps[mp_id] = {"title": r.get("title") or r.get("name") or f"MP {mp_id}",
                      "start": start, "end": _d(r.get("end_date")) or _d(r.get("post_end_date")),
                      "type": r.get("mp"), "syear": r.get("syear")}
    ordered = sorted([k for k in mps if mps[k]["start"]], key=lambda k: mps[k]["start"])
    mp_order = {k: i + 1 for i, k in enumerate(ordered)}
    current_term = None
    for mp_type in ("SEM", "QTR", "FY"):
        for k in ordered:
            m = mps[k]
            if m["type"] == mp_type and m["start"] and m["end"] and m["start"] <= today <= m["end"]:
                current_term = m
                break
        if current_term:
            break

    def course_info(cp_id: Any, course_id: Any = None) -> tuple[str, Optional[str], Optional[float]]:
        cp = course_periods.get(cp_id) or {}
        c = courses.get(course_id or cp.get("course_id")) or {}
        code = (c.get("short_name") or cp.get("short_name") or c.get("title") or cp.get("title")
                or f"CP{cp_id}")
        title = c.get("title") or cp.get("title")
        units = _f(cp.get("credits")) if cp.get("credits") is not None else _f(c.get("credit_hours"))
        return str(code).replace(" ", "").upper(), title, units

    # --- per-student assembly --------------------------------------------
    enroll_by_student: dict[Any, list[dict]] = {}
    for e in enrollment or []:
        enroll_by_student.setdefault(e.get("student_id"), []).append(e)
    sched_by_student: dict[Any, list[dict]] = {}
    for s in schedule or []:
        sched_by_student.setdefault(s.get("student_id"), []).append(s)
    grades_by_student: dict[Any, list[dict]] = {}
    for g in report_grades or []:
        grades_by_student.setdefault(g.get("student_id"), []).append(g)

    records: list[StudentRecord] = []
    for raw in students_raw:
        sid = raw.get("student_id")
        name = " ".join(p for p in [raw.get("first_name"), raw.get("middle_name"), raw.get("last_name")] if p)
        rec = StudentRecord(student_id=str(sid), full_name=name or f"Student {sid}",
                            sources=["rosario"], username=raw.get("username"))

        # Major
        if major_col:
            rec.major_field_available = True
            rec.declared_major = (raw.get(major_col) or "").strip() or "Undeclared"
        else:
            rec.mark_unavailable("declared_major", "Declared major: RosarioSIS has no 'Major' student field. "
                                                   "Add a custom student field named 'Major' to enable.")
        # Holds
        if hold_col:
            value = (raw.get(hold_col) or "").strip()
            rec.holds = [value] if value and value.upper() not in {"N", "NO", "NONE"} else []
        else:
            rec.mark_unavailable("holds", "Registration/academic holds are not provided by RosarioSIS "
                                          "(no custom 'Hold' field).")

        # School enrollment
        if enrollment is None:
            rec.mark_unavailable("enrollment", "School enrollment records not exposed by the API.")
        else:
            rows = sorted(enroll_by_student.get(sid, []),
                          key=lambda e: (str(e.get("syear")), str(e.get("start_date"))))
            if rows:
                e = rows[-1]
                rec.school = (schools.get(e.get("school_id")) or {}).get("title")
                rec.grade_level = (grade_levels.get(e.get("grade_id")) or {}).get("title")
                end = _d(e.get("end_date"))
                if e.get("drop_code") and end and end <= today:
                    code = enrollment_codes.get(e.get("drop_code")) or {}
                    rec.enrollment_status = "withdrawn"
                    rec.enrollment_note = f"Dropped {end}: {code.get('title', 'drop code ' + str(e.get('drop_code')))}"
                else:
                    rec.enrollment_status = "active"

        # Current-term schedule (course registrations and drops)
        rec.current_term = current_term["title"] if current_term else None
        if schedule is None:
            rec.mark_unavailable("current_courses", "Course schedule not exposed by the RosarioSIS API.")
        else:
            term_start = current_term["start"] if current_term else None
            for row in sched_by_student.get(sid, []):
                start, end = _d(row.get("start_date")), _d(row.get("end_date"))
                mp = mps.get(row.get("marking_period_id")) or {}
                # keep rows of the current school term only
                if term_start and mp.get("end") and mp["end"] < term_start:
                    continue
                if term_start and end and end < term_start:
                    continue
                code, title, units = course_info(row.get("course_period_id"), row.get("course_id"))
                rec.current_courses.append(CourseEnrollment(
                    code=code, title=title, units=units,
                    status="dropped" if end and end < today else "enrolled",
                    start_date=start, end_date=end, term=mp.get("title") or rec.current_term,
                ))

        # Academic history (report card grades)
        if report_grades is None:
            rec.mark_unavailable("course_history", "Report card grades not exposed by the RosarioSIS API.")
        else:
            for g in grades_by_student.get(sid, []):
                letter = (g.get("grade_letter") or "").strip().upper() or None
                gp, scale = _f(g.get("unweighted_gp")), _f(g.get("gp_scale"))
                points = round(gp / scale * 4.0, 2) if gp is not None and scale else LETTER_POINTS.get(letter or "")
                attempted, earned = _f(g.get("credit_attempted")), _f(g.get("credit_earned"))
                withdrawn = letter in WITHDRAWAL_LETTERS
                incomplete = letter in INCOMPLETE_LETTERS
                if withdrawn or incomplete:
                    points = None
                passed = None
                if not withdrawn and not incomplete:
                    if attempted is not None and earned is not None:
                        passed = earned > 0
                    elif points is not None:
                        passed = points >= 1.0
                mp_id = g.get("marking_period_id")
                code, title, _ = course_info(g.get("course_period_id"))
                if code.startswith("CP") and g.get("course_title"):
                    code = str(g["course_title"]).replace(" ", "").upper()
                rec.course_history.append(CourseGrade(
                    code=code, title=g.get("course_title") or title,
                    term=(mps.get(mp_id) or {}).get("title"), term_order=mp_order.get(mp_id),
                    grade_letter=letter, grade_percent=_f(g.get("grade_percent")), grade_points=points,
                    credits_attempted=attempted, credits_earned=earned, passed=passed,
                    withdrawn=withdrawn, incomplete=incomplete,
                ))
            rec.term_gpas, rec.cumulative_gpa = compute_gpas(rec.course_history)
            earned_total = [g.credits_earned for g in rec.course_history if g.credits_earned is not None]
            # No grade records => completed units are unknown (not zero)
            rec.completed_units = sum(earned_total) if earned_total else None
            rec.class_standing = standing_from_units(rec.completed_units)
            if not rec.course_history:
                rec.unavailable.append("No report card grades recorded in RosarioSIS yet.")

        # Billing
        if fees is None or payments is None:
            rec.mark_unavailable("financial", "Student Billing tables not exposed by the RosarioSIS API.")
        else:
            my_fees = [f for f in fees if f.get("student_id") == sid]
            my_pay = [p for p in payments if p.get("student_id") == sid]
            total_fees = sum(_f(f.get("amount")) or 0 for f in my_fees)
            total_paid = sum(_f(p.get("amount")) or 0 for p in my_pay)
            balance = round(total_fees - total_paid, 2)
            past_due = sum(_f(f.get("amount")) or 0 for f in my_fees
                           if _d(f.get("due_date")) and _d(f.get("due_date")) < today)
            overdue = round(max(0.0, min(balance, past_due - total_paid)), 2) if balance > 0 else 0.0
            rec.financial = FinancialData(available=True, balance=balance, overdue_amount=overdue,
                                          fees_count=len(my_fees), source="rosario")

        records.append(rec)

    details = {
        "tables": tables,
        "current_term": current_term["title"] if current_term else None,
        "major_field": "found" if major_col else "not available",
        "hold_field": "found" if hold_col else "not available",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    return SourceResult("rosario", OK, f"Retrieved {len(records)} student(s) from RosarioSIS.",
                        records, details)
