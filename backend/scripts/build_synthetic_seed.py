"""
Builds the SYNTHETIC My Coach demonstration dataset (single source of truth).

Outputs (deterministic, re-runnable):
  backend/data/synthetic_student_demo_seed.json          <- the dataset (evidence only)
  backend/data/synthetic_student_demo_expectations.json  <- test oracle (NOT part of the dataset)

Everything here is fictitious. Names are invented, IDs are in the reserved
synthetic range 690001-690030, all e-mail addresses use the .invalid TLD.
The dataset deliberately contains NO risk / risk_level / colour / alert fields:
My Coach must derive risk from the evidence.

Run from backend/:  python scripts/build_synthetic_seed.py
"""
import json
import sys
from datetime import date, datetime, timedelta
from itertools import combinations_with_replacement
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from anomaly_engine import check_prerequisites  # noqa: E402  (same prerequisite semantics as the engine)
from domain import CourseGrade, StudentRecord  # noqa: E402

REFERENCE_DATE = date(2026, 9, 28)          # "today" for the scenario timeline
COURSE_START = date(2026, 8, 31)            # Fall 2026 teaching starts (RosarioSIS Semester 1 continues)
COURSE_END = date(2026, 12, 18)
ADD_DROP_DEADLINE = date(2026, 9, 14)       # institutional calendar fact (used by future rule H8)
MOODLE_COURSES_VISIBLE_FROM = date(2026, 8, 24)  # orientation week

# --------------------------------------------------------------------------
# Academic structure
# --------------------------------------------------------------------------
# Rosario "Main" grade scale (inspected): letter -> (gpa points on 4.0, representative percent)
SCALE = {
    "A": (4.00, 95), "A-": (3.75, 91), "B+": (3.50, 88), "B": (3.00, 85), "B-": (2.75, 81),
    "C+": (2.50, 78), "C": (2.00, 75), "C-": (1.75, 71), "D+": (1.50, 68), "D": (1.00, 65),
    "D-": (0.75, 61), "F": (0.00, 40),
}
LETTER_ORDER = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-"]  # F only via explicit events

MAJORS = [
    "Data Science & Analytics", "Applied Computer Technology", "Information Systems & Technology",
    "Business Administration", "Undeclared",
]

# code: (title, credits, subject, prerequisites text, in_mycoach_catalog)
# Prerequisite text for the 23 existing courses is copied verbatim from the My Coach catalog.
COURSES = {
    "SUS1010": ("Strategies for University Success", 3, "General Education", "None", True),
    "ENG1106": ("Composition I", 3, "General Education", "Pass Placement Exam or ENG 0999", True),
    "ENG2206": ("Composition II", 3, "General Education", "ENG1106 (Grade C or above)", True),
    "MTH1109": ("College Algebra", 3, "Mathematics", "Pass Placement Exam or MTH 1105", True),
    "MTH1110": ("Calculus I", 3, "Mathematics", "MTH1109", True),
    "MTH2010": ("Probability and Statistics", 3, "Mathematics", "MTH1109", True),
    "MTH2215": ("Discrete Mathematics", 3, "Mathematics", "MTH1109", True),
    "GRM2000": ("Introduction to Research Methods", 3, "General Education", "SUS1010, ENG1106", True),
    "CMS3700": ("Community Service", 3, "General Education", "Sophomore Standing (30+ units)", True),
    "IST1020": ("Introduction to Information Systems", 3, "Computing", "Pass Placement Exam or IST 0999", True),
    "DSA1060": ("Intro to Data Science", 3, "Computing", "None", True),
    "DSA1080": ("Programming for Data Science", 3, "Computing", "IST1020, DSA1060", True),
    "APT1030": ("Fundamentals of Programming Languages", 3, "Computing", "IST1020", True),
    "APT1050": ("Database Systems", 3, "Computing", "IST1020", True),
    "APT2060": ("Data Structures and Algorithms", 3, "Computing", "DSA1080, APT1050, MTH2215", True),
    "APT2080": ("Introduction to Software Engineering", 3, "Computing", "APT1030", True),
    "DSA3010": ("Machine Learning Foundations", 3, "Computing", "APT2060, MTH2010", True),
    "DSA3020": ("Data Visualization & Storytelling", 3, "Computing", "DSA1080", True),
    "IST3015": ("Business Data Analytics", 3, "Computing", "MTH2010", True),
    "APT3010": ("Introduction to Artificial Intelligence", 3, "Computing", "APT2060", True),
    "APT3050": ("Introduction to Project Management", 3, "Computing", "Junior Standing (60+ units)", True),
    "DSA4010": ("Deep Learning & Big Data Analytics", 3, "Computing", "DSA3010", True),
    "DSA4090": ("Senior Data Science Capstone Project", 6, "Computing", "Senior Standing (90+ units), APT3050", True),
    # Not yet in the My Coach catalog (H3). Proposed prerequisites, informational only.
    "BUS1010": ("Introduction to Business", 3, "Business", "None", False),
    "ACC2010": ("Principles of Accounting I", 3, "Business", "MTH1109", False),
    "ACC2020": ("Principles of Accounting II", 3, "Business", "ACC2010", False),
    "ECO2010": ("Principles of Microeconomics", 3, "Business", "MTH1109", False),
    "MKT2100": ("Principles of Marketing", 3, "Business", "BUS1010", False),
    "FIN3010": ("Corporate Finance", 3, "Business", "ACC2020, MTH2010", False),
    "BUS3050": ("Organizational Behaviour", 3, "Business", "BUS1010", False),
    "LIT1000": ("Introduction to Literature", 3, "General Education", "None", False),
    "HUM1000": ("Introduction to the Humanities", 3, "General Education", "None", False),
    "PSY1000": ("Introduction to Psychology", 3, "General Education", "None", False),
}
GATEKEEPERS = ["IST1020", "MTH1109", "APT1030", "DSA1060", "DSA1080", "ENG1106"]  # current My Coach list

# The 18 Fall 2026 sections (only courses the 30 students actually take)
OFFERED_FALL_2026 = [
    "SUS1010", "ENG1106", "MTH1109", "ENG2206", "MTH2010", "CMS3700",
    "DSA1060", "DSA1080", "APT1030", "APT2060", "APT2080", "DSA3010", "APT3050", "DSA4090", "IST3015",
    "BUS1010", "ACC2020", "BUS3050",
]
INSTRUCTOR_FOR = {c: "inst.computing" for c in OFFERED_FALL_2026}
INSTRUCTOR_FOR.update({"MTH1109": "inst.maths", "MTH2010": "inst.maths",
                       "SUS1010": "inst.gened", "ENG1106": "inst.gened", "ENG2206": "inst.gened",
                       "CMS3700": "inst.gened", "BUS1010": "inst.business", "ACC2020": "inst.business",
                       "BUS3050": "inst.business"})
INSTRUCTORS = [
    {"username": "inst.computing", "firstname": "Computing", "lastname": "Instructor (Synthetic)"},
    {"username": "inst.maths", "firstname": "Mathematics", "lastname": "Instructor (Synthetic)"},
    {"username": "inst.gened", "firstname": "General Education", "lastname": "Instructor (Synthetic)"},
    {"username": "inst.business", "firstname": "Business", "lastname": "Instructor (Synthetic)"},
]
for i in INSTRUCTORS:
    i["email"] = f"{i['username']}@staff.mycoach.invalid"

# Historical terms (RosarioSIS history_marking_periods). syear = starting year of the academic year.
TERMS = [
    ("FA23", "Fall 2023", date(2023, 9, 4), date(2023, 12, 15), 2023),
    ("SP24", "Spring 2024", date(2024, 1, 8), date(2024, 4, 26), 2023),
    ("SU24", "Summer 2024", date(2024, 5, 13), date(2024, 8, 9), 2023),
    ("FA24", "Fall 2024", date(2024, 9, 2), date(2024, 12, 13), 2024),
    ("SP25", "Spring 2025", date(2025, 1, 6), date(2025, 4, 25), 2024),
    ("SU25", "Summer 2025", date(2025, 5, 12), date(2025, 8, 8), 2024),
    ("FA25", "Fall 2025", date(2025, 9, 1), date(2025, 12, 12), 2025),
    ("SP26", "Spring 2026", date(2026, 1, 5), date(2026, 4, 24), 2025),
    ("SU26", "Summer 2026", date(2026, 5, 11), date(2026, 8, 7), 2025),
]
TERM_KEYS = [t[0] for t in TERMS]
HISTORY_MP_ID = {key: 6901 + i for i, key in enumerate(TERM_KEYS)}  # explicit, far from RosarioSIS' own ids

# Moodle activity schedule (same in every course)
ASSIGNMENTS = [(n, COURSE_START + timedelta(days=4 + 7 * (n - 1))) for n in range(1, 7)]  # Fridays: 4 Sep ... 9 Oct
QUIZZES = [(1, date(2026, 9, 7), date(2026, 9, 13)), (2, date(2026, 9, 21), date(2026, 9, 27)),
           (3, date(2026, 9, 28), date(2026, 10, 11))]
QUIZ_SLOT_MARKS = [1, 2, 4, 8, 5]   # 5 true/false questions, 20 marks: every 5% step from 0..100 is reachable

# --------------------------------------------------------------------------
# Programme sequences (the order a student normally takes courses)
# --------------------------------------------------------------------------
COMMON = ["SUS1010", "ENG1106", "IST1020", "MTH1109", "DSA1060", "ENG2206", "MTH1110", "DSA1080",
          "APT1030", "APT1050", "MTH2215", "GRM2000", "MTH2010"]
SEQ = {
    "Data Science & Analytics": COMMON + [
        "DSA3020", "APT2060", "CMS3700", "LIT1000", "IST3015", "APT2080", "HUM1000", "DSA3010", "PSY1000",
        "APT3010", "APT3050", "ECO2010", "DSA4010", "BUS1010", "MKT2100", "ACC2010", "ACC2020", "BUS3050",
        "FIN3010", "DSA4090"],
    "Applied Computer Technology": COMMON + [
        "APT2060", "APT2080", "CMS3700", "DSA3020", "LIT1000", "APT3010", "IST3015", "HUM1000", "APT3050",
        "PSY1000", "BUS1010", "ACC2010", "DSA3010", "ECO2010", "MKT2100", "ACC2020", "DSA4010", "BUS3050",
        "FIN3010", "DSA4090"],
    "Information Systems & Technology": [
        "SUS1010", "ENG1106", "IST1020", "MTH1109", "DSA1060", "ENG2206", "APT1050", "APT1030", "MTH2010",
        "GRM2000", "MTH1110", "DSA1080", "IST3015", "CMS3700", "MTH2215", "APT2080", "DSA3020", "LIT1000",
        "HUM1000", "APT2060", "APT3050", "PSY1000", "ECO2010", "BUS1010", "ACC2010", "APT3010", "DSA3010", "MKT2100",
        "ACC2020", "DSA4010", "BUS3050", "FIN3010", "DSA4090"],
    "Business Administration": [
        "SUS1010", "ENG1106", "MTH1109", "BUS1010", "LIT1000", "ACC2010", "ECO2010", "MKT2100", "HUM1000",
        "IST1020", "GRM2000", "MTH2010", "PSY1000", "ENG2206", "ACC2020", "MTH1110", "BUS3050", "FIN3010",
        "CMS3700", "MTH2215", "DSA1060", "APT1050", "APT1030", "DSA1080", "DSA3020", "APT2080", "IST3015",
        "APT2060"],
    "Undeclared": [
        "SUS1010", "ENG1106", "IST1020", "MTH1109", "DSA1060", "LIT1000", "HUM1000", "PSY1000", "GRM2000",
        "MTH1110", "APT1050", "ECO2010", "ENG2206", "BUS1010", "MKT2100", "APT1030", "DSA1080", "MTH2215",
        "ACC2010", "MTH2010", "APT2080", "DSA3020", "ACC2020", "APT2060", "BUS3050", "DSA3010", "APT3010",
        "FIN3010", "IST3015", "CMS3700", "APT3050", "DSA4010", "DSA4090"],
}

# --------------------------------------------------------------------------
# The 30 students. Only EVIDENCE is specified here.
#   loads   : history rows per term starting at `entry` (includes F/W/I/retake rows)
#   gpa     : term-GPA targets aligned to the LAST graded terms (earlier terms repeat the first value)
#   events  : {term: [(code, letter)]} forced rows: "F", "W", "I" or a retake letter
#   current : Fall 2026 registrations; ("CODE", start, drop_date or None)
#   moodle  : behaviour of the student in Moodle (None => no Moodle account)
# --------------------------------------------------------------------------
S = COURSE_START


def reg(*codes, start=S):
    return [(c, start, None) for c in codes]


STUDENTS = [
    # ---------------- GREEN ----------------
    dict(id=690001, first="Achieng", last="Otieno", major="Data Science & Analytics", entry="FA24",
         loads=[5, 5, 2, 5, 4, 1], gpa=[3.6, 3.7, 3.8], min_letter="B",
         current=reg("DSA3010", "APT3050", "CMS3700", "APT2080")
         + [("IST3015", S, date(2026, 9, 3)), ("ENG2206", date(2026, 9, 4), None)],
         moodle=dict(access_days=0, quiz=[90, 90])),
    dict(id=690002, first="Daniel", last="Mwangi", major="Applied Computer Technology", entry="FA25",
         loads=[5, 5, 3], gpa=[3.1, 3.0, 3.1], min_letter="C+",
         current=reg("APT2060", "APT2080", "MTH2010", "CMS3700", "ENG2206"), moodle=dict(access_days=1, quiz=[75, 75])),
    dict(id=690003, first="Fatuma", last="Hassan", major="Information Systems & Technology", entry="FA23",
         loads=[4, 4, 2, 4, 4, 2, 4, 4, 2], gpa=[2.6, 2.9, 3.2, 3.4], min_letter="C",
         current=reg("DSA4090", "APT2080", "CMS3700"), moodle=dict(access_days=0, quiz=[80, 80])),
    dict(id=690004, first="Brian", last="Kiprono", major="Business Administration", entry="FA25",
         loads=[5, 5, 1], gpa=[3.3, 3.3, 3.3], min_letter="C+",
         current=reg("ACC2020", "MTH2010", "CMS3700", "BUS3050", "ENG2206"), moodle=dict(access_days=2, quiz=[80, 85])),
    dict(id=690005, first="Grace", last="Njeri", major="Data Science & Analytics", entry="SP26",
         loads=[5, 2], gpa=[3.5, 3.6], min_letter="B-",
         current=reg("DSA1080", "MTH1109", "APT1030", "ENG2206"), moodle=dict(access_days=1, quiz=[85, 80])),
    dict(id=690006, first="Samuel", last="Ochieng", major="Business Administration", entry="FA24",
         loads=[5, 5, 2, 5, 3, 1], gpa=[3.0, 3.2, 3.1], min_letter="C+",
         current=reg("BUS3050", "CMS3700", "ENG2206", "ACC2020"), moodle=dict(access_days=1, quiz=[70, 75])),
    dict(id=690007, first="Mercy", last="Chebet", major="Applied Computer Technology", entry="FA23",
         loads=[4, 4, 2, 4, 4, 2, 4, 4, 2], gpa=[3.4, 3.4, 3.4], min_letter="B-",
         current=reg("DSA4090", "APT2080", "CMS3700"), moodle=dict(access_days=0, quiz=[90, 90])),
    dict(id=690008, first="Ian", last="Mutua", major="Information Systems & Technology", entry="FA25",
         loads=[5, 5, 2], gpa=[2.8, 2.8, 2.9], min_letter="C",
         current=reg("DSA1080", "APT2080", "MTH2010", "CMS3700"), moodle=dict(access_days=1, quiz=[65, 70])),
    # ---------------- EDGE (must not raise false alerts) ----------------
    dict(id=690009, first="Lucy", last="Wambui", major="Data Science & Analytics", entry="SP25",
         loads=[4, 2, 4, 4, 0], gpa=[3.4, 3.4, 2.7, 3.3], min_letter="C",
         current=reg("APT2060", "MTH2010", "CMS3700", "APT2080"), moodle=dict(access_days=1, quiz=[80, 80])),
    dict(id=690010, first="Kevin", last="Omondi", major="Applied Computer Technology", entry="FA24",
         loads=[5, 5, 2, 5, 4, 0], gpa=[3.3, 3.3, 3.3], min_letter="B-", events={"FA24": [("LIT1000", "W")]},
         current=reg("DSA3010", "APT3050", "CMS3700", "APT2080"), moodle=dict(access_days=0, quiz=[80, 80])),
    dict(id=690011, first="Zawadi", last="Mohamed", major="Business Administration", entry=None,
         loads=[], gpa=[], current=reg("SUS1010", "ENG1106", "MTH1109", "BUS1010"),
         fees="installments_not_yet_due", moodle=dict(access_days=2, quiz=[75, 75])),
    dict(id=690012, first="Peter", last="Kamau", major="Data Science & Analytics", entry="FA25",
         loads=[5, 5, 1], gpa=[3.0, 3.0, 3.0], min_letter="C+",
         current=reg("DSA1080", "MTH2010", "CMS3700", "APT2080"),
         moodle=dict(access_days=1, quiz=[75, 70], late={"DSA1080": [2, 3]})),
    dict(id=690013, first="Naliaka", last="Wafula", major="Information Systems & Technology", entry="FA24",
         loads=[5, 5, 1, 5, 5, 0], gpa=[3.2, 3.2, 3.2], min_letter="C+",
         current=reg("DSA3010", "APT3050", "CMS3700", "APT2080"), moodle=None),
    dict(id=690014, first="Tom", last="Barasa", major="Applied Computer Technology", entry="FA24",
         loads=[4, 4, 2, 3, 3, 0], gpa=[2.25, 3.0, 3.0, 3.0, 3.0], min_letter="B-",
         events={"FA24": [("MTH1109", "F")], "SP25": [("MTH1109", "B")]},
         current=reg("APT2060", "CMS3700", "MTH2010", "APT2080"), moodle=dict(access_days=1, quiz=[75, 75])),
    # ---------------- YELLOW ----------------
    dict(id=690015, first="Ruth", last="Akinyi", major="Data Science & Analytics", entry="FA25",
         loads=[5, 5, 3], gpa=[3.4, 3.0, 2.6], min_letter="C",
         current=reg("APT2060", "MTH2010", "CMS3700", "APT2080"), moodle=dict(access_days=1, quiz=[70, 70])),
    dict(id=690016, first="Collins", last="Kiptoo", major="Applied Computer Technology", entry="FA24",
         loads=[5, 5, 2, 4, 4, 0], gpa=[3.2, 3.2, 3.2], min_letter="C+",
         current=reg("APT2060", "APT3050", "CMS3700", "MTH2010"),
         moodle=dict(access_days=1, quiz=[75, 75], missed={"APT2060": [2, 3, 4]})),
    dict(id=690017, first="Wanjiru", last="Kariuki", major="Information Systems & Technology", entry="FA25",
         loads=[5, 5, 2], gpa=[3.0, 3.0, 3.0], min_letter="C+",
         current=reg("DSA1080", "APT2080", "MTH2010", "CMS3700"),
         moodle=dict(access_days=0, quiz=[85, 70], quiz_exact=True, q3=60)),
    dict(id=690018, first="Hassan", last="Abdi", major="Business Administration", entry="FA25",
         loads=[5, 5, 1], gpa=[3.1, 3.1, 3.1], min_letter="C+",
         current=reg("ACC2020", "MTH2010", "CMS3700", "BUS3050"),
         moodle=dict(access_days=16, quiz=[70, None], early_submit_by=date(2026, 9, 11), early_max_n=4)),
    dict(id=690019, first="Esther", last="Moraa", major="Data Science & Analytics", entry="FA24",
         loads=[5, 5, 2, 4, 3, 0], gpa=[3.0, 3.0, 3.0], min_letter="C+",
         current=reg("DSA3010", "CMS3700", "APT2080"), moodle=dict(access_days=1, quiz=[75, 75])),
    dict(id=690020, first="Felix", last="Otieno", major="Applied Computer Technology", entry="SP25",
         loads=[4, 2, 4, 4, 0], gpa=[3.0, 3.0, 3.0], min_letter="C+",
         current=reg("APT2060", "MTH2010", "CMS3700", "ENG2206") + [("APT2080", S, date(2026, 9, 15))],
         moodle=dict(access_days=1, quiz=[70, 70])),
    dict(id=690021, first="Mary", last="Nyambura", major="Business Administration", entry="FA24",
         loads=[5, 5, 2, 4, 5, 3], gpa=[2.4, 2.4, 2.4], min_letter="C",
         events={"FA24": [("HUM1000", "F"), ("LIT1000", "W")],
                 "SP25": [("MTH1110", "F"), ("HUM1000", "B-"), ("GRM2000", "W"), ("DSA1060", "D")],
                 "SU25": [("PSY1000", "F")],
                 "FA25": [("MKT2100", "F"), ("MTH2215", "W"), ("GRM2000", "C+")],
                 "SP26": [("MKT2100", "C"), ("ECO2010", "F"), ("APT1050", "W")],
                 "SU26": [("ENG2206", "D")]},
         current=reg("ACC2020", "MTH2010", "CMS3700", "BUS3050"), moodle=dict(access_days=2, quiz=[65, 65])),
    dict(id=690022, first="Joseph", last="Maina", major="Information Systems & Technology", entry="FA25",
         loads=[5, 4, 1], gpa=[2.4, 2.3, 2.35], min_letter="C-",
         current=reg("DSA1080", "APT2080", "MTH2010", "CMS3700"), moodle=dict(access_days=1, quiz=[60, 60])),
    dict(id=690023, first="Aisha", last="Yusuf", major="Business Administration", entry="FA24",
         loads=[5, 5, 2, 4, 3, 1], gpa=[3.1, 3.2, 3.1], min_letter="C+",
         current=reg("DSA1060", "BUS3050", "CMS3700", "ACC2020"), moodle=dict(access_days=1, quiz=[75, 75])),
    dict(id=690024, first="Kelvin", last="Mutiso", major="Undeclared", entry="FA25",
         loads=[5, 5, 2], gpa=[3.0, 3.0, 3.0], min_letter="C+",
         current=reg("DSA1080", "MTH2010", "CMS3700", "BUS1010", "ENG2206"), moodle=dict(access_days=1, quiz=[70, 70])),
    # ---------------- RED ----------------
    dict(id=690025, first="Victor", last="Onyango", major="Data Science & Analytics", entry="FA24",
         loads=[5, 5, 2, 4, 3, 3], gpa=[3.2, 3.2, 3.2, 3.2, 2.4, 1.6], min_letter="C",
         events={"FA25": [("PSY1000", "W")], "SP26": [("DSA3020", "W"), ("IST3015", "W")],
                 "SU26": [("GRM2000", "I"), ("HUM1000", "C-"), ("LIT1000", "D+")]},
         current=reg("DSA3010", "CMS3700", "APT2080", "ENG2206"),
         moodle=dict(access_days=21, quiz=[40, None], quiz_alt=[40, 35], quiz_exact=True,
                     early_submit_by=date(2026, 9, 6), early_max_n=2, early_skip_courses=["ENG2206"])),
    dict(id=690026, first="Sharon", last="Atieno", major="Applied Computer Technology", entry="FA25",
         loads=[5, 4], gpa=[2.7, 2.7], min_letter="C",
         current=reg("APT2080", "DSA1080", "MTH2010", "ENG2206") + [("APT1030", S, date(2026, 9, 12))],
         moodle=dict(access_days=1, quiz=[55, 55], missed={"APT2080": [3, 4], "DSA1080": [4], "MTH2010": [4]})),
    dict(id=690027, first="Dennis", last="Kirui", major="Information Systems & Technology", entry="FA24",
         loads=[2, 2, 0, 2, 2, 0], gpa=[2.3, 2.3, 2.3], min_letter="C-",
         current=reg("DSA1080", "MTH2010", "ENG2206", "APT2080"),
         moodle=dict(access_days=34, quiz=[None, None], missed_all=True, opened=["DSA1080", "MTH2010"])),
    dict(id=690028, first="Joy", last="Wairimu", major="Business Administration", entry="FA24",
         loads=[4, 4, 1, 4, 4, 1], gpa=[1.8, 1.9, 1.8], min_letter="D",
         events={"SP25": [("MKT2100", "W")], "FA25": [("ECO2010", "W")], "SP26": [("ACC2020", "F")]},
         current=reg("ACC2020", "MTH2010", "CMS3700", "BUS3050"), fees="overdue",
         moodle=dict(access_days=2, quiz=[55, 50], missed={"ACC2020": [3, 4], "BUS3050": [4]})),
    dict(id=690029, first="Abdullahi", last="Omar", major="Data Science & Analytics", entry="FA23",
         loads=[4, 4, 1, 4, 4, 1, 4, 3, 2], gpa=[3.0, 3.0, 3.0, 2.2], min_letter="C",
         events={"SP26": [("DSA3010", "I")]},
         current=reg("APT3050", "APT2080", "CMS3700", "IST3015"),
         moodle=dict(access_days=2, quiz=[45, 40], quiz_exact=True,
                     missed={"APT3050": [4], "IST3015": [3], "CMS3700": [4]})),
    dict(id=690030, first="Beatrice", last="Muthoni", major="Undeclared", entry="FA23",
         loads=[4, 4, 2, 4, 4, 2, 4, 3, 3], gpa=[3.0, 3.0, 3.0], min_letter="B-",
         events={"FA23": [("HUM1000", "F")], "SP24": [("LIT1000", "W")], "SU24": [("PSY1000", "F")],
                 "FA24": [("MTH1110", "W")], "SP25": [("ECO2010", "F")], "FA25": [("MKT2100", "F")],
                 "SP26": [("FIN3010", "W")], "SU26": [("DSA3020", "W")]},
         current=reg("CMS3700", "IST3015"), moodle=dict(access_days=1, quiz=[70, 70])),
]
GROUP = {**{i: "green" for i in range(690001, 690009)}, **{i: "edge" for i in range(690009, 690015)},
         **{i: "yellow" for i in range(690015, 690025)}, **{i: "red" for i in range(690025, 690031)}}


# --------------------------------------------------------------------------
# History generator
# --------------------------------------------------------------------------
def _prior_record(rows, credits):
    rec = StudentRecord(student_id="x", full_name="x")
    rec.course_history = [CourseGrade(code=r["code"], grade_points=r["grade_points"], passed=r["passed"],
                                      withdrawn=r["kind"] == "withdrawn", incomplete=r["kind"] == "incomplete")
                          for r in rows]
    rec.completed_units = credits
    return rec


def eligible(code, rows, credits):
    unmet, _ = check_prerequisites(_prior_record(rows, credits), COURSES[code][3])
    return not unmet  # placement-exam alternatives are treated as satisfied


def solve_letters(n, target, fixed_points, min_letter):
    """Choose n letters (>= min_letter) so that the term mean incl. fixed points is closest to target."""
    if n == 0:
        return []
    palette = LETTER_ORDER[: LETTER_ORDER.index(min_letter) + 1]
    best = None
    for combo in combinations_with_replacement(palette, n):
        pts = [SCALE[c][0] for c in combo] + fixed_points
        mean = sum(pts) / len(pts)
        spread = max(SCALE[c][0] for c in combo) - min(SCALE[c][0] for c in combo)
        key = (round(abs(mean - target), 4), spread, -sum(SCALE[c][0] for c in combo))
        if best is None or key < best[0]:
            best = (key, list(combo))
    return best[1]


def build_history(st):
    if not st["entry"]:
        return []
    start = TERM_KEYS.index(st["entry"])
    terms = TERM_KEYS[start:start + len(st["loads"])]
    current_codes = {c for c, _, _ in st["current"]}
    events = st.get("events", {})
    event_codes = {code for evs in events.values() for code, _ in evs}
    graded_terms = [t for t, n in zip(terms, st["loads"]) if n]
    targets = {}
    gpa = st["gpa"]
    for i, t in enumerate(reversed(graded_terms)):
        targets[t] = gpa[len(gpa) - 1 - i] if i < len(gpa) else gpa[0]
    rows, credits = [], 0
    seq = [c for c in SEQ[st["major"]] if c not in current_codes]
    for term, load in zip(terms, st["loads"]):
        forced = events.get(term, [])
        chosen = [code for code, _ in forced]
        taken = {r["code"] for r in rows if r["passed"] or r["kind"] in ("withdrawn", "incomplete")}
        failed_open = {r["code"] for r in rows if r["passed"] is False}
        for code in seq:
            if len(chosen) >= load:
                break
            if code in chosen or code in taken or code in failed_open or code in event_codes:
                continue
            if code == "DSA4090":
                continue  # capstone is never historical in this dataset
            if eligible(code, rows, credits):
                chosen.append(code)
        if len(chosen) != load:
            raise SystemExit(f"{st['id']}: could not fill {term} (wanted {load}, got {chosen})")
        for code, _ in forced:
            if not eligible(code, rows, credits):
                raise SystemExit(f"{st['id']}: forced {code} in {term} has unmet prerequisites")
        forced_map = dict(forced)
        free = [c for c in chosen if c not in forced_map]
        fixed = [SCALE[l][0] for c, l in forced if l in SCALE]
        letters = solve_letters(len(free), targets.get(term, 3.0), fixed, st["min_letter"])
        # ENG1106 feeds ENG2206 ("Grade C or above"): give it the best letter of the term
        free.sort(key=lambda c: (c != "ENG1106", c))
        letters.sort(key=lambda l: LETTER_ORDER.index(l))
        term_rows = []
        for code, letter in list(zip(free, letters)) + forced:
            cr = COURSES[code][1]
            if letter == "W":
                row = dict(kind="withdrawn", grade_letter="W", grade_percent=None, grade_points=None,
                           credits_attempted=cr, credits_earned=0, passed=None)
            elif letter == "I":
                row = dict(kind="incomplete", grade_letter="I", grade_percent=None, grade_points=None,
                           credits_attempted=cr, credits_earned=0, passed=None)
            else:
                pts, pct = SCALE[letter]
                passed = letter != "F"
                row = dict(kind="graded", grade_letter=letter, grade_percent=pct, grade_points=pts,
                           credits_attempted=cr, credits_earned=cr if passed else 0, passed=passed)
            row.update(term=term, code=code, course_title=code)
            term_rows.append(row)
        rows += sorted(term_rows, key=lambda r: r["code"])
        credits += sum(r["credits_earned"] for r in term_rows)
    return rows


# --------------------------------------------------------------------------
# Moodle behaviour generator
# --------------------------------------------------------------------------
def at(d, hh=20, mm=0):
    return datetime(d.year, d.month, d.day, hh, mm).isoformat(timespec="minutes")


def build_moodle(st):
    m = st["moodle"]
    if m is None:
        return None
    sid = st["id"]
    active = [c for c, _, drop in st["current"] if drop is None]
    last_access = REFERENCE_DATE - timedelta(days=m["access_days"])
    courses = []
    for ci, code in enumerate(active):
        opened = m.get("opened")
        course_access = None if (opened is not None and code not in opened) else at(last_access, 9 + ci)
        a_rows = []
        for n, due in ASSIGNMENTS:
            cutoff = due + timedelta(days=3)
            status, when = "pending", None
            if due < REFERENCE_DATE:
                status, when = "submitted", at(due - timedelta(days=1), 18 + (sid + ci + n) % 4)
                if m.get("missed_all") or n in m.get("missed", {}).get(code, []):
                    status, when = "missed", None
                elif n in m.get("late", {}).get(code, []):
                    status, when = "late", at(due + timedelta(days=1), 10)
                elif m.get("early_submit_by"):
                    # Student stopped accessing Moodle on/after `early_submit_by`: work due before that is
                    # submitted normally; up to assignment `early_max_n` was submitted early; the rest is missed.
                    limit = m["early_submit_by"]
                    if due - timedelta(days=1) <= limit:
                        when = at(due - timedelta(days=1), 17)
                    elif n <= m["early_max_n"] and code not in m.get("early_skip_courses", []):
                        when = at(limit, 17)
                    else:
                        status, when = "missed", None
            a_rows.append(dict(n=n, due=due.isoformat(), cutoff=cutoff.isoformat(), status=status, submitted_at=when))
        q_rows = []
        for qi, (n, opens, closes) in enumerate(QUIZZES):
            score, attempted_at, status = None, None, "not_attempted"
            base = m["quiz"][n - 1] if n <= 2 else m.get("q3")
            if m.get("quiz_alt") and n == 1:
                base = m["quiz_alt"][ci % 2]
            if closes < REFERENCE_DATE or (n == 3 and base is not None):
                if base is not None and (course_access is not None) and opens <= last_access:
                    jitter = 0 if m.get("quiz_exact") else [0, 5, -5, 0, 5][(sid + ci + n) % 5]
                    score = max(0, min(100, base + jitter))
                    day = min(opens + timedelta(days=2), last_access) if n < 3 else REFERENCE_DATE
                    attempted_at, status = at(day, 7 if n == 3 else 19), "attempted"
                else:
                    status = "not_attempted"
            else:
                status = "open_not_attempted" if opens <= REFERENCE_DATE else "not_yet_open"
            q_rows.append(dict(n=n, opens=opens.isoformat(), closes=closes.isoformat(), status=status,
                               attempted_at=attempted_at, score_percent=score))
        courses.append(dict(code=code, last_course_access=course_access, assignments=a_rows, quizzes=q_rows))
    site = at(last_access, 9 + len(active)) if any(c["last_course_access"] for c in courses) else None
    return dict(username=f"s{sid}", idnumber=str(sid), email=f"{sid}@students.mycoach.invalid",
                firstname=st["first"], lastname=st["last"], site_last_access=site, courses=courses)


def build_finance(st):
    mode = st.get("fees", "paid")
    if mode == "installments_not_yet_due":
        fees = [dict(title="Tuition Fall 2026 - installment 1 of 2", amount=750.00, assigned="2026-08-31", due="2026-09-15"),
                dict(title="Tuition Fall 2026 - installment 2 of 2", amount=750.00, assigned="2026-08-31", due="2026-10-15")]
        payments = [dict(amount=750.00, date="2026-09-12", comment="Installment 1")]
    elif mode == "overdue":
        fees = [dict(title="Tuition Fall 2026", amount=1500.00, assigned="2026-08-31", due="2026-09-15")]
        payments = [dict(amount=50.00, date="2026-09-14", comment="Partial payment")]
    else:
        fees = [dict(title="Tuition Fall 2026", amount=1500.00, assigned="2026-08-31", due="2026-09-15")]
        payments = [dict(amount=1500.00, date="2026-09-10", comment="Paid in full")]
    return dict(fees=fees, payments=payments)


def build():
    students, expectations = [], []
    for st in STUDENTS:
        history = build_history(st)
        registrations = [dict(code=c, section=f"{c}-01", start_date=s.isoformat(),
                              end_date=d.isoformat() if d else None) for c, s, d in st["current"]]
        students.append(dict(
            student_id=st["id"], first_name=st["first"], last_name=st["last"], major=st["major"],
            entry_term=st["entry"] or "FA26",
            rosario=dict(username=f"s{st['id']}", grade_id=None,
                         enrollment=dict(syear=2026, start_date=COURSE_START.isoformat(), enrollment_code="EBY"),
                         history=history, current_registrations=registrations, finance=build_finance(st)),
            moodle=build_moodle(st),
        ))
    seed = dict(
        meta=dict(
            name="My Coach synthetic student demonstration dataset", version=1, synthetic=True,
            notice="Entirely fictitious. No real students, staff or PII. Contains no risk labels.",
            generated_by="backend/scripts/build_synthetic_seed.py", reference_date=REFERENCE_DATE.isoformat(),
            timezone="Africa/Nairobi",
            current_term=dict(key="FA26", name="Fall 2026", rosario_marking_period="Semester 1 (existing, unchanged)",
                              course_start=COURSE_START.isoformat(), course_end=COURSE_END.isoformat(),
                              add_drop_deadline=ADD_DROP_DEADLINE.isoformat(),
                              moodle_courses_visible_from=MOODLE_COURSES_VISIBLE_FROM.isoformat()),
            conventions=dict(
                history_course_title="always the exact course code (required by current My Coach mapping)",
                withdrawal="past terms: free-text grade letter W (credits_attempted counted, 0 earned, excluded from GPA); "
                           "current term: schedule end_date",
                incomplete="grade letter I (existing RosarioSIS grade), excluded from GPA",
                grade_scale="RosarioSIS 'Main' scale on 4.0 (A-=3.75, B+=3.5 ...)",
                quiz_scores="multiples of 5% (5 true/false questions weighted 1,2,4,8,5 = 20 marks)",
                prerequisites="kept in the My Coach catalog, never stored in RosarioSIS",
            ),
        ),
        majors=MAJORS,
        courses=[dict(code=c, title=v[0], credits=v[1], subject=v[2], prerequisites=v[3], in_mycoach_catalog=v[4],
                      gatekeeper=c in GATEKEEPERS) for c, v in COURSES.items()],
        terms=[dict(key=k, name=n, start_date=s.isoformat(), end_date=e.isoformat(), syear=y,
                    rosario_history_marking_period_id=HISTORY_MP_ID[k]) for k, n, s, e, y in TERMS],
        sections=[dict(code=c, section=f"{c}-01", term="FA26", credits=COURSES[c][1], instructor=INSTRUCTOR_FOR[c],
                       moodle=dict(shortname=c, idnumber=f"{c}-2026S1", fullname=f"{c} {COURSES[c][0]} (Fall 2026)",
                                   category="Fall 2026", startdate=COURSE_START.isoformat(), enddate=COURSE_END.isoformat()))
                  for c in OFFERED_FALL_2026],
        moodle_activities=dict(
            assignments=[dict(n=n, name=f"Assignment {n}", allow_from=COURSE_START.isoformat(), due=d.isoformat(),
                              cutoff=(d + timedelta(days=3)).isoformat(), max_grade=100) for n, d in ASSIGNMENTS],
            quizzes=[dict(n=n, name=f"Quiz {n}", opens=o.isoformat(), closes=c.isoformat(), max_grade=100,
                          slot_marks=QUIZ_SLOT_MARKS) for n, o, c in QUIZZES],
            question_bank_per_course=[dict(n=i + 1, qtype="truefalse", correct=bool(i % 2 == 0)) for i in range(5)],
        ),
        instructors=INSTRUCTORS,
        rosario_teacher="existing RosarioSIS demo teacher account (staff_id 2) - no new staff created",
        students=students,
    )
    return seed


if __name__ == "__main__":
    seed = build()
    out = BACKEND / "data"
    out.mkdir(exist_ok=True)
    (out / "synthetic_student_demo_seed.json").write_text(json.dumps(seed, indent=1), encoding="utf-8")
    print(f"wrote {out / 'synthetic_student_demo_seed.json'}: {len(seed['students'])} students")
