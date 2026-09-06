"""Fault-injection tests for the dependency-free cockpit runtime."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from tools import cockpit_runtime
from tools.cockpit_runtime import (
    BackupPolicy,
    ConfigField,
    EvidenceLog,
    IdempotencyLock,
    LockBusyError,
    PermanentError,
    RetryExhaustedError,
    RetryPolicy,
    RunIdentity,
    TransientError,
    atomic_write_json,
    create_backup_manifest,
    doctor,
    run_with_retry,
    verify_restore,
)


def test_doctor_is_typed_and_never_prints_values(capsys: pytest.CaptureFixture[str]) -> None:
    secret = "super-secret-value"
    report = doctor(
        [
            ConfigField("API_TOKEN", secret=True),
            ConfigField("PORT", type=int),
            ConfigField("DEBUG", type=bool, required=False),
        ],
        {"API_TOKEN": secret, "PORT": "not-a-port", "DEBUG": "maybe"},
    )

    rendered = report.render()
    assert not report.ok
    assert "API_TOKEN" in rendered and "PORT" in rendered
    assert secret not in rendered
    assert "maybe" not in rendered
    assert capsys.readouterr().out == ""


def test_doctor_accepts_bool_and_choices() -> None:
    report = doctor(
        [ConfigField("MODE", choices=frozenset({"safe", "fast"})), ConfigField("ENABLED", type=bool)],
        {"MODE": "safe", "ENABLED": "yes"},
    )
    assert report.ok


def test_lock_rejects_live_owner_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    first = IdempotencyLock(path, RunIdentity("sync", "customer-1"), stale_after_seconds=10)
    second = IdempotencyLock(path, RunIdentity("sync", "customer-1"), stale_after_seconds=10)
    first.acquire()
    with pytest.raises(LockBusyError):
        second.acquire()
    first.release()
    second.acquire()
    assert json.loads(path.read_text())['run_id'] == second.identity.run_id
    second.release()
    assert not path.exists()


def test_lock_release_survives_corrupted_lock_without_deleting_it(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    lock = IdempotencyLock(path, RunIdentity("sync", "key"))
    lock.acquire()
    path.write_text("{truncated", encoding="utf-8")

    lock.release()

    assert path.exists()
    assert lock._held is False


def test_lock_does_not_recover_old_lock_when_owner_process_is_alive(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    path.write_text(
        json.dumps({"run_id": "slow", "pid": os.getpid(), "host": socket.gethostname()}),
        encoding="utf-8",
    )
    old = path.stat().st_mtime - 100
    os.utime(path, (old, old))
    lock = IdempotencyLock(path, RunIdentity("sync", "key"), stale_after_seconds=10)

    with pytest.raises(LockBusyError):
        lock.acquire()
    assert not list(tmp_path.glob("run.lock.stale.*"))


@pytest.mark.parametrize(("state", "expected"), [(True, True), (False, False), (None, True)])
def test_windows_pid_liveness_never_uses_the_posix_signal_probe(
    monkeypatch: pytest.MonkeyPatch, state: bool | None, expected: bool
) -> None:
    """Windows signal 0 is CTRL_C_EVENT, not the harmless POSIX liveness probe."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(cockpit_runtime, "_windows_process_state", lambda _pid: state)
    monkeypatch.setattr(cockpit_runtime.os, "kill", lambda pid, signal: calls.append((pid, signal)))

    assert cockpit_runtime._pid_is_alive(123, platform="nt") is expected
    assert calls == []


def test_lock_recovers_stale_owner_and_preserves_forensics(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    path.write_text(json.dumps({"run_id": "crashed", "workflow": "sync"}))
    old = path.stat().st_mtime - 100
    os.utime(path, (old, old))
    lock = IdempotencyLock(path, RunIdentity("sync", "key"), stale_after_seconds=10)
    lock.acquire()
    assert path.exists()
    stale_files = list(tmp_path.glob("run.lock.stale.*"))
    assert len(stale_files) == 1
    lock.release()


def test_lock_context_releases_after_fault(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    with pytest.raises(RuntimeError):
        with IdempotencyLock(path, RunIdentity("job", "key")):
            raise RuntimeError("fault")
    assert not path.exists()


def test_retry_retries_transient_with_bounded_delays() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientError("temporary")
        return "done"

    result = run_with_retry(
        operation,
        RetryPolicy(max_attempts=4, deadline_seconds=20, base_delay_seconds=1, jitter_ratio=0),
        sleep=sleeps.append,
        random_value=lambda: 0.5,
    )
    assert result == "done"
    assert attempts == 3
    assert sleeps == [1, 2]


def test_retry_does_not_retry_permanent_failure() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise PermanentError("bad input")

    with pytest.raises(PermanentError):
        run_with_retry(operation, RetryPolicy(max_attempts=5), sleep=lambda _: pytest.fail("slept"))
    assert attempts == 1


def test_retry_converts_exhaustion_and_respects_deadline() -> None:
    attempts = 0
    now = [0.0]
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("network")

    def monotonic() -> float:
        return now[0]

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    with pytest.raises(RetryExhaustedError) as caught:
        run_with_retry(
            operation,
            RetryPolicy(max_attempts=10, deadline_seconds=2, base_delay_seconds=1, jitter_ratio=0),
            sleep=sleep,
            monotonic=monotonic,
        )
    assert attempts == 2
    assert sleeps == [1, 1]
    assert caught.value.attempts == 2
    assert isinstance(caught.value.last_error, TimeoutError)


def test_retry_converts_attempt_exhaustion() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise TransientError("still offline")

    with pytest.raises(RetryExhaustedError) as caught:
        run_with_retry(
            operation,
            RetryPolicy(max_attempts=3, deadline_seconds=20, base_delay_seconds=0),
            sleep=lambda _: None,
        )
    assert attempts == 3
    assert caught.value.attempts == 3
    assert isinstance(caught.value.last_error, TransientError)


def test_atomic_write_tolerates_platform_without_directory_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    real_open = os.open

    def reject_directory(path: str | os.PathLike[str], flags: int, *args: int) -> int:
        if Path(path) == tmp_path:
            raise OSError("directory handles unsupported")
        return real_open(path, flags, *args)

    monkeypatch.setattr(os, "open", reject_directory)
    atomic_write_json(destination, {"version": 1})
    assert json.loads(destination.read_text()) == {"version": 1}


def test_evidence_is_atomic_and_recursively_redacted(tmp_path: Path) -> None:
    evidence = EvidenceLog(tmp_path / "evidence", secret_values=["custom-secret"])
    path = evidence.emit(
        "completed",
        token="custom-secret",
        nested={"password": "visible-never", "message": "Bearer abcdefghijklmnop"},
        count=2,
    )
    payload = json.loads(path.read_text())
    assert payload["event"] == "completed"
    assert payload["fields"]["token"] == "[REDACTED]"
    assert payload["fields"]["nested"]["password"] == "[REDACTED]"
    assert "abcdefghijklmnop" not in path.read_text()
    assert list((tmp_path / "evidence").glob(".*")) == []


def test_atomic_write_leaves_previous_value_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    atomic_write_json(destination, {"version": 1})

    def fail_replace(_source: str, _target: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        atomic_write_json(destination, {"version": 2})
    assert json.loads(destination.read_text())["version"] == 1
    assert list(tmp_path.glob(".state.json.*")) == []


def test_backup_manifest_requires_encryption_metadata(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("hello")
    with pytest.raises(ValueError):
        create_backup_manifest(tmp_path, tmp_path.parent / "manifest.json")


def test_backup_manifest_rejects_any_destination_inside_root(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("hello")
    with pytest.raises(ValueError):
        create_backup_manifest(
            tmp_path,
            tmp_path / "nested" / "manifest.json",
            BackupPolicy(required_key_id="key"),
        )


def test_backup_manifest_and_restore_verification_detect_tamper(tmp_path: Path) -> None:
    source = tmp_path / "source"
    restore = tmp_path / "restore"
    source.mkdir()
    restore.mkdir()
    (source / "data.txt").write_text("hello")
    policy = BackupPolicy(required_key_id="key-2026")
    manifest_path = tmp_path / "manifest.json"
    create_backup_manifest(source, manifest_path, policy)
    (restore / "data.txt").write_text("tampered")
    report = verify_restore(manifest_path, restore, policy)
    assert not report.ok
    assert "hash_mismatch:data.txt" in report.errors


def test_restore_rejects_path_traversal_and_missing_required_file(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    atomic_write_json(
        manifest,
        {
            "encryption": {"required": True, "algorithm": "age", "key_id": "key"},
            "required_paths": ["important.txt"],
            "entries": [
                {"path": "../escape.txt", "size": 0, "sha256": ""},
                {"path": "other.txt", "size": 0, "sha256": ""},
            ],
        },
    )
    report = verify_restore(manifest, tmp_path / "restore", BackupPolicy(required_key_id="key"))
    assert not report.ok
    assert "path_traversal" in report.errors
    assert "required_missing:important.txt" in report.errors


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ([], "manifest_invalid"),
        ({"encryption": [], "entries": []}, "encryption_invalid"),
        (
            {
                "encryption": {"required": True, "algorithm": "age", "key_id": "key"},
                "required_paths": {"bad": "value"},
                "entries": [],
            },
            "required_paths_invalid",
        ),
    ],
)
def test_restore_rejects_malformed_manifest_shapes(
    tmp_path: Path, manifest: object, expected: str
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = verify_restore(manifest_path, tmp_path / "restore", BackupPolicy(required_key_id="key"))
    assert not report.ok
    assert report.errors == (expected,)
