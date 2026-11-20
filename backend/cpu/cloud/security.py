from __future__ import annotations

import hashlib
import posixpath
import re
import shlex
from pathlib import Path


SECRET_PATTERNS = (
    re.compile(r"(RUNPOD_API_KEY=)[^\s]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^'\"\s]+", re.IGNORECASE),
    re.compile(r"(token['\"]?\s*[:=]\s*['\"]?)[^'\"\s]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(/opt/spashiny/secrets/)[^\s]+", re.IGNORECASE),
)


def redact_secrets(text: str) -> str:
    value = str(text)
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(r"\1<redacted>", value)
    return value


def shell_quote(value: object) -> str:
    return shlex.quote(str(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_remote_path(remote_root: str, remote_path: str) -> str:
    root = posixpath.normpath("/" + str(remote_root).strip("/"))
    raw = str(remote_path or "").replace("\\", "/")
    if not raw:
        raise ValueError("Remote path is empty.")

    if raw.startswith("/"):
        normalized = posixpath.normpath(raw)
    else:
        normalized = posixpath.normpath(posixpath.join(root, raw))

    if normalized != root and not normalized.startswith(root + "/"):
        raise ValueError(f"Remote path escapes the job root: {remote_path}")
    return normalized


def safe_remote_join(remote_root: str, *parts: str) -> str:
    return safe_remote_path(remote_root, posixpath.join(*[str(part).strip("/") for part in parts if str(part) != ""]))
