"""Gate do hook `pre-push` versionado em `.githooks/`.

O hook é a primeira linha de defesa: os mesmos gates do CI de PR rodam na máquina de
quem empurra, antes de o push sair. Este arquivo prova, com um `git push` de verdade
para um remoto bare temporário, que o hook (1) libera o push com todos os gates verdes,
(2) bloqueia o push e nomeia o gate quando um deles reprova — e o remoto não recebe o
commit —, (3) não roda gate nenhum quando o push só apaga uma branch, e (4) escolhe o
modo do auditor do padrão ouro pelo placeholder em `AGENTS.md` (template × instância).

Os gates são substituídos por scripts falsos dentro do repositório temporário: o que
está sob teste é a mecânica do hook (ordem, bloqueio, mensagem), não os gates em si —
cada gate tem o seu próprio arquivo de teste. O interpretador vem de `COCKPIT_PYTHON`
(o mesmo que roda esta suíte), porque o repo temporário não tem `.venv` e `python3` no
PATH do Windows pode ser o atalho da Microsoft Store.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / ".githooks" / "pre-push"
TESTS_YML = RAIZ / ".github" / "workflows" / "tests.yml"
TETO = 120

# Os gates que o hook chama, na ordem. `ruff` e `gitleaks` ficam de fora: são
# condicionais (rodam só se a ferramenta existir) e não recebem script falso.
GATES = (
    "gate_veredito.py",
    "lint_routers.py",
    "padrao_ouro_audit.py",
    "policy_check.py",
    "operational_audit.py",
)

FALSO_VERDE = "import sys\nsys.exit(0)\n"
FALSO_VERMELHO = "import sys\nprint('gate falso reprovou', file=sys.stderr)\nsys.exit(1)\n"
# Registra os argumentos recebidos: é como o teste enxerga o modo do auditor.
FALSO_REGISTRA = (
    "import pathlib\nimport sys\n"
    "pathlib.Path('argv.txt').write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n"
    "sys.exit(0)\n"
)


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TETO, check=check,
        env=_env(),
    )


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["COCKPIT_PYTHON"] = sys.executable
    # Sem estas, `git commit` num repo novo pode cair no editor ou reclamar de identidade.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


@pytest.fixture()
def repo_com_hook(tmp_path: Path) -> tuple[Path, Path]:
    """Repo de trabalho com o hook ativado e um remoto bare; devolve (repo, bare)."""
    bare = tmp_path / "remoto.git"
    _git("init", "-q", "--bare", str(bare), cwd=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@t.invalid", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    _git("remote", "add", "origin", str(bare), cwd=repo)

    (repo / "tools").mkdir()
    for gate in GATES:
        (repo / "tools" / gate).write_text(FALSO_VERDE, encoding="utf-8")
    (repo / "AGENTS.md").write_text("# repo\n\ntipo: cockpit\n", encoding="utf-8")
    hooks = repo / ".githooks"
    hooks.mkdir()
    shutil.copy(HOOK, hooks / "pre-push")
    os.chmod(hooks / "pre-push", 0o755)
    _git("config", "core.hooksPath", ".githooks", cwd=repo)

    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "inicial", cwd=repo)
    return repo, bare


def _sha(ref: str, cwd: Path) -> str | None:
    r = _git("rev-parse", "--verify", "--quiet", ref, cwd=cwd, check=False)
    return r.stdout.strip() or None


# ---------------------------------------------------------------------------
# o arquivo em si


def test_hook_esta_versionado_executavel_e_em_lf():
    """Modo 100755 no índice (sem isso o git ignora o hook em silêncio) e LF puro
    (CR no fim da linha quebra o `sh`)."""
    r = _git("ls-files", "-s", ".githooks/pre-push", cwd=RAIZ)
    assert r.stdout.startswith("100755 "), r.stdout or "hook fora do índice git"
    blob = subprocess.run(
        ["git", "cat-file", "blob", "HEAD:.githooks/pre-push"], cwd=str(RAIZ),
        capture_output=True, timeout=TETO, check=False,
    )
    conteudo = blob.stdout if blob.returncode == 0 else HOOK.read_bytes()
    assert b"\r" not in conteudo, "CR no hook: sh do Git Bash e do Mac quebram"
    assert conteudo.startswith(b"#!/bin/sh\n")


def test_hook_e_ci_chamam_os_mesmos_gates():
    """"Gates iguais nos dois" é o contrato do modelo hook + CI de PR, e aqui ele é
    medido: o conjunto de `tools/*.py` invocados no hook é o mesmo do `tests.yml`."""
    import re

    padrao = re.compile(r"tools/([a-z_]+\.py)")

    def invocados(texto: str) -> set[str]:
        # Só linhas de comando; comentário citando um tool não é invocação.
        codigo = "\n".join(linha for linha in texto.splitlines() if not linha.lstrip().startswith("#"))
        return set(padrao.findall(codigo))

    no_hook = invocados(HOOK.read_text(encoding="utf-8"))
    no_ci = invocados(TESTS_YML.read_text(encoding="utf-8"))
    assert no_hook == set(GATES), no_hook
    assert no_hook == no_ci, f"hook={sorted(no_hook)} ci={sorted(no_ci)}"


# ---------------------------------------------------------------------------
# comportamento, com git push de verdade


def test_push_liberado_com_todos_os_gates_verdes(repo_com_hook):
    repo, bare = repo_com_hook
    r = _git("push", "-q", "origin", "main", cwd=repo, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "push liberado" in r.stderr + r.stdout
    assert _sha("refs/heads/main", bare) == _sha("HEAD", repo)


def test_push_bloqueado_nomeia_o_gate_e_o_remoto_nao_recebe(repo_com_hook):
    repo, bare = repo_com_hook
    (repo / "tools" / "lint_routers.py").write_text(FALSO_VERMELHO, encoding="utf-8")
    _git("commit", "-q", "-am", "quebra o lint", cwd=repo)

    r = _git("push", "-q", "origin", "main", cwd=repo, check=False)
    saida = r.stdout + r.stderr
    assert r.returncode != 0, saida
    assert "BLOQUEADO pelo gate" in saida
    assert "lint_routers.py" in saida
    # O gate seguinte não rodou: cadeia para no primeiro vermelho.
    assert "padrao_ouro_audit.py" not in saida
    assert _sha("refs/heads/main", bare) is None, "o remoto recebeu o commit apesar do bloqueio"


def test_push_que_so_apaga_branch_nao_roda_gate(repo_com_hook):
    repo, bare = repo_com_hook
    _git("push", "-q", "origin", "main", cwd=repo)
    _git("push", "-q", "origin", "main:refs/heads/descartavel", cwd=repo)
    # A partir daqui todo gate reprova; a deleção tem que passar mesmo assim.
    for gate in GATES:
        (repo / "tools" / gate).write_text(FALSO_VERMELHO, encoding="utf-8")
    r = _git("push", "-q", "origin", ":refs/heads/descartavel", cwd=repo, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gate:" not in r.stdout + r.stderr
    assert _sha("refs/heads/descartavel", bare) is None


@pytest.mark.parametrize(
    ("agents", "espera_template"),
    [
        ("# {{NOME_DO_REPO}}\n\ntipo: cockpit\n", True),   # padrao-ouro:ignorar
        ("# instancia-real\n\ntipo: cockpit\n", False),
    ],
)
def test_auditor_roda_em_modo_template_so_enquanto_ha_placeholder(repo_com_hook, agents, espera_template):
    repo, _ = repo_com_hook
    (repo / "AGENTS.md").write_text(agents, encoding="utf-8")
    (repo / "tools" / "padrao_ouro_audit.py").write_text(FALSO_REGISTRA, encoding="utf-8")
    _git("commit", "-q", "-am", "modo", cwd=repo)

    r = _git("push", "-q", "origin", "main", cwd=repo, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    argv = (repo / "argv.txt").read_text(encoding="utf-8")
    assert "--tipo cockpit" in argv, argv
    assert ("--template" in argv) is espera_template, argv
