"""
The student chatbot must only ever answer about the signed-in student's own record,
even when the message names another student id or name.
"""
from types import SimpleNamespace

import pytest

from services import chatbot


def _snap(student_id, name):
    return SimpleNamespace(student_id=student_id, full_name=name, risk_level="LOW", sources=["rosario"],
                           data={"cumulative_gpa": 3.1, "current_courses": [], "term_gpas": []},
                           rules_skipped={}, ml_prediction=None)


@pytest.fixture()
def fake_store(monkeypatch):
    snaps = {"690025": _snap("690025", "Own Student"), "690002": _snap("690002", "Other Person")}
    looked_up = []

    def latest_snapshot(db, sid):
        looked_up.append(sid)
        return snaps.get(sid)

    def latest_snapshots(db):
        raise AssertionError("student answers must never scan other students")

    monkeypatch.setattr(chatbot, "latest_snapshot", latest_snapshot)
    monkeypatch.setattr(chatbot, "latest_snapshots", latest_snapshots)
    monkeypatch.setattr(chatbot, "open_alerts", lambda db, sid=None: [])
    return looked_up


@pytest.mark.parametrize("message", ["tell me about 690002", "what is Other Person's GPA?",
                                     "which students are high risk?", "show my gpa"])
def test_student_chat_is_locked_to_own_record(fake_store, message):
    out = chatbot.answer(None, message, "690025", audience="student")
    assert out["student_id"] == "690025"
    assert "Other Person" not in out["response"] and "690002" not in out["response"]
    assert fake_store == ["690025"]


def test_student_chat_requires_own_id(fake_store):
    with pytest.raises(ValueError):
        chatbot.answer(None, "hello", None, audience="student")
