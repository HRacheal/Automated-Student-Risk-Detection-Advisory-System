"""
API behaviour against a fake Moodle (httpx.MockTransport) - no network needed.
Covers sign-in mapping, session isolation, the CSRF header, the 'Moodle unavailable'
state and that the My Coach summary is only ever requested for the session's student.
"""
import time
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from lms import main, mycoach
from lms.config import settings
from lms.moodle import MoodleClient, encode_params
from lms.service import StudentLMS

H = {"X-Requested-With": "mycoach-lms"}
NOW = int(time.time())

USERS = {
    "s690025": {"id": 97, "password": "pw-victor", "idnumber": "690025", "fullname": "Victor Onyango"},
    "s690002": {"id": 75, "password": "pw-daniel", "idnumber": "690002", "fullname": "Daniel Mwangi"},
}
TOKENS = {f"tok-{u}": u for u in USERS}
ENROL = {97: [32], 75: [26]}


class FakeMoodle:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        path = request.url.path
        if path.endswith("/login/token.php"):
            u = USERS.get(form.get("username"))
            if u and u["password"] == form.get("password"):
                return httpx.Response(200, json={"token": f"tok-{form['username']}"})
            return httpx.Response(200, json={"error": "Invalid login", "errorcode": "invalidlogin"})
        token, fn = form.get("wstoken"), form.get("wsfunction")
        self.calls.append((token, fn, form))
        if token == "lookup-token" and fn == "core_user_get_users_by_field":
            found = [{"id": u["id"], "username": name, "idnumber": u["idnumber"]}
                     for name, u in USERS.items() if u["idnumber"] == form.get("values[0]")]
            return httpx.Response(200, json=found)
        username = TOKENS.get(token)
        if not username:
            return httpx.Response(200, json={"exception": "x", "errorcode": "invalidtoken", "message": "bad"})
        u = USERS[username]
        if fn == "core_webservice_get_site_info":
            return httpx.Response(200, json={"userid": u["id"], "username": username, "fullname": u["fullname"]})
        if fn == "core_user_get_users_by_field":
            return httpx.Response(200, json=[{"id": u["id"], "username": username, "fullname": u["fullname"],
                                              "idnumber": u["idnumber"], "email": f"{u['idnumber']}@x.invalid"}])
        if fn == "core_enrol_get_users_courses":
            assert form["userid"] == str(u["id"]), "must only ever ask for the signed-in user's courses"
            return httpx.Response(200, json=[{"id": cid, "shortname": f"C{cid}", "fullname": f"C{cid} Course {cid} (Fall 2026)",
                                              "progress": 50.0, "enablecompletion": 1, "lastaccess": NOW - 3600}
                                             for cid in ENROL[u["id"]]])
        if fn == "core_course_get_courses_by_field":
            return httpx.Response(200, json={"courses": [{"id": cid, "contacts": [{"fullname": "Instructor"}]}
                                                         for cid in ENROL[u["id"]]]})
        if fn == "mod_assign_get_assignments":
            return httpx.Response(200, json={"courses": [{"id": cid, "shortname": f"C{cid}", "assignments": [
                {"id": cid * 10, "cmid": cid * 100, "course": cid, "name": "Report", "duedate": NOW + 86400,
                 "cutoffdate": NOW + 3 * 86400, "allowsubmissionsfromdate": NOW - 86400, "grade": 100,
                 "submissiondrafts": 0, "configs": [{"plugin": "file", "subtype": "assignsubmission", "name": "enabled", "value": "1"}]}]}
                for cid in ENROL[u["id"]]]})
        if fn == "mod_assign_get_submission_status":
            return httpx.Response(200, json={"lastattempt": {"canedit": True, "gradingstatus": "notgraded",
                                                             "submissionsenabled": True}})
        return httpx.Response(200, json={"exception": "x", "errorcode": "nopermission", "message": "no"})


@pytest.fixture()
def fake(monkeypatch):
    fm = FakeMoodle()
    monkeypatch.setattr(settings, "MOODLE_URL", "http://moodle.test")
    monkeypatch.setattr(settings, "MOODLE_LOOKUP_TOKEN", "lookup-token")
    main.throttle._failures.clear()
    return fm


@pytest.fixture()
def client(fake):
    with TestClient(main.app) as c:
        c.app.state.moodle = MoodleClient("http://moodle.test", transport=httpx.MockTransport(fake))
        yield c


def login(c, sid, pw):
    return c.post("/api/auth/login", json={"student_id": sid, "password": pw}, headers=H)


def test_encode_params_matches_moodle_rest_format():
    assert encode_params({"courseids": [3, 4], "options": {"a": True}, "x": None}) == {
        "courseids[0]": 3, "courseids[1]": 4, "options[a]": 1}


def test_login_by_student_id_maps_to_moodle_account(client):
    r = login(client, "690025", "pw-victor")
    assert r.status_code == 200
    assert r.json()["user"]["student_id"] == "690025"
    assert "token" not in r.text                                    # no Moodle token in the response
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_wrong_password_is_rejected_generically(client):
    r = login(client, "690025", "nope")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid student ID or password."
    assert login(client, "999999", "x").json()["detail"] == "Invalid student ID or password."


def test_repeated_failures_are_throttled(client):
    for _ in range(5):
        login(client, "690025", "nope")
    assert login(client, "690025", "pw-victor").status_code == 429


def test_state_changing_calls_need_the_custom_header(client):
    r = client.post("/api/auth/login", json={"student_id": "690025", "password": "pw-victor"})
    assert r.status_code == 403


def test_requires_sign_in(client):
    assert client.get("/api/courses").status_code == 401


def test_each_session_only_sees_its_own_courses(client, fake):
    login(client, "690025", "pw-victor")
    assert [c["code"] for c in client.get("/api/courses").json()["courses"]] == ["C32"]
    # Victor cannot open a course he is not enrolled in (Daniel's)
    assert client.get("/api/courses/26").status_code == 404
    other = TestClient(main.app)
    other.app.state.moodle = client.app.state.moodle
    login(other, "690002", "pw-daniel")
    assert [c["code"] for c in other.get("/api/courses").json()["courses"]] == ["C26"]
    assert other.get("/api/assignments/3200").status_code == 404     # Victor's assignment
    victor_calls = {tok for tok, fn, _ in fake.calls if fn == "core_enrol_get_users_courses"}
    assert victor_calls == {"tok-s690025", "tok-s690002"}             # each with its own token


def test_assignment_state_is_derived_from_moodle(client):
    login(client, "690025", "pw-victor")
    [a] = client.get("/api/assignments").json()["assignments"]
    assert a["state"] == "open" and a["can_edit"] is True and a["submitted_at"] is None


def test_moodle_unavailable_is_reported_not_faked(client, fake):
    login(client, "690025", "pw-victor")
    fake.down = True
    r = client.get("/api/courses")
    assert r.status_code == 503
    assert r.json()["detail"] == "Moodle is currently unavailable. Please try again."


def test_logout_ends_session(client):
    login(client, "690025", "pw-victor")
    assert client.post("/api/auth/logout", headers=H).status_code == 200
    assert client.get("/api/courses").status_code == 401


def test_mycoach_summary_uses_session_student_id(client, monkeypatch):
    seen = []

    async def fake_summary(student_id, transport=None):
        seen.append(student_id)
        return {"available": True, "student_id": student_id, "risk_level": "HIGH", "portal_url": "x"}

    monkeypatch.setattr(mycoach, "risk_summary", fake_summary)
    login(client, "690025", "pw-victor")
    assert client.get("/api/mycoach?student_id=690002").json()["student_id"] == "690025"
    assert seen == ["690025"]


@pytest.mark.anyio
async def test_mycoach_rejects_a_summary_for_another_student(monkeypatch):
    monkeypatch.setattr(settings, "MYCOACH_API_URL", "http://coach.test")
    monkeypatch.setattr(settings, "MYCOACH_INTEGRATION_KEY", "k")

    def handler(request):
        assert request.headers["X-Integration-Key"] == "k"
        return httpx.Response(200, json={"student_id": "690002", "risk_level": "LOW"})

    out = await mycoach.risk_summary("690025", transport=httpx.MockTransport(handler))
    assert out["available"] is False


def test_assignment_view_states():
    from lms.sessions import Session
    svc = StudentLMS(Session(token="t", moodle_userid=1, student_id="1", username="u", fullname="f", expires_at=0), None)
    base = {"cmid": 1, "id": 1, "course": 1, "name": "A", "configs": []}
    view = lambda a, st: svc._assignment_view({**base, **a}, st)
    late = view({"duedate": NOW - 100}, {"lastattempt": {"submission": {"status": "submitted", "timemodified": NOW - 50}}})
    assert late["state"] == "submitted" and late["late"] and late["late_by_seconds"] == 50
    assert view({"duedate": NOW - 100, "cutoffdate": NOW + 100}, {"lastattempt": {}})["state"] == "overdue"
    assert view({"duedate": NOW - 200, "cutoffdate": NOW - 100}, {"lastattempt": {"canedit": True}})["can_edit"] is False
    assert view({"duedate": NOW + 100}, {"lastattempt": {}})["state"] == "open"


def test_only_read_only_moodle_calls_are_retried():
    from lms.moodle import is_read_only
    assert is_read_only("mod_assign_get_submission_status") and is_read_only("core_course_get_contents")
    for write in ("mod_assign_save_submission", "mod_assign_submit_for_grading", "mod_quiz_start_attempt",
                  "mod_quiz_process_attempt", "core_message_mark_notification_read",
                  "core_completion_update_activity_completion_status_manually"):
        assert not is_read_only(write)
