# backend/main.py
"""
My Coach — Automated Student Risk Detection & Advisory System (FastAPI).

RosarioSIS (academic) + Moodle (LMS)  ->  sync & normalise  ->  rule-based anomaly
detection  ->  PostgreSQL (alerts, history, interventions)  ->  Next.js dashboard.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000
"""
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import missing_required_settings, settings

_missing = missing_required_settings()
if _missing:
    # On Render there is no backend/.env: these must be set in the service's Environment tab,
    # otherwise the deploy fails and Render keeps serving the previous (older) build.
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}. "
                       f"Set them in backend/.env locally, or in the Render service's Environment "
                       f"settings in production (see backend/.env.example)")

import models  # noqa: E402
from database import engine  # noqa: E402
from routers import admin, alerts, model_performance, session, student_portal, students, system  # noqa: E402

log = logging.getLogger("mycoach")

# Creates only the application tables that do not exist yet (sync_runs,
# student_snapshots, anomaly_alerts, alert_events, interventions, test_scenarios).
# Existing tables are never altered or dropped.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="My Coach - Student Risk Detection & Advisory API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

def _warm_up_ml():
    """Train the optional experimental ML model in the background so it never delays a request."""
    from analytics_engine import ensure_model
    from database import SessionLocal

    db = SessionLocal()
    try:
        ensure_model(db)
    finally:
        db.close()


threading.Thread(target=_warm_up_ml, daemon=True, name="ml-warmup").start()

app.include_router(session.router)
app.include_router(students.router)
app.include_router(alerts.router)
app.include_router(system.router)
app.include_router(student_portal.router)
app.include_router(admin.router)
app.include_router(model_performance.router)


@app.get("/", tags=["system"], include_in_schema=False)
def root():
    """Landing response for the hosting platform's health check and for anyone opening the API URL."""
    return {"service": "My Coach API", "health": "/api/health", "docs": "/docs"}


@app.get("/api/health", tags=["system"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        db_status = "ok"
    except Exception as exc:
        log.warning("Database health check failed: %s", exc.__class__.__name__)
        db_status = "unavailable"
    return {"status": "ok", "database": db_status, "demo_data_enabled": settings.DEMO_DATA_ENABLED}
