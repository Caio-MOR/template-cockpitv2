"""Gate do hook `pre-commit` versionado em `.githooks/`.

`.githooks/pre-push` é a suíte pesada, na hora do push; `.githooks/pre-commit` é o
gate rápido, na hora do commit — só `ruff check` nos arquivos `.py` staged e
`tools/policy_check.py`. Este arquivo prova, com um `git commit` de verdade num
repositório temporário, que o hook (1) existe versionado, executável e em LF, (2)
declara os dois gates que promete, (3) bloqueia o commit quando um deles reprova,
(4) degrada em silêncio (avisa e segue) sem `ruff` instalado, e (5) que
`.pre-commit-config.yaml` invoca exatamente este mesmo script, sem duplicar a lista
de checagens.

O `ruff` é substituído por um comando falso via `PRECOMMIT_RUFF_CMD` (o vão de teste
documentado no próprio hook) — o que está sob teste é a mecânica do hook (staged-only,
ordem, bloqueio, degradação), não o `ruff` em si. `tools/policy_check.py` também é
substituído por um script falso dentro do repositório temporário, pela mesma razão que
`test_pre_push_hook.py` já usa: cada gate tem o próprio arquivo de teste.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / ".githooks" / "pre-commit"
CONFIG = RAIZ / ".pre-commit-config.yaml"
TETO = 60

FALSO_VERDE = "import sys\nsys.exit(0)\n"
FALSO_VERMELHO = "import sys\nprint('policy_check falso reprovou', file=sys.stderr)\nsys.exit(1)\n"

# Fake de ruff controlado por env var, no mesmo espírito de tests/fixtures/fake_ruff.py
# (T5) — mas aqui é `--version`/`check <arquivos...>`, o formato que o hook invoca.
FAKE_RUFF = (
    "import os, sys\n"
    "modo = os.environ.get('FAKE_RUFF_MODE', 'limpo')\n"
    "if sys.argv[1:2] == ['--version']:\n"
    "    sys.exit(0)\n"
    "if modo == 'achado':\n"
    "    print('x.py:1:1: E501 linha longa demais')\n"
    "    sys.exit(1)\n"
    "sys.exit(0)\n"
)


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TETO, check=check,
        env=env if env is not None else _env(),
    )


def _env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["COCKPIT_PYTHON"] = sys.executable
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.update(extra)
    return env


@pytest.fixture()
def repo_com_hook(tmp_path: Path) -> Path:
    """Repo de trabalho com `core.hooksPath=.githooks` e `policy_check.py` falso verde."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@t.invalid", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)

    (repo / "tools").mkdir()
    (repo / "tools" / "policy_check.py").write_text(FALSO_VERDE, encoding="utf-8")
    (repo / "fake_ruff.py").write_text(FAKE_RUFF, encoding="utf-8")

    hooks = repo / ".githooks"
    hooks.mkdir()
    import shutil
    shutil.copy(HOOK, hooks / "pre-commit")
    os.chmod(hooks / "pre-commit", 0o755)
    _git("config", "core.hooksPath", ".githooks", cwd=repo)

    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    # O ruff real (via COCKPIT_PYTHON) acusaria o próprio fake_ruff.py; o commit
    # inicial do fixture não é o que está sob teste, então roda com o ruff falso
    # neutro (limpo) — cada teste troca o modo pra exercitar o ramo que quer.
    _git(
        "commit", "-q", "-m", "inicial", cwd=repo,
        env=_env(PRECOMMIT_RUFF_CMD=f"{sys.executable} fake_ruff.py", FAKE_RUFF_MODE="limpo"),
    )
    return repo


def _commit_arquivo_py(repo: Path, nome: str, conteudo: str, env: dict[str, str], mensagem: str = "novo py"):
    (repo / nome).write_text(conteudo, encoding="utf-8")
    _git("add", nome, cwd=repo)
    return _git("commit", "-q", "-m", mensagem, cwd=repo, env=env, check=False)


# ---------------------------------------------------------------------------
# o arquivo em si


def test_hook_esta_versionado_executavel_e_em_lf():
    r = _git("ls-files", "-s", ".githooks/pre-commit", cwd=RAIZ)
    assert r.stdout.startswith("100755 "), r.stdout or "hook fora do índice git"
    blob = subprocess.run(
        ["git", "cat-file", "blob", "HEAD:.githooks/pre-commit"], cwd=str(RAIZ),
        capture_output=True, timeout=TETO, check=False,
    )
    conteudo = blob.stdout if blob.returncode == 0 else HOOK.read_bytes()
    assert b"\r" not in conteudo, "CR no hook: sh do Git Bash e do Mac quebram"
    assert conteudo.startswith(b"#!/bin/sh\n")


def test_hook_declara_os_dois_gates():
    texto = HOOK.read_text(encoding="utf-8")
    assert "ruff" in texto
    assert "tools/policy_check.py" in texto


def test_pre_commit_config_invoca_exatamente_o_mesmo_script():
    """Paridade: `.pre-commit-config.yaml` não duplica a lista de checagens — só
    aponta para o script que já tem a lógica."""
    assert CONFIG.is_file(), ".pre-commit-config.yaml ausente na raiz"
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    hooks = config["repos"][0]["hooks"]
    assert len(hooks) == 1
    entry = hooks[0]["entry"]
    assert entry.replace("\\", "/").lstrip("./") == ".githooks/pre-commit".lstrip("./")
    assert (RAIZ / entry).resolve() == HOOK.resolve()
    assert config["repos"][0]["repo"] == "local"


def test_gitignore_libera_o_pre_commit_config():
    texto = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "!/.pre-commit-config.yaml" in texto


# ---------------------------------------------------------------------------
# comportamento, com git commit de verdade


def test_commit_liberado_com_ruff_limpo_e_policy_verde(repo_com_hook: Path):
    env = _env(PRECOMMIT_RUFF_CMD=f"{sys.executable} fake_ruff.py", FAKE_RUFF_MODE="limpo")
    r = _commit_arquivo_py(repo_com_hook, "ok.py", "x = 1\n", env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gates verdes" in r.stdout + r.stderr


def test_commit_bloqueado_com_arquivo_py_sujo_staged(repo_com_hook: Path):
    env = _env(PRECOMMIT_RUFF_CMD=f"{sys.executable} fake_ruff.py", FAKE_RUFF_MODE="achado")
    r = _commit_arquivo_py(repo_com_hook, "sujo.py", "x=1\n", env)
    saida = r.stdout + r.stderr
    assert r.returncode != 0, saida
    assert "BLOQUEADO pelo gate" in saida
    assert "ruff" in saida
    # policy_check não roda: a cadeia para no primeiro vermelho.
    assert "policy_check" not in saida.split("BLOQUEADO pelo gate")[0].split("\n")[-1]


def test_commit_bloqueado_quando_policy_check_reprova(repo_com_hook: Path):
    (repo_com_hook / "tools" / "policy_check.py").write_text(FALSO_VERMELHO, encoding="utf-8")
    env = _env(PRECOMMIT_RUFF_CMD=f"{sys.executable} fake_ruff.py", FAKE_RUFF_MODE="limpo")
    r = _commit_arquivo_py(repo_com_hook, "ok2.py", "x = 1\n", env)
    saida = r.stdout + r.stderr
    assert r.returncode != 0, saida
    assert "BLOQUEADO pelo gate" in saida
    assert "policy_check.py" in saida


def test_degrada_sem_ruff_instalado_e_segue_para_policy_check(repo_com_hook: Path):
    """`PRECOMMIT_RUFF_CMD` apontando pra um binário inexistente simula ruff ausente:
    o hook avisa, não bloqueia por isso, e o próximo gate roda."""
    env = _env(PRECOMMIT_RUFF_CMD="ruff_binario_que_nao_existe_xyz")
    r = _commit_arquivo_py(repo_com_hook, "semruff.py", "x=1\n", env)
    saida = r.stdout + r.stderr
    assert r.returncode == 0, saida
    assert "AVISO" in saida
    assert "gate: politica de segredos" in saida
    assert "gates verdes" in saida


def test_sem_arquivo_staged_sai_zero_rapido(repo_com_hook: Path):
    env = _env(PRECOMMIT_RUFF_CMD=f"{sys.executable} fake_ruff.py", FAKE_RUFF_MODE="achado")
    r = subprocess.run(
        ["sh", str((repo_com_hook / ".githooks" / "pre-commit"))],
        cwd=str(repo_com_hook), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TETO, env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""
