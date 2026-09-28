# backend/routers/model_performance.py
"""Serves the saved evaluation report produced by scripts/evaluate_models.py (read-only)."""
import json

from fastapi import APIRouter, Depends, HTTPException

from auth import staff_only
from config import BACKEND_DIR

router = APIRouter(prefix="/api", tags=["system"])
REPORT = BACKEND_DIR / "reports" / "model_performance.json"


@router.get("/model-performance")
def model_performance(_: dict = Depends(staff_only)):
    if not REPORT.exists():
        raise HTTPException(404, "No evaluation report yet. Run `python scripts/evaluate_models.py` in backend/.")
    return json.loads(REPORT.read_text(encoding="utf-8"))
