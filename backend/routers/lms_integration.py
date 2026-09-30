# backend/routers/lms_integration.py
"""
Server-to-server endpoint for the My Coach LMS app (moodle-lms/).

The LMS shows a small "My Coach" card (risk level + open indicators) and links to the
student portal. It never computes risk itself. The LMS backend calls this endpoint with the
shared LMS_INTEGRATION_KEY and the student ID of ITS signed-in student; browsers cannot use
it (no key), and it is switched off when LMS_INTEGRATION_KEY is not set.
"""
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from repository import latest_snapshot, open_alerts

router = APIRouter(prefix="/api/integration/lms", tags=["lms-integration"])


def require_integration_key(x_integration_key: str | None = Header(default=None)) -> None:
    if not settings.LMS_INTEGRATION_KEY:
        raise HTTPException(503, "LMS integration is not configured.")
    if not x_integration_key or not hmac.compare_digest(x_integration_key.encode(),
                                                        settings.LMS_INTEGRATION_KEY.encode()):
        raise HTTPException(401, "Invalid integration key.")


@router.get("/students/{student_id}/summary", dependencies=[Depends(require_integration_key)])
def student_summary(student_id: str, db: Session = Depends(get_db)):
    snap = latest_snapshot(db, student_id)
    if not snap:
        raise HTTPException(404, "Student not synchronised yet.")
    indicators = open_alerts(db, snap.student_id)
    data = snap.data or {}
    return {
        "student_id": snap.student_id,
        "full_name": snap.full_name,
        "risk_level": snap.risk_level,
        "last_synced_at": snap.created_at,
        "declared_major": data.get("declared_major"),
        "open_indicators": len(indicators),
        # Titles only (the same student-facing titles the student sees in their own portal)
        "indicators": [{"title": a.title, "severity": a.severity} for a in indicators[:5]],
    }
