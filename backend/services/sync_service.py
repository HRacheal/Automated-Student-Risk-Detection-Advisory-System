# backend/services/sync_service.py
"""
Synchronisation pipeline behind the "Sync Data" button:

  1. pull RosarioSIS (academic)      2. pull Moodle (LMS)      [+ DEMO test data]
  3. normalise / merge per student   4. run rule-based anomaly detection
  5. persist snapshots + alert history in PostgreSQL
  6. return a summary

`run_sync()` is a plain function so it can later be called by a scheduler
(e.g. APScheduler / cron hitting POST /api/sync) without changes.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from anomaly_engine import CatalogCourse, RuleContext, evaluate_student, overall_risk_level
from config import settings
from domain import StudentRecord
from services.base import OK, SourceResult
from services.demo_source import fetch_demo
from services.moodle_service import MoodleStudent, fetch_moodle
from services.rosario_service import fetch_rosario

OPEN_STATUSES = ("active", "acknowledged")
_sync_lock = threading.Lock()


class SyncInProgress(Exception):
    pass


def load_catalog(db: Session) -> dict[str, CatalogCourse]:
    try:
        return {
            c.course_code.upper(): CatalogCourse(c.course_code, c.course_name, c.units,
                                                 c.level_standing, c.prerequisites)
            for c in db.query(models.Course).all()
        }
    except Exception:
        db.rollback()
        return {}


def active_scenarios(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in db.query(models.TestScenario).filter(models.TestScenario.enabled.is_(True)).all():
        out.setdefault(row.student_id, []).append(row.scenario_key)
    return out


def merge_sources(rosario: SourceResult, moodle: SourceResult) -> list[StudentRecord]:
    students: dict[str, StudentRecord] = {r.student_id: r for r in rosario.records}
    by_username = {r.username.lower(): r for r in rosario.records if r.username}
    matched: set[str] = set()

    for m in moodle.records:  # type: MoodleStudent
        target: Optional[StudentRecord] = None
        if m.idnumber and m.idnumber in students:
            target = students[m.idnumber]
        elif m.username and m.username.lower() in by_username:
            target = by_username[m.username.lower()]
        if target:
            target.lms = m.lms
            target.sources.append("moodle")
            matched.add(target.student_id)
            continue
        rec = StudentRecord(student_id=f"MDL-{m.moodle_id}", full_name=m.fullname,
                            sources=["moodle"], username=m.username, lms=m.lms)
        for key in ("declared_major", "holds", "current_courses", "course_history", "financial"):
            rec.mark_unavailable(key, "")
        rec.unavailable = ["No matching RosarioSIS student (set the Moodle user's ID number to the "
                           "RosarioSIS student ID to link records); academic data unavailable."]
        students[rec.student_id] = rec

    for rec in rosario.records:
        if rec.student_id in matched:
            continue
        if moodle.status == OK:
            rec.unavailable.append("No matching Moodle account (Moodle ID number / username); LMS data unavailable.")
        else:
            rec.unavailable.append(f"Moodle data unavailable: {moodle.message}")
    return list(students.values())


SOURCE_LABEL = {"rosario": "RosarioSIS", "moodle": "Moodle", "demo": "DEMO data"}


def _summary(status: str, sources: dict, error: Optional[str]) -> str:
    """One honest sentence for the UI: which sources were synchronised and which were not."""
    if status == "running":
        return "Synchronisation is running."
    if status == "failed" and error:
        return f"Synchronisation failed: {error}"
    ok = [SOURCE_LABEL.get(k, k) for k, v in sources.items() if v.get("status") == OK]
    down = [f"{SOURCE_LABEL.get(k, k)} {v.get('status', '').replace('_', ' ')}" for k, v in sources.items()
            if v.get("status") not in (OK, "not_configured")]
    text = f"Synchronised {', '.join(ok)}." if ok else "No source could be synchronised."
    if down:
        text += f" Not synchronised: {', '.join(down)} - its data was not updated and its rules were skipped."
    return text


def snapshot_risk_level(result, open_by_key: dict) -> str:
    """Overall risk for a student's snapshot.

    An open alert whose rule could NOT be evaluated this run (its source, e.g. Moodle, was
    unavailable) stays open, so it keeps counting toward the overall risk level - otherwise a
    partial sync would silently lower the risk of a student who still has open HIGH alerts.
    """
    carried = [a.severity for (sid, a_type), a in open_by_key.items()
               if sid == result.student_id and a_type not in result.evaluated]
    return overall_risk_level([an.severity for an in result.anomalies] + carried)


def sync_in_progress() -> bool:
    return _sync_lock.locked()


def run_sync(db: Session, triggered_by: str = "advisor") -> dict:
    if not _sync_lock.acquire(blocking=False):
        raise SyncInProgress("A synchronisation is already running.")
    try:
        return _run(db, triggered_by)
    finally:
        _sync_lock.release()


def _run(db: Session, triggered_by: str) -> dict:
    now = datetime.now(timezone.utc)
    run = models.SyncRun(started_at=now, status="running", triggered_by=triggered_by, source_status={})
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            rosario_future = pool.submit(fetch_rosario)
            moodle_future = pool.submit(fetch_moodle)
            rosario, moodle = rosario_future.result(), moodle_future.result()
        sources = {"rosario": rosario.summary(), "moodle": moodle.summary()}
        students = merge_sources(rosario, moodle)
        # How many RosarioSIS students were matched to a Moodle account (shown on the Sync page)
        sources["moodle"]["details"] = dict(sources["moodle"]["details"] or {}, linked_to_rosario=sum(
            1 for s in students if "rosario" in s.sources and "moodle" in s.sources))
        if settings.DEMO_DATA_ENABLED:
            demo = fetch_demo(active_scenarios(db))
            sources["demo"] = demo.summary()
            students += demo.records

        ctx = RuleContext(catalog=load_catalog(db), today=date.today())

        # Optional experimental ML; failures are recorded, never block the sync
        from analytics_engine import ensure_model, predict_for_record
        ensure_model(db)

        ids = [s.student_id for s in students]
        open_alerts = db.query(models.AnomalyAlert).filter(
            models.AnomalyAlert.student_id.in_(ids), models.AnomalyAlert.status.in_(OPEN_STATUSES)
        ).all() if ids else []
        open_by_key = {(a.student_id, a.anomaly_type): a for a in open_alerts}

        total_anomalies = resolved = 0
        created: list[models.AnomalyAlert] = []
        still_open_ids: list[int] = []
        for rec in students:
            result = evaluate_student(rec, ctx)
            total_anomalies += len(result.anomalies)
            detected_types = set()
            for an in result.anomalies:
                detected_types.add(an.anomaly_type)
                existing = open_by_key.get((rec.student_id, an.anomaly_type))
                if existing:
                    if existing.severity != an.severity:
                        db.add(models.AlertEvent(alert_id=existing.id, student_id=rec.student_id,
                                                 event_type="severity_changed", actor="system",
                                                 detail=f"{existing.severity} -> {an.severity}"))
                    # Only touch columns that changed (each UPDATE is a remote round trip);
                    # last_seen_at / last_sync_run_id are bulk-updated below.
                    for attr, value in (("severity", an.severity), ("title", an.title),
                                        ("description", an.description), ("evidence", an.evidence),
                                        ("recommended_intervention", an.recommended_intervention),
                                        ("student_name", rec.full_name), ("data_sources", an.data_sources)):
                        if getattr(existing, attr) != value:
                            setattr(existing, attr, value)
                    still_open_ids.append(existing.id)
                else:
                    alert = models.AnomalyAlert(
                        student_id=rec.student_id, student_name=rec.full_name, anomaly_type=an.anomaly_type,
                        severity=an.severity, title=an.title, description=an.description, evidence=an.evidence,
                        recommended_intervention=an.recommended_intervention, status="active", source="rule",
                        data_sources=an.data_sources, detected_at=now, last_seen_at=now,
                        first_sync_run_id=run.id, last_sync_run_id=run.id,
                    )
                    created.append(alert)

            # Resolve open alerts whose rule was evaluated and no longer fires.
            for (sid, a_type), alert in open_by_key.items():
                if sid == rec.student_id and a_type in result.evaluated and a_type not in detected_types:
                    alert.status = "auto_resolved"
                    alert.resolved_at = now
                    alert.last_sync_run_id = run.id
                    db.add(models.AlertEvent(alert_id=alert.id, student_id=sid, event_type="auto_resolved",
                                             actor="system",
                                             detail=f"Condition no longer present in source data (sync #{run.id})"))
                    resolved += 1

            risk_level = snapshot_risk_level(result, open_by_key)
            db.add(models.StudentSnapshot(
                sync_run_id=run.id, student_id=rec.student_id, full_name=rec.full_name, sources=rec.sources,
                risk_level=risk_level, data=rec.model_dump(mode="json"),
                rules_evaluated=result.evaluated, rules_skipped=result.skipped,
                ml_prediction=predict_for_record(rec), created_at=now,
            ))

        # One batched INSERT ... RETURNING for all new alerts (remote DB round trips are expensive)
        if created:
            db.add_all(created)
            db.flush()
            db.add_all([models.AlertEvent(alert_id=a.id, student_id=a.student_id, event_type="detected",
                                          actor="system", detail=f"Detected during sync #{run.id}")
                        for a in created])
        new_alerts = len(created)
        if still_open_ids:
            db.query(models.AnomalyAlert).filter(models.AnomalyAlert.id.in_(still_open_ids)).update(
                {models.AnomalyAlert.last_seen_at: now, models.AnomalyAlert.last_sync_run_id: run.id},
                synchronize_session=False)

        live_ok = [s for s in ("rosario", "moodle") if sources[s]["status"] == OK]
        live_configured = [s for s in ("rosario", "moodle") if sources[s]["status"] != "not_configured"]
        run.status = "completed" if len(live_ok) == len(live_configured) else ("partial" if students else "failed")
        run.source_status = sources
        run.students_analyzed = len(students)
        run.anomalies_detected = total_anomalies
        run.new_alerts = new_alerts
        run.resolved_alerts = resolved
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # record the failure, then surface it
        db.rollback()
        run = db.get(models.SyncRun, run.id)
        run.status = "failed"
        run.error = f"{exc.__class__.__name__}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise
    return sync_run_to_dict(run)


def sync_run_to_dict(run: models.SyncRun) -> dict:
    sources = run.source_status or {}
    moodle_details = (sources.get("moodle") or {}).get("details") or {}
    return {
        "id": run.id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "summary": _summary(run.status, sources, run.error),
        "triggered_by": run.triggered_by,
        "sources": sources,
        "joined_students": moodle_details.get("linked_to_rosario"),
        "students_analyzed": run.students_analyzed,
        "anomalies_detected": run.anomalies_detected,
        "new_alerts": run.new_alerts,
        "resolved_alerts": run.resolved_alerts,
        "error": run.error,
    }
