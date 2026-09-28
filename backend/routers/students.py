# backend/routers/students.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from anomaly_engine import RULE_TITLES
from auth import staff_only
from database import get_db
from repository import (
    OPEN_STATUSES,
    SEVERITY_RANK,
    alert_to_dict,
    event_to_dict,
    intervention_to_dict,
    latest_snapshot,
    latest_snapshots,
    open_alert_counts,
    snapshot_summary,
)
from services.sync_service import sync_run_to_dict

router = APIRouter(prefix="/api", tags=["students"], dependencies=[Depends(staff_only)])
RISK_ORDER = {"HIGH": 0, "MODERATE": 1, "LOW": 2}


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    snaps = latest_snapshots(db)
    counts = open_alert_counts(db)
    summaries = [snapshot_summary(s, counts) for s in snaps]
    by_risk = {"HIGH": 0, "MODERATE": 0, "LOW": 0}
    for s in summaries:
        by_risk[s["risk_level"]] = by_risk.get(s["risk_level"], 0) + 1

    active_alerts = db.query(models.AnomalyAlert).filter(models.AnomalyAlert.status.in_(OPEN_STATUSES)).count()
    recent = (db.query(models.AnomalyAlert).order_by(models.AnomalyAlert.detected_at.desc(),
                                                     models.AnomalyAlert.id.desc()).limit(8).all())

    # Requiring intervention: HIGH/MODERATE risk students with an open alert that has
    # no planned/in-progress/completed intervention linked to it yet.
    handled = {i.alert_id for i in db.query(models.Intervention.alert_id).filter(
        models.Intervention.alert_id.isnot(None)).all()}
    open_rows = db.query(models.AnomalyAlert).filter(models.AnomalyAlert.status.in_(OPEN_STATUSES)).all()
    unhandled: dict[str, int] = {}
    for a in open_rows:
        if a.id not in handled and a.severity in ("HIGH", "MODERATE"):
            unhandled[a.student_id] = unhandled.get(a.student_id, 0) + 1
    needing = [dict(s, unaddressed_alerts=unhandled[s["student_id"]]) for s in summaries
               if s["student_id"] in unhandled and s["risk_level"] in ("HIGH", "MODERATE")]
    needing.sort(key=lambda s: (RISK_ORDER.get(s["risk_level"], 3), -s["unaddressed_alerts"]))

    last_run = db.query(models.SyncRun).order_by(models.SyncRun.id.desc()).first()
    by_type: dict[str, int] = {}
    for a in open_rows:
        by_type[a.anomaly_type] = by_type.get(a.anomaly_type, 0) + 1

    return {
        "total_students": len(summaries),
        "risk_counts": by_risk,
        "active_alerts": active_alerts,
        "alerts_by_type": [{"type": k, "title": RULE_TITLES.get(k, k), "count": v}
                           for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])],
        "recent_anomalies": [alert_to_dict(a) for a in recent],
        "students_requiring_intervention": needing[:10],
        "last_sync": sync_run_to_dict(last_run) if last_run else None,
    }


@router.get("/students")
def list_students(
    q: str = Query("", description="Search by name or student ID"),
    risk: Optional[str] = Query(None, description="HIGH | MODERATE | LOW"),
    source: Optional[str] = Query(None, description="rosario | moodle | demo"),
    anomaly_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    counts = open_alert_counts(db)
    rows = [snapshot_summary(s, counts) for s in latest_snapshots(db)]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in (r["full_name"] or "").lower() or needle in r["student_id"].lower()]
    if risk:
        rows = [r for r in rows if r["risk_level"] == risk.upper()]
    if source:
        rows = [r for r in rows if source.lower() in r["sources"]]
    if anomaly_type:
        ids = {a.student_id for a in db.query(models.AnomalyAlert.student_id).filter(
            models.AnomalyAlert.anomaly_type == anomaly_type, models.AnomalyAlert.status.in_(OPEN_STATUSES))}
        rows = [r for r in rows if r["student_id"] in ids]
    rows.sort(key=lambda r: (RISK_ORDER.get(r["risk_level"], 3), -r["open_alerts"], r["full_name"] or ""))
    return {"students": rows, "count": len(rows)}


@router.get("/students/{student_id}")
def student_detail(student_id: str, db: Session = Depends(get_db)):
    snap = latest_snapshot(db, student_id)
    if not snap:
        raise HTTPException(404, f"Student {student_id} has not been synchronised.")
    alerts = (db.query(models.AnomalyAlert).filter(models.AnomalyAlert.student_id == student_id)
              .order_by(models.AnomalyAlert.detected_at.desc()).all())
    alerts.sort(key=lambda a: (a.status not in OPEN_STATUSES, -SEVERITY_RANK.get(a.severity, 0)))
    events = (db.query(models.AlertEvent).filter(models.AlertEvent.student_id == student_id)
              .order_by(models.AlertEvent.created_at.desc(), models.AlertEvent.id.desc()).limit(100).all())
    interventions = (db.query(models.Intervention).filter(models.Intervention.student_id == student_id)
                     .order_by(models.Intervention.created_at.desc()).all())
    history = (db.query(models.StudentSnapshot.created_at, models.StudentSnapshot.risk_level,
                        models.StudentSnapshot.sync_run_id)
               .filter(models.StudentSnapshot.student_id == student_id)
               .order_by(models.StudentSnapshot.id.desc()).limit(30).all())
    return {
        "student": snap.data,
        "risk_level": snap.risk_level,
        "sources": snap.sources,
        "last_synced_at": snap.created_at,
        "sync_run_id": snap.sync_run_id,
        "rules_evaluated": [{"rule": r, "title": RULE_TITLES.get(r, r)} for r in (snap.rules_evaluated or [])],
        "rules_skipped": [{"rule": r, "title": RULE_TITLES.get(r, r), "reason": why}
                          for r, why in (snap.rules_skipped or {}).items()],
        "ml_prediction": snap.ml_prediction,
        "alerts": [alert_to_dict(a) for a in alerts],
        "events": [event_to_dict(e) for e in events],
        "interventions": [intervention_to_dict(i) for i in interventions],
        "risk_history": [{"synced_at": h.created_at, "risk_level": h.risk_level, "sync_run_id": h.sync_run_id}
                         for h in reversed(history)],
    }
