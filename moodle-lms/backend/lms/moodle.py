"""
Thin async client for Moodle's REST web services.

Every student-facing call is made with THAT student's own token (issued by Moodle's
login/token.php for the mycoach_lms service), so Moodle itself enforces what the
student may see or change. Tokens only ever live in this process.
"""
from typing import Any, Optional

import httpx

from .config import settings


class MoodleUnavailable(Exception):
    """Moodle could not be reached / did not answer. Never answered with fake data."""


class MoodleAuthError(Exception):
    """Wrong credentials, or a token Moodle no longer accepts."""


class MoodleError(Exception):
    def __init__(self, errorcode: str, message: str, function: str = ""):
        super().__init__(message)
        self.errorcode = errorcode or "error"
        self.message = message or "Moodle reported an error."
        self.function = function


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    """Encodes nested params the way Moodle's REST server expects: a[0][b]=1."""
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(f"{prefix}[{key}]", item, out)
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _flatten(f"{prefix}[{i}]", item, out)
    elif isinstance(value, bool):
        out[prefix] = int(value)
    elif value is not None:
        out[prefix] = value


def encode_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in params.items():
        _flatten(key, value, out)
    return out


READ_ONLY_PREFIXES = ("core_webservice_get_", "core_user_get_", "core_enrol_get_", "core_course_get_",
                      "core_calendar_get_", "core_completion_get_", "core_message_get_", "gradereport_user_get_",
                      "message_popup_get_", "mod_assign_get_", "mod_quiz_get_", "mod_resource_get_",
                      "mod_page_get_", "mod_forum_get_")


def is_read_only(function: str) -> bool:
    return function.startswith(READ_ONLY_PREFIXES)


class MoodleClient:
    def __init__(self, base_url: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = (base_url or settings.MOODLE_URL).rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.MOODLE_TIMEOUT_SECONDS, connect=5),
            # Apache closes idle keep-alive connections after 5 s; drop ours before that.
            limits=httpx.Limits(keepalive_expiry=2),
            transport=transport,
        )

    @property
    def rest_url(self) -> str:
        return f"{self.base_url}/webservice/rest/server.php"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _post(self, url: str, retry_safe: bool = False, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise MoodleUnavailable("MOODLE_URL is not configured.")
        try:
            try:
                res = await self.client.post(url, **kwargs)
            except (httpx.RemoteProtocolError, httpx.ReadError):
                # A pooled connection the server had already closed. Only read-only calls are
                # retried, so a submission can never be sent twice.
                if not retry_safe:
                    raise
                res = await self.client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            raise MoodleUnavailable(f"Moodle is not reachable ({exc.__class__.__name__}).") from exc
        if res.status_code >= 500 or res.status_code == 404:
            raise MoodleUnavailable(f"Moodle answered HTTP {res.status_code}.")
        return res

    async def call(self, token: str, function: str, **params: Any) -> Any:
        data = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **encode_params(params)}
        res = await self._post(self.rest_url, retry_safe=is_read_only(function), data=data)
        try:
            body = res.json()
        except ValueError as exc:
            raise MoodleUnavailable(f"Moodle returned a non-JSON response to {function}.") from exc
        if isinstance(body, dict) and body.get("exception"):
            code = body.get("errorcode", "")
            if code in {"invalidtoken", "accessexception"}:
                raise MoodleAuthError(body.get("message") or "Your Moodle session is no longer valid.")
            raise MoodleError(code, body.get("message", ""), function)
        return body

    async def login(self, username: str, password: str) -> str:
        """Moodle's own credential check; returns a per-user token for the LMS service."""
        res = await self._post(f"{self.base_url}/login/token.php",
                               data={"username": username, "password": password,
                                     "service": settings.MOODLE_SERVICE})
        try:
            body = res.json()
        except ValueError as exc:
            raise MoodleUnavailable("Moodle returned an unexpected sign-in response.") from exc
        if body.get("token"):
            return body["token"]
        code = body.get("errorcode", "")
        if code in {"invalidlogin", "usernamenotfound"}:
            raise MoodleAuthError("Invalid student ID or password.")
        if code in {"servicenotavailable", "enablewsdescription", "cannotcreatetoken", "sitemaintenance"}:
            raise MoodleError(code, "Moodle sign-in for the LMS app is not enabled. Run moodle-setup/setup_lms_service.php.")
        raise MoodleAuthError(body.get("error") or "Sign-in failed.")

    async def upload_draft(self, token: str, filename: str, content: bytes, itemid: int = 0) -> list[dict]:
        """Stores a file in the user's own draft area (webservice/upload.php)."""
        res = await self._post(f"{self.base_url}/webservice/upload.php",
                               data={"token": token, "filearea": "draft", "itemid": str(itemid)},
                               files={"file_1": (filename, content)})
        try:
            body = res.json()
        except ValueError as exc:
            raise MoodleUnavailable("Moodle returned an unexpected upload response.") from exc
        if isinstance(body, dict) and (body.get("error") or body.get("exception")):
            if body.get("errorcode") == "invalidtoken":
                raise MoodleAuthError("Your Moodle session is no longer valid.")
            raise MoodleError(body.get("errorcode", "uploadfailed"), body.get("error") or body.get("message", "Upload failed."))
        if not isinstance(body, list) or not body:
            raise MoodleError("uploadfailed", "Moodle did not store the file.")
        return body

    async def download(self, token: str, url: str) -> httpx.Response:
        """Fetches a pluginfile URL as the token owner (Moodle checks the file permission)."""
        if not self.base_url:
            raise MoodleUnavailable("MOODLE_URL is not configured.")
        try:
            res = await self.client.get(url, params={"token": token})
        except httpx.HTTPError as exc:
            raise MoodleUnavailable(f"Moodle is not reachable ({exc.__class__.__name__}).") from exc
        return res
