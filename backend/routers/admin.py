# backend/routers/admin.py
"""Administrator-only system overview (configuration status, never secret values)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

import analytics_engine
import models
from auth import admin_only, role_configured
from config import settings
from database import get_db
from repository import OPEN_STATUSES, latest_snapshot, latest_snapshots
from services.sync_service import sync_in_progress, sync_run_to_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: dict = Depends(admin_only)):
    try:
        db.execute(text("select 1"))
        database = "ok"
    except Exception:
        db.rollback()
        database = "unavailable"
    last = db.query(models.SyncRun).order_by(models.SyncRun.id.desc()).first()
    last_ok = (db.query(models.SyncRun).filter(models.SyncRun.status == "completed")
               .order_by(models.SyncRun.id.desc()).first())
    linked = settings.STUDENT_ID or None
    snaps = latest_snapshots(db)
    risk_counts = {"HIGH": 0, "MODERATE": 0, "LOW": 0}
    for s in snaps:
        risk_counts[s.risk_level] = risk_counts.get(s.risk_level, 0) + 1
    open_q = db.query(models.AnomalyAlert).filter(models.AnomalyAlert.status.in_(OPEN_STATUSES))
    return {
        "viewer": {"name": user.get("name"), "email": user.get("email"), "role": user.get("role")},
        "api": {"status": "ok", "version": "1.0.0"},
        "database": database,
        "sign_in": {
            "student": role_configured("student"),
            "advisor": role_configured("advisor"),
            "admin": role_configured("admin"),
            "student_account_linked_record": linked,
            "student_record_synchronised": bool(linked and latest_snapshot(db, linked)),
        },
        "configuration": {
            "database_configured": bool(settings.DATABASE_URL),
            "jwt_configured": bool(settings.JWT_SECRET),
            "rosario_configured": bool(settings.ROSARIO_API_URL and settings.ROSARIO_API_TOKEN),
            "moodle_configured": bool(settings.MOODLE_API_URL and settings.MOODLE_API_TOKEN),
            "demo_data_enabled": settings.DEMO_DATA_ENABLED,
            "session_hours": settings.JWT_EXPIRE_HOURS,
        },
        "usage": {
            "students_monitored": len(snaps),
            "demo_students": sum(1 for s in snaps if "demo" in (s.sources or [])),
            "risk_counts": risk_counts,
            "open_alerts": open_q.count(),
            "open_high_alerts": open_q.filter(models.AnomalyAlert.severity == "HIGH").count(),
            "interventions": db.query(models.Intervention).count(),
            "sync_runs": db.query(models.SyncRun).count(),
        },
        "sync_running": sync_in_progress(),
        "last_sync": sync_run_to_dict(last) if last else None,
        "last_successful_sync": sync_run_to_dict(last_ok) if last_ok else None,
        "ml": analytics_engine.status(),
    }
