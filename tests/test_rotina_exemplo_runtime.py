"""Integration tests for the example workflow's operational safety contract."""

from __future__ import annotations

import importlib.util
import json
import threading
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "workflows/_exemplo-rotina/scripts/rotina_exemplo.py"
_SPEC = importlib.util.spec_from_file_location("rotina_exemplo_runtime_target", SCRIPT)
assert _SPEC and _SPEC.loader
rotina_exemplo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rotina_exemplo)


@pytest.fixture
def rotina_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    logs = tmp_path / "logs"
    monkeypatch.setattr(rotina_exemplo, "PASTA", tmp_path)
    monkeypatch.setattr(rotina_exemplo, "LOGS", logs)
    monkeypatch.setattr(rotina_exemplo, "LOG", logs / "log.txt")
    monkeypatch.setattr(rotina_exemplo, "MARKER", logs / ".last_ok")
    monkeypatch.setattr(rotina_exemplo, "LOCK", logs / ".rotina_exemplo.lock")
    monkeypatch.setattr(rotina_exemplo, "EVIDENCE", logs / "evidence")
    return logs


def _events(logs: Path) -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted((logs / "evidence").glob("*.json"))]


def test_duplicate_run_is_a_noop_after_success(rotina_fs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(rotina_exemplo, "processar", lambda attempt: calls.append(attempt) or True)
    covered = date(2026, 9, 4)

    assert rotina_exemplo.main(covered) == 0
    assert rotina_exemplo.main(covered) == 0
    assert calls == [1]
    assert rotina_exemplo.MARKER.read_text() == "2026-09-04\n"
    assert [event["event"] for event in _events(rotina_fs)] == ["started", "completed"]
    assert "já concluída" in rotina_exemplo.LOG.read_text()


def test_concurrent_run_cannot_enter_processing_twice(
    rotina_fs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def process(attempt: int) -> bool:
        calls.append(attempt)
        entered.set()
        assert release.wait(timeout=2)
        return True

    monkeypatch.setattr(rotina_exemplo, "processar", process)
    covered = date(2026, 9, 4)
    first_result: list[int] = []
    first = threading.Thread(target=lambda: first_result.append(rotina_exemplo.main(covered)))
    first.start()
    assert entered.wait(timeout=2)
    assert rotina_exemplo.main(covered) == 0
    release.set()
    first.join(timeout=2)

    assert first_result == [0]
    assert calls == [1]
    assert rotina_exemplo.MARKER.exists()
    assert "duplicado/concurrente" in rotina_exemplo.LOG.read_text()


def test_transient_processing_is_bounded_and_completes(
    rotina_fs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def process(attempt: int) -> bool:
        calls.append(attempt)
        return attempt == 3

    monkeypatch.setattr(rotina_exemplo, "processar", process)
    assert rotina_exemplo.main(date(2026, 9, 4)) == 0
    assert calls == [1, 2, 3]
    assert "tentativa 1/3 falhou" in rotina_exemplo.LOG.read_text()
    assert rotina_exemplo.MARKER.exists()


def test_delivery_failure_has_no_completion_marker_or_event(
    rotina_fs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotina_exemplo, "entregar", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    assert rotina_exemplo.main(date(2026, 9, 4)) == 1
    assert not rotina_exemplo.MARKER.exists()
    assert [event["event"] for event in _events(rotina_fs)] == ["started"]
    assert "entrega falhou" in rotina_exemplo.LOG.read_text()


def test_atomic_marker_fault_preserves_previous_marker(
    rotina_fs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rotina_exemplo.LOGS.mkdir(parents=True)
    rotina_exemplo.MARKER.write_text("2026-09-03\n")

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(rotina_exemplo.os, "replace", fail_replace)
    with pytest.raises(OSError):
        rotina_exemplo._write_marker(date(2026, 9, 4))
    assert rotina_exemplo.MARKER.read_text() == "2026-09-03\n"
    assert list(rotina_exemplo.LOGS.glob(".*.tmp")) == []
