# My Coach — Automated Student Risk Detection & Advisory System

```
RosarioSIS (academic)  ─┐
                         ├─► FastAPI: sync → normalise → rule-based anomaly detection ─► PostgreSQL ─► Next.js dashboard
Moodle (LMS activity)  ─┘        (+ experimental ML probability, kept separate)          (alerts, history,
                                                                                            interventions, sync runs)
```

- **RosarioSIS** and **Moodle** are the primary sources of student data. The app only *reads* from them.
- **PostgreSQL** (currently the existing Supabase database) stores application data: sync runs, per-sync
  student snapshots, anomaly alerts, the alert audit trail, interventions and Test Lab switches.
  The pre-existing `courses` and `advising_rules` tables are used as reference data (catalogue and prerequisites).
- **Rule-based anomalies** are the source of alerts. The **ML prediction** (XGBoost + SHAP) is shown separately as
  an experimental estimate and never creates alerts.

## Student LMS (`moodle-lms/`)

A separate student-facing LMS app for the same Moodle (courses, assignments with file submission, quizzes,
grades, progress, calendar, notifications). It links to the My Coach student portal and reads the student's
risk summary from `GET /api/integration/lms/students/{id}/summary` (enabled by `LMS_INTEGRATION_KEY`).
See [moodle-lms/README.md](moodle-lms/README.md).

## Run locally

Prerequisites: XAMPP with RosarioSIS (REST_API plugin active), Python 3.12, Node 20+.

```bash
# 1. Backend  (from backend/)
cp .env.example .env              # first time only; fill in the values
pip install -r requirements.txt   # or use venv\Scripts\python -m pip ...
python -m uvicorn main:app --reload --port 8000

# 2. Frontend (from frontend/)
npm install
npm run dev                       # http://localhost:3000

# 3. Tests    (from backend/)
python -m pytest -q
```

Sign in with `ADVISOR_EMAIL` / `ADVISOR_PASSWORD` from `backend/.env`.

## Public deployment

| Part | Host | Settings |
|---|---|---|
| Frontend (Next.js, `frontend/`) | Vercel | Root directory `frontend`; env `NEXT_PUBLIC_API_URL=https://<render-service>.onrender.com` |
| Backend (FastAPI, `backend/`) | Render web service | Root directory `backend`; build `pip install -r requirements.txt`; start `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Database | Supabase PostgreSQL | `DATABASE_URL` (shared by the local and the public backend) |

Backend environment variables on Render (values are never committed): `DATABASE_URL`, `JWT_SECRET`,
`ADVISOR_EMAIL`, `ADVISOR_PASSWORD`, `ADVISOR_NAME`, `STUDENT_EMAIL`, `STUDENT_PASSWORD`, `STUDENT_NAME`, `STUDENT_ID`,
`ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME`, `DEMO_DATA_ENABLED`, optional `CORS_ORIGINS` (comma-separated; the
Vercel domain and localhost are allowed by default).

RosarioSIS and Moodle run on the local/campus machine, so they are left unset on Render. Run **Sync Data** on the local
instance: it writes to the shared Supabase database, and the public site shows those results. Sync Data on the public
server refreshes Test Lab (DEMO) data only.

## Demonstration (Test Lab)

1. Open **Test Lab** and select *Test Student (Demo) — DEMO-100* (a healthy baseline).
2. Click **Sync Data** → the student is 🟢 LOW with no anomalies.
3. Turn on a scenario (e.g. *Enrol in a course outside the major*) → **Sync Data** → a 🟡/🔴 alert appears on the
   dashboard, the student page and the Alerts page, with evidence and a recommended intervention.
4. Turn the scenario off → **Sync Data** → the alert is automatically resolved (kept in history).

DEMO students are local, clearly labelled test data. They never touch RosarioSIS or Moodle.
Set `DEMO_DATA_ENABLED=false` to use only the live systems.

## Using live RosarioSIS / Moodle data

- **RosarioSIS**: students, enrollment, schedule (current courses and drops), report-card grades, and billing
  fees and payments are read through the REST_API plugin. RosarioSIS has no "major" or "hold" field by default.
  Add custom student fields named **Major** and **Hold** to enable those rules; otherwise they are reported as
  *unavailable*, never guessed.
- **Moodle**: enable REST web services and create a token for a service with these functions:
  `core_webservice_get_site_info`, `core_course_get_courses`, `core_enrol_get_enrolled_users`,
  `mod_assign_get_assignments`, `mod_assign_get_submissions`, `gradereport_user_get_grade_items`.
  Link a Moodle user to a RosarioSIS student by setting the Moodle **ID number** to the RosarioSIS student ID
  (or by using the same username).

## Anomaly rules

Course-major mismatch · prerequisite violation · excessive withdrawals · low course load ·
low grades / weak progression · declining GPA · gatekeeper-course withdrawal · undeclared major ·
tuition balance · missed assignments · low quiz performance · course dropped without replacement ·
academic hold / incomplete · low LMS engagement.

Thresholds live in `backend/advising_config.py`. Risk level: **HIGH** if any HIGH anomaly or 3+ MODERATE;
**MODERATE** if any MODERATE; otherwise **LOW**.
