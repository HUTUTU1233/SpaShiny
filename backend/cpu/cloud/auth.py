from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass


class AuthError(PermissionError):
    """Raised when a cloud API request is not authenticated."""


@dataclass(frozen=True)
class UserContext:
    user_id: str
    is_admin: bool = False


def hash_token(token: str, secret: str | None = None) -> str:
    secret = secret or os.environ.get("SPASHINY_SECRET_KEY", "")
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def require_user(user_id: str | None) -> UserContext:
    if not user_id:
        raise AuthError("A user id is required.")
    return UserContext(user_id=str(user_id), is_admin=False)


def require_admin(user: UserContext) -> UserContext:
    if not user.is_admin:
        raise AuthError("Administrator permission is required.")
    return user


class RateLimiter:
    def __init__(self, max_events: int = 20, window_seconds: int = 3600) -> None:
        self.max_events = int(max_events)
        self.window_seconds = int(window_seconds)
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        events = [ts for ts in self._events.get(key, []) if now - ts <= self.window_seconds]
        if len(events) >= self.max_events:
            self._events[key] = events
            return False
        events.append(now)
        self._events[key] = events
        return True
