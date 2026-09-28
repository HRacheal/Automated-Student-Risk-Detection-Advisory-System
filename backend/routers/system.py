# backend/routers/system.py
"""Sync, integration status, Test Lab, ML status, rules catalogue and chatbot."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

import analytics_engine
import models
from advising_config import GATEKEEPER_COURSES, MAJOR_PROGRAMS, THRESHOLDS
from anomaly_engine import RULE_TITLES
from auth import admin_only, staff_only
from config import settings
from database import get_db
from schemas import ChatRequest, ChatResponse, ScenarioToggle
from services import chatbot
from services.demo_source import BASELINE_BUILDERS, SCENARIOS
from services.moodle_service import check_moodle
from services.rosario_service import check_rosario
from services.sync_service import SyncInProgress, run_sync, sync_in_progress, sync_run_to_dict

router = APIRouter(prefix="/api", tags=["system"])
log = logging.getLogger("mycoach")


# ---- Sync ------------------------------------------------------------------
@router.post("/sync")
def trigger_sync(db: Session = Depends(get_db), user: dict = Depends(staff_only)):
    try:
        return run_sync(db, triggered_by=user["email"])
    except SyncInProgress as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        # run_sync has already recorded the run as failed. Return a JSON error (an unhandled 500
        # has no CORS headers, so the browser would misreport it as "cannot reach the API").
        log.exception("Synchronisation failed")
        raise HTTPException(500, f"Synchronisation failed: {exc.__class__.__name__}: {exc}")


@router.get("/sync/runs")
def sync_runs(limit: int = 20, db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    runs = db.query(models.SyncRun).order_by(models.SyncRun.id.desc()).limit(min(limit, 100)).all()
    return {"runs": [sync_run_to_dict(r) for r in runs]}


@router.get("/sync/status")
def sync_status(db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    """Latest run, latest fully successful run, and whether a sync is running right now."""
    last = db.query(models.SyncRun).order_by(models.SyncRun.id.desc()).first()
    last_ok = (db.query(models.SyncRun).filter(models.SyncRun.status == "completed")
               .order_by(models.SyncRun.id.desc()).first())
    return {"running": sync_in_progress(),
            "last": sync_run_to_dict(last) if last else None,
            "last_successful": sync_run_to_dict(last_ok) if last_ok else None}


@router.get("/integrations/status")
async def integrations_status(_: dict = Depends(staff_only)):
    rosario = await run_in_threadpool(check_rosario)
    moodle = await run_in_threadpool(check_moodle)
    return {
        "rosario": rosario,
        "moodle": moodle,
        "demo": {"status": "ok" if settings.DEMO_DATA_ENABLED else "disabled",
                 "message": "Controlled local test data (Test Lab)" if settings.DEMO_DATA_ENABLED
                 else "DEMO_DATA_ENABLED=false"},
    }


# ---- Test Lab ----------------------------------------------------------------
@router.get("/test-lab")
def test_lab(db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    rows = db.query(models.TestScenario).filter(models.TestScenario.enabled.is_(True)).all()
    active: dict[str, list[str]] = {}
    for r in rows:
        active.setdefault(r.student_id, []).append(r.scenario_key)
    students = [{"student_id": s.student_id, "full_name": s.full_name, "declared_major": s.declared_major}
                for s in (b() for b in BASELINE_BUILDERS)]
    return {
        "enabled": settings.DEMO_DATA_ENABLED,
        "students": students,
        "scenarios": [{"key": k, "label": v["label"], "expected_anomaly": v["expected"],
                       "expected_title": RULE_TITLES.get(v["expected"], v["expected"])} for k, v in SCENARIOS.items()],
        "active": active,
    }


@router.put("/test-lab/scenarios")
def toggle_scenario(body: ScenarioToggle, db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    if body.scenario_key not in SCENARIOS:
        raise HTTPException(400, "Unknown scenario")
    if not body.student_id.startswith("DEMO-"):
        raise HTTPException(400, "Scenarios can only be applied to DEMO students (external data is never modified).")
    row = db.query(models.TestScenario).filter_by(student_id=body.student_id, scenario_key=body.scenario_key).first()
    if row:
        row.enabled = body.enabled
    else:
        db.add(models.TestScenario(student_id=body.student_id, scenario_key=body.scenario_key, enabled=body.enabled))
    db.commit()
    return {"ok": True}


@router.post("/test-lab/reset")
def reset_scenarios(db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    db.query(models.TestScenario).update({models.TestScenario.enabled: False})
    db.commit()
    return {"ok": True}


# ---- Rules / ML -----------------------------------------------------------
@router.get("/rules")
def rules(_: dict = Depends(staff_only)):
    return {"rules": [{"key": k, "title": v} for k, v in RULE_TITLES.items()],
            "thresholds": THRESHOLDS,
            "gatekeeper_courses": sorted(GATEKEEPER_COURSES),
            "major_programs": {k: sorted(v) for k, v in MAJOR_PROGRAMS.items()},
            "risk_level_policy": "HIGH if any HIGH anomaly or 3+ MODERATE; MODERATE if any MODERATE; else LOW."}


@router.get("/ml/status")
def ml_status(_: dict = Depends(staff_only)):
    return analytics_engine.status()


@router.post("/ml/train")
def ml_train(db: Session = Depends(get_db), _: dict = Depends(admin_only)):
    return analytics_engine.train_risk_classifier(db)


# ---- Advising chatbot -----------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
def advisory_chatbot(req: ChatRequest, db: Session = Depends(get_db), _: dict = Depends(staff_only)):
    return chatbot.answer(db, req.message, req.student_id)
