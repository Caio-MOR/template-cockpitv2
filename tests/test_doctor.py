from __future__ import annotations

import subprocess
from pathlib import Path

from tools import doctor


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path, schema: str = "") -> Path:
    """Cockpit válido mínimo: hook pre-push versionado e ativado (core.hooksPath)."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "test@example.invalid", cwd=tmp_path)
    _git("config", "user.name", "test", cwd=tmp_path)
    (tmp_path / ".gitignore").write_text("/*\n.env\n.env.*\n!/.env.example\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(schema, encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.12.13\n", encoding="utf-8")
    (tmp_path / ".githooks").mkdir()
    (tmp_path / ".githooks" / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    _git("config", "core.hooksPath", ".githooks", cwd=tmp_path)
    _git("add", "-f", ".gitignore", ".env.example", ".python-version", ".githooks/pre-push", cwd=tmp_path)
    _git("commit", "-qm", "fixture", cwd=tmp_path)
    return tmp_path


def _codes(report: doctor.DoctorReport) -> set[str]:
    return {issue.code for issue in report.issues}


def test_empty_schema_is_a_valid_cockpit(tmp_path: Path) -> None:
    report = doctor.check(_repo(tmp_path), python_version=(3, 12, 13))

    assert report.ok
    assert report.checked == ("python", "git", "hooks", "security", "environment")


def test_required_and_optional_fields_use_names_only(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        "# optional\nOPTIONAL_URL=\nREQUIRED_TOKEN=\n",
    )
    (repo / ".env").write_text("REQUIRED_TOKEN=super-secret-value\n", encoding="utf-8")
    report = doctor.check(repo, python_version=(3, 12, 13), environ={})

    assert report.ok
    assert "super-secret-value" not in repr(report)
    assert "super-secret-value" not in report.render()


def test_missing_required_field_is_reported_without_value(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "REQUIRED_TOKEN=\n# optional\nOPTIONAL_URL=\n")

    report = doctor.check(repo, python_version=(3, 12, 13), environ={})

    assert not report.ok
    assert doctor.DoctorIssue("environment", "missing_required", "REQUIRED_TOKEN") in report.issues


def test_schema_and_local_env_mutations_fail(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "REQUIRED_TOKEN=example-value\nREQUIRED_TOKEN=\n")
    (repo / ".env").write_text("UNKNOWN=value\nnot-an-assignment\n", encoding="utf-8")

    report = doctor.check(repo, python_version=(3, 12, 13), environ={})

    assert {"schema_contains_value", "schema_duplicate_name", "env_malformed", "unknown_name"} <= _codes(report)


def test_python_version_must_be_exact_and_match_runtime(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    (repo / ".python-version").write_text("3.12\n", encoding="utf-8")
    assert "version_not_exact" in _codes(doctor.check(repo, python_version=(3, 12, 13)))

    (repo / ".python-version").write_text("3.12.13\n", encoding="utf-8")
    assert "version_mismatch" in _codes(doctor.check(repo, python_version=(3, 12, 12)))


def test_git_requires_a_named_branch_and_can_enforce_expected_branch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert "unexpected_branch" in _codes(
        doctor.check(repo, expected_branch="feat/cockpit", python_version=(3, 12, 13))
    )

    _git("checkout", "--detach", cwd=repo)
    assert "detached_head" in _codes(doctor.check(repo, python_version=(3, 12, 13)))


def test_hooks_path_must_point_at_the_versioned_hooks(tmp_path: Path) -> None:
    """Clone que não ativou `core.hooksPath` empurra sem gate: o doctor reprova e
    diz o comando de conserto."""
    repo = _repo(tmp_path)
    _git("config", "--unset", "core.hooksPath", cwd=repo)
    report = doctor.check(repo, python_version=(3, 12, 13))
    assert "hooks_path_not_configured" in _codes(report)
    assert "git config core.hooksPath .githooks" in report.render()

    _git("config", "core.hooksPath", "outra-pasta", cwd=repo)
    assert "hooks_path_not_configured" in _codes(doctor.check(repo, python_version=(3, 12, 13)))

    # Caminho absoluto equivalente também vale: o que importa é aonde aponta.
    _git("config", "core.hooksPath", str(repo / ".githooks"), cwd=repo)
    assert "hooks_path_not_configured" not in _codes(doctor.check(repo, python_version=(3, 12, 13)))


def test_hook_file_must_exist(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".githooks" / "pre-push").unlink()
    report = doctor.check(repo, python_version=(3, 12, 13))
    assert "hook_file_missing" in _codes(report)
    assert ".githooks/pre-push" in report.render()


def test_security_policy_is_a_real_dependency_of_the_doctor(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    calls: list[Path] = []

    def fake_policy_check(root: Path) -> list[str]:
        calls.append(root)
        return ["safe finding name only"]

    monkeypatch.setattr(doctor.policy_check, "check", fake_policy_check)
    report = doctor.check(repo, python_version=(3, 12, 13))

    assert calls == [repo.resolve()]
    assert "policy_failed" in _codes(report)


def test_main_has_a_stable_safe_verdict(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert doctor.main([str(repo), "--branch", "other-branch"]) == 1
    output = capsys.readouterr().out

    assert output.startswith("doctor: REPROVADO")
    assert "3.12.13" not in output


def test_env_file_outside_repo_fails_closed_without_path_or_value(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    outside = tmp_path.parent / "production.env"
    outside.write_text("PRODUCTION_SECRET=do-not-print\n", encoding="utf-8")

    report = doctor.check(repo, env_file=outside, environ={})

    assert "env_file_unsafe" in _codes(report)
    assert "production.env" not in report.render()
    assert "do-not-print" not in repr(report)


def test_env_file_parent_traversal_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    outside = repo.parent / "outside.env"
    outside.write_text("REQUIRED_TOKEN=secret\n", encoding="utf-8")

    report = doctor.check(repo, env_file="../outside.env", environ={})

    assert "env_file_unsafe" in _codes(report)

# O caso de symlink (`.env-link` -> `.env-real`) vive em `tests/test_symlink_privilegio.py`:
# criar symlink exige privilégio no Windows e um teste pulado num arquivo de gate
# reprova o veredito.
