# backend/auth.py
"""
Role-based authentication (Student / Advisor / Admin).

Credentials come ONLY from backend environment variables (backend/.env):
  STUDENT_EMAIL / STUDENT_PASSWORD (+ STUDENT_ID: the student's own record)
  ADVISOR_EMAIL / ADVISOR_PASSWORD
  ADMIN_EMAIL   / ADMIN_PASSWORD
The role in the issued token is decided here, from the credentials that
matched - a role sent by the browser is only a hint that must agree with them.
"""
import hmac
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

ROLES = ("student", "advisor", "admin")
_bearer = HTTPBearer(auto_error=False)


def _accounts() -> dict[str, dict]:
    return {
        "student": {"email": settings.STUDENT_EMAIL, "password": settings.STUDENT_PASSWORD,
                    "name": settings.STUDENT_NAME, "student_id": settings.STUDENT_ID or None},
        "advisor": {"email": settings.ADVISOR_EMAIL, "password": settings.ADVISOR_PASSWORD,
                    "name": settings.ADVISOR_NAME, "student_id": None},
        "admin": {"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD,
                  "name": settings.ADMIN_NAME, "student_id": None},
    }


def role_configured(role: str) -> bool:
    acct = _accounts().get(role)
    return bool(acct and acct["email"] and acct["password"])


def _matches(acct: dict, email: str, password: str) -> bool:
    if not acct["email"] or not acct["password"]:
        return False
    email_ok = hmac.compare_digest(email.strip().lower().encode(), acct["email"].encode())
    password_ok = hmac.compare_digest(password.encode(), acct["password"].encode())
    return email_ok and password_ok


def authenticate(email: str, password: str, requested_role: Optional[str] = None) -> Optional[dict]:
    """Returns the authenticated user (role decided by the matching credentials) or None."""
    for role, acct in _accounts().items():
        if requested_role and role != requested_role:
            continue
        if _matches(acct, email, password):
            user = {"email": acct["email"], "name": acct["name"], "role": role}
            if role == "student":
                user["student_id"] = acct["student_id"]
            return user
    return None


def create_token(user: dict) -> str:
    payload = {
        "sub": user["email"],
        "name": user["name"],
        "role": user["role"],
        "student_id": user.get("student_id"),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    role = payload.get("role")
    if role not in ROLES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session role")
    return {"email": payload["sub"], "name": payload.get("name"), "role": role,
            "student_id": payload.get("student_id")}


def require_role(*allowed: str) -> Callable[..., dict]:
    """Dependency: the signed-in user must have one of the allowed roles (403 otherwise)."""
    def _dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to access this resource")
        return user
    return _dependency


# Common role groups
staff_only = require_role("advisor", "admin")   # advisor functionality (admins may also use it)
admin_only = require_role("admin")
student_only = require_role("student")
