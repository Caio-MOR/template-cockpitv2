"""Os dois casos de symlink do doctor e do inicializador, com skip condicional.

Criar symlink no Windows exige privilégio (modo desenvolvedor ou elevação); sem ele,
`Path.symlink_to` levanta `OSError` [WinError 1314]. Os testes ficam AQUI, fora dos
arquivos de gate, porque `tools/gate_veredito.py` reprova gate com teste pulado — o
skip é legítimo (condição de ambiente, não de código), mas não pode morar em
`tests/test_new_instance.py`. A condição é medida tentando criar um symlink de fato,
não lendo `os.name`: a máquina Windows COM privilégio roda os testes.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools import doctor

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

import initialize_template  # noqa: E402


def _pode_criar_symlink(tmp_path: Path) -> bool:
    alvo = tmp_path / "alvo-sonda"
    alvo.write_text("x", encoding="utf-8")
    try:
        (tmp_path / "link-sonda").symlink_to(alvo)
    except (OSError, NotImplementedError):
        return False
    return True


@pytest.fixture()
def com_symlink(tmp_path: Path) -> Path:
    if not _pode_criar_symlink(tmp_path):
        pytest.skip("este SO/usuário não pode criar symlink (Windows sem modo desenvolvedor)")
    return tmp_path


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=60)


def test_doctor_env_file_symlink_fails_closed_even_when_target_is_inside_repo(com_symlink: Path) -> None:
    repo = com_symlink / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / ".env.example").write_text("REQUIRED_TOKEN=\n", encoding="utf-8")
    (repo / ".env-real").write_text("REQUIRED_TOKEN=secret\n", encoding="utf-8")
    (repo / ".env-link").symlink_to(repo / ".env-real")

    report = doctor.check(repo, env_file=".env-link", environ={})

    assert "env_file_unsafe" in {issue.code for issue in report.issues}
    assert "secret" not in report.render()


def test_initializer_rejects_symlinked_targets(com_symlink: Path) -> None:
    instance = com_symlink / "instance"
    shutil.copytree(RAIZ / ".specs", instance / ".specs")
    outside = com_symlink / "outside"
    outside.mkdir()
    specs = instance / ".specs"
    specs.rename(com_symlink / "saved-specs")
    specs.symlink_to(outside, target_is_directory=True)

    assert initialize_template.initialize(instance, dry_run=False) == 1
    assert not list(outside.iterdir())
