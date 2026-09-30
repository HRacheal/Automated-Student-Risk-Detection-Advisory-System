"""
Configuration for the My Coach LMS backend. Every secret comes from environment
variables / moodle-lms/backend/.env and never reaches the browser.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # Moodle site root (the REST endpoint, login/token.php and upload.php are resolved from it)
    MOODLE_URL: str = os.getenv("MOODLE_URL", "").rstrip("/")
    # External service that per-student tokens are issued for (see moodle-setup/setup_lms_service.php)
    MOODLE_SERVICE: str = os.getenv("MOODLE_SERVICE", "mycoach_lms")
    # Optional read-only service token, used ONLY to resolve "student ID -> Moodle username" at sign-in
    MOODLE_LOOKUP_TOKEN: str = os.getenv("MOODLE_LOOKUP_TOKEN", "")
    MOODLE_TIMEOUT_SECONDS: float = float(os.getenv("MOODLE_TIMEOUT_SECONDS", "45"))
    MOODLE_PARALLEL_CALLS: int = int(os.getenv("MOODLE_PARALLEL_CALLS", "8"))

    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    SESSION_TTL_HOURS: float = float(os.getenv("SESSION_TTL_HOURS", "8"))
    SESSION_COOKIE: str = "mycoach_lms_session"
    COOKIE_SECURE: bool = _bool("COOKIE_SECURE", False)   # set true behind HTTPS
    # Browser origins allowed to call the API cross-site (e.g. the GitHub Pages frontend). Requests from
    # these get CORS credentials and a SameSite=None; Secure session cookie; all others keep SameSite=Lax.
    CORS_ORIGINS: list[str] = [o.strip().rstrip("/") for o in
                               os.getenv("CORS_ORIGINS", "https://hracheal.github.io").split(",") if o.strip()]

    # My Coach (risk engine) - server-to-server only
    MYCOACH_API_URL: str = os.getenv("MYCOACH_API_URL", "").rstrip("/")
    MYCOACH_INTEGRATION_KEY: str = os.getenv("MYCOACH_INTEGRATION_KEY", "")
    MYCOACH_PORTAL_URL: str = os.getenv("MYCOACH_PORTAL_URL", "http://localhost:3000/student")

    LMS_TIMEZONE: str = os.getenv("LMS_TIMEZONE", "Africa/Nairobi")
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))

    FRONTEND_DIST: Path = BACKEND_DIR.parent / "frontend" / "dist"


settings = Settings()
