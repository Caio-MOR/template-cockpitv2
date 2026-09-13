# -*- coding: utf-8 -*-
"""Testes do lint de routers (`tools/lint_routers.py`).

Duas famílias: o smoke, que roda o lint no PRÓPRIO repo por subprocesso e exige
`0 erro(s)`; e o laboratório, que monta árvores sintéticas em `tmp_path` com índice
injetado para provar que o lint REPROVA referência morta — sem isso, "0 erro(s)" no
repo real poderia ser um lint que não enxerga nada.
"""
import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# Teto de duração de todo subprocesso deste gate. Freio da regra `loop-engineering`:
# subprocesso sem teto pendura o gate em vez de reprová-lo.
TETO_SUBPROC = 120

RAIZ = Path(__file__).resolve().parents[1]
LINT_PATH = RAIZ / "tools" / "lint_routers.py"
spec = importlib.util.spec_from_file_location("lint_routers", LINT_PATH)
assert spec is not None and spec.loader is not None, "spec do lint_routers.py não resolveu"
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

SEM_IGNORE: Callable[[list[str]], dict[str, str]] = lambda cands: {}  # noqa: E731 — nada é "fora do git por design"


def arvore(tmp_path, arquivos):
    """Escreve os arquivos e devolve o índice sintético (as chaves)."""
    for rel, texto in arquivos.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return set(arquivos)


def _repo_git(tmp_path, arquivos):
    """Repo git real em tmp_path, com os arquivos no índice (staged, sem commit)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=TETO_SUBPROC)
    for rel, texto in arquivos.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=TETO_SUBPROC)
    return repo


def _roda_cli(*args):
    # encoding explícito: o lint emite UTF-8 quando a saída é capturada; decodificar
    # com o locale traria de volta o mojibake que ele existe para matar.
    return subprocess.run(
        [sys.executable, str(LINT_PATH), *args], capture_output=True, text=True,
        encoding="utf-8", timeout=TETO_SUBPROC,
    )


# ---------------------------------------------------------------- smoke no próprio repo


def test_smoke_lint_no_proprio_repo_devolve_zero_erros():
    """O repo que carrega o lint passa no lint: exit 0 e `0 erro(s)` na última linha."""
    saida = _roda_cli("--root", str(RAIZ))
    assert saida.returncode == 0, saida.stdout + saida.stderr
    assert "lint_routers: 0 erro(s)" in saida.stdout, saida.stdout


# ---------------------------------------------------------------- laboratório: reprova


def test_ref_backtick_quebrada_em_router_vira_erro_com_arquivo_e_linha(tmp_path):
    index = arvore(tmp_path, {
        "docs/CLAUDE.md": "linha um\n- veja `docs/nao-existe.md` aqui\n",
    })
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert len(achados) == 1
    arquivo, linha, ref, motivo = achados[0]
    assert (arquivo, linha, ref) == ("docs/CLAUDE.md", 2, "docs/nao-existe.md")
    assert "não existe no índice git" in motivo


def test_link_markdown_quebrado_no_agents_md_vira_erro(tmp_path):
    index = arvore(tmp_path, {
        "AGENTS.md": "[plano](docs/plano-sumido.md)\n",
        "docs/CLAUDE.md": "vazio\n",
    })
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert [(a[0], a[1], a[2]) for a in achados] == [("AGENTS.md", 1, "docs/plano-sumido.md")]


def test_ref_viva_e_marcacao_de_escopo_nao_geram_erro(tmp_path):
    """Controle positivo: ref que existe passa; ref ausente com marcação também."""
    index = arvore(tmp_path, {
        "CLAUDE.md": "- `docs/guia.md` e `dados/planilha.xlsx` (fora do git)\n",
        "docs/guia.md": "x\n",
    })
    assert lr.lint(tmp_path, index, SEM_IGNORE) == []


def test_script_de_tools_sem_mencao_no_router_vira_erro(tmp_path):
    """Cobertura reversa: script versionado em tools/ tem de aparecer no router."""
    index = arvore(tmp_path, {
        "tools/CLAUDE.md": "- `a.py`\n",
        "tools/a.py": "", "tools/b.py": "",
    })
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert [(a[0], a[2]) for a in achados] == [("tools/CLAUDE.md", "tools/b.py")]


def test_pasta_de_workflow_sem_mencao_no_router_vira_erro(tmp_path):
    index = arvore(tmp_path, {
        "workflows/CLAUDE.md": "| `rotina-a/` | ok |\n",
        "workflows/rotina-a/workflow.md": "x\n",
        "workflows/rotina-b/workflow.md": "x\n",
    })
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert [(a[0], a[2]) for a in achados] == [("workflows/CLAUDE.md", "workflows/rotina-b/")]


def test_ref_skill_resolve_contra_agents_skills_nao_claude_skills(tmp_path):
    """GAT-02: `/nome` resolve contra `.agents/skills/<nome>/SKILL.md`.

    `_exemplo-skill` (prefixo `_`) não casa em `RE_SKILL` por design (primeiro
    caractere após a barra tem de ser alfanumérico) — nome sintético aqui é o
    que de fato exercita a resolução. Skill presente só em `.agents/skills/`
    tem de passar; skill inexistente tem de reprovar. Antes da correção
    (`.claude/skills/` como alvo) este teste reprovava com os dois achados.
    """
    index = arvore(tmp_path, {
        "CLAUDE.md": "- veja `/skill-real` e `/skill-inexistente`\n",
        ".agents/skills/skill-real/SKILL.md": "---\nname: skill-real\ndescription: x\n---\n",
    })
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert [(a[0], a[2]) for a in achados] == [("CLAUDE.md", "/skill-inexistente")]


def test_cli_exit_0_em_repo_limpo_e_1_com_erro(tmp_path):
    repo = _repo_git(tmp_path, {"CLAUDE.md": "- veja `docs/CLAUDE.md`\n", "docs/CLAUDE.md": "ok\n"})
    assert _roda_cli("--root", str(repo)).returncode == 0

    repo2 = _repo_git(tmp_path / "b", {"CLAUDE.md": "- veja `docs/sumiu.md`\n"})
    saida = _roda_cli("--root", str(repo2))
    assert saida.returncode == 1
    assert "CLAUDE.md:1" in saida.stdout and "docs/sumiu.md" in saida.stdout


# ---------------------------------------------------------------- alvos obrigatórios


def test_alvos_obrigatorios_e_o_set_esperado():
    """Espelho da lista: encolher a proteção exige editar dois arquivos no mesmo PR."""
    assert set(lr.ALVOS_OBRIGATORIOS) == {
        "CLAUDE.md", "AGENTS.md", "README.md",
        "workflows/CLAUDE.md", "tools/CLAUDE.md", "docs/CLAUDE.md",
    }
    assert not set(lr.IMPRESSAO_DIGITAL) & set(lr.ALVOS_OBRIGATORIOS)


def test_alvo_obrigatorio_fora_do_indice_reprova_num_repo_com_impressao_digital(tmp_path):
    """Com a impressão digital presente, alvo obrigatório ausente do índice é ERRO —
    mesmo que o arquivo não exista no disco (foi `git rm` com commit)."""
    arquivos = {e: "x\n" for e in lr.IMPRESSAO_DIGITAL}
    arquivos.update({e: "x\n" for e in lr.ALVOS_OBRIGATORIOS})
    arquivos["tools/CLAUDE.md"] = "- `lint_routers.py`\n"
    arquivos.pop("docs/CLAUDE.md")
    index = arvore(tmp_path, arquivos)
    achados = lr.lint(tmp_path, index, SEM_IGNORE)
    assert [(a[0], a[2]) for a in achados] == [("docs/CLAUDE.md", "docs/CLAUDE.md")]
    assert "ALVOS_OBRIGATORIOS" in achados[0][3]
