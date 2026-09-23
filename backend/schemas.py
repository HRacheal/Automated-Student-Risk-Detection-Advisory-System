from pydantic import BaseModel
from typing import List, Optional

class StudentResponse(BaseModel):
    student_id: int
    full_name: str
    declared_major: str
    class_standing: str
    cumulative_gpa: float
    gpa_trend_slope: float
    
    # Flags from distinct engines
    rule_alerts: List[str]
    is_anomaly: bool
    isolation_forest_score: float
    xgboost_risk_probability: Optional[float]
    
    # Consolidated overall alert state
    risk_level: str
    all_anomalies: List[str]

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    student_id: Optional[int] = None
    message: str

class ChatResponse(BaseModel):
    response: str