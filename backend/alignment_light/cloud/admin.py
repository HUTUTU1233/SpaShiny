from __future__ import annotations

from .auth import UserContext, require_admin
from .healthcheck import HealthChecker


class AdminService:
    def __init__(self, health: HealthChecker | None = None) -> None:
        self.health = health or HealthChecker()

    def resource_status(self, user: UserContext) -> dict:
        require_admin(user)
        return self.health.resource_status(include_admin=True)
