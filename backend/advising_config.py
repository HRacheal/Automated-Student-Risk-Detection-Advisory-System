# backend/advising_config.py
"""
Institutional advising configuration used by the anomaly rules.
Everything here is policy — edit these values rather than the rule code.
"""

# Course-code prefixes that count toward each major. General-education
# prefixes are accepted for every major.
GENERAL_EDUCATION_PREFIXES = {"SUS", "ENG", "GRM", "CMS", "MTH", "LIT", "HUM", "PSY", "KIS", "FRE"}

MAJOR_PROGRAMS: dict[str, set[str]] = {
    "data science & analytics": {"DSA", "APT", "IST", "MTH", "STA"},
    "applied computer technology": {"APT", "IST", "DSA", "MTH"},
    "information systems & technology": {"IST", "APT", "DSA", "MTH"},
    "accounting": {"ACC", "FIN", "BUS", "ECO", "MTH"},
    "business administration": {"BUS", "ACC", "FIN", "MKT", "MGT", "ECO"},
    "international relations": {"IRL", "HIS", "ECO", "PSC"},
    "psychology": {"PSY", "SOC", "STA"},
}

UNDECLARED_VALUES = {"", "undeclared", "undecided", "none", "n/a", "not declared"}

# Foundational courses whose withdrawal is strongly associated with delayed
# progression in the DSA/APT/IST programmes.
GATEKEEPER_COURSES = {"IST1020", "MTH1109", "APT1030", "DSA1060", "DSA1080", "ENG1106"}

# Minimum passing letter for prerequisite satisfaction (catalogue text
# "Grade C or above" is honoured when present; otherwise any passing grade).
PASSING_GRADE_POINTS = 1.0  # D and above passes a course
PREREQ_MIN_GRADE_POINTS_WHEN_C_REQUIRED = 2.0

THRESHOLDS = {
    # low course load (units in active current courses)
    "full_time_min_units": 12,
    "critical_min_units": 6,
    # withdrawals (dropped current-term courses + W grades in history)
    "withdrawals_moderate": 3,
    "withdrawals_high": 5,
    # academic progression
    "probation_gpa": 2.0,
    "borderline_gpa": 2.5,
    "min_completion_rate": 0.67,  # credits earned / credits attempted
    "low_passing_points": 2.0,  # D-range grades that still pass
    "low_passing_count_moderate": 2,
    # GPA trend (drop between consecutive terms)
    "gpa_drop_moderate": 0.3,
    "gpa_drop_high": 0.75,
    # undeclared major
    "undeclared_moderate_units": 30,
    "undeclared_high_units": 60,
    # finance
    "balance_high": 1000.0,
    # Moodle assignments
    "missed_assignments_moderate": 2,
    "missed_assignments_high": 4,
    # Moodle quizzes (average % over attempted quizzes)
    "quiz_low_percent": 50.0,
    "quiz_critical_percent": 40.0,
    "quiz_min_count": 2,
    # Moodle engagement (days since last course access)
    "inactivity_moderate_days": 14,
    "inactivity_high_days": 30,
}


def major_prefixes(major: str | None) -> set[str] | None:
    if not major:
        return None
    return MAJOR_PROGRAMS.get(major.strip().lower())


def is_undeclared(major: str | None) -> bool:
    return (major or "").strip().lower() in UNDECLARED_VALUES


def course_prefix(code: str) -> str:
    letters = ""
    for ch in code.strip().upper():
        if ch.isalpha():
            letters += ch
        else:
            break
    return letters
