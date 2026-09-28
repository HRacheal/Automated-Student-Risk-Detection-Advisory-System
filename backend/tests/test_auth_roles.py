"""
Role-based authentication and authorisation tests.

Uses test-only credentials (monkeypatched settings) and the real routers, with the
database dependency replaced so that a request which gets PAST the role guard is
detected (raises ReachedHandler) while a blocked request never touches data.
"""
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from database import get_db
from routers import admin, alerts, model_performance, session, student_portal, students, system

CREDS = {
    "student": ("student.test@example.invalid", "student-test-pass"),
    "advisor": ("advisor.test@example.invalid", "advisor-test-pass"),
    "admin": ("admin.test@example.invalid", "admin-test-pass"),
}


class ReachedHandler(Exception):
    """Raised by the fake DB: proves the request was authorised."""


def _fake_db():
    class _DB:
        def __getattr__(self, name):
            raise ReachedHandler(name)
    yield _DB()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "unit-test-signing-secret-at-least-32-bytes")
    for role, (email, pw) in CREDS.items():
        monkeypatch.setattr(settings, f"{role.upper()}_EMAIL", email)
        monkeypatch.setattr(settings, f"{role.upper()}_PASSWORD", pw)
    monkeypatch.setattr(settings, "STUDENT_ID", "690001")
    app = FastAPI()
    for r in (session, students, alerts, system, student_portal, admin, model_performance):
        app.include_router(r.router)
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def login(client, role, email=None, password=None, as_role="same"):
    e, p = CREDS[role]
    body = {"email": email or e, "password": password or p}
    if as_role:
        body["role"] = role if as_role == "same" else as_role
    return client.post("/api/auth/login", json=body)


def auth(client, role):
    r = login(client, role)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.parametrize("role", ["student", "advisor", "admin"])
def test_each_role_can_sign_in_and_role_comes_from_backend(client, role):
    r = login(client, role)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == role
    claims = jwt.decode(body["token"], "unit-test-signing-secret-at-least-32-bytes", algorithms=["HS256"])
    assert claims["role"] == role
    if role == "student":
        assert claims["student_id"] == "690001"
    assert CREDS[role][1] not in r.text and "password" not in r.text.lower()


def test_wrong_password_rejected(client):
    assert login(client, "advisor", password="nope").status_code == 401


def test_role_hint_cannot_upgrade_privileges(client):
    # student credentials presented on the Admin form are rejected
    e, p = CREDS["student"]
    r = client.post("/api/auth/login", json={"email": e, "password": p, "role": "admin"})
    assert r.status_code == 401


def test_login_without_role_hint_still_gets_matching_role(client):
    r = login(client, "admin", as_role=None)
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"


def test_unconfigured_role_reports_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    r = login(client, "admin")
    assert r.status_code == 503
    assert client.get("/api/auth/roles").json() == {"student": True, "advisor": True, "admin": False}


def test_tampered_token_rejected(client):
    token = jwt.encode({"sub": "x", "role": "admin"}, "a-different-signing-secret-of-32-bytes-min", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


ADVISOR_ENDPOINTS = [("get", "/api/dashboard/summary"), ("get", "/api/students"), ("get", "/api/students/690002"),
                     ("get", "/api/alerts"), ("get", "/api/interventions"), ("post", "/api/sync"),
                     ("get", "/api/sync/runs"), ("get", "/api/test-lab"), ("post", "/api/chat"),
                     ("get", "/api/model-performance")]
ADMIN_ENDPOINTS = [("get", "/api/admin/overview"), ("post", "/api/ml/train")]
STUDENT_ENDPOINTS = [("get", "/api/student/me"), ("post", "/api/student/chat")]


def call(client, method, path, headers):
    kwargs = {"headers": headers}
    if method == "post" and "chat" in path:
        kwargs["json"] = {"message": "hello"}
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path", ADVISOR_ENDPOINTS + ADMIN_ENDPOINTS)
def test_student_blocked_from_advisor_and_admin(client, method, path):
    assert call(client, method, path, auth(client, "student")).status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS + STUDENT_ENDPOINTS)
def test_advisor_blocked_from_admin_and_student_portal(client, method, path):
    assert call(client, method, path, auth(client, "advisor")).status_code == 403


@pytest.mark.parametrize("method,path", STUDENT_ENDPOINTS)
def test_admin_blocked_from_student_portal(client, method, path):
    assert call(client, method, path, auth(client, "admin")).status_code == 403


@pytest.mark.parametrize("role,method,path", [("advisor", m, p) for m, p in ADVISOR_ENDPOINTS[:3]]
                         + [("admin", m, p) for m, p in ADMIN_ENDPOINTS]
                         + [("admin", "get", "/api/students")]
                         + [("student", m, p) for m, p in STUDENT_ENDPOINTS])
def test_allowed_roles_pass_the_guard(client, role, method, path):
    with pytest.raises(ReachedHandler):
        call(client, method, path, auth(client, role))


@pytest.mark.parametrize("method,path", ADVISOR_ENDPOINTS + ADMIN_ENDPOINTS + STUDENT_ENDPOINTS)
def test_anonymous_requests_rejected(client, method, path):
    assert call(client, method, path, {}).status_code == 401


def test_unlinked_student_account(client, monkeypatch):
    monkeypatch.setattr(settings, "STUDENT_ID", "")
    assert client.get("/api/student/me", headers=auth(client, "student")).status_code == 409
