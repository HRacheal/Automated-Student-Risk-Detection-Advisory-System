"""A partial sync (a source unavailable) must not lower a student's risk below their still-open alerts."""
from types import SimpleNamespace

from anomaly_engine import EvaluationResult
from services.sync_service import _summary, snapshot_risk_level


def test_summary_never_claims_an_unavailable_source_was_synchronised():
    sources = {"rosario": {"status": "ok"}, "moodle": {"status": "unavailable"}}
    text = _summary("partial", sources, None)
    assert text.startswith("Synchronised RosarioSIS.")
    assert "Not synchronised: Moodle unavailable" in text
    assert "Synchronised RosarioSIS, Moodle" not in text


def test_summary_complete_and_failed():
    assert _summary("completed", {"rosario": {"status": "ok"}, "moodle": {"status": "ok"}}, None) == \
        "Synchronised RosarioSIS, Moodle."
    assert _summary("failed", {}, "OperationalError: db down") == "Synchronisation failed: OperationalError: db down"


def _alert(severity):
    return SimpleNamespace(severity=severity)


def _result(evaluated, anomalies=()):
    r = EvaluationResult(student_id="690027", evaluated=list(evaluated))
    r.anomalies = [SimpleNamespace(severity=s) for s in anomalies]
    return r


def test_skipped_rule_keeps_open_high_alert_in_risk():
    # Moodle down: lms_inactivity was skipped, its HIGH alert is still open
    open_by_key = {("690027", "lms_inactivity"): _alert("HIGH"),
                   ("690027", "weak_academic_progression"): _alert("MODERATE")}
    res = _result(["weak_academic_progression"], ["MODERATE"])
    assert snapshot_risk_level(res, open_by_key) == "HIGH"


def test_evaluated_and_cleared_alert_no_longer_counts():
    # rule evaluated and condition gone -> alert auto-resolves, must not inflate risk
    open_by_key = {("690027", "lms_inactivity"): _alert("HIGH")}
    assert snapshot_risk_level(_result(["lms_inactivity"]), open_by_key) == "LOW"


def test_other_students_alerts_ignored():
    open_by_key = {("690001", "lms_inactivity"): _alert("HIGH")}
    assert snapshot_risk_level(_result([]), open_by_key) == "LOW"


def test_redetected_alert_uses_fresh_severity_once():
    open_by_key = {("690027", "missed_assignments"): _alert("HIGH")}
    res = _result(["missed_assignments"], ["MODERATE"])
    assert snapshot_risk_level(res, open_by_key) == "MODERATE"
