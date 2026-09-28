# backend/domain.py
"""
Normalised student model shared by every data source (RosarioSIS, Moodle,
Test Lab demo data) and consumed by the anomaly engine, chatbot and API.

Convention: a value of ``None`` means "the source did not provide this" —
it is NOT the same as zero/empty. Rules that need an unavailable value are
skipped (and reported as skipped) instead of guessing.
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CourseEnrollment(BaseModel):
    """A course the student is (or was) registered in for the current term."""
    code: str
    title: Optional[str] = None
    units: Optional[float] = None
    status: str = "enrolled"  # enrolled | dropped
    start_date: Optional[date] = None
    end_date: Optional[date] = None  # set when dropped
    term: Optional[str] = None
    source: str = "rosario"


class CourseGrade(BaseModel):
    """A final/term grade from the student's academic history."""
    code: str
    title: Optional[str] = None
    term: Optional[str] = None
    term_order: Optional[int] = None  # chronological ordering key
    grade_letter: Optional[str] = None
    grade_percent: Optional[float] = None
    grade_points: Optional[float] = None  # normalised to a 4.0 scale
    credits_attempted: Optional[float] = None
    credits_earned: Optional[float] = None
    passed: Optional[bool] = None
    withdrawn: bool = False
    incomplete: bool = False
    source: str = "rosario"


class TermGPA(BaseModel):
    term: str
    term_order: int
    gpa: float
    credits: float


class AssignmentStatus(BaseModel):
    course: str
    name: str
    due_date: Optional[str] = None
    status: str  # submitted | missed | pending
    source: str = "moodle"


class QuizResult(BaseModel):
    course: str
    name: str
    percent: Optional[float] = None
    source: str = "moodle"


class LMSData(BaseModel):
    available: bool = False
    moodle_user_id: Optional[int] = None
    courses: list[str] = Field(default_factory=list)
    last_access: Optional[str] = None  # ISO datetime of latest course access
    days_since_last_access: Optional[int] = None
    assignments: list[AssignmentStatus] = Field(default_factory=list)
    quizzes: list[QuizResult] = Field(default_factory=list)
    course_grades: dict[str, Optional[float]] = Field(default_factory=dict)  # course -> %
    capabilities: dict[str, bool] = Field(default_factory=dict)  # which data Moodle exposed

    @property
    def missed_assignments(self) -> list[AssignmentStatus]:
        return [a for a in self.assignments if a.status == "missed"]


class FinancialData(BaseModel):
    available: bool = False
    balance: Optional[float] = None
    overdue_amount: Optional[float] = None
    fees_count: int = 0
    source: str = "rosario"


class StudentRecord(BaseModel):
    student_id: str
    full_name: str
    sources: list[str] = Field(default_factory=list)
    is_demo: bool = False

    username: Optional[str] = None
    declared_major: Optional[str] = None  # None => field not available in source
    major_field_available: bool = False
    school: Optional[str] = None
    grade_level: Optional[str] = None
    enrollment_status: Optional[str] = None  # active | withdrawn
    enrollment_note: Optional[str] = None

    completed_units: Optional[float] = None
    class_standing: Optional[str] = None
    cumulative_gpa: Optional[float] = None
    term_gpas: list[TermGPA] = Field(default_factory=list)

    current_term: Optional[str] = None
    current_courses: list[CourseEnrollment] = Field(default_factory=list)
    course_history: list[CourseGrade] = Field(default_factory=list)

    holds: Optional[list[str]] = None  # None => holds not available from source
    financial: FinancialData = Field(default_factory=FinancialData)
    lms: LMSData = Field(default_factory=LMSData)

    unavailable: list[str] = Field(default_factory=list)  # human-readable notes
    missing: list[str] = Field(default_factory=list)  # machine keys, e.g. "current_courses"

    # ---- derived helpers -------------------------------------------------
    def unavailable_keys(self) -> set[str]:
        return set(self.missing)

    def mark_unavailable(self, key: str, note: str) -> None:
        if key not in self.missing:
            self.missing.append(key)
        if note not in self.unavailable:
            self.unavailable.append(note)

    @property
    def active_courses(self) -> list[CourseEnrollment]:
        return [c for c in self.current_courses if c.status == "enrolled"]

    @property
    def dropped_courses(self) -> list[CourseEnrollment]:
        return [c for c in self.current_courses if c.status == "dropped"]

    @property
    def withdrawn_history(self) -> list[CourseGrade]:
        return [g for g in self.course_history if g.withdrawn]


def standing_from_units(units: Optional[float]) -> Optional[str]:
    """USIU standing thresholds (advising_rules table): 0-29, 30-59, 60-89, 90+."""
    if units is None:
        return None
    if units >= 90:
        return "Senior"
    if units >= 60:
        return "Junior"
    if units >= 30:
        return "Sophomore"
    return "Freshman"


def compute_gpas(history: list[CourseGrade]) -> tuple[list[TermGPA], Optional[float]]:
    """Credit-weighted GPA per term and cumulative, from graded (non-W/I) courses."""
    by_term: dict[tuple[int, str], list[CourseGrade]] = {}
    for g in history:
        if g.grade_points is None or g.withdrawn or g.incomplete:
            continue
        key = (g.term_order or 0, g.term or "Unknown term")
        by_term.setdefault(key, []).append(g)

    terms: list[TermGPA] = []
    total_points = 0.0
    total_credits = 0.0
    for (order, term), grades in sorted(by_term.items()):
        pts = 0.0
        creds = 0.0
        for g in grades:
            c = g.credits_attempted if g.credits_attempted else 1.0
            pts += g.grade_points * c
            creds += c
        if creds:
            terms.append(TermGPA(term=term, term_order=order, gpa=round(pts / creds, 2), credits=creds))
            total_points += pts
            total_credits += creds
    cumulative = round(total_points / total_credits, 2) if total_credits else None
    return terms, cumulative


LETTER_POINTS = {
    "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0,
    "C-": 1.7, "D+": 1.3, "D": 1.0, "D-": 0.7, "F": 0.0,
}
WITHDRAWAL_LETTERS = {"W", "WF", "WP", "DRP"}
INCOMPLETE_LETTERS = {"I", "INC", "IP", "NG"}
