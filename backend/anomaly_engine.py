# backend/anomaly_engine.py
"""
Rule-based, explainable anomaly detection.

Every rule receives a normalised StudentRecord and either:
  * returns a DetectedAnomaly (with evidence + recommended intervention),
  * returns None (evaluated, condition not present), or
  * raises RuleSkipped(reason) when the data it needs is unavailable.

Rule-based anomalies are deterministic facts about the data. They are kept
separate from the experimental ML probability in analytics_engine.py.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional

from pydantic import BaseModel, Field

from advising_config import (
    GATEKEEPER_COURSES,
    GENERAL_EDUCATION_PREFIXES,
    PASSING_GRADE_POINTS,
    PREREQ_MIN_GRADE_POINTS_WHEN_C_REQUIRED,
    THRESHOLDS as T,
    course_prefix,
    is_undeclared,
    major_prefixes,
)
from domain import StudentRecord

LOW, MODERATE, HIGH = "LOW", "MODERATE", "HIGH"
SEVERITY_RANK = {LOW: 1, MODERATE: 2, HIGH: 3}


class DetectedAnomaly(BaseModel):
    student_id: str
    anomaly_type: str
    title: str
    severity: str
    description: str
    evidence: list[str] = Field(default_factory=list)
    recommended_intervention: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"
    data_sources: list[str] = Field(default_factory=list)


class RuleSkipped(Exception):
    """Raised when a rule cannot be evaluated because the data is unavailable."""


@dataclass
class CatalogCourse:
    code: str
    name: Optional[str] = None
    units: Optional[float] = None
    level: Optional[str] = None
    prerequisites: Optional[str] = None


@dataclass
class EvaluationResult:
    student_id: str
    anomalies: list[DetectedAnomaly] = field(default_factory=list)
    evaluated: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def risk_level(self) -> str:
        return overall_risk_level([a.severity for a in self.anomalies])


def overall_risk_level(severities: list[str]) -> str:
    """HIGH if any HIGH anomaly or 3+ MODERATE; MODERATE if any MODERATE; otherwise LOW."""
    if HIGH in severities or severities.count(MODERATE) >= 3:
        return HIGH
    if MODERATE in severities:
        return MODERATE
    return LOW


@dataclass
class RuleContext:
    catalog: dict[str, CatalogCourse]
    today: date


def _anomaly(s: StudentRecord, anomaly_type: str, title: str, severity: str, description: str,
             evidence: list[str], intervention: str, sources: list[str]) -> DetectedAnomaly:
    return DetectedAnomaly(
        student_id=s.student_id,
        anomaly_type=anomaly_type,
        title=title,
        severity=severity,
        description=description,
        evidence=evidence,
        recommended_intervention=intervention,
        data_sources=sources,
    )


def _require_courses(s: StudentRecord):
    if not s.current_courses and "current_courses" in s.unavailable_keys():
        raise RuleSkipped("Current course registrations are not available from the source systems.")


def _units(course, ctx: RuleContext) -> Optional[float]:
    if course.units is not None:
        return course.units
    cat = ctx.catalog.get(course.code.upper())
    return float(cat.units) if cat and cat.units is not None else None


def _src(s: StudentRecord, *preferred: str) -> list[str]:
    return [p for p in preferred if p in s.sources] or list(s.sources)


# ---------------------------------------------------------------------------
# 1. Course-major mismatch
# ---------------------------------------------------------------------------
def rule_course_major_mismatch(s: StudentRecord, ctx: RuleContext):
    if not s.major_field_available:
        raise RuleSkipped("Declared major is not available from the source systems.")
    if is_undeclared(s.declared_major):
        raise RuleSkipped("Student has no declared major (see 'Undeclared major').")
    allowed = major_prefixes(s.declared_major)
    if allowed is None:
        raise RuleSkipped(f"No course mapping configured for major '{s.declared_major}'.")
    _require_courses(s)
    mismatched = [
        c for c in s.active_courses
        if course_prefix(c.code) not in allowed and course_prefix(c.code) not in GENERAL_EDUCATION_PREFIXES
    ]
    if not mismatched:
        return None
    units = sum(_units(c, ctx) or 0 for c in mismatched)
    severity = HIGH if len(mismatched) >= 2 or units >= 6 else MODERATE
    return _anomaly(
        s, "course_major_mismatch", "Course-major mismatch", severity,
        f"{len(mismatched)} current course(s) do not count toward the declared major "
        f"({s.declared_major}) and are not general-education courses. These credits may not "
        f"count toward graduation ('wasted hours').",
        [f"Declared major: {s.declared_major}"]
        + [f"Enrolled in {c.code}{' – ' + c.title if c.title else ''} (prefix {course_prefix(c.code)} not in "
           f"{', '.join(sorted(allowed))})" for c in mismatched],
        "Review the degree audit with the student; confirm whether the course is an approved "
        "elective, otherwise advise swapping it for a major requirement before the add/drop deadline.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 2. Prerequisite violation
# ---------------------------------------------------------------------------
_CODE_RE = re.compile(r"\b([A-Z]{2,4})\s?(\d{4})\b")
_UNITS_RE = re.compile(r"(\d+)\s*\+\s*units", re.I)


def _passed(s: StudentRecord, code: str, min_points: float) -> bool:
    for g in s.course_history:
        if g.code.upper() != code or g.withdrawn or g.incomplete:
            continue
        if g.grade_points is not None:
            if g.grade_points >= min_points:
                return True
        elif g.passed:
            return True
    return False


def check_prerequisites(s: StudentRecord, prereq_text: str) -> tuple[list[str], list[str]]:
    """Returns (unmet requirement descriptions, unverifiable requirement descriptions)."""
    unmet: list[str] = []
    unverifiable: list[str] = []
    text = (prereq_text or "").strip()
    if not text or text.lower() == "none":
        return unmet, unverifiable
    for group in [g.strip() for g in text.split(",") if g.strip()]:
        min_points = PREREQ_MIN_GRADE_POINTS_WHEN_C_REQUIRED if re.search(r"grade\s+c", group, re.I) \
            else PASSING_GRADE_POINTS
        # "(Grade C or above)" is a grade condition, not an alternative
        requirement = re.sub(r"\(\s*grade[^)]*\)", "", group, flags=re.I)
        alternatives = [a.strip() for a in re.split(r"\bor\b", requirement, flags=re.I) if a.strip()]
        satisfied = False
        verifiable = False
        for alt in alternatives:
            codes = ["".join(m) for m in _CODE_RE.findall(alt.upper())]
            units_match = _UNITS_RE.search(alt)
            if codes:
                verifiable = True
                if all(_passed(s, c, min_points) for c in codes):
                    satisfied = True
            elif units_match:
                if s.completed_units is not None:
                    verifiable = True
                    if s.completed_units >= int(units_match.group(1)):
                        satisfied = True
            # other alternatives (placement exams, consent) cannot be verified from the data
        if satisfied:
            continue
        has_unverifiable_alt = any(
            not _CODE_RE.search(a.upper()) and not _UNITS_RE.search(a) for a in alternatives
        )
        if not verifiable or has_unverifiable_alt:
            unverifiable.append(group)
        else:
            unmet.append(group)
    return unmet, unverifiable


def rule_prerequisite_violation(s: StudentRecord, ctx: RuleContext):
    if not ctx.catalog:
        raise RuleSkipped("Course catalogue with prerequisites is not available.")
    _require_courses(s)
    violations = []
    for c in s.active_courses:
        cat = ctx.catalog.get(c.code.upper())
        if not cat or not cat.prerequisites:
            continue
        unmet, _ = check_prerequisites(s, cat.prerequisites)
        if unmet:
            violations.append((c, unmet))
    if not violations:
        return None
    return _anomaly(
        s, "prerequisite_violation", "Prerequisite violation", HIGH,
        f"Student is enrolled in {len(violations)} course(s) without completing the required "
        f"prerequisites on record.",
        [f"{c.code}: requires {', '.join(unmet)} – not found as passed in academic history"
         for c, unmet in violations]
        + [f"Completed units on record: {s.completed_units:g}" if s.completed_units is not None
           else "Completed units: unavailable"],
        "Verify prerequisite waivers with the Registrar. If none exist, move the student to the "
        "prerequisite course this term and arrange tutoring support.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 3. Excessive course withdrawals
# ---------------------------------------------------------------------------
def rule_excessive_withdrawals(s: StudentRecord, ctx: RuleContext):
    if not s.course_history and not s.current_courses and "course_history" in s.unavailable_keys():
        raise RuleSkipped("Course history / schedule is not available from the source systems.")
    dropped_now = s.dropped_courses
    hist = s.withdrawn_history
    total = len(dropped_now) + len(hist)
    if total < T["withdrawals_moderate"]:
        return None
    severity = HIGH if total >= T["withdrawals_high"] else MODERATE
    return _anomaly(
        s, "excessive_withdrawals", "Excessive course withdrawals", severity,
        f"{total} course withdrawals on record (threshold {T['withdrawals_moderate']} moderate, "
        f"{T['withdrawals_high']} high). Repeated withdrawals delay progression and may affect "
        f"financial aid eligibility.",
        [f"Dropped this term: {c.code}{' on ' + str(c.end_date) if c.end_date else ''}" for c in dropped_now]
        + [f"Withdrawn ({g.grade_letter}) from {g.code} in {g.term or 'earlier term'}" for g in hist],
        "Meet with the student to understand the reasons for repeated withdrawals (workload, "
        "finances, health). Build a realistic course plan and refer to counselling if needed.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 4. Low course load
# ---------------------------------------------------------------------------
def rule_low_course_load(s: StudentRecord, ctx: RuleContext):
    _require_courses(s)
    if s.enrollment_status == "withdrawn":
        raise RuleSkipped("Student is withdrawn from the school; course load not applicable.")
    active = s.active_courses
    if not active and not s.dropped_courses:
        raise RuleSkipped("No current-term course registrations found.")
    unit_values = [_units(c, ctx) for c in active]
    if any(u is None for u in unit_values):
        raise RuleSkipped("Credit units are unavailable for one or more current courses.")
    total = sum(unit_values)  # type: ignore[arg-type]
    if total >= T["full_time_min_units"]:
        return None
    severity = HIGH if total < T["critical_min_units"] else MODERATE
    return _anomaly(
        s, "low_course_load", "Low course load", severity,
        f"Currently registered for {total:g} units, below the full-time minimum of "
        f"{T['full_time_min_units']} units (standard load 12–18).",
        [f"Active courses: {', '.join(c.code for c in active) or 'none'}", f"Total active units: {total:g}"],
        "Confirm whether the reduced load is intentional (approved part-time status). Otherwise "
        "discuss the impact on graduation timeline and financial aid, and add a course if possible.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 5. Low passing grades / weak academic progression
# ---------------------------------------------------------------------------
def rule_weak_progression(s: StudentRecord, ctx: RuleContext):
    graded = [g for g in s.course_history if g.grade_points is not None and not g.withdrawn]
    if not graded and s.cumulative_gpa is None:
        raise RuleSkipped("No graded course history available.")
    evidence = []
    severity = None
    gpa = s.cumulative_gpa
    if gpa is not None and gpa < T["probation_gpa"]:
        severity = HIGH
        evidence.append(f"Cumulative GPA {gpa:.2f} is below the {T['probation_gpa']:.2f} probation threshold")
    elif gpa is not None and gpa < T["borderline_gpa"]:
        severity = MODERATE
        evidence.append(f"Cumulative GPA {gpa:.2f} is borderline (below {T['borderline_gpa']:.2f})")

    failed = [g for g in graded if g.passed is False]
    low_pass = [g for g in graded if g.passed and g.grade_points < T["low_passing_points"]]
    if failed:
        severity = severity or MODERATE
        evidence += [f"Failed {g.code} ({g.grade_letter or g.grade_percent}) in {g.term or 'n/a'}" for g in failed]
    if len(low_pass) >= T["low_passing_count_moderate"]:
        severity = severity or MODERATE
        evidence += [f"Low passing grade in {g.code}: {g.grade_letter or g.grade_percent}" for g in low_pass]

    attempted = sum(g.credits_attempted or 0 for g in s.course_history if not g.incomplete)
    earned = sum(g.credits_earned or 0 for g in s.course_history)
    if attempted >= 9:
        rate = earned / attempted
        if rate < T["min_completion_rate"]:
            severity = HIGH if severity == HIGH or rate < 0.5 else MODERATE
            evidence.append(f"Completion rate {rate:.0%} ({earned:g}/{attempted:g} credits) below "
                            f"{T['min_completion_rate']:.0%}")
    if not severity:
        return None
    return _anomaly(
        s, "weak_academic_progression", "Low grades / weak academic progression", severity,
        "Academic performance indicators show weak progression (low GPA, failed or barely-passed "
        "courses, or low credit completion).",
        evidence,
        "Place the student on an academic success plan: mandatory advising within 5 business days, "
        "referral to tutoring / the writing & math centres, and a mid-term progress check.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 6. Declining GPA trend
# ---------------------------------------------------------------------------
def rule_declining_gpa(s: StudentRecord, ctx: RuleContext):
    terms = sorted(s.term_gpas, key=lambda t: t.term_order)
    if len(terms) < 2:
        raise RuleSkipped("Fewer than two graded terms available; no trend can be computed.")
    last, prev = terms[-1], terms[-2]
    drop = prev.gpa - last.gpa
    consecutive = len(terms) >= 3 and terms[-3].gpa > prev.gpa > last.gpa
    if drop < T["gpa_drop_moderate"] and not consecutive:
        return None
    severity = HIGH if drop >= T["gpa_drop_high"] else MODERATE
    return _anomaly(
        s, "declining_gpa", "Declining GPA trend", severity,
        f"Term GPA fell by {drop:.2f} points from {prev.term} to {last.term}"
        + (" and has declined for three consecutive terms." if consecutive else "."),
        [f"{t.term}: GPA {t.gpa:.2f} ({t.credits:g} credits)" for t in terms[-4:]],
        "Discuss what changed this term (course difficulty, workload, personal factors). Agree on "
        "specific study goals and schedule a follow-up after the next assessment period.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 7. Gatekeeper-course withdrawal
# ---------------------------------------------------------------------------
def rule_gatekeeper_withdrawal(s: StudentRecord, ctx: RuleContext):
    dropped = [c.code for c in s.dropped_courses if c.code.upper() in GATEKEEPER_COURSES]
    dropped += [g.code for g in s.withdrawn_history if g.code.upper() in GATEKEEPER_COURSES]
    if not dropped:
        return None
    return _anomaly(
        s, "gatekeeper_withdrawal", "Gatekeeper course withdrawal", HIGH,
        "Student withdrew from a foundational 'gatekeeper' course that later courses depend on. "
        "This blocks progression through the major sequence.",
        [f"Withdrew from gatekeeper course {c}" for c in dict.fromkeys(dropped)]
        + [f"Gatekeeper list: {', '.join(sorted(GATEKEEPER_COURSES))}"],
        "Re-enrol the student in the gatekeeper course next term with tutoring/supplemental "
        "instruction, and adjust the course plan so dependent courses are not blocked.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 8. Undeclared major
# ---------------------------------------------------------------------------
def rule_undeclared_major(s: StudentRecord, ctx: RuleContext):
    if not s.major_field_available:
        raise RuleSkipped("Declared major is not available from the source systems.")
    if not is_undeclared(s.declared_major):
        return None
    units = s.completed_units
    if units is None:
        severity = LOW
    elif units >= T["undeclared_high_units"]:
        severity = HIGH
    elif units >= T["undeclared_moderate_units"]:
        severity = MODERATE
    else:
        severity = LOW
    return _anomaly(
        s, "undeclared_major", "Undeclared major", severity,
        "Student has not declared a major"
        + (f" after completing {units:g} units ({s.class_standing})." if units is not None else "."),
        [f"Declared major field: '{s.declared_major or ''}'",
         f"Completed units: {units:g}" if units is not None else "Completed units: unavailable"],
        "Schedule a major-exploration session with Career Services and set a deadline for major "
        "declaration so that required courses are not delayed.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 9. Financial / tuition risk
# ---------------------------------------------------------------------------
def rule_financial_risk(s: StudentRecord, ctx: RuleContext):
    f = s.financial
    if not f.available or f.balance is None:
        raise RuleSkipped("Tuition / billing information is not available from the source systems.")
    if f.balance <= 0:
        return None
    overdue = f.overdue_amount or 0
    severity = HIGH if f.balance >= T["balance_high"] or overdue > 0 else MODERATE
    return _anomaly(
        s, "financial_risk", "Outstanding tuition balance", severity,
        f"Student has an outstanding balance of {f.balance:,.2f}"
        + (f", of which {overdue:,.2f} is past due." if overdue else "."),
        [f"Balance: {f.balance:,.2f}", f"Past-due amount: {overdue:,.2f}", f"Fee records: {f.fees_count}"],
        "Refer the student to the Finance/Bursar office to discuss a payment plan or financial aid "
        "before a registration hold is applied.",
        [f.source],
    )


# ---------------------------------------------------------------------------
# 10. Missed assignments (Moodle)
# ---------------------------------------------------------------------------
def rule_missed_assignments(s: StudentRecord, ctx: RuleContext):
    if not s.lms.available or not s.lms.capabilities.get("assignments", False):
        raise RuleSkipped("Moodle assignment/submission data is not available.")
    missed = s.lms.missed_assignments
    if len(missed) < T["missed_assignments_moderate"]:
        return None
    severity = HIGH if len(missed) >= T["missed_assignments_high"] else MODERATE
    return _anomaly(
        s, "missed_assignments", "Missed assignments", severity,
        f"{len(missed)} assignment(s) are past their due date with no submission in Moodle.",
        [f"{a.course}: '{a.name}' due {a.due_date or 'n/a'} – not submitted" for a in missed],
        "Contact the student and course instructors; agree on a catch-up plan and check for "
        "underlying issues (access, workload, wellbeing).",
        ["moodle" if "moodle" in s.sources else "demo"],
    )


# ---------------------------------------------------------------------------
# 11. Low quiz performance (Moodle)
# ---------------------------------------------------------------------------
def rule_low_quiz_performance(s: StudentRecord, ctx: RuleContext):
    if not s.lms.available or not s.lms.capabilities.get("quizzes", False):
        raise RuleSkipped("Moodle quiz grades are not available.")
    scored = [q for q in s.lms.quizzes if q.percent is not None]
    if len(scored) < T["quiz_min_count"]:
        return None
    avg = sum(q.percent for q in scored) / len(scored)  # type: ignore[misc]
    if avg >= T["quiz_low_percent"]:
        return None
    severity = HIGH if avg < T["quiz_critical_percent"] else MODERATE
    return _anomaly(
        s, "low_quiz_performance", "Low quiz performance", severity,
        f"Average quiz score is {avg:.0f}% across {len(scored)} graded quizzes "
        f"(threshold {T['quiz_low_percent']:.0f}%).",
        [f"{q.course}: '{q.name}' – {q.percent:.0f}%" for q in scored],
        "Refer the student to tutoring for the affected course(s) and review study strategies; "
        "ask the instructor about formative feedback.",
        ["moodle" if "moodle" in s.sources else "demo"],
    )


# ---------------------------------------------------------------------------
# 12. Course dropped without replacement
# ---------------------------------------------------------------------------
def rule_dropped_without_replacement(s: StudentRecord, ctx: RuleContext):
    _require_courses(s)
    unreplaced = []
    for d in s.dropped_courses:
        replacement = [
            c for c in s.active_courses
            if c.start_date and d.end_date and c.start_date >= d.end_date
        ]
        if not replacement:
            unreplaced.append(d)
    if not unreplaced:
        return None
    active_units = [_units(c, ctx) for c in s.active_courses]
    known = None if any(u is None for u in active_units) else sum(active_units)  # type: ignore[arg-type]
    severity = HIGH if known is not None and known < T["full_time_min_units"] else MODERATE
    return _anomaly(
        s, "dropped_without_replacement", "Course dropped without replacement", severity,
        f"{len(unreplaced)} course(s) were dropped this term and no replacement course was added.",
        [f"Dropped {c.code}{' – ' + c.title if c.title else ''}"
         f"{' on ' + str(c.end_date) if c.end_date else ''}" for c in unreplaced]
        + ([f"Remaining active units: {known:g}"] if known is not None else []),
        "Check whether the drop leaves the student below full-time status or delays required "
        "sequences; plan a replacement course (or late add) where possible.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 13. Academic hold / incomplete grade
# ---------------------------------------------------------------------------
def rule_hold_or_incomplete(s: StudentRecord, ctx: RuleContext):
    incompletes = [g for g in s.course_history if g.incomplete]
    if s.holds is None and not incompletes and not s.course_history:
        raise RuleSkipped("Neither hold information nor grade history is available.")
    holds = s.holds or []
    if not holds and not incompletes:
        return None
    severity = HIGH if holds else MODERATE
    evidence = [f"Hold: {h}" for h in holds] + [
        f"Incomplete grade ({g.grade_letter}) in {g.code}, {g.term or 'n/a'}" for g in incompletes
    ]
    if s.holds is None:
        evidence.append("Hold information is not available from the source; only incompletes checked.")
    return _anomaly(
        s, "hold_or_incomplete", "Academic hold / incomplete grade", severity,
        "The student has " + " and ".join(
            p for p in [f"{len(holds)} active hold(s)" if holds else "",
                        f"{len(incompletes)} incomplete grade(s)" if incompletes else ""] if p
        ) + ", which can block registration or graduation.",
        evidence,
        "Help the student clear the hold with the responsible office and agree a completion "
        "deadline for incomplete work with the instructor.",
        _src(s, "rosario", "demo"),
    )


# ---------------------------------------------------------------------------
# 14. LMS inactivity (Moodle engagement)
# ---------------------------------------------------------------------------
def rule_lms_inactivity(s: StudentRecord, ctx: RuleContext):
    if not s.lms.available or not s.lms.capabilities.get("engagement", False):
        raise RuleSkipped("Moodle course access (engagement) data is not available.")
    days = s.lms.days_since_last_access
    if days is None:
        return _anomaly(
            s, "lms_inactivity", "No LMS activity", HIGH,
            "Student is enrolled in Moodle courses but has never accessed them.",
            [f"Moodle courses: {', '.join(s.lms.courses) or 'n/a'}", "Last course access: never"],
            "Contact the student immediately to confirm they are attending and can access Moodle.",
            ["moodle" if "moodle" in s.sources else "demo"],
        )
    if days < T["inactivity_moderate_days"]:
        return None
    severity = HIGH if days >= T["inactivity_high_days"] else MODERATE
    return _anomaly(
        s, "lms_inactivity", "Low LMS engagement", severity,
        f"No Moodle course access for {days} days (threshold {T['inactivity_moderate_days']} days).",
        [f"Last course access: {s.lms.last_access}", f"Moodle courses: {', '.join(s.lms.courses) or 'n/a'}"],
        "Reach out to the student to check on attendance and wellbeing; notify course instructors.",
        ["moodle" if "moodle" in s.sources else "demo"],
    )


RULES: dict[str, Callable[[StudentRecord, RuleContext], Optional[DetectedAnomaly]]] = {
    "course_major_mismatch": rule_course_major_mismatch,
    "prerequisite_violation": rule_prerequisite_violation,
    "excessive_withdrawals": rule_excessive_withdrawals,
    "low_course_load": rule_low_course_load,
    "weak_academic_progression": rule_weak_progression,
    "declining_gpa": rule_declining_gpa,
    "gatekeeper_withdrawal": rule_gatekeeper_withdrawal,
    "undeclared_major": rule_undeclared_major,
    "financial_risk": rule_financial_risk,
    "missed_assignments": rule_missed_assignments,
    "low_quiz_performance": rule_low_quiz_performance,
    "dropped_without_replacement": rule_dropped_without_replacement,
    "hold_or_incomplete": rule_hold_or_incomplete,
    "lms_inactivity": rule_lms_inactivity,
}

RULE_TITLES = {
    "course_major_mismatch": "Course-major mismatch",
    "prerequisite_violation": "Prerequisite violation",
    "excessive_withdrawals": "Excessive course withdrawals",
    "low_course_load": "Low course load",
    "weak_academic_progression": "Low grades / weak academic progression",
    "declining_gpa": "Declining GPA trend",
    "gatekeeper_withdrawal": "Gatekeeper course withdrawal",
    "undeclared_major": "Undeclared major",
    "financial_risk": "Outstanding tuition balance",
    "missed_assignments": "Missed assignments",
    "low_quiz_performance": "Low quiz performance",
    "dropped_without_replacement": "Course dropped without replacement",
    "hold_or_incomplete": "Academic hold / incomplete grade",
    "lms_inactivity": "Low LMS engagement",
}


def evaluate_student(s: StudentRecord, ctx: RuleContext) -> EvaluationResult:
    result = EvaluationResult(student_id=s.student_id)
    for name, rule in RULES.items():
        try:
            anomaly = rule(s, ctx)
        except RuleSkipped as exc:
            result.skipped[name] = str(exc)
            continue
        result.evaluated.append(name)
        if anomaly is not None:
            result.anomalies.append(anomaly)
    result.anomalies.sort(key=lambda a: -SEVERITY_RANK[a.severity])
    return result
