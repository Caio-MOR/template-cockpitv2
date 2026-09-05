"""Mutation tests for the local operational maturity auditor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.operational_audit import Repo, audit, main, snapshot

ROOT = Path(__file__).resolve().parents[1]


def _repo_mutated(path: str, replacement: str) -> Repo:
    repo = snapshot(ROOT)
    texts = dict(repo.texts)
    original = repo.text(path)
    assert original is not None
    texts[path] = replacement
    return Repo(repo.root, repo.files, texts)


def test_current_checkout_is_a_complete_local_ten() -> None:
    result = audit(ROOT)
    assert result.score == 10.0
    assert result.ok
    assert len(result.categories) == 10
    assert all(category.ok for category in result.categories)
    assert result.remote_checks


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        ("AGENTS.md", "type: cockpit\n"),
        ("tools/gate_veredito.py", ""),
        (".gitignore", "/*\n"),
        ("requirements.txt", "not-a-lock==0\n"),
        ("tools/policy_check.py", ""),
        ("tools/cockpit_runtime.py", ""),
        ("README.md", "# no operating contract\n"),
    ],
)
def test_removing_a_control_lowers_the_score(path: str, replacement: str) -> None:
    mutated = _repo_mutated(path, replacement)
    result = audit(mutated)
    assert result.score < 10.0
    assert any(not category.ok for category in result.categories)


@pytest.mark.parametrize(
    "command",
    (
        "ruff check .",
        "gitleaks detect --source . --no-banner --redact --verbose",
        "bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows",
    ),
)
def test_missing_required_local_command_lowers_the_score(command: str) -> None:
    readme = ROOT.joinpath("README.md").read_text(encoding="utf-8")
    mutated = _repo_mutated("README.md", readme.replace(command, "", 1))
    result = audit(mutated)
    assert result.score < 10.0
    assert any(finding.path == "README.md" and command in finding.message for finding in result.findings)


def test_findings_are_path_only_and_no_secret_values_are_echoed() -> None:
    repo = _repo_mutated(".gitignore", "real-secret-value\n")
    result = audit(repo)
    rendered = "\n".join(finding.render() for finding in result.findings)
    assert "real-secret-value" not in rendered
    assert all(finding.path for finding in result.findings)


def test_synthetic_repo_cannot_pass_empty_truth() -> None:
    result = audit(Repo(ROOT, frozenset()))
    assert result.score == 0.0
    assert not result.ok


def test_json_output_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--json", str(ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["score"] == 10.0
    assert len(payload["categories"]) == 10
    assert payload["remote_checks"]


def test_invalid_root_is_a_usage_error() -> None:
    assert main(["/this/path/does/not/exist"]) == 2
