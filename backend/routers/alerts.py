# backend/routers/alerts.py
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from anomaly_engine import RULE_TITLES
from auth import staff_only
from database import get_db
from repository import SEVERITY_RANK, alert_to_dict, event_to_dict, intervention_to_dict
from schemas import AlertUpdate, InterventionCreate, InterventionUpdate

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    status: Optional[str] = Query(None, description="open | active | acknowledged | resolved | auto_resolved | all"),
    severity: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    student_id: Optional[str] = None,
    q: str = "",
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _: dict = Depends(staff_only),
):
    query = db.query(models.AnomalyAlert)
    if status in (None, "open"):
        query = query.filter(models.AnomalyAlert.status.in_(("active", "acknowledged")))
    elif status != "all":
        query = query.filter(models.AnomalyAlert.status == status)
    if severity:
        query = query.filter(models.AnomalyAlert.severity == severity.upper())
    if anomaly_type:
        query = query.filter(models.AnomalyAlert.anomaly_type == anomaly_type)
    if student_id:
        query = query.filter(models.AnomalyAlert.student_id == student_id)
    rows = query.order_by(models.AnomalyAlert.detected_at.desc(), models.AnomalyAlert.id.desc()).limit(limit).all()
    if q:
        needle = q.lower()
        rows = [a for a in rows if needle in (a.student_name or "").lower() or needle in a.student_id.lower()
                or needle in (a.title or "").lower()]
    rows.sort(key=lambda a: -SEVERITY_RANK.get(a.severity, 0))
    return {"alerts": [alert_to_dict(a) for a in rows], "count": len(rows),
            "types": [{"type": k, "title": v} for k, v in RULE_TITLES.items()]}


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: int, body: AlertUpdate, db: Session = Depends(get_db),
                 user: dict = Depends(staff_only)):
    alert = db.get(models.AnomalyAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    previous = alert.status
    alert.status = body.status
    alert.resolved_at = datetime.now(timezone.utc) if body.status == "resolved" else None
    event_type = {"acknowledged": "acknowledged", "resolved": "resolved", "active": "reopened"}[body.status]
    db.add(models.AlertEvent(alert_id=alert.id, student_id=alert.student_id, event_type=event_type,
                             actor=user["email"], detail=body.note or f"{previous} -> {body.status}"))
    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert)


@router.get("/alerts/{alert_id}/events")
def alert_events(alert_id: int, db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    events = (db.query(models.AlertEvent).filter(models.AlertEvent.alert_id == alert_id)
              .order_by(models.AlertEvent.created_at.desc()).all())
    return {"events": [event_to_dict(e) for e in events]}


@router.get("/interventions")
def list_interventions(student_id: Optional[str] = None, status: Optional[str] = None,
                       db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    query = db.query(models.Intervention)
    if student_id:
        query = query.filter(models.Intervention.student_id == student_id)
    if status:
        query = query.filter(models.Intervention.status == status)
    rows = query.order_by(models.Intervention.created_at.desc()).limit(500).all()
    names = {}
    if rows:
        for a in db.query(models.AnomalyAlert.student_id, models.AnomalyAlert.student_name).filter(
                models.AnomalyAlert.student_id.in_({r.student_id for r in rows})).distinct():
            names[a.student_id] = a.student_name
    return {"interventions": [dict(intervention_to_dict(r), student_name=names.get(r.student_id)) for r in rows]}


@router.post("/interventions")
def create_intervention(body: InterventionCreate, db: Session = Depends(get_db),
                        user: dict = Depends(staff_only)):
    if body.alert_id is not None:
        alert = db.get(models.AnomalyAlert, body.alert_id)
        if not alert or alert.student_id != body.student_id:
            raise HTTPException(400, "alert_id does not belong to this student")
    item = models.Intervention(student_id=body.student_id, alert_id=body.alert_id, action_type=body.action_type,
                               notes=body.notes, status=body.status, follow_up_date=body.follow_up_date,
                               advisor=user["name"] or user["email"])
    db.add(item)
    db.flush()
    if body.alert_id is not None:
        db.add(models.AlertEvent(alert_id=body.alert_id, student_id=body.student_id, event_type="intervention",
                                 actor=user["email"], detail=f"{body.action_type} ({body.status})"))
    db.commit()
    db.refresh(item)
    return intervention_to_dict(item)


@router.patch("/interventions/{intervention_id}")
def update_intervention(intervention_id: int, body: InterventionUpdate, db: Session = Depends(get_db),
                        user: dict = Depends(staff_only)):
    item = db.get(models.Intervention, intervention_id)
    if not item:
        raise HTTPException(404, "Intervention not found")
    for field in ("status", "notes", "follow_up_date"):
        value = getattr(body, field)
        if value is not None:
            setattr(item, field, value)
    if item.alert_id is not None and body.status:
        db.add(models.AlertEvent(alert_id=item.alert_id, student_id=item.student_id, event_type="intervention",
                                 actor=user["email"], detail=f"{item.action_type} -> {body.status}"))
    db.commit()
    db.refresh(item)
    return intervention_to_dict(item)
