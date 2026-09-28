"""
Unit tests for the rule-based anomaly engine. No database or external
system is needed: records are built in memory.

Run from backend/:  python -m pytest -q
"""
from datetime import date, timedelta

import pytest

from anomaly_engine import (
    HIGH,
    LOW,
    MODERATE,
    CatalogCourse,
    RuleContext,
    check_prerequisites,
    evaluate_student,
    overall_risk_level,
)
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
)
from services.demo_source import SCENARIOS, fetch_demo

TODAY = date.today()

CATALOG = {
    "IST1020": CatalogCourse("IST1020", "Intro to IS", 3, "Freshman", "Pass Placement Exam or IST 0999"),
    "MTH1109": CatalogCourse("MTH1109", "College Algebra", 3, "Freshman", "Pass Placement Exam or MTH 1105"),
    "ENG1106": CatalogCourse("ENG1106", "Composition I", 3, "Freshman", "None"),
    "ENG2206": CatalogCourse("ENG2206", "Composition II", 3, "Freshman", "ENG1106 (Grade C or above)"),
    "DSA1060": CatalogCourse("DSA1060", "Intro to Data Science", 3, "Freshman", "None"),
    "DSA1080": CatalogCourse("DSA1080", "Programming for DS", 3, "Freshman", "IST1020, DSA1060"),
    "APT1030": CatalogCourse("APT1030", "Fundamentals of Programming", 3, "Freshman", "IST1020"),
    "APT1050": CatalogCourse("APT1050", "Database Systems", 3, "Freshman", "IST1020"),
    "MTH2215": CatalogCourse("MTH2215", "Discrete Mathematics", 3, "Sophomore", "MTH1109"),
    "MTH2010": CatalogCourse("MTH2010", "Probability and Statistics", 3, "Sophomore", "MTH1109"),
    "APT2060": CatalogCourse("APT2060", "DSA", 3, "Sophomore", "DSA1080, APT1050, MTH2215"),
    "CMS3700": CatalogCourse("CMS3700", "Community Service", 3, "Sophomore", "Sophomore Standing (30+ units)"),
    "DSA3010": CatalogCourse("DSA3010", "ML Foundations", 3, "Junior", "APT2060, MTH2010"),
    "DSA4010": CatalogCourse("DSA4010", "Deep Learning", 3, "Senior", "DSA3010"),
}
CTX = RuleContext(catalog=CATALOG, today=TODAY)


def grade(code, term, letter, units=3.0):
    letter = letter.upper()
    withdrawn = letter == "W"
    incomplete = letter == "I"
    pts = None if withdrawn or incomplete else LETTER_POINTS[letter]
    passed = None if withdrawn or incomplete else pts >= 1.0
    return CourseGrade(code=code, term=f"T{term}", term_order=term, grade_letter=letter, grade_points=pts,
                       credits_attempted=0 if withdrawn else units, credits_earned=units if passed else 0,
                       passed=passed, withdrawn=withdrawn, incomplete=incomplete)


def course(code, units=3.0, dropped_days_ago=None, started_days_ago=30):
    return CourseEnrollment(
        code=code, units=units, status="dropped" if dropped_days_ago is not None else "enrolled",
        start_date=TODAY - timedelta(days=started_days_ago),
        end_date=TODAY - timedelta(days=dropped_days_ago) if dropped_days_ago is not None else None,
    )


def healthy_student(**overrides) -> StudentRecord:
    history = [grade(c, t, g) for c, t, g in [
        ("IST1020", 1, "A"), ("MTH1109", 1, "B+"), ("ENG1106", 1, "B"), ("DSA1060", 1, "A-"),
        ("DSA1080", 2, "B+"), ("APT1030", 2, "A-"), ("APT1050", 2, "B"), ("ENG2206", 2, "B+"),
        ("MTH2215", 3, "B+"), ("MTH2010", 3, "A-"),
    ]]
    rec = StudentRecord(
        student_id="T-1", full_name="Test", sources=["demo"], declared_major="Data Science & Analytics",
        major_field_available=True, enrollment_status="active", holds=[],
        course_history=history,
        current_courses=[course("APT2060"), course("CMS3700"), course("ENG2206"), course("DSA1080")],
        financial=FinancialData(available=True, balance=0.0, overdue_amount=0.0, source="demo"),
        lms=LMSData(available=True, courses=["APT2060"], days_since_last_access=1,
                    last_access="2026-01-01T00:00",
                    assignments=[AssignmentStatus(course="APT2060", name="A1", status="submitted")],
                    quizzes=[QuizResult(course="APT2060", name="Q1", percent=80),
                             QuizResult(course="APT2060", name="Q2", percent=75)],
                    capabilities={"engagement": True, "assignments": True, "quizzes": True}),
    )
    rec.term_gpas, rec.cumulative_gpa = compute_gpas(rec.course_history)
    rec.completed_units = sum(g.credits_earned or 0 for g in rec.course_history)
    for k, v in overrides.items():
        setattr(rec, k, v)
    return rec


def types(rec):
    return {a.anomaly_type: a.severity for a in evaluate_student(rec, CTX).anomalies}


# ---------------------------------------------------------------------------
def test_healthy_student_is_low_risk_with_no_anomalies():
    result = evaluate_student(healthy_student(), CTX)
    assert result.anomalies == []
    assert result.risk_level == LOW


def test_course_major_mismatch():
    rec = healthy_student()
    rec.current_courses.append(course("ACC2010"))
    assert types(rec)["course_major_mismatch"] == MODERATE
    rec.current_courses.append(course("BUS1000"))
    assert types(rec)["course_major_mismatch"] == HIGH


def test_general_education_course_is_not_a_mismatch():
    rec = healthy_student()
    rec.current_courses.append(course("SUS1010"))
    assert "course_major_mismatch" not in types(rec)


def test_mismatch_skipped_when_major_unavailable():
    rec = healthy_student(major_field_available=False, declared_major=None)
    rec.current_courses.append(course("ACC2010"))
    result = evaluate_student(rec, CTX)
    assert "course_major_mismatch" in result.skipped
    assert "undeclared_major" in result.skipped  # unavailable != undeclared


def test_prerequisite_violation():
    rec = healthy_student()
    rec.current_courses.append(course("DSA4010"))
    anomaly = next(a for a in evaluate_student(rec, CTX).anomalies if a.anomaly_type == "prerequisite_violation")
    assert anomaly.severity == HIGH
    assert any("DSA3010" in e for e in anomaly.evidence)


def test_prerequisite_grade_c_requirement():
    rec = healthy_student()
    rec.course_history = [g for g in rec.course_history if g.code != "ENG1106"] + [grade("ENG1106", 1, "D")]
    unmet, _ = check_prerequisites(rec, "ENG1106 (Grade C or above)")
    assert unmet == ["ENG1106 (Grade C or above)"]


def test_placement_exam_alternative_is_unverifiable_not_violation():
    rec = healthy_student(course_history=[])
    unmet, unverifiable = check_prerequisites(rec, "Pass Placement Exam or MTH 1105")
    assert unmet == [] and unverifiable


def test_standing_requirement():
    rec = healthy_student(completed_units=12)
    unmet, _ = check_prerequisites(rec, "Sophomore Standing (30+ units)")
    assert unmet
    rec.completed_units = 45
    assert check_prerequisites(rec, "Sophomore Standing (30+ units)")[0] == []


def test_excessive_withdrawals_thresholds():
    rec = healthy_student()
    rec.course_history += [grade("X1000", 1, "W"), grade("X1001", 2, "W")]
    assert "excessive_withdrawals" not in types(rec)
    rec.course_history.append(grade("X1002", 3, "W"))
    assert types(rec)["excessive_withdrawals"] == MODERATE
    rec.course_history += [grade("X1003", 3, "W"), grade("X1004", 3, "W")]
    assert types(rec)["excessive_withdrawals"] == HIGH


def test_low_course_load():
    rec = healthy_student(current_courses=[course("APT2060"), course("CMS3700"), course("ENG2206")])
    assert types(rec)["low_course_load"] == MODERATE  # 9 units
    rec.current_courses = [course("APT2060")]
    assert types(rec)["low_course_load"] == HIGH  # 3 units


def test_low_course_load_skipped_when_units_unknown():
    rec = healthy_student(current_courses=[CourseEnrollment(code="ZZZ9999", units=None)])
    assert "low_course_load" in evaluate_student(rec, CTX).skipped


def test_weak_progression_probation():
    rec = healthy_student()
    rec.course_history = [grade("IST1020", 1, "D"), grade("MTH1109", 1, "F"), grade("ENG1106", 1, "D+")]
    rec.term_gpas, rec.cumulative_gpa = compute_gpas(rec.course_history)
    assert types(rec)["weak_academic_progression"] == HIGH


def test_declining_gpa():
    rec = healthy_student()
    rec.course_history += [grade("DSA3010", 4, "C"), grade("APT2080", 4, "C")]
    rec.term_gpas, rec.cumulative_gpa = compute_gpas(rec.course_history)
    assert types(rec)["declining_gpa"] == HIGH  # ~3.85 -> 2.0


def test_declining_gpa_needs_two_terms():
    rec = healthy_student()
    rec.term_gpas = rec.term_gpas[:1]
    assert "declining_gpa" in evaluate_student(rec, CTX).skipped


def test_gatekeeper_withdrawal():
    rec = healthy_student()
    rec.current_courses.append(course("APT1030", dropped_days_ago=3))
    assert types(rec)["gatekeeper_withdrawal"] == HIGH


def test_undeclared_major_severity_by_units():
    assert types(healthy_student(declared_major="Undeclared", completed_units=12))["undeclared_major"] == LOW
    assert types(healthy_student(declared_major="Undeclared", completed_units=45))["undeclared_major"] == MODERATE
    assert types(healthy_student(declared_major="Undeclared", completed_units=75))["undeclared_major"] == HIGH


def test_financial_risk():
    rec = healthy_student(financial=FinancialData(available=True, balance=300.0, overdue_amount=0.0))
    assert types(rec)["financial_risk"] == MODERATE
    rec.financial = FinancialData(available=True, balance=1450.0, overdue_amount=1450.0)
    assert types(rec)["financial_risk"] == HIGH


def test_financial_skipped_when_unavailable():
    rec = healthy_student(financial=FinancialData(available=False))
    assert "financial_risk" in evaluate_student(rec, CTX).skipped


def test_missed_assignments():
    rec = healthy_student()
    rec.lms.assignments += [AssignmentStatus(course="APT2060", name=f"M{i}", status="missed") for i in range(2)]
    assert types(rec)["missed_assignments"] == MODERATE
    rec.lms.assignments += [AssignmentStatus(course="APT2060", name=f"N{i}", status="missed") for i in range(2)]
    assert types(rec)["missed_assignments"] == HIGH


def test_lms_rules_skipped_without_moodle():
    rec = healthy_student(lms=LMSData(available=False))
    skipped = evaluate_student(rec, CTX).skipped
    assert {"missed_assignments", "low_quiz_performance", "lms_inactivity"} <= set(skipped)


def test_low_quiz_performance():
    rec = healthy_student()
    rec.lms.quizzes = [QuizResult(course="C", name="Q1", percent=45), QuizResult(course="C", name="Q2", percent=48)]
    assert types(rec)["low_quiz_performance"] == MODERATE
    rec.lms.quizzes = [QuizResult(course="C", name="Q1", percent=30), QuizResult(course="C", name="Q2", percent=35)]
    assert types(rec)["low_quiz_performance"] == HIGH


def test_dropped_without_replacement_vs_replaced():
    rec = healthy_student()
    rec.current_courses.append(course("MTH2010", dropped_days_ago=10, started_days_ago=40))
    assert "dropped_without_replacement" in types(rec)
    rec.current_courses.append(course("DSA1060", started_days_ago=5))  # added after the drop
    assert "dropped_without_replacement" not in types(rec)


def test_hold_and_incomplete():
    rec = healthy_student()
    rec.course_history.append(grade("GRM2000", 3, "I"))
    assert types(rec)["hold_or_incomplete"] == MODERATE
    rec.holds = ["Registrar hold"]
    assert types(rec)["hold_or_incomplete"] == HIGH


def test_lms_inactivity():
    rec = healthy_student()
    rec.lms.days_since_last_access = 15
    assert types(rec)["lms_inactivity"] == MODERATE
    rec.lms.days_since_last_access = 45
    assert types(rec)["lms_inactivity"] == HIGH


def test_every_anomaly_has_required_fields():
    rec = healthy_student(declared_major="Undeclared", completed_units=75)
    for a in evaluate_student(rec, CTX).anomalies:
        assert a.student_id and a.anomaly_type and a.severity in (LOW, MODERATE, HIGH)
        assert a.description and a.evidence and a.recommended_intervention
        assert a.detected_at and a.status == "active"


def test_overall_risk_policy():
    assert overall_risk_level([]) == LOW
    assert overall_risk_level([LOW, LOW]) == LOW
    assert overall_risk_level([MODERATE]) == MODERATE
    assert overall_risk_level([MODERATE] * 3) == HIGH
    assert overall_risk_level([HIGH]) == HIGH


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_each_test_lab_scenario_triggers_its_anomaly(key):
    """Normal DEMO-100 -> inject one scenario -> the expected anomaly is detected."""
    baseline = next(r for r in fetch_demo({}).records if r.student_id == "DEMO-100")
    assert evaluate_student(baseline, CTX).risk_level == LOW
    rec = next(r for r in fetch_demo({"DEMO-100": [key]}).records if r.student_id == "DEMO-100")
    assert SCENARIOS[key]["expected"] in types(rec)
