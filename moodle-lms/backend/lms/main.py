"""
My Coach LMS - backend-for-frontend.

Browser  --(HttpOnly session cookie)-->  this API  --(student's own Moodle token)-->  Moodle
                                                  --(integration key, server-side)--> My Coach

Run from moodle-lms/backend:
    .venv\\Scripts\\python -m uvicorn lms.main:app --port 8100
"""
import datetime as dt
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import mycoach
from .config import settings
from .moodle import MoodleAuthError, MoodleClient, MoodleError, MoodleUnavailable
from .service import NotFound, StudentLMS
from .sessions import LoginThrottle, Session, SessionStore

log = logging.getLogger("mycoach-lms")
UNAVAILABLE = "Moodle is currently unavailable. Please try again."
PERMISSION_CODES = {"nopermission", "nopermissions", "requireloginerror", "errorcoursecontextnotvalid",
                    "notenrolled", "nopermissiontoviewgrades", "noreview", "noreviewattempt", "notyourattempt",
                    "attemptalreadyclosed", "invalidrecord", "invalidrecordunknown"}

store = SessionStore()
throttle = LoginThrottle()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.moodle = MoodleClient()
    yield
    await app.state.moodle.aclose()


app = FastAPI(title="My Coach LMS API", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------- errors
@app.exception_handler(MoodleUnavailable)
async def _unavailable(request: Request, exc: MoodleUnavailable):
    log.warning("Moodle unavailable: %s", exc)
    return JSONResponse({"detail": UNAVAILABLE, "code": "moodle_unavailable"}, status_code=503)


@app.exception_handler(MoodleAuthError)
async def _auth(request: Request, exc: MoodleAuthError):
    store.delete(request.cookies.get(settings.SESSION_COOKIE))
    res = JSONResponse({"detail": "Your session has expired. Please sign in again.", "code": "session_expired"},
                       status_code=401)
    res.delete_cookie(settings.SESSION_COOKIE, path="/", httponly=True, **_cookie_attrs(request))
    return res


@app.exception_handler(MoodleError)
async def _moodle_error(request: Request, exc: MoodleError):
    status = 403 if exc.errorcode in PERMISSION_CODES else 400
    detail = "You do not have access to this item." if status == 403 and exc.errorcode != "noreview" else exc.message
    return JSONResponse({"detail": detail, "code": exc.errorcode}, status_code=status)


@app.exception_handler(NotFound)
async def _not_found(request: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc), "code": "not_found"}, status_code=404)


# ---------------------------------------------------------------- CSRF guard
@app.middleware("http")
async def require_ajax_header(request: Request, call_next):
    """State-changing API calls must carry a custom header, which a cross-site form cannot send
    (and a cross-site script cannot add without a CORS preflight, which this API never grants)."""
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-requested-with") != "mycoach-lms":
            return JSONResponse({"detail": "Missing request header."}, status_code=403)
    return await call_next(request)


# Only the configured frontend origins (e.g. GitHub Pages) get CORS; added last so it is the outermost layer.
if settings.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Accept", "Content-Type", "X-Requested-With"])


def _cookie_attrs(request: Request) -> dict:
    """SameSite=Lax for same-origin use; a cross-site frontend needs SameSite=None, which requires Secure."""
    if request.headers.get("origin", "").rstrip("/") in settings.CORS_ORIGINS:
        return {"samesite": "none", "secure": True}
    return {"samesite": "lax", "secure": settings.COOKIE_SECURE}


# ---------------------------------------------------------------- session helpers
def current_session(request: Request) -> Session:
    session = store.get(request.cookies.get(settings.SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Not signed in")
    return session


def lms(request: Request, session: Session = Depends(current_session)) -> StudentLMS:
    return StudentLMS(session, request.app.state.moodle)


def _public_user(s: Session) -> dict:
    return {"fullname": s.fullname, "student_id": s.student_id, "username": s.username,
            "timezone": settings.LMS_TIMEZONE, "mycoach_portal_url": settings.MYCOACH_PORTAL_URL}


class LoginBody(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


GENERIC_LOGIN_ERROR = "Invalid student ID or password."


@app.post("/api/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    moodle: MoodleClient = request.app.state.moodle
    ident = body.student_id.strip()
    key = f"{request.client.host if request.client else '-'}:{ident.lower()}"
    if throttle.blocked(key):
        raise HTTPException(429, "Too many failed attempts. Please wait a few minutes and try again.")

    by_student_id = bool(re.fullmatch(r"\d{3,12}", ident))
    username = ident
    if by_student_id:
        # Student ID -> Moodle account via the Moodle ID number (the existing My Coach mapping)
        if not settings.MOODLE_LOOKUP_TOKEN:
            raise HTTPException(503, "Sign-in with a student ID is not configured; use your Moodle username.")
        try:
            users = await moodle.call(settings.MOODLE_LOOKUP_TOKEN, "core_user_get_users_by_field",
                                      field="idnumber", values=[ident])
        except (MoodleAuthError, MoodleError) as exc:
            log.error("Student ID lookup failed: %s", exc)
            raise HTTPException(503, "Student ID sign-in is temporarily unavailable.")
        if len(users) != 1:
            throttle.fail(key)
            raise HTTPException(401, GENERIC_LOGIN_ERROR)
        if not users[0].get("username"):
            log.error("The lookup token cannot read usernames (needs moodle/user:viewalldetails).")
            raise HTTPException(503, "Student ID sign-in is temporarily unavailable.")
        username = users[0]["username"]

    try:
        token = await moodle.login(username, body.password)
    except MoodleAuthError:
        throttle.fail(key)
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    info = await moodle.call(token, "core_webservice_get_site_info")
    me = await moodle.call(token, "core_user_get_users_by_field", field="id", values=[info["userid"]])
    idnumber = str((me[0] if me else {}).get("idnumber") or "").strip()
    if not idnumber:
        raise HTTPException(403, "This Moodle account is not linked to a student ID.")
    if by_student_id and idnumber != ident:
        throttle.fail(key)
        raise HTTPException(401, GENERIC_LOGIN_ERROR)
    throttle.reset(key)

    sid, session = store.create(token=token, moodle_userid=int(info["userid"]), student_id=idnumber,
                                username=info.get("username", username), fullname=info.get("fullname", ""))
    response.set_cookie(settings.SESSION_COOKIE, sid, httponly=True, **_cookie_attrs(request),
                        max_age=int(settings.SESSION_TTL_HOURS * 3600), path="/")
    return {"user": _public_user(session)}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    store.delete(request.cookies.get(settings.SESSION_COOKIE))
    response.delete_cookie(settings.SESSION_COOKIE, path="/", httponly=True, **_cookie_attrs(request))
    return {"ok": True}


@app.get("/api/auth/me")
async def me(session: Session = Depends(current_session)):
    return {"user": _public_user(session)}


# ---------------------------------------------------------------- health
@app.get("/api/health")
async def health(request: Request):
    moodle: MoodleClient = request.app.state.moodle
    try:
        await moodle._post(f"{moodle.base_url}/login/token.php", data={})
        status = "ok"
    except MoodleUnavailable:
        status = "unavailable"
    return {"status": "ok", "moodle": status}


# ---------------------------------------------------------------- learning data
@app.get("/api/dashboard")
async def dashboard(svc: StudentLMS = Depends(lms)):
    return await svc.dashboard()


@app.get("/api/courses")
async def courses(svc: StudentLMS = Depends(lms)):
    return {"courses": await svc.courses()}


@app.get("/api/courses/{course_id}")
async def course(course_id: int, svc: StudentLMS = Depends(lms)):
    return await svc.course_detail(course_id)


class CompletionBody(BaseModel):
    completed: bool


@app.post("/api/activities/{cmid}/completion")
async def manual_completion(cmid: int, body: CompletionBody, svc: StudentLMS = Depends(lms)):
    await svc.set_manual_completion(cmid, body.completed)
    return {"ok": True}


@app.get("/api/assignments")
async def assignments(course_id: Optional[int] = None, svc: StudentLMS = Depends(lms)):
    if course_id is not None:
        await svc.require_course(course_id)
    return {"assignments": await svc.assignments(course_id)}


@app.get("/api/assignments/{cmid}")
async def assignment(cmid: int, svc: StudentLMS = Depends(lms)):
    return await svc.assignment(cmid)


@app.post("/api/assignments/{cmid}/files")
async def upload_file(cmid: int, file: UploadFile = File(...), svc: StudentLMS = Depends(lms)):
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Files larger than {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB are not accepted.")
    if not content:
        raise HTTPException(400, "The file is empty.")
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", (file.filename or "upload").strip())[:200] or "upload"
    return await svc.stage_file(cmid, name, content)


@app.delete("/api/assignments/{cmid}/files")
async def clear_files(cmid: int, svc: StudentLMS = Depends(lms)):
    svc.clear_staged(cmid)
    return {"staged_files": []}


class SubmitBody(BaseModel):
    text: Optional[str] = Field(default=None, max_length=100_000)


@app.post("/api/assignments/{cmid}/submit")
async def submit(cmid: int, body: SubmitBody, svc: StudentLMS = Depends(lms)):
    return await svc.submit(cmid, body.text)


@app.get("/api/quizzes")
async def quizzes(course_id: Optional[int] = None, svc: StudentLMS = Depends(lms)):
    if course_id is not None:
        await svc.require_course(course_id)
    return {"quizzes": await svc.quizzes(course_id)}


@app.get("/api/quizzes/{cmid}")
async def quiz(cmid: int, svc: StudentLMS = Depends(lms)):
    return await svc.quiz(cmid)


@app.post("/api/quizzes/{cmid}/start")
async def start_quiz(cmid: int, svc: StudentLMS = Depends(lms)):
    return await svc.start_attempt(cmid)


@app.get("/api/quiz-attempts/{attempt_id}")
async def attempt(attempt_id: int, page: int = Query(0, ge=0), svc: StudentLMS = Depends(lms)):
    data = await svc.attempt_page(attempt_id, page)
    data.pop("_parsed", None)
    return data


class AnswersBody(BaseModel):
    page: int = Field(ge=0)
    answers: dict[str, str] = Field(default_factory=dict)
    finish: bool = False


@app.post("/api/quiz-attempts/{attempt_id}")
async def save_attempt(attempt_id: int, body: AnswersBody, svc: StudentLMS = Depends(lms)):
    return await svc.save_attempt_page(attempt_id, body.page, body.answers, body.finish)


@app.post("/api/quiz-attempts/{attempt_id}/finish")
async def finish_attempt(attempt_id: int, svc: StudentLMS = Depends(lms)):
    return await svc.finish_attempt(attempt_id)


@app.get("/api/quiz-attempts/{attempt_id}/summary")
async def attempt_summary(attempt_id: int, svc: StudentLMS = Depends(lms)):
    return await svc.attempt_summary(attempt_id)


@app.get("/api/quiz-attempts/{attempt_id}/review")
async def attempt_review(attempt_id: int, svc: StudentLMS = Depends(lms)):
    return await svc.attempt_review(attempt_id)


@app.get("/api/grades")
async def grades(svc: StudentLMS = Depends(lms)):
    return {"courses": await svc.all_grades()}


@app.get("/api/grades/{course_id}")
async def course_grades(course_id: int, svc: StudentLMS = Depends(lms)):
    return await svc.grades(course_id)


@app.get("/api/progress")
async def progress(svc: StudentLMS = Depends(lms)):
    ids = await svc.course_ids()
    return {"courses": list(await svc.gather(*(svc.course_progress(cid) for cid in ids)))}


@app.get("/api/calendar")
async def calendar(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"), svc: StudentLMS = Depends(lms)):
    tz = ZoneInfo(settings.LMS_TIMEZONE)
    today = dt.datetime.now(tz)
    year, mon = (int(month[:4]), int(month[5:])) if month else (today.year, today.month)
    if not 1 <= mon <= 12:
        raise HTTPException(400, "Invalid month.")
    start = dt.datetime(year, mon, 1, tzinfo=tz)
    end = dt.datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=tz)
    events = await svc.calendar(int(start.timestamp()), int(end.timestamp()) - 1)
    return {"month": f"{year:04d}-{mon:02d}", "timezone": settings.LMS_TIMEZONE, "events": events}


@app.get("/api/upcoming")
async def upcoming(svc: StudentLMS = Depends(lms)):
    return await svc.upcoming()


@app.get("/api/activity")
async def activity(svc: StudentLMS = Depends(lms)):
    return {"activity": await svc.recent_activity(60)}


@app.get("/api/notifications")
async def notifications(svc: StudentLMS = Depends(lms)):
    return {"notifications": await svc.notifications()}


@app.post("/api/notifications/{moodle_id}/read")
async def notification_read(moodle_id: int, svc: StudentLMS = Depends(lms)):
    await svc.mark_notification_read(moodle_id)
    return {"ok": True}


@app.get("/api/profile")
async def profile(svc: StudentLMS = Depends(lms)):
    data = await svc.profile()
    coach = await mycoach.risk_summary(svc.s.student_id)
    data["program"] = coach.get("declared_major") if coach.get("available") else None
    return data


@app.get("/api/mycoach")
async def my_coach(session: Session = Depends(current_session)):
    # The student ID comes from the server-side session, never from the request.
    return await mycoach.risk_summary(session.student_id)


@app.get("/api/files")
async def file_proxy(url: str, request: Request, session: Session = Depends(current_session)):
    """Streams a Moodle file the student may access, adding their token server-side."""
    moodle: MoodleClient = request.app.state.moodle
    url = unquote(url)
    base = moodle.base_url
    for prefix in (f"{base}/webservice/pluginfile.php/", f"{base}/pluginfile.php/"):
        if url.startswith(prefix):
            url = f"{base}/webservice/pluginfile.php/" + url[len(prefix):].split("?")[0]
            break
    else:
        raise HTTPException(400, "Not a Moodle file.")
    res = await moodle.download(session.token, url)
    if res.status_code != 200 or res.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(404, "File not available.")
    headers = {k: v for k, v in res.headers.items() if k.lower() in {"content-disposition", "content-type"}}
    headers["Cache-Control"] = "private, no-store"
    return Response(content=res.content, headers=headers)


# ---------------------------------------------------------------- built frontend (production)
if settings.FRONTEND_DIST.is_dir():
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = (settings.FRONTEND_DIST / path).resolve()
        if path and target.is_file() and settings.FRONTEND_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(settings.FRONTEND_DIST / "index.html")
