# backend/schemas.py
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str
    # Sign-in option chosen in the UI. Only a hint: the backend grants a role
    # solely when that role's configured credentials match.
    role: Optional[Literal["student", "advisor", "admin"]] = None


class AlertUpdate(BaseModel):
    status: Literal["active", "acknowledged", "resolved"]
    note: Optional[str] = None


class InterventionCreate(BaseModel):
    student_id: str
    alert_id: Optional[int] = None
    action_type: str = Field(min_length=2, max_length=120)
    notes: Optional[str] = None
    status: Literal["planned", "in_progress", "completed"] = "planned"
    follow_up_date: Optional[str] = None


class InterventionUpdate(BaseModel):
    status: Optional[Literal["planned", "in_progress", "completed"]] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None


class ScenarioToggle(BaseModel):
    student_id: str
    scenario_key: str
    enabled: bool


class ChatRequest(BaseModel):
    student_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=1000)


class StudentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    response: str
    student_id: Optional[str] = None
    intent: Optional[str] = None
