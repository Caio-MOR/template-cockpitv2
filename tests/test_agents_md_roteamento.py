"""Gate de roteamento do `AGENTS.md` — porta de entrada multi-vendor.

Três dos quatro agentes suportados (Codex, Cursor, Grok Build) leem o
`AGENTS.md` e nada mais do dialeto `.claude/`. Para eles, um arquivo de harness
que não é citado por caminho aqui é um arquivo que não existe: não há
autocarregamento que compense a omissão.

O `tools/lint_routers.py` já reprova referência morta (caminho citado que não
existe). Este gate cobre o sentido inverso, que nenhum outro cobre: caminho que
existe e **deveria** estar citado, mas não está. Cobre também a ausência das
seções de overview, cujo corte é decisão registrada (AD-005) apoiada em medição
externa, não gosto de redação.

Requisitos: ENT-01, ENT-03, ROT-01, ENX-01 da feature
`porta-de-entrada-multi-vendor`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
AGENTS = RAIZ / "AGENTS.md"

TETO_SUBPROC = 30  # loop-engineering: subprocess sem timeout pendura o gate

# Todo arquivo de harness que um agente sem `.claude/` precisa alcançar.
# Entrada nova aqui é de graça; o custo está em esquecer de acrescentar.
CAMINHOS_OBRIGATORIOS = (
    "SECURITY.md",
    "README.md",
    "CLAUDE.md",
    ".claude/rules/como-operar.md",
    ".claude/rules/conduta-colaborador.md",
    ".claude/rules/delegacao-barata.md",
    ".claude/rules/estrutura-e-logging.md",
    ".claude/rules/graph-engineering.md",
    ".claude/rules/loop-engineering.md",
    "docs/CLAUDE.md",
    "docs/OPERATIONS.md",
    "docs/THREAT_MODEL.md",
    "docs/padrao-ouro/PADRAO.md",
    ".claude/agents/verificador.md",
    ".claude/commands/gates.md",
    ".claude/commands/verificar.md",
    ".agents/skills/",
    ".claude/skills/",
    ".grok/skills/",
    "tools/sync_skills.py",
)

AGENTES_SUPORTADOS = ("Claude Code", "Codex", "Cursor", "Grok Build")

# Trechos cortados por AD-005: justificativa motivacional e fecho de discurso.
# Reintroduzir exige derrubar a decisão, não só reescrever o texto.
#
# A declaração WAT em si NÃO entra aqui, e a distinção é o achado que fez esta
# lista existir: `tools/operational_audit.py:166` reprova o repo se o AGENTS.md
# não declarar "Workflows", "Agents", "Tools" e "WAT". Os três bullets definem
# papéis — instrução, categoria que o paper da ETH mede como bem seguida. O que
# sai é a parte sem imperativo: a aritmética motivacional e o parágrafo-resumo.
SECOES_PROIBIDAS = (
    "se cada etapa tem 90% de acerto",
    "## Resumo",
    "Seja pragmático",
)

TETO_LINHAS_TABELA_COBERTURA = 6


def _texto() -> str:
    return AGENTS.read_text(encoding="utf-8")


def _indice_git() -> frozenset[str]:
    saida = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=RAIZ,
        capture_output=True,
        check=True,
        timeout=TETO_SUBPROC,
    )
    return frozenset(p for p in saida.stdout.decode("utf-8").split("\0") if p)


@pytest.mark.parametrize("caminho", CAMINHOS_OBRIGATORIOS)
def test_caminho_obrigatorio_citado_no_agents_md(caminho: str) -> None:
    """ROT-01: cada arquivo de harness aparece citado entre crases."""
    assert f"`{caminho}`" in _texto(), (
        f"{caminho} não é citado entre crases no AGENTS.md. Um agente que não "
        f"carrega .claude/ não tem como alcançá-lo."
    )


@pytest.mark.parametrize("caminho", CAMINHOS_OBRIGATORIOS)
def test_caminho_obrigatorio_existe_no_indice(caminho: str) -> None:
    """A lista acima não pode virar ficção: o alvo tem que existir."""
    indice = _indice_git()
    existe = (
        any(p.startswith(caminho) for p in indice)
        if caminho.endswith("/")
        else caminho in indice
    )
    assert existe, f"{caminho} está na lista obrigatória mas não existe no índice git"


@pytest.mark.parametrize("agente", AGENTES_SUPORTADOS)
def test_tabela_de_cobertura_nomeia_cada_agente(agente: str) -> None:
    """ENT-03: o agente descobre aqui o que ele NÃO carrega."""
    assert agente in _texto(), f"a tabela de cobertura não nomeia {agente}"


def test_tabela_de_cobertura_cabe_no_teto() -> None:
    """ENT-03: tabela de cobertura curta; texto sempre-carregado custa inferência."""
    linhas = _texto().splitlines()
    inicio = next(
        i for i, linha in enumerate(linhas) if linha.startswith("## Cobertura por agente")
    )
    resto = linhas[inicio + 1 :]
    fim = next(
        (i for i, linha in enumerate(resto) if linha.startswith("## ")), len(resto)
    )
    corpo = [
        linha
        for linha in resto[:fim]
        if linha.startswith("|") and not set(linha) <= set("|- ")
    ]
    # -1 descarta o cabeçalho da tabela; sobram as linhas de conteúdo.
    assert len(corpo) - 1 <= TETO_LINHAS_TABELA_COBERTURA, (
        f"tabela de cobertura com {len(corpo) - 1} linhas de conteúdo, "
        f"teto é {TETO_LINHAS_TABELA_COBERTURA}"
    )


@pytest.mark.parametrize("secao", SECOES_PROIBIDAS)
def test_overview_nao_volta_ao_texto_sempre_carregado(secao: str) -> None:
    """ENX-01: overview de repositório não melhora acerto e custa inferência."""
    assert secao not in _texto(), (
        f"{secao!r} voltou ao AGENTS.md. Corte registrado em AD-005 "
        f"(.specs/STATE.md); reintroduzir exige derrubar a decisão."
    )


def test_eval_aponta_para_a_fonte_de_skills() -> None:
    """O comando publicado tem que rodar contra a fonte, não contra o espelho."""
    texto = _texto()
    assert "--skills-dir .agents/skills" in texto
    assert "--skills-dir .claude/skills" not in texto
