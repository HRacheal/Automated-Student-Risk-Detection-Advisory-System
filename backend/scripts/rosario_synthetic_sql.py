"""
Generates RosarioSIS SQL for the synthetic dataset from
backend/data/synthetic_student_demo_seed.json (the single source of truth).

The script only WRITES SQL FILES; it never connects to a database and contains
no credentials. Execute the files with the XAMPP mysql client against
port 3306 / rosariosdb (each file starts with a guard that aborts otherwise).

  python scripts/rosario_synthetic_sql.py field    OUT.sql   # 'Major' custom field (DDL, mirrors AddDBField)
  python scripts/rosario_synthetic_sql.py data     OUT.sql   # all data, one transaction
  python scripts/rosario_synthetic_sql.py rollback OUT.sql   # delete ONLY synthetic rows (ID-scoped)

ID ranges (all synthetic, reserved): students 690001-690030, course_subjects 6901-6904,
courses 690101-690133, course_periods 690201-690218, history marking periods 6901-6909,
custom field 200000012 ('Major').
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SEED = json.loads((BACKEND / "data" / "synthetic_student_demo_seed.json").read_text(encoding="utf-8"))

MAJOR_FIELD_ID = 200000012
SCHOOL_ID, SYEAR = 1, 2026
SEMESTER_1_MP_ID = 2       # existing RosarioSIS 'Semester 1' (short name S1), unchanged
TEACHER_ID = 2             # existing RosarioSIS demo teacher 'Teach Teacher'
TEACHER_NAME = "Teach Teacher"
ENROLLMENT_CODE_EBY = 3    # existing 'Beginning of Year' (Add) code
CALENDAR_ID = 1
GRADE_SCALE_ID = 1
GRADE_IDS = {"A+": 1, "A": 2, "A-": 3, "B+": 4, "B": 5, "B-": 6, "C+": 7, "C": 8, "C-": 9, "D+": 10,
             "D": 11, "D-": 12, "F": 13, "I": 14}   # existing 'Main' scale; no W grade added
SUBJECTS = {"General Education": 6901, "Mathematics": 6902, "Computing": 6903, "Business": 6904}
COURSE_ID = {c["code"]: 690101 + i for i, c in enumerate(SEED["courses"])}
CP_ID = {s["code"]: 690201 + i for i, s in enumerate(SEED["sections"])}
MP_ID = {t["key"]: t["rosario_history_marking_period_id"] for t in SEED["terms"]}
TERM_SYEAR = {t["key"]: t["syear"] for t in SEED["terms"]}
STUDENT_IDS = [s["student_id"] for s in SEED["students"]]

NL = chr(10)
GUARD = NL.join([
    '-- Abort unless connected to the RosarioSIS database on port 3306 (never Moodle MariaDB on 3307)',
    'DELIMITER //',
    'BEGIN NOT ATOMIC',
    "  IF @@port <> 3306 OR DATABASE() <> 'rosariosdb' THEN",
    "    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WRONG TARGET: expected rosariosdb on port 3306';",
    '  END IF;',
    'END //',
    'DELIMITER ;',
]) + NL


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "'Y'" if v else "'N'"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def insert(table, rows):
    if not rows:
        return ""
    cols = list(rows[0])
    values = ",\n".join("(" + ", ".join(q(r[c]) for c in cols) + ")" for r in rows)
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};\n"


def field_sql():
    options = "\n".join(SEED["majors"])
    return GUARD + (
        f"-- 'Major' student field, exactly as RosarioSIS AddDBField() creates a select field\n"
        f"INSERT INTO custom_fields (id, type, title, sort_order, select_options, category_id, required, default_selection)\n"
        f"VALUES ({MAJOR_FIELD_ID}, 'select', 'Major', 12, {q(options)}, 1, NULL, NULL);\n"
        f"ALTER TABLE students ADD custom_{MAJOR_FIELD_ID} TEXT COMMENT 'Major';\n"
        f"CREATE INDEX custom_ind{MAJOR_FIELD_ID} ON students (custom_{MAJOR_FIELD_ID}(255));\n"
    )


def data_sql():
    out = [GUARD, "SET autocommit = 0;\nSTART TRANSACTION;\n"]
    out.append(insert("history_marking_periods", [dict(
        marking_period_id=t["rosario_history_marking_period_id"], parent_id=None, mp_type="semester",
        name=t["name"], short_name=t["key"], post_end_date=t["end_date"], school_id=SCHOOL_ID, syear=t["syear"])
        for t in SEED["terms"]]))
    out.append(insert("course_subjects", [dict(subject_id=sid, syear=SYEAR, school_id=SCHOOL_ID, title=title,
                                               short_name=title[:25], sort_order=i + 1)
                                          for i, (title, sid) in enumerate(SUBJECTS.items())]))
    out.append(insert("courses", [dict(course_id=COURSE_ID[c["code"]], syear=SYEAR, subject_id=SUBJECTS[c["subject"]],
                                       school_id=SCHOOL_ID, grade_level=None, title=c["title"], short_name=c["code"],
                                       credit_hours=c["credits"], description=None) for c in SEED["courses"]]))
    active_count = {}
    for s in SEED["students"]:
        for r in s["rosario"]["current_registrations"]:
            if not r["end_date"]:
                active_count[r["code"]] = active_count.get(r["code"], 0) + 1
    out.append(insert("course_periods", [dict(
        course_period_id=CP_ID[sec["code"]], syear=SYEAR, school_id=SCHOOL_ID, course_id=COURSE_ID[sec["code"]],
        title=f"S1 - {sec['section']} - {TEACHER_NAME}", short_name=sec["section"], mp="SEM",
        marking_period_id=SEMESTER_1_MP_ID, teacher_id=TEACHER_ID, total_seats=40,
        filled_seats=active_count.get(sec["code"], 0), does_honor_roll="Y", does_class_rank="Y",
        gender_restriction="N", parent_id=CP_ID[sec["code"]], calendar_id=CALENDAR_ID,
        grade_scale_id=GRADE_SCALE_ID, credits=sec["credits"]) for sec in SEED["sections"]]))
    out.append(insert("students", [dict(student_id=s["student_id"], last_name=s["last_name"],
                                        first_name=s["first_name"], middle_name=None, username=s["rosario"]["username"],
                                        password=None, **{f"custom_{MAJOR_FIELD_ID}": s["major"]})
                                   for s in SEED["students"]]))
    out.append(insert("student_enrollment", [dict(
        syear=SYEAR, school_id=SCHOOL_ID, student_id=s["student_id"], grade_id=None,
        start_date=s["rosario"]["enrollment"]["start_date"], end_date=None, enrollment_code=ENROLLMENT_CODE_EBY,
        drop_code=None, next_school=SCHOOL_ID, calendar_id=CALENDAR_ID, last_school=None) for s in SEED["students"]]))
    grades = []
    for s in SEED["students"]:
        for h in s["rosario"]["history"]:
            pts = h["grade_points"]
            grades.append(dict(
                syear=TERM_SYEAR[h["term"]], school_id=SCHOOL_ID, student_id=s["student_id"], course_period_id=None,
                report_card_grade_id=GRADE_IDS.get(h["grade_letter"]), grade_percent=h["grade_percent"],
                marking_period_id=MP_ID[h["term"]], grade_letter=h["grade_letter"], weighted_gp=pts,
                unweighted_gp=pts, gp_scale=4 if pts is not None else None,
                credit_attempted=h["credits_attempted"], credit_earned=h["credits_earned"],
                course_title=h["course_title"], credit_hours=h["credits_attempted"] or 3))
    out.append(insert("student_report_card_grades", grades))
    out.append(insert("schedule", [dict(
        syear=SYEAR, school_id=SCHOOL_ID, student_id=s["student_id"], start_date=r["start_date"], end_date=r["end_date"],
        course_id=COURSE_ID[r["code"]], course_period_id=CP_ID[r["code"]], mp="SEM", marking_period_id=SEMESTER_1_MP_ID)
        for s in SEED["students"] for r in s["rosario"]["current_registrations"]]))
    out.append(insert("billing_fees", [dict(
        student_id=s["student_id"], assigned_date=f["assigned"], due_date=f["due"], comments="Synthetic demo data",
        title=f["title"], amount=f["amount"], school_id=SCHOOL_ID, syear=SYEAR, created_by="Synthetic seed")
        for s in SEED["students"] for f in s["rosario"]["finance"]["fees"]]))
    out.append(insert("billing_payments", [dict(
        syear=SYEAR, school_id=SCHOOL_ID, student_id=s["student_id"], amount=p["amount"], payment_date=p["date"],
        comments=p["comment"], created_by="Synthetic seed")
        for s in SEED["students"] for p in s["rosario"]["finance"]["payments"]]))
    out.append("COMMIT;\n")
    return "".join(out)


def rollback_sql():
    ids = ", ".join(map(str, STUDENT_IDS))
    return GUARD + "START TRANSACTION;\n" + "".join(
        f"DELETE FROM {t} WHERE student_id IN ({ids});\n"
        for t in ("billing_payments", "billing_fees", "schedule", "student_report_card_grades", "student_enrollment")) + (
        f"DELETE FROM students WHERE student_id IN ({ids});\n"
        f"DELETE FROM course_periods WHERE course_period_id BETWEEN 690201 AND 690218;\n"
        f"DELETE FROM courses WHERE course_id BETWEEN 690101 AND 690133;\n"
        f"DELETE FROM course_subjects WHERE subject_id BETWEEN 6901 AND 6904;\n"
        f"DELETE FROM history_marking_periods WHERE marking_period_id BETWEEN 6901 AND 6909;\n"
        "COMMIT;\n"
        f"-- Optional, removes the 'Major' field too:\n"
        f"-- ALTER TABLE students DROP COLUMN custom_{MAJOR_FIELD_ID};\n"
        f"-- DELETE FROM custom_fields WHERE id = {MAJOR_FIELD_ID};\n")


if __name__ == "__main__":
    mode, out = sys.argv[1], Path(sys.argv[2])
    sql = {"field": field_sql, "data": data_sql, "rollback": rollback_sql}[mode]()
    out.write_text(sql, encoding="utf-8")
    print(f"{mode}: wrote {out} ({sql.count(chr(10))} lines)")
