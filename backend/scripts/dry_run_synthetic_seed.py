"""
DRY RUN for the synthetic dataset - performs NO database writes.

1. Structural validation of backend/data/synthetic_student_demo_seed.json.
2. End-to-end in-memory run through the REAL My Coach code path:
      seed -> RosarioSIS-shaped REST rows -> services.rosario_service._build_records
      seed -> Moodle-shaped web-service responses -> services.moodle_service._collect
      -> services.sync_service.merge_sources -> anomaly_engine.evaluate_student
   (the course catalogue is read from the My Coach database, read-only)
3. Comparison with backend/data/synthetic_student_demo_expectations.json.

Run from backend/:  python scripts/dry_run_synthetic_seed.py
Exit code 0 = safe to populate, 1 = validation failed.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from anomaly_engine import RuleContext, check_prerequisites, evaluate_student, overall_risk_level  # noqa: E402
from domain import CourseGrade, StudentRecord  # noqa: E402

SEED = json.loads((BACKEND / "data" / "synthetic_student_demo_seed.json").read_text(encoding="utf-8"))
EXPECT = json.loads((BACKEND / "data" / "synthetic_student_demo_expectations.json").read_text(encoding="utf-8"))
NAIROBI = timezone(timedelta(hours=3))  # Africa/Nairobi has no DST
REF = date.fromisoformat(SEED["meta"]["reference_date"])
CUR = SEED["meta"]["current_term"]

# Designed values (refined design report) and documented, deliberate deviations
DESIGN_CREDITS = {690001: 66, 690002: 39, 690003: 90, 690004: 33, 690005: 21, 690006: 63, 690007: 90, 690008: 36,
                  690009: 42, 690010: 60, 690011: 0, 690012: 33, 690013: 63, 690014: 45, 690015: 39, 690016: 60,
                  690017: 36, 690018: 33, 690019: 57, 690020: 42, 690021: 45, 690022: 30, 690023: 60, 690024: 36,
                  690025: 54, 690026: 27, 690027: 24, 690028: 45, 690029: 78, 690030: 66}
FORBIDDEN_KEYS = {"risk", "risk_level", "expected_risk", "alert_status", "color", "colour", "alert_count"}

checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def ts(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=NAIROBI).timestamp()) if iso else 0


students = SEED["students"]
by_id = {s["student_id"]: s for s in students}
courses = {c["code"]: c for c in SEED["courses"]}
sections = {s["code"]: s for s in SEED["sections"]}
terms = {t["key"]: t for t in SEED["terms"]}
term_order = {t["key"]: i for i, t in enumerate(SEED["terms"])}

# ---------------------------------------------------------------------------
# 1. Structural validation
# ---------------------------------------------------------------------------
def all_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from all_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from all_keys(v)


check("dataset contains no risk/label fields", not (set(all_keys(SEED)) & FORBIDDEN_KEYS),
      str(set(all_keys(SEED)) & FORBIDDEN_KEYS))
ids = [s["student_id"] for s in students]
check("30 unique student IDs in 690001-690030", len(ids) == 30 == len(set(ids)) and all(690001 <= i <= 690030 for i in ids))
names = [f"{s['first_name']} {s['last_name']}" for s in students]
check("student names unique", len(set(names)) == len(names))
emails = [s["moodle"]["email"] for s in students if s["moodle"]] + [i["email"] for i in SEED["instructors"]]
check("every e-mail uses the .invalid TLD", all(e.endswith(".invalid") for e in emails))
check("dataset flagged synthetic, no PII-type fields", SEED["meta"]["synthetic"] is True and not (
    set(all_keys(SEED)) & {"phone", "national_id", "passport", "address", "birthdate", "ssn", "password"}))
check("33 catalogue courses, all 3 credits except DSA4090 (6)", len(courses) == 33 and all(
    c["credits"] == (6 if c["code"] == "DSA4090" else 3) for c in courses.values()))
check("18 current sections, all catalogue codes", len(sections) == 18 and set(sections) <= set(courses))
check("9 historical terms", len(terms) == 9)

hist_title_ok, hist_code_ok, w_ok, i_ok, dates_ok = True, True, True, True, True
prereq_fail, cur_prereq_fail, reg_problems, credit_problems = [], [], [], []
for s in students:
    sid, r = s["student_id"], s["rosario"]
    rows = r["history"]
    for h in rows:
        hist_title_ok &= h["course_title"] == h["code"]
        hist_code_ok &= h["code"] in courses and h["term"] in terms
        if h["kind"] == "withdrawn":
            w_ok &= h["grade_letter"] == "W" and h["grade_points"] is None and h["credits_earned"] == 0
        if h["kind"] == "incomplete":
            i_ok &= h["grade_letter"] == "I" and h["grade_points"] is None and h["credits_earned"] == 0
    # prerequisites satisfied in chronological order (history)
    seen, credits = [], 0
    for tkey in sorted({h["term"] for h in rows}, key=term_order.get):
        prior = StudentRecord(student_id="x", full_name="x", completed_units=credits, course_history=[
            CourseGrade(code=h["code"], grade_points=h["grade_points"], passed=h["passed"],
                        withdrawn=h["kind"] == "withdrawn", incomplete=h["kind"] == "incomplete") for h in seen])
        for h in [h for h in rows if h["term"] == tkey]:
            unmet, _ = check_prerequisites(prior, courses[h["code"]]["prerequisites"])
            if unmet:
                prereq_fail.append(f"{sid} {tkey} {h['code']} needs {unmet}")
        seen += [h for h in rows if h["term"] == tkey]
        credits += sum(h["credits_earned"] for h in rows if h["term"] == tkey)
    if credits != DESIGN_CREDITS[sid]:
        credit_problems.append(f"{sid}: earned {credits}, design {DESIGN_CREDITS[sid]}")
    # current registrations
    final = StudentRecord(student_id="x", full_name="x", completed_units=credits, course_history=[
        CourseGrade(code=h["code"], grade_points=h["grade_points"], passed=h["passed"],
                    withdrawn=h["kind"] == "withdrawn", incomplete=h["kind"] == "incomplete") for h in rows])
    passed = {h["code"] for h in rows if h["passed"]}
    regs = r["current_registrations"]
    for g in regs:
        if g["code"] not in sections:
            reg_problems.append(f"{sid}: {g['code']} not offered")
        if g["code"] in passed:
            reg_problems.append(f"{sid}: already passed {g['code']}")
        start = date.fromisoformat(g["start_date"])
        end = date.fromisoformat(g["end_date"]) if g["end_date"] else None
        dates_ok &= date.fromisoformat(CUR["course_start"]) <= start <= REF and (end is None or start <= end <= REF)
        unmet, _ = check_prerequisites(final, courses[g["code"]]["prerequisites"])
        if unmet and g["end_date"] is None:
            cur_prereq_fail.append(f"{sid} {g['code']} needs {unmet}")
    active = [g["code"] for g in regs if not g["end_date"]]
    if len(active) != len(set(active)):
        reg_problems.append(f"{sid}: duplicate active registration")

check("historical course_title == exact course code (all rows)", hist_title_ok)
check("historical rows reference valid codes and terms", hist_code_ok)
check("W rows: letter W, no grade points, 0 credits earned", w_ok)
check("I rows: letter I, no grade points, 0 credits earned", i_ok)
check("history prerequisites satisfied in chronological order", not prereq_fail, "; ".join(prereq_fail))
check("credits earned match the design", not credit_problems, "; ".join(credit_problems))
check("current registrations coherent (offered, not already passed, no duplicates)", not reg_problems, "; ".join(reg_problems))
check("registration dates inside Fall 2026 and not after the reference date", dates_ok)
check("current prerequisites satisfied EXCEPT the deliberate 690026 APT2080 case",
      cur_prereq_fail == ["690026 APT2080 needs ['APT1030']"], "; ".join(cur_prereq_fail))

# Moodle / identity
ident_ok, drop_ok, time_ok, quiz_ok = True, True, True, True
for s in students:
    m = s["moodle"]
    if not m:
        continue
    ident_ok &= m["idnumber"] == str(s["student_id"]) and m["username"] == s["rosario"]["username"] == f"s{s['student_id']}"
    active = {g["code"] for g in s["rosario"]["current_registrations"] if not g["end_date"]}
    drop_ok &= {c["code"] for c in m["courses"]} == active
    for c in m["courses"]:
        access = c["last_course_access"]
        for a in c["assignments"]:
            if a["submitted_at"]:
                t = datetime.fromisoformat(a["submitted_at"])
                time_ok &= t.date() <= REF and (access is not None and t <= datetime.fromisoformat(access) + timedelta(days=1))
                if a["status"] == "late":
                    time_ok &= date.fromisoformat(a["due"]) < t.date() <= date.fromisoformat(a["cutoff"])
        for q in c["quizzes"]:
            if q["status"] == "attempted":
                t = datetime.fromisoformat(q["attempted_at"]).date()
                time_ok &= date.fromisoformat(q["opens"]) <= t <= min(date.fromisoformat(q["closes"]), REF)
                quiz_ok &= q["score_percent"] % 5 == 0
check("Moodle idnumber = RosarioSIS student_id, usernames match", ident_ok)
check("Moodle enrolments == active RosarioSIS registrations (dropped courses not enrolled)", drop_ok)
check("submission/attempt times coherent with windows, access and reference date", time_ok)
check("quiz scores representable (multiples of 5%)", quiz_ok)
check("690013 has no Moodle account", by_id[690013]["moodle"] is None)
h14 = [(h["term"], h["grade_letter"]) for h in by_id[690014]["rosario"]["history"] if h["code"] == "MTH1109"]
check("690014 MTH1109: F then B retake", h14 == [("FA24", "F"), ("SP25", "B")], str(h14))


def balance(s):
    f = s["rosario"]["finance"]
    fees = sum(x["amount"] for x in f["fees"])
    paid = sum(x["amount"] for x in f["payments"])
    past_due = sum(x["amount"] for x in f["fees"] if date.fromisoformat(x["due"]) < REF)
    return round(fees - paid, 2), round(max(0.0, min(fees - paid, past_due - paid)), 2)


check("690011 balance > 0 but nothing overdue", balance(by_id[690011])[0] > 0 and balance(by_id[690011])[1] == 0, str(balance(by_id[690011])))
check("690028 overdue balance", balance(by_id[690028])[1] > 0, str(balance(by_id[690028])))
others = [sid for sid in ids if sid not in (690011, 690028) and balance(by_id[sid])[0] != 0]
check("all other students paid in full", not others, str(others))


# ---------------------------------------------------------------------------
# 2. In-memory run through the real My Coach services
# ---------------------------------------------------------------------------
class FakeRosario:
    """Returns rows shaped exactly like RosarioSIS REST 'records/<table>' responses."""

    def __init__(self, reference_tables):
        self.t = reference_tables
        major_id = 200000012
        self.t["custom_fields"] = self.t["custom_fields"] + [{"id": major_id, "type": "select", "title": "Major"}]
        self.t["history_marking_periods"] = [
            {"marking_period_id": t["rosario_history_marking_period_id"], "name": t["name"], "short_name": t["key"],
             "mp_type": "semester", "post_end_date": t["end_date"], "syear": t["syear"], "school_id": 1}
            for t in SEED["terms"]]
        cid = {c: 690100 + i for i, c in enumerate(courses)}
        cpid = {c: 690200 + i for i, c in enumerate(sections)}
        self.t["courses"] = [{"course_id": cid[c], "short_name": c, "title": v["title"], "credit_hours": v["credits"],
                              "syear": 2026, "school_id": 1} for c, v in courses.items()]
        self.t["course_periods"] = [{"course_period_id": cpid[c], "course_id": cid[c], "short_name": f"{c}-01",
                                     "title": f"{c}-01", "credits": v["credits"], "marking_period_id": 2, "mp": "SEM"}
                                    for c, v in sections.items()]
        self.t["students"], self.t["student_enrollment"], self.t["schedule"] = [], [], []
        self.t["student_report_card_grades"], self.t["billing_fees"], self.t["billing_payments"] = [], [], []
        for s in students:
            sid, r = s["student_id"], s["rosario"]
            self.t["students"].append({"student_id": sid, "first_name": s["first_name"], "last_name": s["last_name"],
                                       "middle_name": None, "username": r["username"], f"custom_{major_id}": s["major"]})
            self.t["student_enrollment"].append({"student_id": sid, "syear": 2026, "school_id": 1, "grade_id": None,
                                                 "start_date": r["enrollment"]["start_date"], "end_date": None,
                                                 "enrollment_code": 3, "drop_code": None})
            for g in r["current_registrations"]:
                self.t["schedule"].append({"student_id": sid, "course_id": cid[g["code"]], "course_period_id": cpid[g["code"]],
                                           "marking_period_id": 2, "start_date": g["start_date"], "end_date": g["end_date"]})
            for h in r["history"]:
                self.t["student_report_card_grades"].append({
                    "student_id": sid, "course_period_id": None, "course_title": h["course_title"],
                    "marking_period_id": terms[h["term"]]["rosario_history_marking_period_id"],
                    "grade_letter": h["grade_letter"], "grade_percent": h["grade_percent"],
                    "unweighted_gp": h["grade_points"], "gp_scale": 4 if h["grade_points"] is not None else None,
                    "credit_attempted": h["credits_attempted"], "credit_earned": h["credits_earned"]})
            for f in r["finance"]["fees"]:
                self.t["billing_fees"].append({"student_id": sid, "amount": f["amount"], "due_date": f["due"], "title": f["title"]})
            for p in r["finance"]["payments"]:
                self.t["billing_payments"].append({"student_id": sid, "amount": p["amount"], "payment_date": p["date"]})

    def records(self, table, **_):
        if table not in self.t:
            raise KeyError(table)
        return self.t[table]


class FakeMoodle:
    """Returns data shaped exactly like the Moodle 4.1 web-service responses My Coach reads."""

    def __init__(self):
        self.course_ids = {c: 690300 + i for i, c in enumerate(sections)}
        self.user_ids = {s["student_id"]: 690400 + i for i, s in enumerate(students) if s["moodle"]}
        self.assign_ids = {}
        for c, cid in self.course_ids.items():
            for a in SEED["moodle_activities"]["assignments"]:
                self.assign_ids[(c, a["n"])] = cid * 10 + a["n"]

    def call(self, fn, **p):
        acts = SEED["moodle_activities"]
        if fn == "core_webservice_get_site_info":
            names = ["core_course_get_courses", "core_enrol_get_enrolled_users", "mod_assign_get_assignments",
                     "mod_assign_get_submissions", "gradereport_user_get_grade_items"]
            return {"sitename": "My Coach LMS (dry run)", "functions": [{"name": n} for n in names]}
        if fn == "core_course_get_courses":
            return [{"id": 1, "format": "site", "shortname": "site"}] + [
                {"id": cid, "shortname": c, "fullname": sections[c]["moodle"]["fullname"], "format": "topics"}
                for c, cid in self.course_ids.items()]
        code = {v: k for k, v in self.course_ids.items()}
        if fn == "core_enrol_get_enrolled_users":
            c = code[p["courseid"]]
            out = []
            for s in students:
                m = s["moodle"]
                course = next((x for x in m["courses"] if x["code"] == c), None) if m else None
                if course:
                    out.append({"id": self.user_ids[s["student_id"]], "username": m["username"], "idnumber": m["idnumber"],
                                "fullname": f"{m['firstname']} {m['lastname']}", "email": m["email"],
                                "roles": [{"shortname": "student"}], "lastaccess": ts(m["site_last_access"]),
                                "lastcourseaccess": ts(course["last_course_access"])})
            return out
        if fn == "mod_assign_get_assignments":
            return {"courses": [{"id": cid, "assignments": [
                {"id": self.assign_ids[(code[cid], a["n"])], "name": a["name"], "duedate": ts(a["due"] + "T23:59"),
                 "cutoffdate": ts(a["cutoff"] + "T23:59"), "nosubmissions": 0} for a in acts["assignments"]]}
                for cid in p["courseids"]]}
        if fn == "mod_assign_get_submissions":
            out = []
            for aid in p["assignmentids"]:
                c, n = next(k for k, v in self.assign_ids.items() if v == aid)
                subs = []
                for s in students:
                    m = s["moodle"]
                    course = next((x for x in m["courses"] if x["code"] == c), None) if m else None
                    if course:
                        a = course["assignments"][n - 1]
                        if a["submitted_at"]:
                            subs.append({"userid": self.user_ids[s["student_id"]], "status": "submitted",
                                         "timemodified": ts(a["submitted_at"])})
                out.append({"assignmentid": aid, "submissions": subs})
            return {"assignments": out}
        if fn == "gradereport_user_get_grade_items":
            c = code[p["courseid"]]
            ug = []
            for s in students:
                m = s["moodle"]
                course = next((x for x in m["courses"] if x["code"] == c), None) if m else None
                if course:
                    items = [{"itemname": f"Quiz {q['n']}", "itemmodule": "quiz", "itemtype": "mod",
                              "graderaw": q["score_percent"], "grademax": 100} for q in course["quizzes"]]
                    ug.append({"userid": self.user_ids[s["student_id"]], "gradeitems": items})
            return {"usergrades": ug}
        raise RuntimeError(f"unexpected function {fn}")


def reference_tables():
    """Existing RosarioSIS reference tables (read-only GET through the REST API)."""
    from config import settings
    from services.rosario_service import RosarioClient
    client = RosarioClient(settings.ROSARIO_API_URL, settings.ROSARIO_API_TOKEN, 15)
    try:
        client.authenticate()
        return {t: client.records(t) for t in ("custom_fields", "student_enrollment_codes", "school_gradelevels",
                                                "schools", "school_marking_periods")}
    finally:
        client.close()


def run_engine():
    from services import rosario_service, moodle_service
    from services.sync_service import load_catalog, merge_sources
    from database import SessionLocal

    rosario = rosario_service._build_records(FakeRosario(reference_tables()))
    moodle = moodle_service._collect(FakeMoodle())
    merged = merge_sources(rosario, moodle)
    db = SessionLocal()
    try:
        ctx = RuleContext(catalog=load_catalog(db), today=date.today())
    finally:
        db.close()
    results = {}
    for rec in merged:
        res = evaluate_student(rec, ctx)
        results[rec.student_id] = (rec, res)
    return rosario, moodle, merged, ctx, results


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 100)
    print("STRUCTURAL VALIDATION")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail and not ok else ""))
    structural_ok = all(ok for _, ok, _ in checks)

    print("=" * 100)
    print("IN-MEMORY RUN THROUGH THE REAL MY COACH PIPELINE (no database writes)")
    rosario, moodle, merged, ctx, results = run_engine()
    print(f"  rosario: {rosario.status} - {rosario.message}")
    print(f"  moodle : {moodle.status} - {moodle.message}")
    ids_merged = {r.student_id for r in merged}
    joined = [r for r in merged if "rosario" in r.sources and "moodle" in r.sources]
    moodle_only = [r.student_id for r in merged if r.sources == ["moodle"]]
    print(f"  merged students: {len(merged)} | matched RosarioSIS+Moodle: {len(joined)} | Moodle-only: {moodle_only or 'none'}")
    pipeline_ok = rosario.status == "ok" and moodle.status == "ok" and len(merged) == 30 and len(joined) == 29 and not moodle_only
    pipeline_ok &= ids_merged == {str(i) for i in ids}
    print(f"  catalogue courses used by the rules: {len(ctx.catalog)}")

    print("=" * 100)
    print(f"{'ID':7} {'grp':6} {'exp':9} {'actual':9} {'credits':>7} {'GPA':>5}  term GPAs / indicators")
    mismatches = []
    for e in EXPECT["students"]:
        sid = str(e["student_id"])
        rec, res = results[sid]
        actual = {a.anomaly_type: a.severity for a in res.anomalies}
        exp = e["current_code"]["indicators"]
        ok = actual == exp and res.risk_level == e["current_code"]["risk_level"]
        if not ok:
            mismatches.append((sid, exp, actual, e["current_code"]["risk_level"], res.risk_level))
        tg = " ".join(f"{t.gpa:.2f}" for t in rec.term_gpas[-4:])
        ind = ", ".join(f"{k}:{v[0]}" for k, v in actual.items()) or "-"
        print(f"{'OK ' if ok else 'XX '}{sid:6} {e['group']:6} {e['current_code']['risk_level']:9} {res.risk_level:9} "
              f"{(rec.completed_units or 0):>7g} {(rec.cumulative_gpa or 0):>5.2f}  [{tg}]  {ind}")
    gaps = [e for e in EXPECT["students"] if e["target"]["risk_level"] != e["current_code"]["risk_level"] or e["target"].get("add") or e["target"].get("remove")]
    print("=" * 100)
    print("KNOWN GAPS (target behaviour needs enhancements, documented in the expectation file):")
    for e in gaps:
        print(f"  {e['student_id']}: current {e['current_code']['risk_level']} -> target {e['target']['risk_level']}"
              f" | add {e['target'].get('add', [])} remove {e['target'].get('remove', [])} | needs {e['target'].get('requires', [])}")
    print("=" * 100)
    for sid, exp, act, er, ar in mismatches:
        print(f"MISMATCH {sid}: expected {er} {exp} | actual {ar} {act}")
    passed = structural_ok and pipeline_ok and not mismatches
    print(f"RESULT: structural {'PASS' if structural_ok else 'FAIL'} | pipeline {'PASS' if pipeline_ok else 'FAIL'} | "
          f"expectations {len(EXPECT['students']) - len(mismatches)}/{len(EXPECT['students'])} match -> "
          f"{'DRY RUN PASSED' if passed else 'DRY RUN FAILED'}")
    sys.exit(0 if passed else 1)
