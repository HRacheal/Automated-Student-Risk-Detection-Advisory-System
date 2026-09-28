# backend/models.py
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


# =====================================================================
# REFERENCE DATA (pre-existing tables, read-only for the app)
# =====================================================================
class Course(Base):
    """Course catalogue: codes, units, level and prerequisites used by the rules."""
    __tablename__ = "courses"
    course_code = Column(String, primary_key=True, index=True)
    course_name = Column(String)
    units = Column(Integer)
    level_standing = Column(String)
    prerequisites = Column(String)


class AdvisingRule(Base):
    """Institutional advising policies (standing thresholds, repeat policy, ...)."""
    __tablename__ = "advising_rules"
    rule_id = Column(Integer, primary_key=True, index=True)
    category = Column(String)
    rule_name = Column(String)
    condition_detail = Column(String)
    action_or_limit = Column(String)


# =====================================================================
# LEGACY DATASET (pre-existing tables). No longer a source of student
# information — RosarioSIS and Moodle are. Kept untouched because the
# experimental ML model (analytics_engine.py) is trained on these labels.
# =====================================================================
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


class StudentCourseHistory(Base):
    __tablename__ = "student_course_history"
    history_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.student_id"))
    course_code = Column(String, ForeignKey("courses.course_code"))
    semester = Column(String)
    grade = Column(String)
    attempt_number = Column(Integer)


# =====================================================================
# APPLICATION DATA (created by this app)
# =====================================================================
class SyncRun(Base):
    """One execution of "Sync Data": what was pulled from each source and what was found."""
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = Column(DateTime(timezone=True))
    status = Column(String, default="running", nullable=False)  # running|completed|partial|failed
    triggered_by = Column(String)
    # {"rosario": {"status": "ok", "students": 3, "message": "..."}, "moodle": {...}, "demo": {...}}
    source_status = Column(JSON, default=dict)
    students_analyzed = Column(Integer, default=0)
    anomalies_detected = Column(Integer, default=0)
    new_alerts = Column(Integer, default=0)
    resolved_alerts = Column(Integer, default=0)
    error = Column(Text)


class StudentSnapshot(Base):
    """
    Normalised view of one student as of one sync. This is a cache of what
    RosarioSIS/Moodle returned (needed so the dashboard does not call the
    external systems on every page view, and so each alert's evidence can be
    traced back to the data it was computed from). Only the latest snapshot
    per student is shown; older ones form the GPA / risk history.
    """
    __tablename__ = "student_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id"), index=True)
    student_id = Column(String, index=True, nullable=False)
    full_name = Column(String)
    sources = Column(JSON, default=list)  # e.g. ["rosario", "moodle"] or ["demo"]
    risk_level = Column(String)  # LOW | MODERATE | HIGH
    data = Column(JSON, nullable=False)  # normalised StudentRecord
    rules_evaluated = Column(JSON, default=list)
    rules_skipped = Column(JSON, default=dict)  # {rule: reason data unavailable}
    ml_prediction = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnomalyAlert(Base):
    """A rule-based anomaly detected for a student. One row per episode."""
    __tablename__ = "anomaly_alerts"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, index=True, nullable=False)
    student_name = Column(String)
    anomaly_type = Column(String, index=True, nullable=False)
    severity = Column(String, nullable=False)  # LOW | MODERATE | HIGH
    title = Column(String)
    description = Column(Text, nullable=False)
    evidence = Column(JSON, default=list)
    recommended_intervention = Column(Text)
    # active -> acknowledged -> resolved ; auto_resolved when the condition disappears
    status = Column(String, default="active", index=True, nullable=False)
    source = Column(String, default="rule")
    data_sources = Column(JSON, default=list)
    detected_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    first_sync_run_id = Column(Integer, ForeignKey("sync_runs.id"))
    last_sync_run_id = Column(Integer, ForeignKey("sync_runs.id"))


class AlertEvent(Base):
    """Audit trail for alerts: detected, severity changed, acknowledged, resolved, reopened..."""
    __tablename__ = "alert_events"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("anomaly_alerts.id"), index=True, nullable=False)
    student_id = Column(String, index=True)
    event_type = Column(String, nullable=False)
    detail = Column(Text)
    actor = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Intervention(Base):
    """An advisor action taken for a student (optionally linked to an alert)."""
    __tablename__ = "interventions"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, index=True, nullable=False)
    alert_id = Column(Integer, ForeignKey("anomaly_alerts.id"), nullable=True)
    action_type = Column(String, nullable=False)
    notes = Column(Text)
    status = Column(String, default="planned", nullable=False)  # planned | in_progress | completed
    follow_up_date = Column(String)
    advisor = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TestScenario(Base):
    """Test Lab switches that inject a risk condition into a DEMO student's local data."""
    __tablename__ = "test_scenarios"
    __table_args__ = (UniqueConstraint("student_id", "scenario_key", name="uq_test_scenario"),)
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, nullable=False)
    scenario_key = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
