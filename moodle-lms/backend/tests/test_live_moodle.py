"""
Live integration tests against the local Moodle (synthetic data only).

Skipped automatically when Moodle is not reachable or TEST_STUDENT_PASSWORD is not set.
Tests that CHANGE Moodle data only run when explicitly enabled:
    LMS_E2E_WRITE=1  -> uploads + submits Victor's DSA3010 "Assignment 5" (once; later runs verify it)
    LMS_E2E_QUIZ=1   -> takes Victor's DSA3010 "Quiz 3" (once; later runs verify it)

Run:  .venv\\Scripts\\python -m pytest -q tests/test_live_moodle.py
"""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from lms import main
from lms.config import settings

H = {"X-Requested-With": "mycoach-lms"}
PASSWORD = os.getenv("TEST_STUDENT_PASSWORD") or dotenv_values(Path(__file__).parents[1] / ".env").get("TEST_STUDENT_PASSWORD")
VICTOR = "690025"


def _moodle_up() -> bool:
    try:
        return httpx.get(f"{settings.MOODLE_URL}/login/index.php", timeout=30).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not PASSWORD or not _moodle_up(), reason="live Moodle / test password not available")


@pytest.fixture(scope="module")
def victor():
    with TestClient(main.app) as c:
        r = c.post("/api/auth/login", json={"student_id": VICTOR, "password": PASSWORD}, headers=H)
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture(scope="module")
def dsa3010(victor):
    course = next(c for c in victor.get("/api/courses").json()["courses"] if c["code"] == "DSA3010")
    return victor.get(f"/api/courses/{course['id']}").json()


def _assignment(dsa3010, name):
    return next(a for a in dsa3010["assignments"] if a["name"] == name)


def test_moodle_connectivity(victor):
    assert victor.get("/api/health").json()["moodle"] == "ok"


def test_1_victor_logs_in(victor):
    me = victor.get("/api/auth/me").json()["user"]
    assert me["student_id"] == VICTOR and me["fullname"] == "Victor Onyango"


def test_2_victor_sees_his_courses(victor):
    codes = {c["code"] for c in victor.get("/api/courses").json()["courses"]}
    assert {"DSA3010", "APT2080", "CMS3700", "ENG2206"} <= codes


def test_3_4_open_dsa3010_and_its_activities(dsa3010):
    assert dsa3010["title"] == "Machine Learning Foundations"
    modules = [m for s in dsa3010["sections"] for m in s["modules"]]
    assert {m["module"] for m in modules} >= {"assign", "quiz"}
    assert len(dsa3010["assignments"]) == 6 and len(dsa3010["quizzes"]) == 3


def test_5_6_open_assignment_with_correct_deadline(victor, dsa3010):
    a = victor.get(f"/api/assignments/{_assignment(dsa3010, 'Assignment 5')['cmid']}").json()
    due = datetime.fromtimestamp(a["due_date"], ZoneInfo("Africa/Nairobi"))
    assert (due.year, due.month, due.day, due.hour, due.minute) == (2026, 10, 2, 23, 59)
    assert a["course_code"] == "DSA3010" and a["file_submissions"] is True


@pytest.mark.skipif(os.getenv("LMS_E2E_WRITE") != "1", reason="set LMS_E2E_WRITE=1 to submit to Moodle")
def test_7_to_10_upload_and_submit_assignment(victor, dsa3010):
    cmid = _assignment(dsa3010, "Assignment 5")["cmid"]
    before = victor.get(f"/api/assignments/{cmid}").json()
    if before["state"] != "submitted":
        content = b"Synthetic test submission for My Coach LMS end-to-end testing (not real student work).\n"
        up = victor.post(f"/api/assignments/{cmid}/files", headers=H,
                         files={"file": ("victor_ml_report_test.txt", content, "text/plain")})
        assert up.status_code == 200, up.text
        assert up.json()["staged_files"][0]["filename"] == "victor_ml_report_test.txt"
        r = victor.post(f"/api/assignments/{cmid}/submit", headers=H, json={"text": None})
        assert r.status_code == 200, r.text
    after = victor.get(f"/api/assignments/{cmid}").json()
    assert after["state"] == "submitted" and after["submission_status"] == "submitted"
    assert after["submitted_at"] and after["late"] is False
    assert any(f["filename"] == "victor_ml_report_test.txt" for f in after["submitted_files"])
    # The stored file can be downloaded back through the token-less proxy
    f = next(f for f in after["submitted_files"] if f["filename"] == "victor_ml_report_test.txt")
    assert victor.get(f["url"]).content.startswith(b"Synthetic test submission")


def test_13_quiz_information(victor, dsa3010):
    quiz1 = next(q for q in dsa3010["quizzes"] if q["name"] == "Quiz 1")
    detail = victor.get(f"/api/quizzes/{quiz1['cmid']}").json()
    assert detail["attempts"] and detail["attempts"][0]["state"] == "finished"
    assert detail["grade"] is not None                     # real Moodle grade, not invented
    quiz3 = victor.get(f"/api/quizzes/{next(q for q in dsa3010['quizzes'] if q['name'] == 'Quiz 3')['cmid']}").json()
    assert quiz3["opens"] and quiz3["closes"] and quiz3["rules"]


@pytest.mark.skipif(os.getenv("LMS_E2E_QUIZ") != "1", reason="set LMS_E2E_QUIZ=1 to take a quiz in Moodle")
def test_quiz_attempt_flow(victor, dsa3010):
    cmid = next(q for q in dsa3010["quizzes"] if q["name"] == "Quiz 3")["cmid"]
    quiz = victor.get(f"/api/quizzes/{cmid}").json()
    if quiz["attempts_used"] == 0:
        attempt_id = victor.post(f"/api/quizzes/{cmid}/start", headers=H).json()["attempt_id"]
        page = victor.get(f"/api/quiz-attempts/{attempt_id}?page=0").json()
        assert page["questions"] and all(q["fields"] for q in page["questions"])
        answers = {q["fields"][0]["name"]: q["fields"][0]["options"][0]["value"] for q in page["questions"]}
        r = victor.post(f"/api/quiz-attempts/{attempt_id}", headers=H, json={"page": 0, "answers": answers})
        assert r.status_code == 200, r.text
        summary = victor.get(f"/api/quiz-attempts/{attempt_id}/summary").json()
        assert all(q["answered"] for q in summary["questions"])
        assert victor.post(f"/api/quiz-attempts/{attempt_id}/finish", headers=H).json()["state"] == "finished"
    quiz = victor.get(f"/api/quizzes/{cmid}").json()
    assert quiz["attempts_used"] == 1 and quiz["attempts"][0]["state"] == "finished"
    review = victor.get(f"/api/quiz-attempts/{quiz['attempts'][0]['id']}/review")
    assert review.status_code in (200, 403)                 # depends on the quiz's review options


def test_14_grades(victor, dsa3010):
    g = victor.get(f"/api/grades/{dsa3010['id']}").json()
    a1 = next(i for i in g["items"] if i["name"] == "Assignment 1")
    assert a1["grade"] is not None and a1["percentage"]
    assert g["course_total"] is not None


def test_15_course_progress(victor, dsa3010):
    progress = {p["course_code"]: p for p in victor.get("/api/progress").json()["courses"]}
    p = progress["DSA3010"]
    assert p["percentage"] is not None and p["tracked"] == 9
    assert p["completed"] + p["remaining"] == p["tracked"]


def test_16_upcoming_deadlines_and_calendar(victor):
    up = victor.get("/api/upcoming").json()
    assert all(e["due"] for e in up["upcoming"])
    cal = victor.get("/api/calendar?month=2026-10").json()
    assert any(e["course_code"] == "DSA3010" and e["event_type"] == "due" for e in cal["events"])


def test_17_notifications(victor):
    notes = victor.get("/api/notifications").json()["notifications"]
    assert isinstance(notes, list) and all(n["title"] for n in notes)


def test_activity_and_profile(victor):
    assert victor.get("/api/activity").json()["activity"]
    p = victor.get("/api/profile").json()
    assert p["student_id"] == VICTOR and len(p["courses"]) >= 4


def test_18_my_coach_integration(victor):
    coach = victor.get("/api/mycoach").json()
    if not coach["available"]:
        pytest.skip(f"My Coach not running: {coach.get('message')}")
    assert coach["student_id"] == VICTOR and coach["risk_level"] in {"LOW", "MODERATE", "HIGH"}
    assert coach["portal_url"].endswith("/student")


def test_19_another_student_cannot_access_victors_data(victor, dsa3010):
    victor_quiz = victor.get(f"/api/quizzes/{next(q for q in dsa3010['quizzes'] if q['name'] == 'Quiz 1')['cmid']}").json()
    victor_attempt = victor_quiz["attempts"][0]["id"]
    victor_assign = _assignment(dsa3010, "Assignment 1")["cmid"]
    with TestClient(main.app) as other:
        # a synthetic student who is not enrolled in DSA3010
        for sid in ("690001", "690002", "690003", "690004"):
            other.cookies.clear()
            assert other.post("/api/auth/login", json={"student_id": sid, "password": PASSWORD}, headers=H).status_code == 200
            if "DSA3010" not in {c["code"] for c in other.get("/api/courses").json()["courses"]}:
                break
        else:
            pytest.skip("no synthetic student outside DSA3010")
        assert other.get("/api/auth/me").json()["user"]["student_id"] != VICTOR
        assert other.get(f"/api/courses/{dsa3010['id']}").status_code == 404
        assert other.get(f"/api/assignments/{victor_assign}").status_code == 404
        assert other.get(f"/api/grades/{dsa3010['id']}").status_code == 404
        assert other.get(f"/api/quiz-attempts/{victor_attempt}/review").status_code in (403, 404)
        assert other.get(f"/api/quiz-attempts/{victor_attempt}").status_code in (403, 404)
        assert other.get("/api/profile").json()["student_id"] != VICTOR
    # a wrong password for Victor is rejected
    with TestClient(main.app) as c:
        assert c.post("/api/auth/login", json={"student_id": VICTOR, "password": "wrong-password"}, headers=H).status_code == 401
