"""Gate do hook `.claude/hooks/guarda_espelho.py` (T7 da feature
`porta-de-entrada-multi-vendor`).

`.agents/skills/` é a fonte única; `.claude/skills/` e `.grok/skills/` são espelhos
gerados por `python tools/sync_skills.py`. Este arquivo prova só o comportamento da
função do hook (negar escrita no espelho, permitir na fonte e fora das três
árvores, não derrubar com payload malformado) — invocando o script diretamente
com `sys.executable`, sem passar por `run_hook.sh`.

Isso é deliberado: T7 (este arquivo) precede T8, que é quem coloca
`guarda_espelho.py` na allowlist de `run_hook.sh` e no `PreToolUse` do
`settings.json`. Testar via `run_hook.sh` aqui reprovaria por motivo errado
("script de hook não permitido") antes de T8 existir, e continuaria reprovando
por esse motivo se alguém removesse a entrada da allowlist depois — mascarando
exatamente a fiação que T8 prova. A prova de que o hook está de fato LIGADO (a
fiação) é T8, em `tests/test_hooks.py`, com discriminação própria.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / ".claude" / "hooks" / "guarda_espelho.py"
TETO = 30


def _rodar(payload) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )


# ---------------------------------------------------------------------------
# Nega escrita nos dois espelhos


def test_bloqueia_write_em_claude_skills():
    r = _rodar({"tool_input": {"file_path": ".claude/skills/x/SKILL.md", "content": "y"}})
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr
    assert "python tools/sync_skills.py" in r.stderr


def test_bloqueia_write_em_grok_skills():
    r = _rodar({"tool_input": {"file_path": ".grok/skills/x/SKILL.md", "content": "y"}})
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr
    assert "python tools/sync_skills.py" in r.stderr


def test_bloqueia_edit_em_claude_skills():
    r = _rodar(
        {"tool_input": {"file_path": ".claude/skills/x/SKILL.md", "old_string": "a", "new_string": "b"}},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr


def test_bloqueia_multiedit_em_grok_skills():
    r = _rodar(
        {
            "tool_input": {
                "file_path": ".grok/skills/x/SKILL.md",
                "edits": [{"old_string": "a", "new_string": "b"}],
            },
        },
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr


def test_bloqueia_caminho_absoluto_sob_claude_skills():
    r = _rodar(
        {"tool_input": {"file_path": str(RAIZ / ".claude" / "skills" / "x" / "SKILL.md"), "content": "y"}},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr


def test_bloqueia_caminho_com_separador_windows():
    r = _rodar({"tool_input": {"file_path": r".claude\\skills\\x\\SKILL.md", "content": "y"}})
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills/x/SKILL.md" in r.stderr


def test_bloqueia_a_propria_raiz_do_espelho():
    """Escrever `.claude/skills` (sem sub-caminho) também é negado — não só arquivos
    dentro dele."""
    r = _rodar({"tool_input": {"file_path": ".claude/skills", "content": "y"}})
    assert r.returncode == 2, r.stdout + r.stderr
    assert ".agents/skills" in r.stderr


# ---------------------------------------------------------------------------
# Permite fonte e fora das três árvores


def test_permite_escrita_na_fonte():
    r = _rodar({"tool_input": {"file_path": ".agents/skills/x/SKILL.md", "content": "y"}})
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_escrita_fora_das_tres_arvores():
    r = _rodar({"tool_input": {"file_path": "README.md", "content": "y"}})
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_arquivo_que_so_comeca_parecido_com_o_espelho():
    """`claude/skills-outra-coisa` não é `claude/skills`: sem `/` de fronteira o
    prefixo não deve casar."""
    r = _rodar({"tool_input": {"file_path": ".claude/skills-outra-coisa/x.md", "content": "y"}})
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# Falha fechada sem derrubar o hook


def test_payload_malformado_nao_derruba_o_hook():
    r = _rodar("isto nao e json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_tool_input_ausente_nao_derruba_o_hook():
    r = _rodar({})
    assert r.returncode == 0, r.stdout + r.stderr


def test_file_path_ausente_nao_derruba_o_hook():
    r = _rodar({"tool_input": {"content": "y"}})
    assert r.returncode == 0, r.stdout + r.stderr
