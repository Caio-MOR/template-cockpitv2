"""Small, dependency-free runtime primitives for cockpit workflows.

The module intentionally contains no provider-specific code.  It is suitable for
scripts which need a safe configuration check, an idempotency guard, bounded
retries, and durable evidence without introducing a runtime dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import socket
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:pass(word)?|secret|token|api[_-]?key|authorization|credential|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"(?:ghp|github_pat|sk|xox[baprs])[-_][A-Za-z0-9_-]{12,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


class RuntimeErrorBase(Exception):
    """Base class for errors intentionally exposed by this module."""


class LockBusyError(RuntimeErrorBase):
    """Raised when a live run already owns an idempotency lock."""


class RetryExhaustedError(RuntimeErrorBase):
    """Raised after a transient operation exceeds its bounded retry budget."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"operation failed after {attempts} attempt(s): {type(last_error).__name__}")


class TransientError(RuntimeErrorBase):
    """An explicit marker for failures which can safely be retried."""


class PermanentError(RuntimeErrorBase):
    """An explicit marker for failures which must not be retried."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return repr(value)


class SecretRedactor:
    """Redact values by sensitive key, known token shape, or exact secret value."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._values = tuple(sorted({value for value in secret_values if value}, key=len, reverse=True))

    def text(self, value: str) -> str:
        result = value
        for secret in self._values:
            result = result.replace(secret, REDACTED)
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(REDACTED, result)
        return result

    def value(self, value: Any, key: str | None = None) -> Any:
        if key and _SENSITIVE_KEY.search(key):
            return REDACTED
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            return {str(k): self.value(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.value(item) for item in value]
        return _json_safe(value)


@dataclass(frozen=True)
class ConfigField:
    """One typed environment/configuration field."""

    name: str
    type: type = str
    required: bool = True
    secret: bool = False
    choices: frozenset[Any] | None = None
    validator: Callable[[Any], bool] | None = None


@dataclass(frozen=True)
class ConfigIssue:
    name: str
    code: str


@dataclass(frozen=True)
class DoctorReport:
    """Machine-readable doctor result; values are deliberately absent."""

    issues: tuple[ConfigIssue, ...] = ()
    checked: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    def render(self) -> str:
        lines = [f"configuration: {'ok' if self.ok else 'invalid'}"]
        for name in self.checked:
            lines.append(f"checked: {name}")
        for issue in self.issues:
            lines.append(f"issue: {issue.name} ({issue.code})")
        return "\n".join(lines)


def _coerce(value: str, expected: type) -> Any:
    if expected is bool:
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError("invalid boolean")
    if expected is str:
        return value
    return expected(value)


def doctor(
    schema: Sequence[ConfigField],
    values: Mapping[str, Any] | None = None,
) -> DoctorReport:
    """Validate configuration and return only field names and error codes.

    ``values`` defaults to ``os.environ``.  No supplied value, including a secret,
    is ever included in the report or its string rendering.
    """

    source = os.environ if values is None else values
    issues: list[ConfigIssue] = []
    checked: list[str] = []
    for field_spec in schema:
        checked.append(field_spec.name)
        raw = source.get(field_spec.name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if field_spec.required:
                issues.append(ConfigIssue(field_spec.name, "missing"))
            continue
        try:
            value = _coerce(raw, field_spec.type) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            issues.append(ConfigIssue(field_spec.name, "invalid_type"))
            continue
        if not isinstance(value, field_spec.type):
            issues.append(ConfigIssue(field_spec.name, "invalid_type"))
        elif field_spec.choices is not None and value not in field_spec.choices:
            issues.append(ConfigIssue(field_spec.name, "invalid_choice"))
        elif field_spec.validator is not None:
            try:
                valid = bool(field_spec.validator(value))
            except Exception:
                valid = False
            if not valid:
                issues.append(ConfigIssue(field_spec.name, "invalid_value"))
    return DoctorReport(tuple(issues), tuple(checked))


@dataclass(frozen=True)
class RunIdentity:
    workflow: str
    idempotency_key: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, str]:
        return {
            "workflow": self.workflow,
            "idempotency_key": self.idempotency_key,
            "run_id": self.run_id,
            "created_at": self.created_at,
        }


class IdempotencyLock:
    """An exclusive, crash-recoverable lock for one workflow/idempotency key."""

    def __init__(
        self,
        path: str | Path,
        identity: RunIdentity,
        stale_after_seconds: float = 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self.path = Path(path)
        self.identity = identity
        self.stale_after_seconds = stale_after_seconds
        self._clock = clock
        self._held = False

    def _payload(self) -> dict[str, Any]:
        return {**self.identity.as_dict(), "pid": os.getpid(), "host": socket.gethostname()}

    def _create(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._payload(), sort_keys=True).encode()
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._held = True
        return True

    def _recover_stale(self) -> bool:
        try:
            age = self._clock() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age <= self.stale_after_seconds:
            return False
        # A slow or hung process can legitimately outlive the timestamp budget.
        # Never recover its lock while the recorded owner is still alive on this
        # host; otherwise a second scheduler invocation could duplicate delivery.
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0)) if isinstance(payload, Mapping) else 0
            host = payload.get("host") if isinstance(payload, Mapping) else None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pid, host = 0, None
        if host == socket.gethostname() and pid > 0:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Lack of permission means the process exists; do not steal its lock.
                return False
            except OSError:
                pass
            else:
                return False
        stale = self.path.with_name(f"{self.path.name}.stale.{int(self._clock())}.{os.getpid()}")
        try:
            os.replace(self.path, stale)
        except FileNotFoundError:
            return False
        return True

    def acquire(self) -> RunIdentity:
        if self._held:
            raise LockBusyError("lock is already held by this process")
        if self._create() or (self._recover_stale() and self._create()):
            return self.identity
        raise LockBusyError(f"live lock exists for workflow {self.identity.workflow!r}")

    def heartbeat(self) -> None:
        if not self._held:
            raise LockBusyError("cannot heartbeat an unheld lock")
        os.utime(self.path, None)

    def release(self) -> None:
        if not self._held:
            return
        try:
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                # The ownership proof is unavailable (for example, a truncated
                # lock after an external filesystem fault), so preserve the file
                # for stale recovery rather than deleting another run's lock.
                return
            if isinstance(current, Mapping) and current.get("run_id") == self.identity.run_id:
                try:
                    self.path.unlink(missing_ok=True)
                except OSError:
                    pass
        finally:
            self._held = False

    def __enter__(self) -> IdempotencyLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    deadline_seconds: float = 30.0
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.deadline_seconds <= 0:
            raise ValueError("retry budget must be positive")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("invalid retry delays")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


def is_transient(error: BaseException) -> bool:
    if isinstance(error, PermanentError):
        return False
    if isinstance(error, TransientError):
        return True
    return isinstance(error, (TimeoutError, ConnectionError, OSError))


def run_with_retry(
    operation: Callable[[], Any],
    policy: RetryPolicy = RetryPolicy(),
    *,
    classifier: Callable[[BaseException], bool] = is_transient,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    random_value: Callable[[], float] = random.random,
) -> Any:
    """Execute with a finite attempt/deadline budget and exponential backoff."""

    started = monotonic()
    last_error: BaseException | None = None
    attempts_made = 0
    for attempt in range(1, policy.max_attempts + 1):
        if monotonic() - started >= policy.deadline_seconds:
            break
        attempts_made = attempt
        try:
            return operation()
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            last_error = error
            if not classifier(error):
                raise
            if attempt >= policy.max_attempts:
                raise RetryExhaustedError(attempts_made, error) from error
            elapsed = monotonic() - started
            remaining = policy.deadline_seconds - elapsed
            delay = min(policy.max_delay_seconds, policy.base_delay_seconds * (2 ** (attempt - 1)))
            delay *= 1 + policy.jitter_ratio * ((random_value() * 2) - 1)
            if remaining <= 0:
                break
            sleep(min(max(0.0, delay), remaining))
    if last_error is None:
        last_error = TimeoutError("retry deadline elapsed before first attempt")
    raise RetryExhaustedError(attempts_made, last_error) from last_error


def atomic_write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    """Write JSON through a same-directory temporary file and durable rename."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        # Opening a directory is unsupported on Windows. The file itself is
        # already flushed; directory fsync adds rename durability where the OS
        # exposes it.
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class EvidenceLog:
    """Durable, one-event-per-file JSON evidence with recursive redaction."""

    def __init__(self, directory: str | Path, secret_values: Iterable[str] = ()) -> None:
        self.directory = Path(directory)
        self.redactor = SecretRedactor(secret_values)

    def emit(self, event: str, **fields: Any) -> Path:
        if not event or any(char.isspace() for char in event):
            raise ValueError("event must be a non-empty token")
        payload = {
            "event": event,
            "occurred_at": _utc_now(),
            "fields": self.redactor.value(fields),
        }
        stamp = time.time_ns()
        destination = self.directory / f"{stamp:020d}-{uuid.uuid4().hex}.json"
        atomic_write_json(destination, payload)
        return destination


@dataclass(frozen=True)
class BackupEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BackupPolicy:
    encryption_required: bool = True
    required_algorithm: str = "age"
    required_key_id: str | None = None
    required_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestoreReport:
    ok: bool
    errors: tuple[str, ...] = ()

    def render(self) -> str:
        return "restore: " + ("ok" if self.ok else "invalid\n" + "\n".join(self.errors))


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def create_backup_manifest(
    root: str | Path,
    manifest_path: str | Path,
    policy: BackupPolicy = BackupPolicy(),
) -> Path:
    """Record restore hashes and encryption requirements; never encrypts data itself."""

    if policy.encryption_required and (not policy.required_algorithm or not policy.required_key_id):
        raise ValueError("an encryption algorithm and key id are required")
    base = Path(root).resolve()
    entries: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(base).as_posix()
            size, digest = _file_digest(path)
            entries.append({"path": relative, "size": size, "sha256": digest})
    manifest = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "encryption": {
            "required": policy.encryption_required,
            "algorithm": policy.required_algorithm if policy.encryption_required else None,
            "key_id": policy.required_key_id if policy.encryption_required else None,
        },
        "required_paths": list(policy.required_paths),
        "entries": entries,
    }
    destination = Path(manifest_path)
    try:
        destination.resolve().relative_to(base)
    except ValueError:
        pass
    else:
        raise ValueError("manifest must not be inside the backup root")
    atomic_write_json(destination, manifest)
    return destination


def verify_restore(
    manifest_path: str | Path,
    restore_root: str | Path,
    policy: BackupPolicy = BackupPolicy(),
) -> RestoreReport:
    """Verify encryption metadata, required paths, sizes, and SHA-256 content hashes."""

    errors: list[str] = []
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return RestoreReport(False, ("manifest_unreadable",))
    if not isinstance(manifest, Mapping):
        return RestoreReport(False, ("manifest_invalid",))
    encryption = manifest.get("encryption", {})
    if not isinstance(encryption, Mapping):
        return RestoreReport(False, ("encryption_invalid",))
    if policy.encryption_required:
        if not encryption.get("required"):
            errors.append("encryption_not_required")
        if encryption.get("algorithm") != policy.required_algorithm:
            errors.append("encryption_algorithm_mismatch")
        if policy.required_key_id and encryption.get("key_id") != policy.required_key_id:
            errors.append("encryption_key_mismatch")
    root = Path(restore_root).resolve()
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return RestoreReport(False, tuple(errors + ["entries_invalid"]))
    declared_paths: set[str] = set()
    for entry in entries:
        relative = entry.get("path") if isinstance(entry, Mapping) else None
        if not isinstance(relative, str) or not relative or relative.startswith("/"):
            errors.append("path_invalid")
            continue
        candidate = (root / relative).resolve()
        if root != candidate and root not in candidate.parents:
            errors.append("path_traversal")
            continue
        declared_paths.add(relative)
        if not candidate.is_file():
            errors.append(f"missing:{relative}")
            continue
        size, digest = _file_digest(candidate)
        if size != entry.get("size"):
            errors.append(f"size_mismatch:{relative}")
        if digest != entry.get("sha256"):
            errors.append(f"hash_mismatch:{relative}")
    manifest_required_paths = manifest.get("required_paths", [])
    if not isinstance(manifest_required_paths, list) or not all(
        isinstance(path, str) for path in manifest_required_paths
    ):
        return RestoreReport(False, tuple(errors + ["required_paths_invalid"]))
    required_paths = set(policy.required_paths) | set(manifest_required_paths)
    errors.extend(f"required_missing:{path}" for path in sorted(required_paths - declared_paths))
    return RestoreReport(not errors, tuple(errors))
