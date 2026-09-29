# My Coach LMS — student Learning Management System

A standalone, student-facing LMS for the **existing Moodle** used by My Coach. It shows the same
courses, activities, assignments, quizzes, grades and completion that are in Moodle — nothing is
duplicated or invented. It is separate from the My Coach app (`../frontend`, `../backend`).

```
Student ── browser (React) ──cookie──► LMS backend (FastAPI, :8100) ──student's own token──► Moodle (:8081) ──► Moodle DB
                                               │
                                               └──integration key (server-side)──► My Coach backend (:8000) ─► risk engine

Moodle ──web services (read-only token)──► My Coach backend ──► risk engine ──► My Coach dashboards   (unchanged)
```

| Responsibility | Where |
|---|---|
| Courses, content, assignments, submissions, quizzes, grades, completion, learning activity | **Moodle** (via this LMS) |
| Risk indicators, risk levels, alerts, interventions, recommendations, advising chatbot | **My Coach** |

## How it works

- **Sign-in**: the student enters their student ID (e.g. `690025`) and password. The backend maps the ID to
  the Moodle account through the Moodle **ID number** (the existing My Coach mapping), then asks Moodle's own
  `login/token.php` for a token for the `mycoach_lms` service. Moodle checks the password; the LMS never stores it.
- **Per-student tokens**: every Moodle call runs *as the signed-in student*, so Moodle itself enforces that a student
  sees only their own courses, submissions, attempts and grades. The token is kept in the backend's memory; the
  browser only gets an opaque, HttpOnly, SameSite=Lax session cookie. State-changing calls also require an
  `X-Requested-With` header (CSRF guard). Five failed sign-ins lock that ID for 5 minutes.
- **Assignments**: files go to the student's Moodle draft area (`webservice/upload.php`) and are submitted with
  `mod_assign_save_submission` (+ `submit_for_grading` when the assignment uses drafts). Status, timestamps,
  lateness, grade and feedback come from `mod_assign_get_submission_status`.
- **Quizzes**: `mod_quiz_start_attempt / get_attempt_data / process_attempt`. Question HTML from Moodle is parsed
  server-side into plain structured data (text + answer options), so no Moodle HTML is injected into the page.
  Review and grades are shown only when the quiz's review options allow it.
- **Progress**: Moodle's own course progress percentage and activity completion states.
- **Notifications**: Moodle notifications and news-forum announcements, plus reminders computed from the
  student's real Moodle dates/statuses (due soon, overdue, submitted, grade released) — labelled as such.
- **My Coach card**: the backend calls `GET /api/integration/lms/students/{id}/summary` on My Coach with a shared
  key and the student ID *from the session*. "Open My Coach" links to the My Coach student portal.
- Opening a course/assignment/quiz is logged in Moodle (`*_view_*` functions), so real LMS engagement flows back
  into My Coach on its next sync.
- If Moodle is down every page shows *"Moodle is currently unavailable. Please try again."* — never cached or
  fake data.

## Folder layout

```
moodle-lms/
├── backend/            FastAPI backend-for-frontend (Python 3.12)
│   ├── lms/            config, moodle client, sessions, student service, quiz parser, API routes
│   ├── tests/          offline tests (fake Moodle) + live integration tests
│   ├── requirements.txt, .env.example
├── frontend/           React 19 + TypeScript + Vite + React Router (no UI framework)
│   └── src/            pages/, components/, api.ts, auth.tsx, styles.css
└── moodle-setup/
    └── setup_lms_service.php   one-time, idempotent Moodle configuration (see below)
```

Pages: Login, Dashboard, My Courses, Course (content / assignments / quizzes / grades / progress tabs),
Assignments, Assignment (details, upload, submit), Quizzes, Quiz, Quiz attempt, Attempt review, Grades, Progress,
Calendar (month grid + agenda), Recent Activity, Notifications, My Coach, Profile.

## One-time Moodle setup

`moodle-setup/setup_lms_service.php` (run with Moodle's bundled PHP; `--dry-run` rolls everything back):

1. creates the external service **My Coach LMS** (`mycoach_lms`) with only the student functions the app uses;
2. creates the system role **My Coach LMS student** (`moodle/webservice:createtoken`, `webservice/rest:use`) and
   assigns it to the synthetic students `s6900NN` only;
3. enables **file submissions** (in addition to online text) on the Fall 2026 synthetic assignments;
4. sets the synthetic students' password to `LMS_STUDENT_TEST_PASSWORD` (they previously had unknown random ones);
5. creates the lookup-only account/service `mycoach_lms_lookup` (one function, `core_user_get_users_by_field`) and
   writes its token to `LMS_LOOKUP_TOKEN_FILE`.

It never deletes data and does not touch courses, grades, submissions, attempts or the My Coach service/token.

```powershell
$env:LMS_STUDENT_TEST_PASSWORD = "<password>"
$env:LMS_LOOKUP_TOKEN_FILE = "$env:TEMP\lookup_token.txt"
C:\Users\Admin\Downloads\Moodle\server\php\php.exe moodle-setup\setup_lms_service.php `
    C:\Users\Admin\Downloads\Moodle\server\moodle\config.php
```

## Run locally

Prerequisites: Moodle running (`Start Moodle.exe`, http://localhost:8081), My Coach backend on :8000 (for the
My Coach card), Python 3.12, Node 20+.

```powershell
# backend (from moodle-lms/backend)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env        # fill in
.venv\Scripts\python -m uvicorn lms.main:app --port 8100

# frontend (from moodle-lms/frontend)
npm install
npm run dev                   # http://localhost:5173  (proxies /api to :8100)
# or: npm run build  -> the backend then serves the built app at http://localhost:8100
```

My Coach needs `LMS_INTEGRATION_KEY` in `backend/.env` (same value as `MYCOACH_INTEGRATION_KEY` here).

## Tests

```powershell
# frontend
npm run typecheck ; npm run build
# backend - offline (fake Moodle) + live read-only integration tests
.venv\Scripts\python -m pytest -q
# live tests that WRITE to Moodle (synthetic data; idempotent - later runs only verify):
$env:LMS_E2E_WRITE = "1"   # uploads + submits Victor's DSA3010 Assignment 5
$env:LMS_E2E_QUIZ  = "1"   # takes Victor's DSA3010 Quiz 3
.venv\Scripts\python -m pytest -q tests/test_live_moodle.py
```

## Notes / limits

- Sessions live in memory: restarting the backend signs everyone out. Use a single worker (or add a shared store).
- A new file submission replaces the previously submitted files (Moodle's file-manager behaviour).
- Question types other than true/false, multiple choice, short answer, numerical, select and essay text are shown
  with a link to answer them in Moodle.
- Courses currently contain only assignments and quizzes; other module types (files, pages, links) are listed
  with download / "Open in Moodle" links.
