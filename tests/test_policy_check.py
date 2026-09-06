from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import policy_check


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "test@example.invalid", cwd=tmp_path)
    _git("config", "user.name", "test", cwd=tmp_path)
    (tmp_path / ".gitignore").write_text("/*\n.env\n.env.*\n!/.env.example\n", encoding="utf-8")
    return tmp_path


def test_aprova_repo_sem_segredo(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _git("add", "-f", ".gitignore", "README.md", cwd=repo)
    assert policy_check.check(repo) == []


def test_reprova_arquivo_env_rastreado(tmp_path: Path):
    repo = _repo(tmp_path)
    env = repo / ".env.local"
    env.write_text("TOKEN=local\n", encoding="utf-8")
    _git("add", "-f", ".env.local", cwd=repo)
    findings = policy_check.check(repo)
    assert any(".env.local" in finding for finding in findings)


def test_reprova_segredo_em_arquivo_rastreado(tmp_path: Path):
    repo = _repo(tmp_path)
    # Montado em partes para não virar uma credencial literal no teste.
    secret = "AKIA" + "A" * 16
    (repo / "config.txt").write_text(f"credential={secret}\n", encoding="utf-8")
    _git("add", "-f", "config.txt", cwd=repo)
    findings = policy_check.check(repo)
    assert any("config.txt" in finding and "aws-access-key" in finding for finding in findings)


def test_marker_sintetico_e_apenas_de_linha(tmp_path: Path):
    repo = _repo(tmp_path)
    synthetic = "AKIA" + "B" * 16
    (repo / "tests").mkdir()
    (repo / "tests" / "test_fixture.py").write_text(
        f"fake={synthetic}  # SINTETICO\n", encoding="utf-8"
    )
    _git("add", "-f", "tests/test_fixture.py", cwd=repo)
    assert policy_check.check(repo) == []

    (repo / "tests" / "test_fixture.py").write_text(
        f"fake={synthetic}  # SINTETICO\nother={synthetic}\n", encoding="utf-8"
    )
    findings = policy_check.check(repo)
    assert any("tests/test_fixture.py" in finding for finding in findings)


def test_marker_sintetico_fora_de_fixture_canonica_nao_isenta(tmp_path: Path):
    repo = _repo(tmp_path)
    synthetic = "AKIA" + "C" * 16
    (repo / "app.py").write_text(
        f"credential={synthetic}  # SINTETICO\n", encoding="utf-8"
    )
    _git("add", "-f", "app.py", cwd=repo)
    findings = policy_check.check(repo)
    assert any("app.py" in finding and "aws-access-key" in finding for finding in findings)


def test_gitignore_incompleto_reprova(tmp_path: Path):
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    assert any("regra obrigatória ausente" in item for item in policy_check._check_gitignore(tmp_path))


@pytest.mark.parametrize("suffix,kind,needle", [
    (".txt", "oversized", "grande demais"),
    (".bin", "binary", "binário"),
])
def test_conteudo_fora_do_scanner_limit_reprova(
    tmp_path: Path, suffix: str, kind: str, needle: str
):
    repo = _repo(tmp_path)
    path = repo / ("payload" + suffix)
    if kind == "binary":
        path.write_bytes(b"safe\x00credential")
    else:
        path.write_text("safe\n" + "x" * (policy_check.MAX_TEXT_BYTES + 1), encoding="utf-8")
    _git("add", "-f", path.name, cwd=repo)
    findings = policy_check.check(repo)
    assert any(path.name in finding and needle in finding for finding in findings)
