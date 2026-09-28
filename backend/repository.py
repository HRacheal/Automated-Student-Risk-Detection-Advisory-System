# backend/repository.py
"""Read helpers shared by the API routers and the chatbot."""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models

OPEN_STATUSES = ("active", "acknowledged")
SEVERITY_RANK = {"HIGH": 3, "MODERATE": 2, "LOW": 1}


def latest_snapshots(db: Session) -> list[models.StudentSnapshot]:
    latest_ids = db.query(func.max(models.StudentSnapshot.id)).group_by(models.StudentSnapshot.student_id)
    return db.query(models.StudentSnapshot).filter(models.StudentSnapshot.id.in_(latest_ids)).all()


def latest_snapshot(db: Session, student_id: str) -> Optional[models.StudentSnapshot]:
    return (db.query(models.StudentSnapshot)
            .filter(models.StudentSnapshot.student_id == student_id)
            .order_by(models.StudentSnapshot.id.desc()).first())


def open_alerts(db: Session, student_id: Optional[str] = None) -> list[models.AnomalyAlert]:
    q = db.query(models.AnomalyAlert).filter(models.AnomalyAlert.status.in_(OPEN_STATUSES))
    if student_id:
        q = q.filter(models.AnomalyAlert.student_id == student_id)
    alerts = q.order_by(models.AnomalyAlert.detected_at.desc()).all()
    alerts.sort(key=lambda a: -SEVERITY_RANK.get(a.severity, 0))  # stable: HIGH first, newest first
    return alerts


def alert_to_dict(a: models.AnomalyAlert) -> dict:
    return {
        "id": a.id,
        "student_id": a.student_id,
        "student_name": a.student_name,
        "anomaly_type": a.anomaly_type,
        "title": a.title,
        "severity": a.severity,
        "description": a.description,
        "evidence": a.evidence or [],
        "recommended_intervention": a.recommended_intervention,
        "status": a.status,
        "source": a.source,
        "data_sources": a.data_sources or [],
        "detected_at": a.detected_at,
        "last_seen_at": a.last_seen_at,
        "resolved_at": a.resolved_at,
    }


def event_to_dict(e: models.AlertEvent) -> dict:
    return {"id": e.id, "alert_id": e.alert_id, "student_id": e.student_id, "event_type": e.event_type,
            "detail": e.detail, "actor": e.actor, "created_at": e.created_at}


def intervention_to_dict(i: models.Intervention) -> dict:
    return {"id": i.id, "student_id": i.student_id, "alert_id": i.alert_id, "action_type": i.action_type,
            "notes": i.notes, "status": i.status, "follow_up_date": i.follow_up_date, "advisor": i.advisor,
            "created_at": i.created_at, "updated_at": i.updated_at}


def snapshot_summary(s: models.StudentSnapshot, alert_counts: dict[str, dict[str, int]]) -> dict:
    d = s.data or {}
    counts = alert_counts.get(s.student_id, {})
    active_courses = [c for c in d.get("current_courses", []) if c.get("status") == "enrolled"]
    return {
        "student_id": s.student_id,
        "full_name": s.full_name,
        "sources": s.sources or [],
        "is_demo": d.get("is_demo", False),
        "declared_major": d.get("declared_major"),
        "major_field_available": d.get("major_field_available", False),
        "class_standing": d.get("class_standing"),
        "cumulative_gpa": d.get("cumulative_gpa"),
        "completed_units": d.get("completed_units"),
        "current_course_count": len(active_courses),
        "risk_level": s.risk_level,
        "open_alerts": sum(counts.values()),
        "open_alerts_by_severity": counts,
        "last_synced_at": s.created_at,
        "ml_prediction": s.ml_prediction,
    }


def open_alert_counts(db: Session) -> dict[str, dict[str, int]]:
    rows = (db.query(models.AnomalyAlert.student_id, models.AnomalyAlert.severity, func.count())
            .filter(models.AnomalyAlert.status.in_(OPEN_STATUSES))
            .group_by(models.AnomalyAlert.student_id, models.AnomalyAlert.severity).all())
    out: dict[str, dict[str, int]] = {}
    for sid, sev, n in rows:
        out.setdefault(sid, {})[sev] = n
    return out
