"""Temporary-copy proof for explicit template initialization."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import initialize_template  # noqa: E402
import validate_new_instance  # noqa: E402


def _copy_template(tmp_path: Path) -> Path:
    instance = tmp_path / "instance"
    shutil.copytree(RAIZ, instance, ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__"))
    return instance


def _add_v2_build_records(instance: Path) -> None:
    record = instance / ".specs" / "features" / "template-v2"
    record.mkdir(parents=True, exist_ok=True)
    (record / "spec.md").write_text("build evidence", encoding="utf-8")


def test_dry_run_is_non_mutating_and_apply_is_allowlisted(tmp_path):
    instance = _copy_template(tmp_path)
    _add_v2_build_records(instance)
    unrelated = instance / ".specs" / "features" / "user-work" / "note.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    before = (instance / ".specs" / "STATE.md").read_text(encoding="utf-8")

    assert initialize_template.initialize(instance, dry_run=True) == 0
    assert (instance / ".specs" / "features" / "template-v2").is_dir()
    assert (instance / ".specs" / "STATE.md").read_text(encoding="utf-8") == before

    assert initialize_template.initialize(instance, dry_run=False) == 0
    assert not (instance / ".specs" / "features" / "template-v2").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (instance / ".specs" / "STATE.md").read_text(encoding="utf-8") == initialize_template.INITIAL_STATE


def test_validator_rejects_build_records_and_placeholders_but_allows_later_files(tmp_path):
    instance = _copy_template(tmp_path)
    _add_v2_build_records(instance)
    (instance / "AGENTS.md").write_text("{{NOME_DO_REPO}}", encoding="utf-8")
    findings = validate_new_instance.static_findings(instance)
    assert ".specs/features/template-v2" in findings
    assert "AGENTS.md" in findings

    assert initialize_template.initialize(instance, dry_run=False) == 0
    for path in instance.rglob("*"):
        if path.is_file() and path.suffix.lower() in validate_new_instance.TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8")
            path.write_text(validate_new_instance.PLACEHOLDER.sub("resolved", text), encoding="utf-8")
    (instance / ".github" / "CODEOWNERS").write_text("* @resolved\n", encoding="utf-8")
    (instance / ".gitleaksignore").write_text("known-fingerprint\n", encoding="utf-8")
    assert validate_new_instance.static_findings(instance) == []

    (instance / ".specs" / "features" / "template-v2").mkdir(parents=True)
    assert ".specs/features/template-v2" in validate_new_instance.static_findings(instance)
