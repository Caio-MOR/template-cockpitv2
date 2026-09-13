"""Gate do texto sempre-carregado (`AGENTS.md` + `CLAUDE.md` + `.claude/rules/`).

Tudo aqui entra no contexto de toda sessão de todo clone, então cada linha custa
inferência para sempre. O corte foi feito com base em medição externa (trilha C
do `harness-eval` e o paper da ETH sobre AGENTS.md), e este gate protege as duas
pontas: o que foi cortado não volta, e o que foi **deliberadamente mantido contra
o plano de corte** não sai.

A segunda ponta é a que importa. O plano da trilha C mandava cortar dois trechos
que, verificados, não podiam sair:

1. "Versionamento é padrão" — o juiz mandou cortar porque `guarda_bash.py` já
   aplica a regra. O hook aplica mesmo, mas só no Claude Code; para Codex, Cursor
   e Grok Build o texto é a única aplicação que existe. Régua calibrada para um
   vendor não decide num repositório de quatro.
2. A tabela dos três freios da `loop-engineering.md` — os dois juízes a acharam
   redundante com `workflows/_exemplo-rotina/`. Só que sete pontos de código
   citam a regra pelo nome como a **definição** de freio (`tools/gate_veredito.py`,
   `tools/lint_routers.py`, `tools/eval_runner.py`, `tests/test_sync_skills.py`,
   entre outros). O fan-in da própria trilha não viu, porque só varre superfícies
   de harness, não comentário de código.

Requisitos: ENT-02, ENX-02, ENX-03 da feature `porta-de-entrada-multi-vendor`.
Decisão: AD-005 em `.specs/STATE.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CLAUDE_MD = RAIZ / "CLAUDE.md"
RULES = RAIZ / ".claude" / "rules"

# `CLAUDE.md` é adendo, não cópia: importa o AGENTS.md e guarda só o que é do
# Claude Code. Teto folgado — o que ele proíbe é o arquivo virar um segundo
# manual, não a adição de um bullet.
TETO_LINHAS_CLAUDE_MD = 12

# Frases mantidas CONTRA o plano de corte. Cada uma tem um motivo verificado no
# docstring acima; remover exige derrubar o motivo, não só reescrever o texto.
MANTIDAS_CONTRA_O_PLANO = (
    ("conduta-colaborador.md", "Todo trabalho nasce em branch"),
    ("conduta-colaborador.md", "Merge é decisão humana"),
    ("loop-engineering.md", "Teto de iterações"),
    ("loop-engineering.md", "Detector de estagnação"),
    ("loop-engineering.md", "Orçamento por run"),
)

# Frases que o plano de corte mandava manter e que de fato ficaram.
MANTIDAS_PELO_PLANO = (
    ("conduta-colaborador.md", "**intenção de negócio**"),
    ("loop-engineering.md", "somente após o sucesso completo da entrega"),
    ("loop-engineering.md", "silêncio legítimo é diferente de morte"),
)

# Cortados: instanciados em código funcionando ou duplicatas do `AGENTS.md`.
CORTADOS = (
    ("loop-engineering.md", '## Bloco "Freios"'),
    ("conduta-colaborador.md", "## Segredos"),
    ("conduta-colaborador.md", "## Entrega com evidência"),
)

# Sete pontos de código citam a regra pelo nome como a definição de freio.
# Se a tabela sumir, essas citações apontam para o nada.
CITADORES_DE_LOOP_ENGINEERING = (
    "tools/gate_veredito.py",
    "tools/lint_routers.py",
    "tools/eval_runner.py",
    "tests/test_sync_skills.py",
)


def test_claude_md_comeca_importando_o_agents_md() -> None:
    """ENT-02: a porta de entrada do Claude Code é um import, não uma cópia."""
    primeira = CLAUDE_MD.read_text(encoding="utf-8").splitlines()[0]
    assert primeira == "@AGENTS.md", (
        f"primeira linha do CLAUDE.md é {primeira!r}; tem que ser '@AGENTS.md' "
        f"para o Claude Code receber as mesmas instruções dos outros agentes"
    )


def test_claude_md_nao_vira_um_segundo_manual() -> None:
    """ENT-02: adendo é adendo; conteúdo canônico mora no AGENTS.md."""
    linhas = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
    assert len(linhas) <= TETO_LINHAS_CLAUDE_MD, (
        f"CLAUDE.md com {len(linhas)} linhas, teto é {TETO_LINHAS_CLAUDE_MD}. "
        f"Conteúdo canônico vai para o AGENTS.md, que todos os agentes leem."
    )


@pytest.mark.parametrize(("arquivo", "frase"), MANTIDAS_CONTRA_O_PLANO)
def test_frase_mantida_contra_o_plano_de_corte_segue_presente(
    arquivo: str, frase: str
) -> None:
    """ENX-02: o que foi mantido por motivo verificado não sai sem derrubar o motivo."""
    texto = (RULES / arquivo).read_text(encoding="utf-8")
    assert frase in texto, (
        f"{arquivo} perdeu {frase!r}. Esse trecho foi mantido CONTRA o plano de "
        f"corte da trilha C, por motivo verificado — ver o docstring deste gate."
    )


@pytest.mark.parametrize(("arquivo", "frase"), MANTIDAS_PELO_PLANO)
def test_frase_keep_do_plano_segue_presente(arquivo: str, frase: str) -> None:
    """ENX-02: os KEEP da trilha C são contrato, não sugestão."""
    assert frase in (RULES / arquivo).read_text(encoding="utf-8")


@pytest.mark.parametrize(("arquivo", "trecho"), CORTADOS)
def test_trecho_cortado_nao_volta(arquivo: str, trecho: str) -> None:
    """ENX-02: o corte é decisão registrada (AD-005), não preferência de redação."""
    assert trecho not in (RULES / arquivo).read_text(encoding="utf-8"), (
        f"{trecho!r} voltou a {arquivo}; o corte está registrado em AD-005"
    )


@pytest.mark.parametrize("citador", CITADORES_DE_LOOP_ENGINEERING)
def test_quem_cita_loop_engineering_tem_alvo_vivo(citador: str) -> None:
    """ENX-02: citação de regra em código só vale se a regra ainda define o termo."""
    codigo = (RAIZ / citador).read_text(encoding="utf-8")
    assert "loop-engineering" in codigo, (
        f"{citador} deixou de citar a regra; atualize esta lista no mesmo commit"
    )
    regra = (RULES / "loop-engineering.md").read_text(encoding="utf-8")
    assert "Teto de iterações" in regra, (
        f"{citador} cita `loop-engineering` como a definição de freio, mas a regra "
        f"não define mais o teto de iterações"
    )
