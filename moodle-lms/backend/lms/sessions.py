"""
Server-side sessions. The browser only holds an opaque random id in an HttpOnly cookie;
the student's Moodle token stays in this process's memory (never written to disk,
never sent to the browser). A restart simply signs everyone out.
"""
import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .config import settings


@dataclass
class Session:
    token: str
    moodle_userid: int
    student_id: str
    username: str
    fullname: str
    expires_at: float
    cache: dict[str, tuple[float, Any]] = field(default_factory=dict)
    # cmid -> staged draft item id / files uploaded but not yet submitted
    drafts: dict[int, int] = field(default_factory=dict)
    draft_files: dict[int, list[dict]] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def invalidate(self, *prefixes: str) -> None:
        """Drops cached Moodle answers (all, or those whose key starts with a prefix)."""
        if not prefixes:
            self.cache.clear()
            return
        for key in [k for k in self.cache if k.startswith(prefixes)]:
            self.cache.pop(key, None)

    async def cached(self, key: str, ttl: float, factory: Callable[[], Awaitable[Any]]) -> Any:
        hit = self.cache.get(key)
        now = time.monotonic()
        if hit and hit[0] > now:
            return hit[1]
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:   # concurrent requests for the same key share one Moodle call
            hit = self.cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            value = await factory()
            self.cache[key] = (time.monotonic() + ttl, value)
            return value


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._secret = (settings.SESSION_SECRET or secrets.token_urlsafe(32)).encode()

    def _key(self, sid: str) -> str:
        return hmac.new(self._secret, sid.encode(), hashlib.sha256).hexdigest()

    def create(self, **kwargs) -> tuple[str, Session]:
        self._purge()
        sid = secrets.token_urlsafe(32)
        session = Session(expires_at=time.time() + settings.SESSION_TTL_HOURS * 3600, **kwargs)
        self._sessions[self._key(sid)] = session
        return sid, session

    def get(self, sid: Optional[str]) -> Optional[Session]:
        if not sid:
            return None
        session = self._sessions.get(self._key(sid))
        if session and session.expires_at < time.time():
            self._sessions.pop(self._key(sid), None)
            return None
        return session

    def delete(self, sid: Optional[str]) -> None:
        if sid:
            self._sessions.pop(self._key(sid), None)

    def _purge(self) -> None:
        now = time.time()
        for key in [k for k, s in self._sessions.items() if s.expires_at < now]:
            self._sessions.pop(key, None)


class LoginThrottle:
    """Slows down password guessing: 5 failures per key within 5 minutes locks it for the rest of the window."""

    def __init__(self, limit: int = 5, window: float = 300) -> None:
        self.limit, self.window = limit, window
        self._failures: dict[str, list[float]] = {}

    def blocked(self, key: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = recent
        return len(recent) >= self.limit

    def fail(self, key: str) -> None:
        self._failures.setdefault(key, []).append(time.time())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
