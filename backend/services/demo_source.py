# backend/services/demo_source.py
"""
Controlled local test data for demonstrating the anomaly engine ("Test Lab").

* Every record is labelled source="demo" and is_demo=True, with IDs "DEMO-xxx".
* Nothing here is written to RosarioSIS or Moodle.
* Test scenarios (toggled in the Test Lab UI, stored in the test_scenarios
  table) inject one specific risk condition into a demo student's local data,
  so the full Sync -> detect -> alert flow can be demonstrated even when the
  live systems do not contain that condition.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from domain import (
    LETTER_POINTS,
    AssignmentStatus,
    CourseEnrollment,
    CourseGrade,
    FinancialData,
    LMSData,
    QuizResult,
    StudentRecord,
    compute_gpas,
    standing_from_units,
)
from services.base import OK, SourceResult

TERMS = ["Fall 2025", "Spring 2026", "Summer 2026"]
CURRENT_TERM = "Fall 2026"


def _today() -> date:
    return date.today()


def _grade(code: str, term_idx: int, letter: str, units: float = 3.0, title: str | None = None) -> CourseGrade:
    letter = letter.upper()
    withdrawn = letter == "W"
    incomplete = letter in {"I", "INC"}
    points = None if withdrawn or incomplete else LETTER_POINTS.get(letter)
    passed = None if withdrawn or incomplete else (points is not None and points >= 1.0)
    return CourseGrade(
        code=code, title=title, term=TERMS[term_idx], term_order=term_idx + 1, grade_letter=letter,
        grade_points=points, credits_attempted=0.0 if withdrawn else units,
        credits_earned=units if passed else 0.0, passed=passed, withdrawn=withdrawn,
        incomplete=incomplete, source="demo",
    )


def _course(code: str, title: str, units: float = 3.0, dropped_days_ago: int | None = None) -> CourseEnrollment:
    start = _today() - timedelta(days=40)
    return CourseEnrollment(
        code=code, title=title, units=units, term=CURRENT_TERM, source="demo",
        status="dropped" if dropped_days_ago is not None else "enrolled",
        start_date=start,
        end_date=_today() - timedelta(days=dropped_days_ago) if dropped_days_ago is not None else None,
    )


def _lms(courses: list[str], days_since_access: int | None, quiz_scores: list[float],
         missed: int = 0, submitted: int = 3) -> LMSData:
    now = datetime.now(timezone.utc)
    assignments = []
    for i in range(submitted):
        c = courses[i % len(courses)]
        assignments.append(AssignmentStatus(course=c, name=f"Assignment {i + 1}",
                                            due_date=(now - timedelta(days=20 - i)).date().isoformat(),
                                            status="submitted", source="demo"))
    for i in range(missed):
        c = courses[i % len(courses)]
        assignments.append(AssignmentStatus(course=c, name=f"Lab/Problem Set {i + 1}",
                                            due_date=(now - timedelta(days=12 - i)).date().isoformat(),
                                            status="missed", source="demo"))
    quizzes = [QuizResult(course=courses[i % len(courses)], name=f"Quiz {i + 1}", percent=p, source="demo")
               for i, p in enumerate(quiz_scores)]
    last = (now - timedelta(days=days_since_access)) if days_since_access is not None else None
    return LMSData(
        available=True, courses=courses, assignments=assignments, quizzes=quizzes,
        last_access=last.isoformat(timespec="minutes") if last else None,
        days_since_last_access=days_since_access,
        capabilities={"engagement": True, "assignments": True, "quizzes": True},
    )


def _finalise(rec: StudentRecord) -> StudentRecord:
    rec.term_gpas, rec.cumulative_gpa = compute_gpas(rec.course_history)
    rec.completed_units = sum(g.credits_earned or 0 for g in rec.course_history)
    rec.class_standing = standing_from_units(rec.completed_units)
    return rec


def _base(student_id: str, name: str, major: str) -> StudentRecord:
    return StudentRecord(
        student_id=student_id, full_name=name, sources=["demo"], is_demo=True,
        declared_major=major, major_field_available=True, school="USIU-Africa (demo)",
        enrollment_status="active", current_term=CURRENT_TERM, holds=[],
        financial=FinancialData(available=True, balance=0.0, overdue_amount=0.0, fees_count=2, source="demo"),
    )


# ---------------------------------------------------------------------------
# Baseline demo students
# ---------------------------------------------------------------------------
def _test_student() -> StudentRecord:
    """DEMO-100: a normal, healthy student — the starting point for Test Lab demos."""
    s = _base("DEMO-100", "Test Student (Demo)", "Data Science & Analytics")
    s.course_history = [
        _grade("SUS1010", 0, "A-"), _grade("ENG1106", 0, "B+"), _grade("IST1020", 0, "A"),
        _grade("MTH1109", 0, "B"), _grade("DSA1060", 0, "A-"),
        _grade("ENG2206", 1, "B"), _grade("MTH1110", 1, "B+"), _grade("DSA1080", 1, "A-"),
        _grade("APT1030", 1, "B+"), _grade("APT1050", 1, "B"),
        _grade("MTH2215", 2, "B+"), _grade("MTH2010", 2, "B"), _grade("GRM2000", 2, "A-"),
    ]
    s.current_courses = [
        _course("APT2060", "Data Structures and Algorithms"),
        _course("APT2080", "Introduction to Software Engineering"),
        _course("DSA3020", "Data Visualization & Storytelling"),
        _course("IST3015", "Business Data Analytics"),
        _course("CMS3700", "Community Service"),
    ]
    s.lms = _lms(["APT2060", "APT2080", "DSA3020", "IST3015"], 1, [78, 84, 71])
    return _finalise(s)


def _kevin() -> StudentRecord:
    s = _base("DEMO-101", "Kevin Kimani (Demo)", "Data Science & Analytics")
    s.course_history = [
        _grade("SUS1010", 0, "B"), _grade("ENG1106", 0, "C+"), _grade("IST1020", 0, "B-"),
        _grade("MTH1109", 0, "C"), _grade("DSA1060", 1, "B-"), _grade("ENG2206", 1, "C"),
        _grade("MTH1110", 1, "C-"), _grade("DSA1080", 2, "C"),
    ]
    s.current_courses = [
        _course("ACC2010", "Principles of Accounting I"),
        _course("APT2060", "Data Structures and Algorithms"),
        _course("MTH2010", "Probability and Statistics"),
        _course("APT1030", "Fundamentals of Programming Languages", dropped_days_ago=9),
    ]
    s.lms = _lms(["APT2060", "MTH2010"], 6, [62, 58], missed=1, submitted=3)
    return _finalise(s)


def _amina() -> StudentRecord:
    s = _base("DEMO-102", "Amina Mohamed (Demo)", "Applied Computer Technology")
    s.course_history = [
        _grade("IST1020", 0, "A-"), _grade("MTH1109", 0, "B+"), _grade("ENG1106", 0, "B+"),
        _grade("APT1030", 1, "B-"), _grade("APT1050", 1, "C+"), _grade("ENG2206", 1, "B-"),
        _grade("MTH2215", 2, "C-"), _grade("DSA1060", 2, "D+"), _grade("SUS1010", 2, "C"),
    ]
    s.current_courses = [
        _course("APT2080", "Introduction to Software Engineering"),
        _course("DSA1080", "Programming for Data Science"),
        _course("MTH2010", "Probability and Statistics"),
        _course("GRM2000", "Introduction to Research Methods"),
    ]
    s.lms = _lms(["APT2080", "DSA1080", "MTH2010"], 4, [55, 61, 49], missed=3, submitted=2)
    return _finalise(s)


def _brian() -> StudentRecord:
    s = _base("DEMO-103", "Brian Otieno (Demo)", "Undeclared")
    s.course_history = [_grade(c, i % 3, "B") for i, c in enumerate(
        ["SUS1010", "ENG1106", "IST1020", "MTH1109", "DSA1060", "ENG2206", "MTH1110",
         "APT1030", "APT1050", "MTH2215", "MTH2010", "GRM2000", "DSA1080", "APT2080",
         "CMS3700", "IST3015", "DSA3020", "APT2060", "MTH1105", "LIT1000", "HUM1000"])]
    s.current_courses = [_course("APT3050", "Introduction to Project Management"),
                         _course("DSA3010", "Machine Learning Foundations"),
                         _course("APT3010", "Introduction to Artificial Intelligence"),
                         _course("PSY1000", "Introduction to Psychology")]
    s.lms = _lms(["APT3050", "DSA3010", "APT3010"], 2, [70, 75])
    return _finalise(s)


def _grace() -> StudentRecord:
    s = _base("DEMO-104", "Grace Wanjiru (Demo)", "Information Systems & Technology")
    s.course_history = [
        _grade("IST1020", 0, "B+"), _grade("ENG1106", 0, "B"), _grade("MTH1109", 0, "B"),
        _grade("APT1030", 1, "B"), _grade("SUS1010", 1, "A-"), _grade("APT1050", 2, "B-"),
        _grade("GRM2000", 2, "I"),
    ]
    s.current_courses = [_course("MTH2010", "Probability and Statistics"),
                         _course("APT2080", "Introduction to Software Engineering"),
                         _course("ENG2206", "Composition II"), _course("DSA1060", "Intro to Data Science")]
    s.holds = ["Bursar hold – unpaid tuition balance"]
    s.financial = FinancialData(available=True, balance=1450.0, overdue_amount=1450.0, fees_count=3, source="demo")
    s.lms = _lms(["MTH2010", "APT2080", "ENG2206"], 3, [66, 72])
    return _finalise(s)


def _faith() -> StudentRecord:
    s = _base("DEMO-105", "Faith Chebet (Demo)", "Data Science & Analytics")
    s.course_history = [
        _grade("SUS1010", 0, "B"), _grade("IST1020", 0, "B-"), _grade("DSA1060", 0, "B"),
        _grade("MTH1109", 1, "C+"), _grade("ENG1106", 1, "B-"), _grade("DSA1080", 1, "C+"),
    ]
    s.current_courses = [_course("APT1030", "Fundamentals of Programming Languages"),
                         _course("MTH1110", "Calculus I"), _course("ENG2206", "Composition II"),
                         _course("APT1050", "Database Systems")]
    s.lms = _lms(["APT1030", "MTH1110", "APT1050"], 20, [38, 41, 35], missed=1, submitted=2)
    return _finalise(s)


def _samuel() -> StudentRecord:
    s = _base("DEMO-106", "Samuel Kiptoo (Demo)", "Data Science & Analytics")
    codes = ["SUS1010", "ENG1106", "IST1020", "MTH1109", "DSA1060", "ENG2206", "MTH1110", "DSA1080",
             "APT1030", "APT1050", "MTH2215", "MTH2010", "APT2060", "GRM2000", "APT2080", "CMS3700",
             "DSA3010", "DSA3020", "IST3015", "APT3010", "APT3050", "ENG1105", "MTH1105", "LIT1000",
             "HUM1000", "PSY1000", "DSA2050", "DSA2070", "DSA3030", "DSA3040", "IST2010"]
    # steady / improving performance: A- in the first term, A afterwards
    s.course_history = [_grade(c, i % 3, "A-" if i % 3 == 0 else "A") for i, c in enumerate(codes)]
    s.current_courses = [_course("DSA4010", "Deep Learning & Big Data Analytics"),
                         _course("DSA4090", "Senior Data Science Capstone Project", 6.0),
                         _course("IST3020", "IT Project Management")]
    s.lms = _lms(["DSA4010", "DSA4090", "IST3020"], 0, [88, 92, 90])
    return _finalise(s)


BASELINE_BUILDERS: list[Callable[[], StudentRecord]] = [_test_student, _kevin, _amina, _brian, _grace, _faith, _samuel]


# ---------------------------------------------------------------------------
# Test Lab scenarios — each injects exactly one risk condition
# ---------------------------------------------------------------------------
def _sc_mismatch(s: StudentRecord):
    s.current_courses.append(_course("ACC2010", "Principles of Accounting I"))


def _sc_prereq(s: StudentRecord):
    s.current_courses.append(_course("DSA4010", "Deep Learning & Big Data Analytics"))


def _sc_withdrawals(s: StudentRecord):
    s.course_history += [_grade("DSA3010", 2, "W"), _grade("APT3010", 2, "W"), _grade("IST3015", 1, "W")]


def _sc_low_load(s: StudentRecord):
    s.current_courses = s.current_courses[:2]


def _sc_weak(s: StudentRecord):
    s.course_history += [_grade("DSA3010", 2, "F"), _grade("APT3010", 2, "D"), _grade("IST3015", 2, "D+")]


def _sc_declining(s: StudentRecord):
    for g in s.course_history:
        if g.term_order == 3:
            g.grade_letter = "C"
            g.grade_points = LETTER_POINTS["C"]


def _sc_gatekeeper(s: StudentRecord):
    s.current_courses.append(_course("DSA1080", "Programming for Data Science (retake)", dropped_days_ago=5))
    s.current_courses.append(_course("SUS1015", "Study Skills Workshop"))  # added after, so not "without replacement"
    s.current_courses[-1].start_date = _today() - timedelta(days=3)


def _sc_undeclared(s: StudentRecord):
    s.declared_major = "Undeclared"


def _sc_financial(s: StudentRecord):
    s.financial = FinancialData(available=True, balance=1450.0, overdue_amount=1450.0, fees_count=3, source="demo")


def _sc_missed(s: StudentRecord):
    s.lms.assignments += [
        AssignmentStatus(course=c, name=f"Weekly Lab {i + 1}", status="missed", source="demo",
                         due_date=(_today() - timedelta(days=10 - i)).isoformat())
        for i, c in enumerate((s.lms.courses or ["COURSE"]) * 2)
    ][:4]


def _sc_quiz(s: StudentRecord):
    s.lms.quizzes = [QuizResult(course=c, name=f"Quiz {i + 1}", percent=p, source="demo")
                     for i, (c, p) in enumerate(zip((s.lms.courses or ["COURSE"]) * 3, [35, 42, 38]))]


def _sc_dropped(s: StudentRecord):
    for c in reversed(s.current_courses):
        if c.status == "enrolled":
            c.status = "dropped"
            c.end_date = _today() - timedelta(days=7)
            break


def _sc_hold(s: StudentRecord):
    s.holds = (s.holds or []) + ["Registrar hold – missing high-school transcript"]
    s.course_history.append(_grade("GRM2000", 2, "I"))


def _sc_inactive(s: StudentRecord):
    s.lms.days_since_last_access = 18
    s.lms.last_access = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat(timespec="minutes")


SCENARIOS: dict[str, dict] = {
    "course_major_mismatch": {"label": "Enrol in a course outside the major (ACC2010 Accounting)",
                              "expected": "course_major_mismatch", "apply": _sc_mismatch},
    "prerequisite_violation": {"label": "Enrol in DSA4010 without passing DSA3010",
                               "expected": "prerequisite_violation", "apply": _sc_prereq},
    "excessive_withdrawals": {"label": "Add three withdrawals (W) to the transcript",
                              "expected": "excessive_withdrawals", "apply": _sc_withdrawals},
    "low_course_load": {"label": "Reduce registration to two courses (6 units)",
                        "expected": "low_course_load", "apply": _sc_low_load},
    "weak_progression": {"label": "Record failing / D grades last term",
                         "expected": "weak_academic_progression", "apply": _sc_weak},
    "declining_gpa": {"label": "Lower all grades in the most recent term to C",
                      "expected": "declining_gpa", "apply": _sc_declining},
    "gatekeeper_withdrawal": {"label": "Drop gatekeeper course DSA1080 (retake)",
                              "expected": "gatekeeper_withdrawal", "apply": _sc_gatekeeper},
    "undeclared_major": {"label": "Change declared major to 'Undeclared'",
                         "expected": "undeclared_major", "apply": _sc_undeclared},
    "financial_risk": {"label": "Add an overdue tuition balance of 1,450.00",
                       "expected": "financial_risk", "apply": _sc_financial},
    "missed_assignments": {"label": "Miss four Moodle assignments",
                           "expected": "missed_assignments", "apply": _sc_missed},
    "low_quiz_performance": {"label": "Score below 45% on Moodle quizzes",
                             "expected": "low_quiz_performance", "apply": _sc_quiz},
    "dropped_without_replacement": {"label": "Drop a current course without adding another",
                                    "expected": "dropped_without_replacement", "apply": _sc_dropped},
    "hold_or_incomplete": {"label": "Add a registrar hold and an incomplete (I) grade",
                           "expected": "hold_or_incomplete", "apply": _sc_hold},
    "lms_inactivity": {"label": "No Moodle course access for 18 days",
                       "expected": "lms_inactivity", "apply": _sc_inactive},
}


def demo_student_ids() -> list[str]:
    return [b().student_id for b in BASELINE_BUILDERS]


def fetch_demo(active_scenarios: dict[str, list[str]]) -> SourceResult:
    """active_scenarios: {student_id: [scenario_key, ...]} from the test_scenarios table."""
    records = []
    applied: dict[str, list[str]] = {}
    for build in BASELINE_BUILDERS:
        rec = build()
        for key in active_scenarios.get(rec.student_id, []):
            sc = SCENARIOS.get(key)
            if sc:
                sc["apply"](rec)
                applied.setdefault(rec.student_id, []).append(key)
        records.append(_finalise(rec))
    return SourceResult("demo", OK, f"Loaded {len(records)} DEMO student(s) (controlled local test data).",
                        records, {"scenarios_applied": applied})
