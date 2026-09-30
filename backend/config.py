# backend/config.py
"""
Central configuration. Every secret (DB URL, API tokens, JWT secret, advisor
password) is read from environment variables / backend/.env — never hard-coded.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Settings:
    # Application database (alerts, anomaly history, interventions, sync runs)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # RosarioSIS REST_API plugin (api.php); auth.php is resolved next to it
    ROSARIO_API_URL: str = os.getenv("ROSARIO_API_URL", "")
    ROSARIO_API_TOKEN: str = os.getenv("ROSARIO_API_TOKEN", "")

    # Moodle REST web services endpoint (webservice/rest/server.php)
    MOODLE_API_URL: str = os.getenv("MOODLE_API_URL", "")
    MOODLE_API_TOKEN: str = os.getenv("MOODLE_API_TOKEN", "")

    EXTERNAL_TIMEOUT_SECONDS: float = float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "10"))
    # Moodle bulk calls (all assignments / submissions) can take >10 s on a cold start.
    MOODLE_READ_TIMEOUT_SECONDS: float = float(os.getenv("MOODLE_READ_TIMEOUT_SECONDS", "60"))

    # Role-based sign-in (Student / Advisor / Admin). A role whose e-mail or
    # password is empty is treated as "not configured" and cannot sign in.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "8"))
    ADVISOR_EMAIL: str = os.getenv("ADVISOR_EMAIL", "").strip().lower()
    ADVISOR_PASSWORD: str = os.getenv("ADVISOR_PASSWORD", "")
    ADVISOR_NAME: str = os.getenv("ADVISOR_NAME", "Academic Advisor")
    STUDENT_EMAIL: str = os.getenv("STUDENT_EMAIL", "").strip().lower()
    STUDENT_PASSWORD: str = os.getenv("STUDENT_PASSWORD", "")
    STUDENT_NAME: str = os.getenv("STUDENT_NAME", "Student")
    # RosarioSIS student_id this student account is linked to (their own record only)
    STUDENT_ID: str = os.getenv("STUDENT_ID", "").strip()
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "System Administrator")

    # Controlled local test data (clearly labelled DEMO in the UI). Never
    # written to RosarioSIS or Moodle.
    DEMO_DATA_ENABLED: bool = _bool("DEMO_DATA_ENABLED", True)

    # Shared key for the My Coach LMS app (moodle-lms/) server-to-server risk summary.
    # Empty => the integration endpoint is disabled.
    LMS_INTEGRATION_KEY: str = os.getenv("LMS_INTEGRATION_KEY", "")

    CORS_ORIGINS: list[str] = _list(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://192.168.56.1:3000,"
        "https://automated-student-risk-detection-ad.vercel.app",
    )


settings = Settings()


def missing_required_settings() -> list[str]:
    missing = []
    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL")
    if not settings.JWT_SECRET:
        missing.append("JWT_SECRET")
    if not settings.ADVISOR_EMAIL or not settings.ADVISOR_PASSWORD:
        missing.append("ADVISOR_EMAIL/ADVISOR_PASSWORD")
    return missing
