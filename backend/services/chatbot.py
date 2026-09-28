# backend/services/chatbot.py
"""
Rule-based advising assistant (no external LLM).

Answers are assembled only from the latest synchronised student snapshot,
the stored alerts and the logged interventions — so every statement can be
traced back to RosarioSIS / Moodle (or DEMO) data.
"""
import re
from typing import Optional

from sqlalchemy.orm import Session

import models
from repository import OPEN_STATUSES, latest_snapshot, latest_snapshots, open_alerts

SEV_ICON = {"HIGH": "🔴", "MODERATE": "🟡", "LOW": "🟢"}

INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("ml", ("ml", "machine learning", "predict", "probability", "model")),
    ("discuss", ("discuss", "talk about", "meeting", "bring up", "talking points", "prepare")),
    ("intervention", ("intervention", "recommend", "what should", "next step", "action", "help the student")),
    ("courses", ("course", "taking", "enrolled", "schedule", "registered", "classes")),
    ("withdrawals", ("withdraw", "dropped", "drop ")),
    ("lms", ("moodle", "lms", "assignment", "quiz", "engagement", "login", "access")),
    ("gpa", ("gpa", "grade", "performance", "transcript", "history")),
    ("anomalies", ("anomal", "flag", "why", "alert", "risk", "issue", "problem", "concern", "detected")),
]


def _detect_intent(msg: str) -> str:
    for intent, keywords in INTENTS:
        if any(re.search(rf"\b{re.escape(k)}", msg) for k in keywords):
            return intent
    return "summary"


def _find_student(db: Session, msg: str, student_id: Optional[str]) -> Optional[models.StudentSnapshot]:
    if student_id:
        return latest_snapshot(db, str(student_id))
    snaps = latest_snapshots(db)
    for token in re.findall(r"\b(demo-\d+|mdl-\d+|\d{1,7})\b", msg, re.I):
        for s in snaps:
            if s.student_id.lower() == token.lower():
                return s
    best = None
    for s in snaps:
        parts = [p.lower() for p in re.findall(r"[A-Za-z]{3,}", s.full_name or "") if p.lower() != "demo"]
        hits = sum(1 for p in parts if re.search(rf"\b{re.escape(p)}\b", msg))
        if hits and (best is None or hits > best[0]):
            best = (hits, s)
    return best[1] if best else None


def answer(db: Session, message: str, student_id: Optional[str] = None, audience: str = "staff") -> dict:
    """audience="student": the caller is the student themself. The answer is locked to
    `student_id` (never looked up from the message) and advisor-only notes are left out."""
    msg = message.strip().lower()
    if audience == "student":
        if not student_id:
            raise ValueError("A student-audience answer needs the student's own id")
        snap = latest_snapshot(db, str(student_id))
    else:
        snap = _find_student(db, msg, student_id)
    intent = _detect_intent(msg)

    if snap is None:
        if audience == "student":
            return {"response": "Your academic record has not been synchronised yet.",
                    "student_id": None, "intent": "general"}
        return {"response": _general(db, msg), "student_id": None, "intent": "general"}
    if audience == "student" and intent == "intervention":
        return {"response": _own_next_steps(db, snap, open_alerts(db, snap.student_id)),
                "student_id": snap.student_id, "intent": intent}

    d = snap.data or {}
    alerts = open_alerts(db, snap.student_id)
    header = f"**{snap.full_name}** ({snap.student_id}) — overall risk {SEV_ICON.get(snap.risk_level, '')} **{snap.risk_level}**"
    if d.get("is_demo"):
        header += " · _DEMO test data_"
    body = {
        "anomalies": _anomalies,
        "courses": _courses,
        "intervention": _interventions,
        "discuss": _discuss,
        "gpa": _gpa,
        "withdrawals": _withdrawals,
        "lms": _lms,
        "ml": _ml,
        "summary": _summary,
    }[intent](db, snap, d, alerts)
    return {"response": f"{header}\n\n{body}", "student_id": snap.student_id, "intent": intent}


# ---------------------------------------------------------------------------
def _anomalies(db, snap, d, alerts) -> str:
    if not alerts:
        skipped = snap.rules_skipped or {}
        note = f"\n\n_{len(skipped)} rule(s) could not be evaluated because data was unavailable._" if skipped else ""
        return "No active rule-based anomalies were detected in the latest sync." + note
    lines = [f"**{len(alerts)} active anomaly alert(s)** (rule-based):"]
    for a in alerts:
        lines.append(f"\n{SEV_ICON.get(a.severity, '')} **{a.title}** — {a.severity}\n{a.description}")
        for e in (a.evidence or [])[:4]:
            lines.append(f"  - {e}")
    return "\n".join(lines)


def _courses(db, snap, d, alerts) -> str:
    courses = d.get("current_courses", [])
    if not courses:
        if "current_courses" in d.get("missing", []):
            return "Current course registrations are **not available** from the source systems."
        return f"No course registrations found for the current term ({d.get('current_term') or 'n/a'})."
    active = [c for c in courses if c["status"] == "enrolled"]
    dropped = [c for c in courses if c["status"] == "dropped"]
    units = sum(c.get("units") or 0 for c in active)
    lines = [f"**Current term ({d.get('current_term') or 'n/a'}): {len(active)} active course(s), {units:g} units**"]
    lines += [f"- {c['code']} — {c.get('title') or ''} ({c.get('units') if c.get('units') is not None else '?'} units)"
              for c in active]
    if dropped:
        lines.append("\n**Dropped this term:**")
        lines += [f"- {c['code']} — {c.get('title') or ''} (dropped {c.get('end_date') or ''})" for c in dropped]
    return "\n".join(lines)


def _interventions(db, snap, d, alerts) -> str:
    lines = []
    if alerts:
        lines.append("**Recommended interventions (from the detected anomalies):**")
        for a in alerts:
            lines.append(f"- {SEV_ICON.get(a.severity, '')} _{a.title}_: {a.recommended_intervention}")
    else:
        lines.append("No active anomalies — no intervention is required. Continue routine advising check-ins.")
    logged = (db.query(models.Intervention).filter(models.Intervention.student_id == snap.student_id)
              .order_by(models.Intervention.created_at.desc()).limit(5).all())
    if logged:
        lines.append("\n**Interventions already logged:**")
        lines += [f"- {i.action_type} ({i.status}) — {i.created_at:%Y-%m-%d}{': ' + i.notes if i.notes else ''}"
                  for i in logged]
    return "\n".join(lines)


def _own_next_steps(db, snap, alerts) -> str:
    """Student-facing recommendations: no advisor notes, only what the student can act on."""
    header = f"**Your overall risk:** {SEV_ICON.get(snap.risk_level, '')} **{snap.risk_level}**"
    if not alerts:
        return header + "\n\nNo active concerns were detected. Keep up your routine check-ins with your advisor."
    lines = [header, "", "**Recommended next steps:**"]
    lines += [f"- {SEV_ICON.get(a.severity, '')} _{a.title}_: {a.recommended_intervention}" for a in alerts]
    planned = (db.query(models.Intervention.action_type, models.Intervention.status)
               .filter(models.Intervention.student_id == snap.student_id,
                       models.Intervention.status.in_(("planned", "in_progress")))
               .limit(5).all())
    if planned:
        lines.append("\n**Support your advisor has planned with you:**")
        lines += [f"- {p.action_type} ({p.status.replace('_', ' ')})" for p in planned]
    return "\n".join(lines)


def _discuss(db, snap, d, alerts) -> str:
    points = []
    for a in alerts:
        points.append(f"- **{a.title}**: {a.description}")
    if d.get("cumulative_gpa") is not None:
        points.append(f"- Academic standing: cumulative GPA {d['cumulative_gpa']:.2f}, "
                      f"{d.get('completed_units') or 0:g} units completed ({d.get('class_standing') or 'n/a'}).")
    active = [c["code"] for c in d.get("current_courses", []) if c["status"] == "enrolled"]
    if active:
        points.append(f"- Current course plan: {', '.join(active)} — confirm these count toward the degree.")
    if not d.get("major_field_available"):
        points.append("- Confirm the declared major (not available in the source system).")
    points.append("- Any personal, financial or health factors affecting study, and support services needed.")
    points.append("- Agree on concrete goals and a follow-up date.")
    return "**Suggested discussion points for the advising meeting:**\n" + "\n".join(points)


def _gpa(db, snap, d, alerts) -> str:
    terms = d.get("term_gpas", [])
    if not terms and d.get("cumulative_gpa") is None:
        return "No graded course history is available for this student."
    lines = [f"**Cumulative GPA:** {d['cumulative_gpa']:.2f}" if d.get("cumulative_gpa") is not None
             else "**Cumulative GPA:** unavailable"]
    if terms:
        lines.append("**Term GPA trend:** " + " → ".join(f"{t['term']}: {t['gpa']:.2f}" for t in terms))
    low = [g for g in d.get("course_history", []) if g.get("grade_points") is not None and g["grade_points"] < 2.0]
    if low:
        lines.append("**Grades below C:** " + ", ".join(f"{g['code']} ({g['grade_letter']})" for g in low))
    return "\n".join(lines)


def _withdrawals(db, snap, d, alerts) -> str:
    dropped = [c for c in d.get("current_courses", []) if c["status"] == "dropped"]
    hist = [g for g in d.get("course_history", []) if g.get("withdrawn")]
    if not dropped and not hist:
        return "No course withdrawals on record."
    lines = [f"**{len(dropped) + len(hist)} withdrawal(s) on record:**"]
    lines += [f"- {c['code']} dropped this term ({c.get('end_date') or ''})" for c in dropped]
    lines += [f"- {g['code']} withdrawn ({g['grade_letter']}) in {g.get('term') or 'n/a'}" for g in hist]
    return "\n".join(lines)


def _lms(db, snap, d, alerts) -> str:
    lms = d.get("lms", {})
    if not lms.get("available"):
        return "Moodle LMS data is **not available** for this student (no linked Moodle account or Moodle unreachable)."
    missed = [a for a in lms.get("assignments", []) if a["status"] == "missed"]
    quizzes = [q for q in lms.get("quizzes", []) if q.get("percent") is not None]
    lines = [f"**Moodle courses:** {', '.join(lms.get('courses', [])) or 'none'}",
             f"**Last course access:** {lms.get('last_access') or 'never'}"
             + (f" ({lms['days_since_last_access']} days ago)" if lms.get("days_since_last_access") is not None else ""),
             f"**Assignments:** {len(lms.get('assignments', []))} tracked, {len(missed)} missed"]
    lines += [f"  - missed: {a['course']} – {a['name']} (due {a.get('due_date') or 'n/a'})" for a in missed]
    if quizzes:
        avg = sum(q["percent"] for q in quizzes) / len(quizzes)
        lines.append(f"**Quizzes:** average {avg:.0f}% over {len(quizzes)} graded quiz(zes)")
    return "\n".join(lines)


def _ml(db, snap, d, alerts) -> str:
    p = snap.ml_prediction or {}
    if p.get("status") != "ok":
        return f"ML predictive risk is not available: {p.get('reason', 'no prediction')}"
    lines = [f"**Experimental ML probability of high risk:** {p['probability_high_risk']:.0%} ({p['band']})",
             f"_Model: {p.get('model')}, trained on {p.get('training_samples')} records, "
             f"leave-one-out accuracy {p.get('loocv_accuracy')}._"]
    if p.get("top_factors"):
        lines.append("Top contributing factors: " + ", ".join(
            f"{f['feature']} ({'+' if f['contribution'] > 0 else ''}{f['contribution']:.2f})" for f in p["top_factors"][:3]))
    lines.append(f"\n_{p.get('disclaimer')}_ This is separate from the rule-based anomalies.")
    return "\n".join(lines)


def _summary(db, snap, d, alerts) -> str:
    gpa = f"{d['cumulative_gpa']:.2f}" if d.get("cumulative_gpa") is not None else "unavailable"
    major = d.get("declared_major") if d.get("major_field_available") else "not available in source"
    lines = [f"- **Major:** {major}",
             f"- **Standing:** {d.get('class_standing') or 'unavailable'} · **GPA:** {gpa}",
             f"- **Data sources:** {', '.join(snap.sources or [])}",
             f"- **Active alerts:** {len(alerts)}"]
    for a in alerts[:5]:
        lines.append(f"  - {SEV_ICON.get(a.severity, '')} {a.title}")
    lines.append("\nAsk me about _anomalies_, _courses_, _GPA trend_, _withdrawals_, _Moodle activity_, "
                 "_recommended interventions_ or _what to discuss in the advising meeting_.")
    return "\n".join(lines)


def _general(db: Session, msg: str) -> str:
    snaps = latest_snapshots(db)
    if not snaps:
        return "No student data has been synchronised yet. Click **Sync Data** on the dashboard first."
    if any(k in msg for k in ("high", "risk", "list", "who", "which", "students")):
        order = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
        flagged = sorted([s for s in snaps if s.risk_level in ("HIGH", "MODERATE")],
                         key=lambda s: order.get(s.risk_level, 3))
        if not flagged:
            return "All monitored students are currently 🟢 LOW risk."
        lines = [f"**{len(flagged)} student(s) currently flagged:**"]
        lines += [f"- {SEV_ICON[s.risk_level]} {s.full_name} ({s.student_id}) — {s.risk_level}" for s in flagged[:15]]
        return "\n".join(lines)
    n_alerts = db.query(models.AnomalyAlert).filter(models.AnomalyAlert.status.in_(OPEN_STATUSES)).count()
    return (f"I'm monitoring **{len(snaps)} student(s)** with **{n_alerts} open alert(s)**.\n\n"
            "Select a student (or mention a student ID / name) and ask, for example:\n"
            "- What anomalies were detected for this student?\n- Why was this student flagged?\n"
            "- What courses is this student currently taking?\n- What intervention is recommended?\n"
            "- What should the student discuss with their advisor?\n\nOr ask: _Which students are high risk?_")
