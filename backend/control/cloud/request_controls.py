from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RateLimitExceeded(Exception):
    category: str
    retry_after: int

    def __str__(self) -> str:
        return "Too many requests. Please wait before trying again."


class SlidingWindowRateLimiter:
    """Small process-local limiter for HTTP controls, deliberately DB-free.

    Status polling and authentication failures must not add SQLite write
    traffic.  The key is a salted digest and records live only in memory.
    """

    def __init__(self, *, secret: str) -> None:
        self._secret = str(secret or "spashiny-rate-limit").encode("utf-8")
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, *, category: str, subject: str, limit: int, window_seconds: int) -> None:
        cap = max(0, int(limit))
        if not cap:
            return
        window = max(1, int(window_seconds))
        key = self._key(category, subject)
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - window
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= cap:
                retry_after = max(1, int(events[0] + window - now + 0.999))
                raise RateLimitExceeded(category=str(category), retry_after=retry_after)
            events.append(now)

    def _key(self, category: str, subject: str) -> str:
        payload = f"{str(category)}\x1f{str(subject)}".encode("utf-8")
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ClientIpIdentity:
    source: str
    masked_ip: str
    hashed_ip: str


class ClientIpResolver:
    """Use CF-Connecting-IP only from a configured, trusted proxy peer."""

    def __init__(self, *, trusted_proxy_cidrs: tuple[str, ...], secret: str) -> None:
        self._trusted_networks = tuple(
            network
            for item in trusted_proxy_cidrs
            for network in self._parse_network(item)
        )
        self._secret = str(secret or "spashiny-security-audit").encode("utf-8")

    def resolve(self, *, peer_ip: str, headers: Any) -> ClientIpIdentity:
        peer = self._parse_ip(peer_ip)
        candidate = peer
        source = "PEER_IP"
        if peer is not None and self._is_trusted_proxy(peer):
            forwarded = self._parse_ip(str(headers.get("cf-connecting-ip") or "").strip())
            if forwarded is not None:
                candidate = forwarded
                source = "CF_CONNECTING_IP"
        if candidate is None:
            return ClientIpIdentity(source="UNKNOWN", masked_ip="", hashed_ip="")
        raw = str(candidate)
        digest = hmac.new(self._secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return ClientIpIdentity(source=source, masked_ip=self._mask(candidate), hashed_ip=digest)

    @staticmethod
    def _parse_network(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        try:
            return (ipaddress.ip_network(str(value).strip(), strict=False),)
        except ValueError:
            return ()

    @staticmethod
    def _parse_ip(value: str):
        try:
            return ipaddress.ip_address(str(value).strip())
        except ValueError:
            return None

    def _is_trusted_proxy(self, peer) -> bool:
        return any(peer in network for network in self._trusted_networks)

    @staticmethod
    def _mask(address) -> str:
        if isinstance(address, ipaddress.IPv4Address):
            return str(ipaddress.ip_network(f"{address}/24", strict=False).network_address) + "/24"
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address) + "/64"


class SecurityAuditLogger:
    """Append only minimized records; raw IPs, tokens and paths are excluded."""

    def __init__(self, *, enabled: bool, log_dir: Path, secret: str) -> None:
        self.enabled = bool(enabled)
        self.path = Path(log_dir) / "security-audit.log"
        self._secret = str(secret or "spashiny-security-audit").encode("utf-8")
        self._lock = threading.Lock()

    def record(
        self,
        *,
        event_type: str,
        success: bool,
        identity: ClientIpIdentity,
        owner_identifier: str = "",
        user_agent: str = "",
        endpoint_category: str = "",
    ) -> None:
        if not self.enabled:
            return
        owner_hash = (
            hmac.new(self._secret, str(owner_identifier).encode("utf-8"), hashlib.sha256).hexdigest()[:24]
            if owner_identifier
            else ""
        )
        record = {
            "timestamp": int(time.time()),
            "event_type": str(event_type)[:80],
            "success": bool(success),
            "masked_ip": identity.masked_ip,
            "ip_hash": identity.hashed_ip,
            "user_agent_family": str(user_agent or "").split(" ", 1)[0][:80],
            "owner_hash": owner_hash,
            "endpoint_category": str(endpoint_category)[:80],
        }
        line = json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)


def admin_token_matches(*, expected: str | None, supplied: str | None) -> bool:
    configured = str(expected or "")
    return bool(configured and supplied and hmac.compare_digest(configured, str(supplied)))
