#!/usr/bin/env python3
"""Hook `PostToolUse` (matcher `Edit|Write|MultiEdit`) — devolve achado do `ruff`.

%% formato: cadeia — lê o JSON do stdin, roda `ruff check` no arquivo `.py`
tocado e devolve o achado ao agente via `additionalContext`, sem bloquear a
edição (a ferramenta já rodou; este hook só informa). É o par exato de
`guarda_segredo.py` (mesmo matcher, mesma leitura de `tool_input.file_path`),
mas na direção oposta: aquele falha fechado ANTES da escrita, este nunca
bloqueia e degrada em silêncio DEPOIS dela.

Degradação obrigatória (sempre exit 0, sem saída, sem exceção vazando):
  - `ruff` ausente ou não executável;
  - erro de permissão ao invocar o processo (`ruff.exe` bloqueado por
    antivírus é o caso real na máquina Windows do dono);
  - timeout do subprocesso;
  - JSON inválido no stdin;
  - `file_path` ausente, fora do projeto, ou que não seja `.py`.

Ganchos de teste (não usados em produção): `RUFF_FEEDBACK_CMD` troca o comando
`ruff` por outro (ex.: um script Python fake) para simular cada ramo sem
depender do `ruff` real instalado na máquina; `RUFF_FEEDBACK_TIMEOUT_SEC` troca
o teto de tempo para exercitar o ramo de timeout sem esperar o teto real.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

TIMEOUT_PADRAO = 15.0


def _raiz_projeto() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve(strict=False)


def _caminho_py_no_projeto(file_path) -> Path | None:
    """Resolve `file_path` e devolve o caminho só se for `.py` dentro do projeto."""
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    raiz = _raiz_projeto()
    candidato = Path(file_path.replace("\\", "/"))
    if not candidato.is_absolute():
        candidato = raiz / candidato
    caminho = candidato.resolve(strict=False)
    try:
        caminho.relative_to(raiz)
    except ValueError:
        return None
    if caminho.suffix != ".py":
        return None
    return caminho


def _comando_ruff(caminho: Path) -> list[str]:
    override = os.environ.get("RUFF_FEEDBACK_CMD")
    if override:
        # POSIX shlex trata `\` como escape e destrói caminho do Windows; ver
        # a mesma correção em guarda_bash.py._diretorios_de_commit.
        base = shlex.split(override, posix=os.name != "nt")
        base = [token.strip("\"'") for token in base]
    else:
        base = [sys.executable, "-m", "ruff", "check"]
    return [*base, str(caminho)]


def _timeout() -> float:
    try:
        return float(os.environ.get("RUFF_FEEDBACK_TIMEOUT_SEC", TIMEOUT_PADRAO))
    except ValueError:
        return TIMEOUT_PADRAO


def _emitir_achado(texto: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": texto,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            sys.exit(0)
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            sys.exit(0)

        caminho = _caminho_py_no_projeto(tool_input.get("file_path"))
        if caminho is None or not caminho.is_file():
            sys.exit(0)

        resultado = subprocess.run(
            _comando_ruff(caminho),
            capture_output=True,
            text=True,
            timeout=_timeout(),
        )
        achado = (resultado.stdout or "").strip()
        if resultado.returncode != 0 and achado:
            _emitir_achado(achado)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        # Degradação obrigatória: ruff ausente, sem permissão (WinError 5),
        # timeout, JSON inválido ou qualquer outro erro interno nunca vaza —
        # este hook informa, nunca bloqueia.
        sys.exit(0)


if __name__ == "__main__":
    main()
