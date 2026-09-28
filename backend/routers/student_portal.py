# backend/routers/student_portal.py
"""Student self-service: a signed-in student can only ever read THEIR OWN record."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import student_only
from database import get_db
from repository import latest_snapshot, open_alerts
from schemas import ChatResponse, StudentChatRequest
from services import chatbot

router = APIRouter(prefix="/api/student", tags=["student"])


def _own_snapshot(db: Session, user: dict):
    # The student id comes from the signed token, never from the request.
    sid = user.get("student_id")
    if not sid:
        raise HTTPException(409, "This student account is not linked to a student record yet.")
    snap = latest_snapshot(db, str(sid))
    if not snap:
        raise HTTPException(404, "Your academic record has not been synchronised yet.")
    return snap


@router.get("/me")
def my_record(db: Session = Depends(get_db), user: dict = Depends(student_only)):
    snap = _own_snapshot(db, user)
    return {
        "student": snap.data,
        "risk_level": snap.risk_level,
        "last_synced_at": snap.created_at,
        # Student-facing view of the indicators: what was found, why, and what to do next.
        "indicators": [{"title": a.title, "severity": a.severity, "description": a.description,
                        "evidence": a.evidence or [], "recommended_action": a.recommended_intervention,
                        "detected_at": a.detected_at} for a in open_alerts(db, snap.student_id)],
    }


@router.post("/chat", response_model=ChatResponse)
def my_chat(req: StudentChatRequest, db: Session = Depends(get_db), user: dict = Depends(student_only)):
    snap = _own_snapshot(db, user)
    # Always scoped to the student's own record: the id comes from the JWT, and the
    # "student" audience ignores any other student id / name mentioned in the message.
    return chatbot.answer(db, req.message, snap.student_id, audience="student")
