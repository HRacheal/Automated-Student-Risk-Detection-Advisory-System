# backend/routers/session.py
from fastapi import APIRouter, Depends, HTTPException, status

from auth import authenticate, create_token, get_current_user, role_configured
from schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

ROLE_LABEL = {"student": "Student", "advisor": "Advisor", "admin": "Admin"}


@router.post("/login")
def login(req: LoginRequest):
    if req.role and not role_configured(req.role):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{ROLE_LABEL[req.role]} sign-in is not configured on the server yet.")
    user = authenticate(req.email, req.password, req.role)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return {"token": create_token(user), "user": user}   # never includes a password


@router.get("/roles")
def available_roles():
    """Which sign-in options are configured (booleans only - no e-mails or passwords)."""
    return {role: role_configured(role) for role in ROLE_LABEL}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
