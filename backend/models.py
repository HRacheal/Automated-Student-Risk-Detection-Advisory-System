# backend/models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from database import Base

class Student(Base):
    __tablename__ = "students"
    student_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    declared_major = Column(String)
    class_standing = Column(String)
    completed_units = Column(Integer)
    cumulative_gpa = Column(Float)
    tuition_balance = Column(Float)
    registration_hold = Column(Boolean)
    hold_reason = Column(String)
    advisor_assigned = Column(String)

class LMSActivity(Base):
    __tablename__ = "lms_activity"
    activity_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"))
    lms_login_frequency_per_week = Column(Integer)
    missed_assignments_count = Column(Integer)
    gatekeeper_course_dropped = Column(Boolean)
    gpa_trend = Column(String)
    risk_level = Column(String)

class Course(Base):
    __tablename__ = "courses"
    course_code = Column(String, primary_key=True, index=True)
    course_name = Column(String)
    units = Column(Integer)
    level_standing = Column(String)
    prerequisites = Column(String)

class StudentCourseHistory(Base):
    __tablename__ = "student_course_history"
    history_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"))
    course_code = Column(String, ForeignKey("courses.course_code"))
    semester = Column(String)
    grade = Column(String)
    attempt_number = Column(Integer)

class AdvisingRule(Base):
    __tablename__ = "advising_rules"
    rule_id = Column(Integer, primary_key=True, index=True)
    category = Column(String)
    rule_name = Column(String)
    condition_detail = Column(String)
    action_or_limit = Column(String)