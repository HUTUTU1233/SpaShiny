from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    mode: str
    session_id: str | None = None
    user_id: str | None = None

    @property
    def is_cloud(self) -> bool:
        return self.mode == "cloud"

    @property
    def is_desktop(self) -> bool:
        return self.mode == "desktop"


def cloud_context(session_id: str) -> RequestContext:
    return RequestContext(mode="cloud", session_id=str(session_id), user_id=None)


def desktop_context(user_id: str = "default") -> RequestContext:
    return RequestContext(mode="desktop", session_id=None, user_id=str(user_id))
