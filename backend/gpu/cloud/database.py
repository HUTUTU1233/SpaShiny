from __future__ import annotations

import gzip
import inspect
import json
import multiprocessing
import os
import re
import secrets
import shutil
import sqlite3
import threading
import traceback
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import SpaShinyCloudConfig, load_cloud_config
from .models import (
    ACTIVE_JOB_STATUSES,
    JOBS_COLUMNS,
    UPLOADS_COLUMNS,
    CleanupRetryStatus,
    JobRecord,
    JobStatus,
    ResourceType,
    UploadRecord,
    UploadStatus,
    WorkerStatus,
    row_to_job,
    row_to_upload,
    validate_job_status_transition,
)


SCHEMA_VERSION = 15


def _configured_sqlite_file_mode() -> int:
    """Parse the optional TEST file mode; preserve the historical default."""
    value = os.environ.get("SPASHINY_SQLITE_FILE_MODE")
    if value is None:
        return 0o666
    value = value.strip().lower()
    if re.fullmatch(r"(?:0o[0-7]{3}|0[0-7]{3})", value) is None:
        raise ValueError("SPASHINY_SQLITE_FILE_MODE must be an octal mode such as 0660 or 0o660")
    return int(value, 8)


RUNPOD_INSTANCE_TERMINAL_STATES = {
    "TERMINATED",
    "CREATE_FAILED",
    "READY_TIMEOUT",
}


# TEST-only diagnostic context.  It is intentionally observational: callers
# label a bounded write path and CloudDatabase emits the label only when
# SPASHINY_DB_DEBUG=1.  It does not alter SQLite connection or transaction
# semantics.
_DB_DEBUG_STAGE: ContextVar[str] = ContextVar("spashiny_db_debug_stage", default="")
_DB_DEBUG_SQL_SEQUENCE: ContextVar[tuple[str, ...]] = ContextVar(
    "spashiny_db_debug_sql_sequence", default=()
)
_DB_FORENSIC_CONTEXT: ContextVar[dict[str, str]] = ContextVar(
    "spashiny_db_forensic_context", default={}
)


@contextmanager
def db_debug_stage(stage: str) -> Iterator[None]:
    token = _DB_DEBUG_STAGE.set(str(stage or ""))
    try:
        yield
    finally:
        _DB_DEBUG_STAGE.reset(token)


@contextmanager
def db_forensic_context(
    *,
    worker_id: str = "",
    job_id: str = "",
    workflow: str = "",
    operation: str = "",
) -> Iterator[None]:
    """Attach non-sensitive worker/job identifiers to TEST forensic records."""
    context = {
        "worker_id": str(worker_id or ""),
        "job_id": str(job_id or ""),
        "workflow": str(workflow or ""),
        "operation": str(operation or ""),
    }
    token = _DB_FORENSIC_CONTEXT.set(context)
    try:
        yield
    finally:
        _DB_FORENSIC_CONTEXT.reset(token)


class DatabaseError(RuntimeError):
    """Raised when the SpaShiny cloud database operation fails."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _heartbeat_debug_enabled() -> bool:
    """Keep the TEST diagnostic bounded to the worker heartbeat by default."""
    return os.environ.get("SPASHINY_DB_DEBUG") == "1"


def _db_path_snapshot(path: Path) -> dict[str, Any]:
    """Read filesystem identity only; never create, open, or modify a DB file."""
    try:
        resolved = path.resolve(strict=False)
        stat = resolved.stat()
        return {
            "path": str(path),
            "realpath": str(resolved),
            "exists": True,
            "dev": stat.st_dev,
            "inode": stat.st_ino,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
            "mode": oct(stat.st_mode & 0o777),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    except FileNotFoundError:
        return {"path": str(path), "realpath": str(path.resolve(strict=False)), "exists": False}
    except Exception as exc:
        return {"path": str(path), "snapshot_error": f"{type(exc).__name__}: {exc}"}


def _mount_flags_for(path: Path) -> dict[str, str]:
    """Read this process mount namespace without invoking a subprocess."""
    try:
        target = str(path.resolve(strict=False))
        best: tuple[int, str, str] | None = None
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if "-" not in fields or len(fields) < 6:
                continue
            mountpoint = fields[4].replace("\\040", " ").replace("\\011", "\t")
            if target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/"):
                candidate = (len(mountpoint), mountpoint, fields[5])
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best is not None:
            return {"mountpoint": best[1], "mount_flags": best[2]}
    except Exception as exc:
        return {"mount_error": f"{type(exc).__name__}: {exc}"}
    return {}


def _sqlite_fd_flags(database: "CloudDatabase") -> dict[str, list[dict[str, Any]]]:
    """Inspect only descriptors already held by this worker process."""
    targets = {
        "db": str(database.path.resolve(strict=False)),
        "wal": str(Path(str(database.path) + "-wal").resolve(strict=False)),
        "shm": str(Path(str(database.path) + "-shm").resolve(strict=False)),
    }
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in targets}
    try:
        for fd_path in Path("/proc/self/fd").iterdir():
            try:
                target = os.readlink(fd_path).removesuffix(" (deleted)")
                for name, expected in targets.items():
                    if target != expected:
                        continue
                    fields = (Path("/proc/self/fdinfo") / fd_path.name).read_text(encoding="utf-8").splitlines()
                    raw = next((line.split("\t", 1)[1] for line in fields if line.startswith("flags:")), "")
                    flags = int(raw, 8) if raw else 0
                    access_mode = flags & os.O_ACCMODE
                    access = {os.O_RDONLY: "O_RDONLY", os.O_WRONLY: "O_WRONLY", os.O_RDWR: "O_RDWR"}.get(
                        access_mode, str(access_mode)
                    )
                    result[name].append({"fd": fd_path.name, "flags_octal": raw, "access": access})
            except Exception:
                continue
    except Exception as exc:
        result["fd_snapshot_error"] = [{"error": f"{type(exc).__name__}: {exc}"}]
    return result


def _forensic_log_path() -> Path | None:
    """Return the explicitly configured TEST-only forensic sink, if any."""
    if os.environ.get("SPASHINY_DB_DEBUG") != "1":
        return None
    configured = os.environ.get("SPASHINY_SQLITE_FORENSIC_LOG", "").strip()
    return Path(configured) if configured else None


def _bounded_positive_int(name: str, default: int, *, lower: int, upper: int) -> int:
    try:
        return max(lower, min(upper, int(os.environ.get(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _rotate_forensic_log(path: Path, incoming_bytes: int) -> None:
    """Bound only the dedicated TEST forensic stream; never touch normal logs."""
    try:
        max_bytes = _bounded_positive_int(
            "SPASHINY_SQLITE_FORENSIC_MAX_BYTES", 150 * 1024 * 1024, lower=1 * 1024 * 1024, upper=200 * 1024 * 1024
        )
        keep = _bounded_positive_int("SPASHINY_SQLITE_FORENSIC_ROTATE_COUNT", 7, lower=1, upper=10)
        if not path.exists() or path.stat().st_size + incoming_bytes <= max_bytes:
            return
        for index in range(keep, 1, -1):
            source = Path(f"{path}.{index - 1}.gz")
            destination = Path(f"{path}.{index}.gz")
            if source.exists():
                os.replace(source, destination)
        raw_rotated = Path(f"{path}.1")
        if raw_rotated.exists():
            raw_rotated.unlink()
        os.replace(path, raw_rotated)
        compressed_tmp = Path(f"{path}.1.gz.tmp")
        compressed = Path(f"{path}.1.gz")
        with raw_rotated.open("rb") as source, compressed_tmp.open("wb") as raw_target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_target, mtime=0) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            raw_target.flush()
            os.fsync(raw_target.fileno())
        os.replace(compressed_tmp, compressed)
        raw_rotated.unlink()
    except Exception:
        # Rotation must never mask the SQLite failure that triggered evidence capture.
        return


def _sql_summary(statement: str) -> dict[str, str]:
    normalized = " ".join(str(statement or "").split())
    tokens = normalized.split()
    verb = tokens[0].upper() if tokens else ""
    table = ""
    upper = [token.upper() for token in tokens]
    try:
        if verb == "UPDATE" and len(tokens) > 1:
            table = tokens[1]
        elif verb == "INSERT" and "INTO" in upper:
            table = tokens[upper.index("INTO") + 1]
        elif verb in {"DELETE", "SELECT"} and "FROM" in upper:
            table = tokens[upper.index("FROM") + 1]
    except (IndexError, ValueError):
        table = ""
    return {"sql_verb": verb, "sql_table": table, "sql_operation": normalized[:1000]}


def _durable_forensic_write(payload: dict[str, Any]) -> None:
    """Append one error record with flush+fsync so a following restart cannot lose it."""
    path = _forensic_log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        _rotate_forensic_log(path, len(encoded))
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            offset = 0
            while offset < len(encoded):
                offset += os.write(descriptor, encoded[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        # The original SQLite error must always preserve its propagation semantics.
        return


def _heartbeat_runtime_debug(
    *,
    event: str,
    database: "CloudDatabase",
    conn: sqlite3.Connection | None = None,
    failure_stage: str = "",
    error: BaseException | None = None,
    worker_id: str = "",
) -> None:
    """Emit bounded TEST-only heartbeat evidence without altering the operation."""
    if not _heartbeat_debug_enabled():
        return
    if error is None and os.environ.get("SPASHINY_DB_DEBUG_VERBOSE") != "1":
        return
    try:
        db = _db_path_snapshot(database.path)
        parent = _db_path_snapshot(database.path.parent)
        wal = _db_path_snapshot(Path(str(database.path) + "-wal"))
        shm = _db_path_snapshot(Path(str(database.path) + "-shm"))
        payload: dict[str, Any] = {
            "timestamp": utc_now(),
            "event": event,
            "pid": os.getpid(),
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
            "db": db,
            "parent": parent,
            "wal": wal,
            "shm": shm,
            "mount": _mount_flags_for(database.path),
            "fd_flags": _sqlite_fd_flags(database),
            "read_only": database.read_only,
            "failure_stage": failure_stage,
            "sql_sequence": list(_DB_DEBUG_SQL_SEQUENCE.get()),
            "transaction_mode": "autocommit (isolation_level=None)",
            "begin_ok": "NOT_APPLICABLE_AUTOCOMMIT",
            **_DB_FORENSIC_CONTEXT.get(),
        }
        if worker_id:
            payload["worker_id"] = str(worker_id)
        if conn is not None:
            payload["connection_id"] = id(conn)
            payload["connection_in_transaction"] = bool(conn.in_transaction)
            try:
                payload["pragma_query_only"] = conn.execute("PRAGMA query_only").fetchone()[0]
                payload["pragma_journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
                payload["pragma_locking_mode"] = conn.execute("PRAGMA locking_mode").fetchone()[0]
                payload["pragma_busy_timeout"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            except Exception as pragma_exc:
                payload["pragma_snapshot_error"] = f"{type(pragma_exc).__name__}: {pragma_exc}"
        if error is not None:
            payload["sqlite_error_type"] = type(error).__name__
            payload["sqlite_error_message"] = str(error)
            payload["sqlite_errorcode"] = getattr(error, "sqlite_errorcode", None)
            payload["sqlite_errorname"] = getattr(error, "sqlite_errorname", None)
            payload["traceback"] = traceback.format_exc(limit=30)
            payload.update(_sql_summary(" ".join(_DB_DEBUG_SQL_SEQUENCE.get()) or "UPDATE worker_instances"))
            _durable_forensic_write(payload)
        if os.environ.get("SPASHINY_DB_DEBUG_VERBOSE") == "1":
            print("SPASHINY_HEARTBEAT_DB_DEBUG=" + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    except Exception:
        # Observability must never alter heartbeat exception propagation.
        return


def _runtime_db_debug(
    *,
    event: str,
    database: "CloudDatabase",
    conn: sqlite3.Connection | None = None,
    connection_created_at: str = "",
    connection_debug_id: str = "",
    last_sql: str = "",
    error: BaseException | None = None,
) -> None:
    """Emit TEST-only SQLite connection identity diagnostics when enabled."""
    if os.environ.get("SPASHINY_DB_DEBUG") != "1":
        return
    # The earlier generic logger emitted every connection and grew to gigabytes.
    # Keep non-heartbeat records only for errors unless explicitly requested.
    if event != "operation_error" and os.environ.get("SPASHINY_DB_DEBUG_VERBOSE") != "1":
        return
    try:
        try:
            stat = database.path.resolve().stat()
            device_inode = f"{stat.st_dev}:{stat.st_ino}"
        except Exception:
            device_inode = ""
        frames = inspect.stack(context=0)[2:9]
        callers = [f"{Path(frame.filename).name}:{frame.function}" for frame in frames]
        payload: dict[str, Any] = {
            "timestamp": utc_now(),
            "event": event,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "uid": os.getuid(),
            "gid": os.getgid(),
            "thread": threading.get_ident(),
            "process_name": multiprocessing.current_process().name,
            "caller_function": callers[0] if callers else "",
            "callers": callers,
            "db_operation_stage": _DB_DEBUG_STAGE.get(),
            "db_realpath": str(database.path.resolve()),
            "device_inode": device_inode,
            "read_only": database.read_only,
            "connection_created_time": connection_created_at,
            "connection_debug_id": connection_debug_id,
            "connection_id": id(conn) if conn is not None else None,
            "connection_uri": f"file:{database.path}?mode=ro" if database.read_only else str(database.path),
            "sqlite_version": sqlite3.sqlite_version,
            "sqlite_module_version": sqlite3.version,
            "db": _db_path_snapshot(database.path),
            "parent": _db_path_snapshot(database.path.parent),
            "wal": _db_path_snapshot(Path(str(database.path) + "-wal")),
            "shm": _db_path_snapshot(Path(str(database.path) + "-shm")),
            "mount": _mount_flags_for(database.path),
            "fd_flags": _sqlite_fd_flags(database),
            **_DB_FORENSIC_CONTEXT.get(),
        }
        if conn is not None:
            payload["connection_in_transaction"] = bool(conn.in_transaction)
            try:
                payload["pragma_query_only"] = conn.execute("PRAGMA query_only").fetchone()[0]
                payload["pragma_journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
                payload["pragma_locking_mode"] = conn.execute("PRAGMA locking_mode").fetchone()[0]
                payload["pragma_synchronous"] = conn.execute("PRAGMA synchronous").fetchone()[0]
                payload["pragma_busy_timeout"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
                payload["pragma_temp_store"] = conn.execute("PRAGMA temp_store").fetchone()[0]
            except Exception as pragma_exc:
                payload["pragma_snapshot_error"] = f"{type(pragma_exc).__name__}: {pragma_exc}"
        if last_sql:
            payload.update(_sql_summary(last_sql))
        payload["failure_stage"] = "CONNECT" if conn is None else (payload.get("sql_verb") or "OTHER")
        if error is not None:
            # Test-only diagnosis: retain SQLite's native subtype when the
            # runtime exposes it.  This must never affect propagation.
            payload["sqlite_error_type"] = type(error).__name__
            payload["sqlite_error_message"] = str(error)
            payload["sqlite_errorcode"] = getattr(error, "sqlite_errorcode", None)
            payload["sqlite_errorname"] = getattr(error, "sqlite_errorname", None)
            payload["sqlite_error"] = repr(error)
            payload["traceback"] = traceback.format_exc(limit=30)
            _durable_forensic_write(payload)
        if os.environ.get("SPASHINY_DB_DEBUG_VERBOSE") == "1":
            print("SPASHINY_DB_DEBUG=" + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    except Exception:
        # Diagnostics must not mask or change the original database operation.
        return


class CloudDatabase:
    def __init__(
        self,
        path: Path | None = None,
        config: SpaShinyCloudConfig | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        self.config = config or load_cloud_config()
        self.read_only = bool(read_only)
        if path is not None:
            self.path = Path(path)
        elif self.config.is_lab_profile:
            self.path = Path(self.config.lab_sqlite_root) / "spashiny_cloud.sqlite3"
        else:
            self.path = self.config.workspace / "spashiny_cloud.sqlite3"
        if not self.read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_shared_sqlite_permissions()
            self.init_db()
            self._ensure_shared_sqlite_permissions()

    def _ensure_shared_sqlite_permissions(self) -> None:
        """Best-effort permissions for rootless Docker + host-native workers sharing SQLite."""
        mode = _configured_sqlite_file_mode()
        for candidate in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            try:
                if candidate.exists():
                    candidate.chmod(mode)
            except Exception:
                pass

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn: sqlite3.Connection | None = None
        connection_created_at = ""
        connection_debug_id = secrets.token_hex(12)
        last_sql = ""
        sql_sequence: list[str] = []
        sequence_token = _DB_DEBUG_SQL_SEQUENCE.set(())

        def _remember_sql(statement: str) -> None:
            nonlocal last_sql
            last_sql = statement
            if _DB_DEBUG_STAGE.get() == "WORKER_HEARTBEAT":
                sql_sequence.append(" ".join(statement.split())[:1000])
                _DB_DEBUG_SQL_SEQUENCE.set(tuple(sql_sequence))
            normalized = statement.strip().upper()
            if os.environ.get("SPASHINY_DB_DEBUG") == "1" and normalized in {"BEGIN", "BEGIN IMMEDIATE", "COMMIT", "ROLLBACK"}:
                _runtime_db_debug(
                    event=f"transaction_{normalized.lower().replace(' ', '_')}",
                    database=self,
                    conn=conn,
                    connection_created_at=connection_created_at,
                    connection_debug_id=connection_debug_id,
                    last_sql=statement,
                )

        try:
            if self.read_only:
                conn = sqlite3.connect(
                    f"file:{self.path}?mode=ro",
                    uri=True,
                    timeout=30,
                    isolation_level=None,
                )
            else:
                self._ensure_shared_sqlite_permissions()
                conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
            connection_created_at = utc_now()
            conn.set_trace_callback(_remember_sql)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if not self.read_only:
                conn.execute("PRAGMA journal_mode = WAL")
                if "SPASHINY_SQLITE_FILE_MODE" in os.environ:
                    self._ensure_shared_sqlite_permissions()
            conn.execute("PRAGMA busy_timeout = 30000")
            _runtime_db_debug(
                event="connection_open",
                database=self,
                conn=conn,
                connection_created_at=connection_created_at,
                connection_debug_id=connection_debug_id,
                last_sql=last_sql,
            )
            yield conn
        except Exception as exc:
            _runtime_db_debug(
                event="operation_error",
                database=self,
                conn=conn,
                connection_created_at=connection_created_at,
                connection_debug_id=connection_debug_id,
                last_sql=last_sql,
                error=exc,
            )
            raise
        finally:
            if conn is not None:
                _runtime_db_debug(
                    event="connection_close",
                    database=self,
                    conn=conn,
                    connection_created_at=connection_created_at,
                    connection_debug_id=connection_debug_id,
                    last_sql=last_sql,
                )
                conn.close()
                if not self.read_only and "SPASHINY_SQLITE_FILE_MODE" in os.environ:
                    self._ensure_shared_sqlite_permissions()
            _DB_DEBUG_SQL_SEQUENCE.reset(sequence_token)

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._create_base_schema(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.apply_migrations()
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def _create_base_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workflow TEXT NOT NULL,
                workflow_name TEXT NOT NULL DEFAULT '',
                session_id TEXT,
                owner_session_id TEXT NOT NULL DEFAULT '',
                analysis_session_id TEXT NOT NULL DEFAULT '',
                anonymous_workspace_id TEXT NOT NULL DEFAULT '',
                resource_type TEXT NOT NULL DEFAULT 'gpu',
                execution_backend TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                progress REAL NOT NULL DEFAULT 0,
                current_step TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                parameters_json TEXT NOT NULL DEFAULT '{}',
                local_workspace TEXT NOT NULL DEFAULT '',
                remote_workspace TEXT NOT NULL DEFAULT '',
                runpod_pod_id TEXT NOT NULL DEFAULT '',
                remote_pid INTEGER,
                queue_name TEXT NOT NULL DEFAULT 'gpu',
                requested_resource TEXT NOT NULL DEFAULT '',
                assigned_gpu TEXT NOT NULL DEFAULT '',
                device TEXT NOT NULL DEFAULT '',
                gpu_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                queued_at TEXT NOT NULL DEFAULT '',
                claimed_at TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                cancel_requested_at TEXT NOT NULL DEFAULT '',
                timeout_at TEXT NOT NULL DEFAULT '',
                worker_id TEXT NOT NULL DEFAULT '',
                claim_token TEXT NOT NULL DEFAULT '',
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 0,
                estimated_gpu_cost_usd REAL NOT NULL DEFAULT 0,
                actual_gpu_cost_usd REAL NOT NULL DEFAULT 0,
                input_upload_ids_json TEXT NOT NULL DEFAULT '[]',
                input_manifest TEXT NOT NULL DEFAULT '{}',
                output_manifest TEXT NOT NULL DEFAULT '{}',
                output_prefix TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                last_remote_sync_at TEXT NOT NULL DEFAULT '',
                runtime_seconds REAL NOT NULL DEFAULT 0,
                error_code TEXT NOT NULL DEFAULT '',
                error_type TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                traceback TEXT NOT NULL DEFAULT '',
                result_synced INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC)")
        if self.column_exists(conn, "jobs", "session_id"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_created ON jobs(session_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)")
        if self.column_exists(conn, "jobs", "owner_session_id"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner_session_created ON jobs(owner_session_id, created_at DESC)")
        if self.column_exists(conn, "jobs", "analysis_session_id"):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_owner_analysis_created "
                "ON jobs(owner_session_id, analysis_session_id, created_at DESC)"
            )
        if self.column_exists(conn, "jobs", "assigned_gpu"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_assigned_gpu_status ON jobs(assigned_gpu, status)")
        if self.column_exists(conn, "jobs", "timeout_at"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_timeout_at ON jobs(timeout_at)")
        if self.column_exists(conn, "jobs", "worker_id"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id)")
        if self.column_exists(conn, "jobs", "queue_name"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_queue_status_created ON jobs(queue_name, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS locks (
                name TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )

    def apply_migrations(self) -> None:
        migrations = [
            (1, "initial_cloud_schema", self._migration_001_initial_cloud_schema),
            (2, "anonymous_sessions", self._migration_002_anonymous_sessions),
            (3, "session_uploads", self._migration_003_session_uploads),
            (4, "job_queue", self._migration_004_job_queue),
            (5, "cleanup_recovery", self._migration_005_cleanup_recovery),
            (6, "runpod_instances", self._migration_006_runpod_instances),
            (7, "storage_quota", self._migration_007_storage_quota),
            (8, "storage_objects", self._migration_008_storage_objects),
            (9, "storage_objects_bucket_key_unique", self._migration_009_storage_objects_bucket_key_unique),
            (10, "example_asset_references", self._migration_010_example_asset_references),
            (11, "example_action_bindings", self._migration_011_example_action_bindings),
            (12, "lab_anonymous_runtime_fields", self._migration_012_lab_anonymous_runtime_fields),
            (13, "analysis_sessions", self._migration_013_analysis_sessions),
            (14, "jobs_analysis_session", self._migration_014_jobs_analysis_session),
            (15, "tab_scoped_analysis_inputs", self._migration_015_tab_scoped_analysis_inputs),
        ]
        for version, name, migration in migrations:
            with self.connect() as conn:
                row = conn.execute("SELECT version FROM schema_migrations WHERE version=?", (version,)).fetchone()
                if row is not None:
                    continue
                conn.execute("BEGIN IMMEDIATE")
                try:
                    migration(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?, ?, ?)",
                        (version, name, utc_now()),
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _migration_001_initial_cloud_schema(self, conn: sqlite3.Connection) -> None:
        # Databases created before migrations existed already have these tables.
        self._create_base_schema(conn)

    def _migration_002_anonymous_sessions(self, conn: sqlite3.Connection) -> None:
        if not self.column_exists(conn, "jobs", "session_id"):
            conn.execute("ALTER TABLE jobs ADD COLUMN session_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_created ON jobs(session_id, created_at DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY,
                session_id TEXT UNIQUE NOT NULL,
                anonymous_workspace_id TEXT NOT NULL DEFAULT '',
                token_hash TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_heartbeat_at TEXT NOT NULL,
                disconnected_at TEXT,
                expires_at TEXT,
                abandoned_at TEXT,
                cleaned_at TEXT,
                total_upload_bytes INTEGER NOT NULL DEFAULT 0,
                active_job_id TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_last_heartbeat ON sessions(last_heartbeat_at)")

    def _migration_003_session_uploads(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY,
                upload_id TEXT UNIQUE NOT NULL,
                session_id TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                safe_filename TEXT NOT NULL,
                object_key TEXT UNIQUE NOT NULL,
                multipart_upload_id TEXT NOT NULL,
                declared_size_bytes INTEGER NOT NULL,
                actual_size_bytes INTEGER NOT NULL DEFAULT 0,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                aborted_at TEXT,
                expires_at TEXT,
                sha256 TEXT,
                error_code TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_session ON uploads(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_object_key ON uploads(object_key)")

    def _migration_004_job_queue(self, conn: sqlite3.Connection) -> None:
        job_columns = {
            "workflow_name": "TEXT NOT NULL DEFAULT ''",
            "resource_type": "TEXT NOT NULL DEFAULT 'gpu'",
            "priority": "INTEGER NOT NULL DEFAULT 0",
            "claimed_at": "TEXT NOT NULL DEFAULT ''",
            "cancel_requested_at": "TEXT NOT NULL DEFAULT ''",
            "timeout_at": "TEXT NOT NULL DEFAULT ''",
            "worker_id": "TEXT NOT NULL DEFAULT ''",
            "claim_token": "TEXT NOT NULL DEFAULT ''",
            "attempt": "INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "INTEGER NOT NULL DEFAULT 0",
            "estimated_gpu_cost_usd": "REAL NOT NULL DEFAULT 0",
            "actual_gpu_cost_usd": "REAL NOT NULL DEFAULT 0",
            "input_upload_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "output_prefix": "TEXT NOT NULL DEFAULT ''",
            "error_code": "TEXT NOT NULL DEFAULT ''",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in job_columns.items():
            self.add_column_if_missing(conn, "jobs", column, definition)
        conn.execute("UPDATE jobs SET workflow_name=workflow WHERE workflow_name=''")
        conn.execute("UPDATE jobs SET resource_type='gpu' WHERE resource_type=''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_queue_status_created ON jobs(queue_name, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_timeout_at ON jobs(timeout_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_attempts (
                id INTEGER PRIMARY KEY,
                job_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error_code TEXT,
                error_message TEXT,
                metadata_json TEXT,
                UNIQUE(job_id, attempt_number)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_attempts_job ON job_attempts(job_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_leases (
                lease_id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                released_at TEXT,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_leases_resource_status ON resource_leases(resource_type, status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_leases_active_job ON resource_leases(job_id) WHERE status='ACTIVE'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                usage_date TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                jobs_started INTEGER NOT NULL DEFAULT 0,
                runtime_seconds REAL NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                actual_cost_usd REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(usage_date, resource_type)
            )
            """
        )

    def _migration_005_cleanup_recovery(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cleanup_retries (
                id INTEGER PRIMARY KEY,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                next_retry_at TEXT NOT NULL,
                last_error_code TEXT NOT NULL DEFAULT '',
                last_error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cleanup_retries_status_next ON cleanup_retries(status, next_retry_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cleanup_retries_session ON cleanup_retries(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cleanup_retries_resource ON cleanup_retries(resource_type, resource_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cleanup_events (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                error_code TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cleanup_events_session ON cleanup_events(session_id, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_instances (
                worker_id TEXT PRIMARY KEY,
                worker_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_heartbeat_at TEXT NOT NULL,
                stopped_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_instances_status ON worker_instances(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_instances_heartbeat ON worker_instances(last_heartbeat_at)")

    def _migration_006_runpod_instances(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runpod_instances (
                id INTEGER PRIMARY KEY,
                instance_id TEXT UNIQUE NOT NULL,
                provider_pod_id TEXT UNIQUE,
                job_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                pod_name TEXT NOT NULL,
                state TEXT NOT NULL,
                template_id TEXT NOT NULL DEFAULT '',
                image_reference TEXT NOT NULL DEFAULT '',
                gpu_type TEXT NOT NULL DEFAULT '',
                gpu_count INTEGER NOT NULL DEFAULT 1,
                cloud_type TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                public_ip TEXT NOT NULL DEFAULT '',
                ssh_port INTEGER,
                requested_at TEXT NOT NULL,
                created_at TEXT,
                ready_at TEXT,
                started_at TEXT,
                stop_requested_at TEXT,
                terminate_requested_at TEXT,
                terminated_at TEXT,
                last_polled_at TEXT,
                last_provider_status TEXT NOT NULL DEFAULT '',
                estimated_hourly_cost_usd REAL NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                actual_runtime_seconds REAL NOT NULL DEFAULT 0,
                actual_cost_usd REAL NOT NULL DEFAULT 0,
                create_request_key TEXT UNIQUE NOT NULL,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_job ON runpod_instances(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_session ON runpod_instances(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_provider_pod ON runpod_instances(provider_pod_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_state ON runpod_instances(state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_last_polled ON runpod_instances(last_polled_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runpod_instances_create_key ON runpod_instances(create_request_key)")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_runpod_instances_one_active_job
            ON runpod_instances(job_id)
            WHERE state NOT IN ('TERMINATED', 'CREATE_FAILED', 'READY_TIMEOUT')
            """
        )

    def _migration_007_storage_quota(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storage_usage_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                physical_usage_bytes INTEGER NOT NULL DEFAULT 0,
                last_reconciled_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO storage_usage_state(id, physical_usage_bytes, last_reconciled_at, updated_at) VALUES(1, 0, NULL, ?)",
            (utc_now(),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storage_reservations (
                reservation_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                object_key TEXT NOT NULL,
                expected_bytes INTEGER NOT NULL,
                actual_bytes INTEGER,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                error_message TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_reservations_session ON storage_reservations(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_reservations_object ON storage_reservations(object_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_reservations_status ON storage_reservations(status, expires_at)")

    def _migration_008_storage_objects(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storage_objects (
                id TEXT PRIMARY KEY,
                bucket TEXT NOT NULL,
                object_key TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                object_type TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                reserved_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                last_error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_objects_bucket_key_unique ON storage_objects(bucket, object_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_objects_session ON storage_objects(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_objects_job ON storage_objects(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_objects_status ON storage_objects(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_objects_expires_at ON storage_objects(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_objects_sha256 ON storage_objects(sha256)")

    def _migration_009_storage_objects_bucket_key_unique(self, conn: sqlite3.Connection) -> None:
        conn.execute("DROP INDEX IF EXISTS idx_storage_objects_object_key_unique")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_objects_bucket_key_unique ON storage_objects(bucket, object_key)")

    def _migration_010_example_asset_references(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS example_asset_references (
                reference_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                reference_type TEXT NOT NULL DEFAULT 'example_asset',
                asset_id TEXT NOT NULL,
                asset_version TEXT NOT NULL,
                manifest_version TEXT NOT NULL,
                object_key TEXT NOT NULL,
                asset_object_keys_json TEXT NOT NULL DEFAULT '[]',
                display_name TEXT NOT NULL,
                eligible_workflows_json TEXT NOT NULL DEFAULT '[]',
                modality TEXT NOT NULL DEFAULT '',
                file_format TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                species TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(session_id, asset_id, manifest_version)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_asset_refs_session_created ON example_asset_references(session_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_asset_refs_asset ON example_asset_references(asset_id)")

    def _migration_011_example_action_bindings(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS example_action_bindings (
                binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                page_name TEXT NOT NULL DEFAULT '',
                bundle_id TEXT NOT NULL,
                manifest_version TEXT NOT NULL,
                asset_version TEXT NOT NULL DEFAULT '',
                ready INTEGER NOT NULL DEFAULT 0,
                bound_roles_json TEXT NOT NULL DEFAULT '[]',
                missing_roles_json TEXT NOT NULL DEFAULT '[]',
                sample_ids_json TEXT NOT NULL DEFAULT '[]',
                available_workflows_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(session_id, action_id, manifest_version)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_action_bindings_session_updated ON example_action_bindings(session_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_action_bindings_action ON example_action_bindings(action_id)")

    def _migration_012_lab_anonymous_runtime_fields(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY,
                session_id TEXT UNIQUE NOT NULL,
                anonymous_workspace_id TEXT NOT NULL DEFAULT '',
                token_hash TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_heartbeat_at TEXT NOT NULL,
                disconnected_at TEXT,
                expires_at TEXT,
                abandoned_at TEXT,
                cleaned_at TEXT,
                total_upload_bytes INTEGER NOT NULL DEFAULT 0,
                active_job_id TEXT,
                metadata_json TEXT
            )
            """
        )
        job_columns = {
            "owner_session_id": "TEXT NOT NULL DEFAULT ''",
            "anonymous_workspace_id": "TEXT NOT NULL DEFAULT ''",
            "requested_resource": "TEXT NOT NULL DEFAULT ''",
            "assigned_gpu": "TEXT NOT NULL DEFAULT ''",
            "input_manifest": "TEXT NOT NULL DEFAULT '{}'",
            "output_manifest": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in job_columns.items():
            self.add_column_if_missing(conn, "jobs", column, definition)
        self.add_column_if_missing(conn, "sessions", "anonymous_workspace_id", "TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE jobs SET owner_session_id=session_id WHERE owner_session_id='' AND session_id IS NOT NULL")
        conn.execute("UPDATE sessions SET anonymous_workspace_id=session_id WHERE anonymous_workspace_id=''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner_session_created ON jobs(owner_session_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_assigned_gpu_status ON jobs(assigned_gpu, status)")

    def _migration_013_analysis_sessions(self, conn: sqlite3.Connection) -> None:
        """Persist browser-owned analysis workspaces independently of WebSockets.

        This is intentionally a small ownership table in the existing database,
        not a parallel job manager.  A workflow/job must still carry this id in
        its own persistent metadata before it can be restored or published.
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                analysis_session_id TEXT PRIMARY KEY,
                owner_session_id TEXT NOT NULL,
                browser_client_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_sessions_owner_updated "
            "ON analysis_sessions(owner_session_id, updated_at DESC)"
        )

    def _migration_014_jobs_analysis_session(self, conn: sqlite3.Connection) -> None:
        """Bind new Lab jobs to the browser-owned analysis workspace.

        Existing jobs intentionally retain an empty value.  They remain
        historical owner-scoped records and are never silently claimed by a
        newly started analysis session.
        """
        self.add_column_if_missing(conn, "jobs", "analysis_session_id", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_owner_analysis_created "
            "ON jobs(owner_session_id, analysis_session_id, created_at DESC)"
        )

    def _migration_015_tab_scoped_analysis_inputs(self, conn: sqlite3.Connection) -> None:
        # Keep owner quota/accounting, but prevent owner-shared browser tabs
        # from resolving each other's input records.
        self.add_column_if_missing(conn, "uploads", "analysis_session_id", "TEXT NOT NULL DEFAULT ''")
        self.add_column_if_missing(conn, "storage_reservations", "analysis_session_id", "TEXT NOT NULL DEFAULT ''")
        self.add_column_if_missing(conn, "example_asset_references", "analysis_session_id", "TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_owner_analysis ON uploads(session_id, analysis_session_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_reservations_owner_analysis ON storage_reservations(session_id, analysis_session_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_asset_refs_owner_analysis ON example_asset_references(session_id, analysis_session_id, created_at DESC)")
        # v11 had a unique key without analysis scope. Rebuild once, retaining
        # legacy rows under empty analysis scope but allowing independent tab bindings.
        columns = [str(r["name"]) for r in conn.execute("PRAGMA table_info(example_action_bindings)").fetchall()]
        if "analysis_session_id" not in columns:
            conn.execute("ALTER TABLE example_action_bindings RENAME TO example_action_bindings_legacy_v15")
            conn.execute("""
                CREATE TABLE example_action_bindings (
                    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    analysis_session_id TEXT NOT NULL DEFAULT '',
                    action_id TEXT NOT NULL,
                    page_name TEXT NOT NULL DEFAULT '',
                    bundle_id TEXT NOT NULL,
                    manifest_version TEXT NOT NULL,
                    asset_version TEXT NOT NULL DEFAULT '',
                    ready INTEGER NOT NULL DEFAULT 0,
                    bound_roles_json TEXT NOT NULL DEFAULT '[]',
                    missing_roles_json TEXT NOT NULL DEFAULT '[]',
                    sample_ids_json TEXT NOT NULL DEFAULT '[]',
                    available_workflows_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, analysis_session_id, action_id, manifest_version)
                )
            """)
            conn.execute("""
                INSERT INTO example_action_bindings(
                    binding_id, session_id, analysis_session_id, action_id, page_name, bundle_id,
                    manifest_version, asset_version, ready, bound_roles_json, missing_roles_json,
                    sample_ids_json, available_workflows_json, created_at, updated_at, metadata_json
                )
                SELECT binding_id, session_id, '', action_id, page_name, bundle_id,
                    manifest_version, asset_version, ready, bound_roles_json, missing_roles_json,
                    sample_ids_json, available_workflows_json, created_at, updated_at, metadata_json
                FROM example_action_bindings_legacy_v15
            """)
            conn.execute("DROP TABLE example_action_bindings_legacy_v15")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_example_action_bindings_owner_analysis ON example_action_bindings(session_id, analysis_session_id, updated_at DESC)")

    @staticmethod
    def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row["name"]) == column for row in rows)

    def add_column_if_missing(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        if not self.column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def get_schema_migrations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version").fetchall()
        return [dict(row) for row in rows]

    def table_columns(self, table: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(row["name"]) for row in rows]

    def create_analysis_session(
        self,
        *,
        owner_session_id: str,
        browser_client_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owner = str(owner_session_id or "").strip()
        if not owner:
            raise DatabaseError("owner_session_id is required for an analysis session")
        analysis_session_id = f"analysis_{secrets.token_hex(24)}"
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_sessions(
                    analysis_session_id, owner_session_id, browser_client_id,
                    status, created_at, updated_at, metadata_json
                ) VALUES(?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (
                    analysis_session_id,
                    owner,
                    str(browser_client_id or "").strip(),
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
                ),
            )
        return self.get_analysis_session(analysis_session_id, owner_session_id=owner)

    def get_analysis_session(
        self,
        analysis_session_id: str,
        *,
        owner_session_id: str | None = None,
    ) -> dict[str, Any]:
        query = "SELECT * FROM analysis_sessions WHERE analysis_session_id=?"
        args: list[Any] = [str(analysis_session_id or "").strip()]
        if owner_session_id is not None:
            query += " AND owner_session_id=?"
            args.append(str(owner_session_id or "").strip())
        with self.connect() as conn:
            row = conn.execute(query, args).fetchone()
        if row is None:
            raise KeyError(analysis_session_id)
        data = dict(row)
        try:
            data["metadata"] = json.loads(str(data.pop("metadata_json") or "{}"))
        except Exception:
            data["metadata"] = {}
            data.pop("metadata_json", None)
        return data

    def get_latest_active_analysis_session(
        self,
        *,
        owner_session_id: str,
        browser_client_id: str = "",
    ) -> dict[str, Any]:
        """Restore the newest active workspace for this owner/browser only."""
        owner = str(owner_session_id or "").strip()
        browser = str(browser_client_id or "").strip()
        if not owner or not browser:
            raise KeyError("analysis_session")
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM analysis_sessions
                WHERE owner_session_id=? AND browser_client_id=? AND status='ACTIVE'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (owner, browser),
            ).fetchone()
        if row is None:
            raise KeyError("analysis_session")
        data = dict(row)
        try:
            data["metadata"] = json.loads(str(data.pop("metadata_json") or "{}"))
        except Exception:
            data["metadata"] = {}
            data.pop("metadata_json", None)
        return data

    def create_job(self, job: JobRecord) -> JobRecord:
        values = job.to_dict()
        values["result_synced"] = int(bool(values["result_synced"]))
        placeholders = ", ".join("?" for _ in JOBS_COLUMNS)
        columns = ", ".join(JOBS_COLUMNS)
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO jobs({columns}) VALUES({placeholders})",
                [values.get(column) for column in JOBS_COLUMNS],
            )
        return self.get_job(job.job_id)

    def update_job(self, job_id: str, **updates: Any) -> JobRecord:
        allowed = set(JOBS_COLUMNS) - {"job_id"}
        filtered = {key: value for key, value in updates.items() if key in allowed}
        if not filtered:
            return self.get_job(job_id)
        if "result_synced" in filtered:
            filtered["result_synced"] = int(bool(filtered["result_synced"]))
        assignments = ", ".join(f"{key}=?" for key in filtered)
        with self.connect() as conn:
            if "status" in filtered:
                row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None:
                    raise KeyError(f"Job was not found: {job_id}")
                validate_job_status_transition(str(row["status"]), str(filtered["status"]))
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id=?",
                [*filtered.values(), job_id],
            )
        return self.get_job(job_id)

    def get_job(
        self,
        job_id: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
    ) -> JobRecord:
        query = "SELECT * FROM jobs WHERE job_id=?"
        params: list[Any] = [job_id]
        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)
        if session_id is not None:
            query += " AND session_id=?"
            params.append(session_id)
        if analysis_session_id is not None:
            query += " AND analysis_session_id=?"
            params.append(analysis_session_id)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(f"Job was not found: {job_id}")
        return row_to_job(row)

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        clauses = []
        if user_id is not None:
            clauses.append("user_id=?")
            params.append(user_id)
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if analysis_session_id is not None:
            clauses.append("analysis_session_id=?")
            params.append(analysis_session_id)
        if statuses:
            clauses.append("status IN (" + ", ".join("?" for _ in statuses) + ")")
            params.extend(statuses)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [row_to_job(row) for row in rows]

    def list_active_jobs_for_analysis(self, *, owner_session_id: str, analysis_session_id: str, statuses: set[str] | frozenset[str]) -> list[JobRecord]:
        """Return active jobs in one exact tab analysis scope."""
        owner = str(owner_session_id or "").strip()
        analysis = str(analysis_session_id or "").strip()
        values = sorted(str(status) for status in statuses)
        if not owner or not analysis or not values:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE owner_session_id=? AND analysis_session_id=? AND status IN (" + ", ".join("?" for _ in values) + ")",
                [owner, analysis, *values],
            ).fetchall()
        return [row_to_job(row) for row in rows]

    def add_event(self, job_id: str, created_at: str, level: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO job_events(job_id, created_at, level, message) VALUES(?, ?, ?, ?)",
                (job_id, created_at, level, message),
            )

    def list_events(self, job_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT created_at, level, message FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def create_or_get_example_asset_reference(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = [
            "reference_id",
            "session_id",
            "reference_type",
            "asset_id",
            "asset_version",
            "manifest_version",
            "object_key",
            "asset_object_keys_json",
            "display_name",
            "eligible_workflows_json",
            "modality",
            "file_format",
            "size_bytes",
            "species",
            "created_at",
            "metadata_json",
        ]
        placeholders = ", ".join("?" for _ in columns)
        with self.connect() as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO example_asset_references({', '.join(columns)}) VALUES({placeholders})",
                [values.get(column) for column in columns],
            )
            row = conn.execute(
                """
                SELECT * FROM example_asset_references
                WHERE session_id=? AND asset_id=? AND manifest_version=?
                """,
                (values.get("session_id"), values.get("asset_id"), values.get("manifest_version")),
            ).fetchone()
        if row is None:
            raise DatabaseError("Example asset reference was not created.")
        return dict(row)

    def get_example_asset_reference(self, reference_id: str, *, session_id: str | None = None) -> dict[str, Any]:
        query = "SELECT * FROM example_asset_references WHERE reference_id=?"
        params: list[Any] = [reference_id]
        if session_id is not None:
            query += " AND session_id=?"
            params.append(session_id)
        if analysis_session_id is not None:
            query += " AND analysis_session_id=?"
            params.append(analysis_session_id)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(f"Example asset reference was not found: {reference_id}")
        return dict(row)

    def list_example_asset_references(self, *, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM example_asset_references
                WHERE session_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_example_asset_reference_used(self, reference_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute("UPDATE example_asset_references SET last_used_at=? WHERE reference_id=?", (now, reference_id))
        return self.get_example_asset_reference(reference_id)

    def create_or_update_example_action_binding(self, values: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        columns = [
            "session_id",
            "analysis_session_id",
            "action_id",
            "page_name",
            "bundle_id",
            "manifest_version",
            "asset_version",
            "ready",
            "bound_roles_json",
            "missing_roles_json",
            "sample_ids_json",
            "available_workflows_json",
            "created_at",
            "updated_at",
            "metadata_json",
        ]
        payload = dict(values)
        payload["created_at"] = payload.get("created_at") or now
        payload["updated_at"] = now
        payload["ready"] = int(bool(payload.get("ready")))
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT binding_id, created_at FROM example_action_bindings
                WHERE session_id=? AND analysis_session_id=? AND action_id=? AND manifest_version=?
                """,
                (payload.get("session_id"), payload.get("analysis_session_id"), payload.get("action_id"), payload.get("manifest_version")),
            ).fetchone()
            if existing is None:
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT INTO example_action_bindings({', '.join(columns)}) VALUES({placeholders})",
                    [payload.get(column) for column in columns],
                )
            else:
                payload["created_at"] = str(existing["created_at"])
                update_columns = [column for column in columns if column not in {"session_id", "analysis_session_id", "action_id", "manifest_version", "created_at"}]
                assignments = ", ".join(f"{column}=?" for column in update_columns)
                conn.execute(
                    f"""
                    UPDATE example_action_bindings
                    SET {assignments}
                    WHERE binding_id=?
                    """,
                    [payload.get(column) for column in update_columns] + [existing["binding_id"]],
                )
        return self.get_example_action_binding(
            session_id=str(payload.get("session_id") or ""),
            analysis_session_id=str(payload.get("analysis_session_id") or ""),
            action_id=str(payload.get("action_id") or ""),
            manifest_version=str(payload.get("manifest_version") or ""),
        )

    def get_example_action_binding(self, *, session_id: str, analysis_session_id: str = "", action_id: str, manifest_version: str | None = None) -> dict[str, Any]:
        query = "SELECT * FROM example_action_bindings WHERE session_id=? AND analysis_session_id=? AND action_id=?"
        params: list[Any] = [session_id, analysis_session_id, action_id]
        if manifest_version is not None:
            query += " AND manifest_version=?"
            params.append(manifest_version)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(f"Example action binding was not found: {action_id}")
        return dict(row)

    def list_example_action_bindings(self, *, session_id: str, analysis_session_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM example_action_bindings
                WHERE session_id=? AND analysis_session_id=?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, analysis_session_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_upload(self, upload: UploadRecord) -> UploadRecord:
        values = upload.to_dict()
        placeholders = ", ".join("?" for _ in UPLOADS_COLUMNS)
        columns = ", ".join(UPLOADS_COLUMNS)
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO uploads({columns}) VALUES({placeholders})",
                [values.get(column) for column in UPLOADS_COLUMNS],
            )
        return self.get_upload(upload.upload_id)

    def update_upload(
        self, upload_id: str, *, session_id: str | None = None,
        analysis_session_id: str | None = None, **updates: Any
    ) -> UploadRecord:
        allowed = set(UPLOADS_COLUMNS) - {"upload_id"}
        filtered = {key: value for key, value in updates.items() if key in allowed}
        if not filtered:
            return self.get_upload(
                upload_id, session_id=session_id, analysis_session_id=analysis_session_id
            )
        assignments = ", ".join(f"{key}=?" for key in filtered)
        clauses = ["upload_id=?"]
        params: list[Any] = [*filtered.values(), upload_id]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if analysis_session_id is not None:
            clauses.append("analysis_session_id=?")
            params.append(analysis_session_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE uploads SET {assignments} WHERE {' AND '.join(clauses)}", params
            )
        return self.get_upload(
            upload_id, session_id=session_id, analysis_session_id=analysis_session_id
        )

    def get_upload(self, upload_id: str, *, session_id: str | None = None, analysis_session_id: str | None = None) -> UploadRecord:
        query = "SELECT * FROM uploads WHERE upload_id=?"
        params: list[Any] = [upload_id]
        if session_id is not None:
            query += " AND session_id=?"
            params.append(session_id)
        if analysis_session_id is not None:
            query += " AND analysis_session_id=?"
            params.append(analysis_session_id)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(f"Upload was not found: {upload_id}")
        return row_to_upload(row)

    def list_uploads(self, *, session_id: str, analysis_session_id: str | None = None, limit: int = 100) -> list[UploadRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM uploads
                WHERE session_id=? AND (? IS NULL OR analysis_session_id=?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, analysis_session_id, analysis_session_id, int(limit)),
            ).fetchall()
        return [row_to_upload(row) for row in rows]

    def list_uploads_for_cleanup(self, session_id: str) -> list[UploadRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM uploads WHERE session_id=? AND status NOT IN (?, ?)",
                (session_id, UploadStatus.DELETED.value, UploadStatus.ABORTED.value),
            ).fetchall()
        return [row_to_upload(row) for row in rows]

    def count_session_uploads(self, session_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM uploads
                WHERE session_id=?
                AND status NOT IN (?, ?, ?)
                """,
                (
                    session_id,
                    UploadStatus.ABORTED.value,
                    UploadStatus.DELETED.value,
                    UploadStatus.FAILED.value,
                ),
            ).fetchone()
        return int(row["count"] or 0)

    def sum_session_declared_upload_bytes(self, session_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(declared_size_bytes), 0) AS total
                FROM uploads
                WHERE session_id=?
                AND status IN (?, ?, ?)
                """,
                (
                    session_id,
                    UploadStatus.INITIATED.value,
                    UploadStatus.UPLOADING.value,
                    UploadStatus.COMPLETING.value,
                ),
            ).fetchone()
        return int(row["total"] or 0)

    def count_active_upload_sessions(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT session_id) AS count
                FROM uploads
                WHERE status IN (?, ?, ?)
                """,
                (
                    UploadStatus.INITIATED.value,
                    UploadStatus.UPLOADING.value,
                    UploadStatus.COMPLETING.value,
                ),
            ).fetchone()
        return int(row["count"] or 0)

    def session_has_active_upload(self, session_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM uploads
                WHERE session_id=?
                AND status IN (?, ?, ?)
                LIMIT 1
                """,
                (
                    session_id,
                    UploadStatus.INITIATED.value,
                    UploadStatus.UPLOADING.value,
                    UploadStatus.COMPLETING.value,
                ),
            ).fetchone()
        return row is not None

    def add_session_upload_bytes(self, session_id: str, delta: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET total_upload_bytes=MAX(0, total_upload_bytes + ?)
                WHERE session_id=?
                """,
                (int(delta), session_id),
            )

    def acquire_lock(self, name: str, owner: str, now: float, ttl_seconds: int = 300) -> bool:
        expires_at = now + ttl_seconds
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT owner, expires_at FROM locks WHERE name=?", (name,)).fetchone()
            if row is not None and float(row["expires_at"]) > now and row["owner"] != owner:
                conn.execute("COMMIT")
                return False
            conn.execute(
                "INSERT OR REPLACE INTO locks(name, owner, expires_at) VALUES(?, ?, ?)",
                (name, owner, expires_at),
            )
            conn.execute("COMMIT")
            return True

    def release_lock(self, name: str, owner: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM locks WHERE name=? AND owner=?", (name, owner))

    def create_or_update_cleanup_retry(
        self,
        *,
        resource_type: str,
        resource_id: str,
        action: str,
        session_id: str = "",
        error_code: str = "",
        error_message: str = "",
        max_attempts: int = 5,
        metadata_json: str = "{}",
        next_retry_at: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        next_retry_at = next_retry_at or now
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM cleanup_retries
                WHERE resource_type=? AND resource_id=? AND action=?
                AND status IN (?, ?, ?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    resource_type,
                    resource_id,
                    action,
                    CleanupRetryStatus.PENDING.value,
                    CleanupRetryStatus.RUNNING.value,
                    CleanupRetryStatus.RETRY_WAIT.value,
                ),
            ).fetchone()
            if row is not None:
                conn.execute(
                    """
                    UPDATE cleanup_retries
                    SET session_id=?,
                        max_attempts=?,
                        next_retry_at=?,
                        last_error_code=?,
                        last_error_message=?,
                        updated_at=?,
                        status=?
                    WHERE id=?
                    """,
                    (
                        session_id,
                        int(max_attempts),
                        next_retry_at,
                        error_code,
                        error_message,
                        now,
                        CleanupRetryStatus.RETRY_WAIT.value,
                        row["id"],
                    ),
                )
                updated = conn.execute("SELECT * FROM cleanup_retries WHERE id=?", (row["id"],)).fetchone()
                conn.execute("COMMIT")
                return dict(updated)
            conn.execute(
                """
                INSERT INTO cleanup_retries(
                    resource_type, resource_id, session_id, action,
                    attempt_count, max_attempts, next_retry_at,
                    last_error_code, last_error_message,
                    created_at, updated_at, completed_at, status, metadata_json
                )
                VALUES(?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    resource_type,
                    resource_id,
                    session_id,
                    action,
                    int(max_attempts),
                    next_retry_at,
                    error_code,
                    error_message,
                    now,
                    now,
                    CleanupRetryStatus.PENDING.value,
                    metadata_json or "{}",
                ),
            )
            retry_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            created = conn.execute("SELECT * FROM cleanup_retries WHERE id=?", (retry_id,)).fetchone()
            conn.execute("COMMIT")
            return dict(created)

    def list_due_cleanup_retries(self, *, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        now = now or utc_now()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cleanup_retries
                WHERE status IN (?, ?)
                AND next_retry_at <= ?
                ORDER BY next_retry_at ASC, id ASC
                LIMIT ?
                """,
                (CleanupRetryStatus.PENDING.value, CleanupRetryStatus.RETRY_WAIT.value, now, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_cleanup_retry_running(self, retry_id: int) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE cleanup_retries
                SET status=?, updated_at=?
                WHERE id=? AND status IN (?, ?)
                """,
                (
                    CleanupRetryStatus.RUNNING.value,
                    now,
                    int(retry_id),
                    CleanupRetryStatus.PENDING.value,
                    CleanupRetryStatus.RETRY_WAIT.value,
                ),
            )
            row = conn.execute("SELECT * FROM cleanup_retries WHERE id=?", (int(retry_id),)).fetchone()
        return dict(row)

    def mark_cleanup_retry_completed(self, retry_id: int) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE cleanup_retries
                SET status=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (CleanupRetryStatus.COMPLETED.value, now, now, int(retry_id)),
            )
            row = conn.execute("SELECT * FROM cleanup_retries WHERE id=?", (int(retry_id),)).fetchone()
        return dict(row)

    def mark_cleanup_retry_failed(
        self,
        retry_id: int,
        *,
        error_code: str,
        error_message: str,
        next_retry_at: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute("SELECT attempt_count, max_attempts FROM cleanup_retries WHERE id=?", (int(retry_id),)).fetchone()
            if row is None:
                raise KeyError("Cleanup retry was not found.")
            attempt_count = int(row["attempt_count"] or 0) + 1
            max_attempts = int(row["max_attempts"] or 0)
            status = CleanupRetryStatus.EXHAUSTED.value if attempt_count >= max_attempts else CleanupRetryStatus.RETRY_WAIT.value
            conn.execute(
                """
                UPDATE cleanup_retries
                SET status=?,
                    attempt_count=?,
                    next_retry_at=?,
                    last_error_code=?,
                    last_error_message=?,
                    updated_at=?
                WHERE id=?
                """,
                (status, attempt_count, next_retry_at, error_code, error_message, now, int(retry_id)),
            )
            updated = conn.execute("SELECT * FROM cleanup_retries WHERE id=?", (int(retry_id),)).fetchone()
        return dict(updated)

    def list_cleanup_retries(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM cleanup_retries"
        params: list[Any] = []
        if session_id is not None:
            query += " WHERE session_id=?"
            params.append(session_id)
        query += " ORDER BY id ASC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def record_cleanup_event(
        self,
        *,
        session_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        status: str,
        error_code: str = "",
        message: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cleanup_events(
                    session_id, resource_type, resource_id, action,
                    status, created_at, error_code, message
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, resource_type, resource_id, action, status, utc_now(), error_code, message),
            )

    def list_cleanup_events(self, *, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, resource_type, resource_id, action, status, created_at, error_code, message
                FROM cleanup_events
                WHERE session_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def list_sessions_by_statuses(self, statuses: list[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status IN (" + ", ".join("?" for _ in statuses) + ") ORDER BY id ASC",
                list(statuses),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_worker_instance(
        self,
        *,
        worker_id: str,
        worker_type: str,
        status: str = WorkerStatus.ACTIVE.value,
        metadata_json: str = "{}",
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_instances(
                    worker_id, worker_type, status, started_at,
                    last_heartbeat_at, stopped_at, metadata_json
                )
                VALUES(?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    worker_type=excluded.worker_type,
                    status=excluded.status,
                    last_heartbeat_at=excluded.last_heartbeat_at,
                    stopped_at=NULL,
                    metadata_json=excluded.metadata_json
                """,
                (worker_id, worker_type, status, now, now, metadata_json or "{}"),
            )
            row = conn.execute("SELECT * FROM worker_instances WHERE worker_id=?", (worker_id,)).fetchone()
        return dict(row)

    def heartbeat_worker(self, worker_id: str, *, status: str = WorkerStatus.ACTIVE.value) -> dict[str, Any]:
        now = utc_now()
        with db_forensic_context(worker_id=worker_id, operation="heartbeat_worker"):
            with db_debug_stage("WORKER_HEARTBEAT"):
                with self.connect() as conn:
                    _heartbeat_runtime_debug(event="before_update", database=self, conn=conn, failure_stage="UPDATE", worker_id=worker_id)
                    try:
                        conn.execute(
                            "UPDATE worker_instances SET status=?, last_heartbeat_at=? WHERE worker_id=?",
                            (status, now, worker_id),
                        )
                    except sqlite3.OperationalError as exc:
                        _heartbeat_runtime_debug(
                            event="update_error",
                            database=self,
                            conn=conn,
                            failure_stage="UPDATE",
                            error=exc,
                            worker_id=worker_id,
                        )
                        raise
                    _heartbeat_runtime_debug(event="after_update", database=self, conn=conn, failure_stage="SELECT", worker_id=worker_id)
                    try:
                        row = conn.execute("SELECT * FROM worker_instances WHERE worker_id=?", (worker_id,)).fetchone()
                    except sqlite3.OperationalError as exc:
                        _heartbeat_runtime_debug(
                            event="select_error",
                            database=self,
                            conn=conn,
                            failure_stage="SELECT",
                            error=exc,
                            worker_id=worker_id,
                        )
                        raise
        if row is None:
            raise KeyError("Worker was not found.")
        return dict(row)

    def mark_worker_stopped(self, worker_id: str, *, status: str = WorkerStatus.STOPPED.value) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE worker_instances SET status=?, stopped_at=?, last_heartbeat_at=? WHERE worker_id=?",
                (status, now, now, worker_id),
            )
            row = conn.execute("SELECT * FROM worker_instances WHERE worker_id=?", (worker_id,)).fetchone()
        if row is None:
            raise KeyError("Worker was not found.")
        return dict(row)

    def mark_lost_workers(self, *, heartbeat_before: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT worker_id FROM worker_instances
                WHERE status IN (?, ?)
                AND last_heartbeat_at < ?
                """,
                (WorkerStatus.STARTING.value, WorkerStatus.ACTIVE.value, heartbeat_before),
            ).fetchall()
            worker_ids = [str(row["worker_id"]) for row in rows]
            if worker_ids:
                conn.execute(
                    "UPDATE worker_instances SET status=? WHERE worker_id IN (" + ", ".join("?" for _ in worker_ids) + ")",
                    [WorkerStatus.LOST.value, *worker_ids],
                )
        return worker_ids

    def get_worker_instance(self, worker_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM worker_instances WHERE worker_id=?", (worker_id,)).fetchone()
        return dict(row) if row is not None else None

    def create_runpod_instance(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = [
            "instance_id",
            "provider_pod_id",
            "job_id",
            "session_id",
            "provider_name",
            "pod_name",
            "state",
            "template_id",
            "image_reference",
            "gpu_type",
            "gpu_count",
            "cloud_type",
            "location",
            "public_ip",
            "ssh_port",
            "requested_at",
            "created_at",
            "ready_at",
            "started_at",
            "stop_requested_at",
            "terminate_requested_at",
            "terminated_at",
            "last_polled_at",
            "last_provider_status",
            "estimated_hourly_cost_usd",
            "estimated_cost_usd",
            "actual_runtime_seconds",
            "actual_cost_usd",
            "create_request_key",
            "error_code",
            "error_message",
            "metadata_json",
        ]
        placeholders = ", ".join("?" for _ in columns)
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO runpod_instances({', '.join(columns)}) VALUES({placeholders})",
                [values.get(column) for column in columns],
            )
        return self.get_runpod_instance(str(values["instance_id"]))

    def update_runpod_instance(self, instance_id: str, **updates: Any) -> dict[str, Any]:
        allowed = {
            "provider_pod_id",
            "state",
            "gpu_type",
            "cloud_type",
            "location",
            "public_ip",
            "ssh_port",
            "created_at",
            "ready_at",
            "started_at",
            "stop_requested_at",
            "terminate_requested_at",
            "terminated_at",
            "last_polled_at",
            "last_provider_status",
            "estimated_hourly_cost_usd",
            "estimated_cost_usd",
            "actual_runtime_seconds",
            "actual_cost_usd",
            "error_code",
            "error_message",
            "metadata_json",
        }
        filtered = {key: value for key, value in updates.items() if key in allowed}
        if not filtered:
            return self.get_runpod_instance(instance_id)
        assignments = ", ".join(f"{key}=?" for key in filtered)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE runpod_instances SET {assignments} WHERE instance_id=?",
                [*filtered.values(), instance_id],
            )
        return self.get_runpod_instance(instance_id)

    def get_runpod_instance(self, instance_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runpod_instances WHERE instance_id=?", (instance_id,)).fetchone()
        if row is None:
            raise KeyError(f"RunPod instance was not found: {instance_id}")
        return dict(row)

    def get_runpod_instance_by_job(self, job_id: str, *, active_only: bool = False) -> dict[str, Any] | None:
        query = "SELECT * FROM runpod_instances WHERE job_id=?"
        params: list[Any] = [job_id]
        if active_only:
            query += " AND state NOT IN (" + ", ".join("?" for _ in RUNPOD_INSTANCE_TERMINAL_STATES) + ")"
            params.extend(sorted(RUNPOD_INSTANCE_TERMINAL_STATES))
        query += " ORDER BY id DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return dict(row) if row is not None else None

    def get_runpod_instance_by_provider_pod_id(self, provider_pod_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runpod_instances WHERE provider_pod_id=?", (provider_pod_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_runpod_instances(
        self,
        *,
        states: list[str] | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        active_only: bool = False,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM runpod_instances"
        params: list[Any] = []
        clauses: list[str] = []
        if states:
            clauses.append("state IN (" + ", ".join("?" for _ in states) + ")")
            params.extend(states)
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if job_id is not None:
            clauses.append("job_id=?")
            params.append(job_id)
        if active_only:
            clauses.append("state NOT IN (" + ", ".join("?" for _ in RUNPOD_INSTANCE_TERMINAL_STATES) + ")")
            params.extend(sorted(RUNPOD_INSTANCE_TERMINAL_STATES))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_storage_usage_state(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM storage_usage_state WHERE id=1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO storage_usage_state(id, physical_usage_bytes, last_reconciled_at, updated_at) VALUES(1, 0, NULL, ?)",
                    (utc_now(),),
                )
                row = conn.execute("SELECT * FROM storage_usage_state WHERE id=1").fetchone()
        return dict(row)

    def set_storage_usage_state(self, *, physical_usage_bytes: int, last_reconciled_at: str | None = None) -> dict[str, Any]:
        now = utc_now()
        usage = max(0, int(physical_usage_bytes))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO storage_usage_state(id, physical_usage_bytes, last_reconciled_at, updated_at)
                VALUES(1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    physical_usage_bytes=excluded.physical_usage_bytes,
                    last_reconciled_at=excluded.last_reconciled_at,
                    updated_at=excluded.updated_at
                """,
                (usage, last_reconciled_at, now),
            )
        return self.get_storage_usage_state()

    def increment_storage_usage(self, delta_bytes: int) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO storage_usage_state(id, physical_usage_bytes, last_reconciled_at, updated_at)
                VALUES(1, 0, NULL, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE storage_usage_state
                SET physical_usage_bytes=MAX(0, physical_usage_bytes + ?),
                    updated_at=?
                WHERE id=1
                """,
                (int(delta_bytes), now),
            )
        return self.get_storage_usage_state()

    def list_storage_reservations(
        self,
        *,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
        statuses: list[str] | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM storage_reservations"
        params: list[Any] = []
        clauses: list[str] = []
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if analysis_session_id is not None:
            clauses.append("analysis_session_id=?")
            params.append(analysis_session_id)
        if statuses:
            clauses.append("status IN (" + ", ".join("?" for _ in statuses) + ")")
            params.extend(statuses)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_storage_reservation(
        self,
        reservation_id: str,
        *,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
    ) -> dict[str, Any]:
        query = "SELECT * FROM storage_reservations WHERE reservation_id=?"
        params: list[Any] = [reservation_id]
        if session_id is not None:
            query += " AND session_id=?"
            params.append(session_id)
        if analysis_session_id is not None:
            query += " AND analysis_session_id=?"
            params.append(analysis_session_id)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(f"Storage reservation was not found: {reservation_id}")
        return dict(row)

    def get_storage_reservation_by_object_key(self, object_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM storage_reservations WHERE object_key=? ORDER BY created_at DESC LIMIT 1",
                (object_key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def update_storage_reservation(
        self,
        reservation_id: str,
        *,
        session_id: str | None = None,
        analysis_session_id: str | None = None,
        **updates: Any,
    ) -> dict[str, Any]:
        allowed = {
            "actual_bytes",
            "status",
            "updated_at",
            "expires_at",
            "error_message",
            "metadata_json",
        }
        filtered = {key: value for key, value in updates.items() if key in allowed}
        if not filtered:
            return self.get_storage_reservation(
                reservation_id, session_id=session_id, analysis_session_id=analysis_session_id
            )
        if "updated_at" not in filtered:
            filtered["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in filtered)
        clauses = ["reservation_id=?"]
        params: list[Any] = [*filtered.values(), reservation_id]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if analysis_session_id is not None:
            clauses.append("analysis_session_id=?")
            params.append(analysis_session_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE storage_reservations SET {assignments} WHERE {' AND '.join(clauses)}",
                params,
            )
        return self.get_storage_reservation(
            reservation_id, session_id=session_id, analysis_session_id=analysis_session_id
        )
