#!/usr/bin/env python3
"""Hook PreToolUse (matcher `Edit|Write|MultiEdit`) — nega escrita no espelho de skills.

%% formato: cadeia — lê o JSON do stdin, decide, sai.

`.agents/skills/` é a fonte única (D1 do `.specs/features/porta-de-entrada-multi-vendor/
spec.md`); `.claude/skills/` e `.grok/skills/` são espelhos gerados por
`python tools/sync_skills.py`. Este hook nega `Edit`, `Write` e `MultiEdit` cujo
caminho caia sob qualquer um dos dois espelhos, apontando o caminho equivalente na
fonte e o comando de sincronização — sem isso, "fonte única" é só uma frase que
ninguém lê na hora de errar (`design.md`, seção "Guarda de escrita no espelho").

Escrita em `.agents/skills/` (a fonte) e fora das três árvores é sempre permitida.

Falha fechada: entrada inválida ou caminho fora do projeto não derrubam o hook — a
escrita é permitida (o hook não tem nada de negativo a dizer sobre um payload que
não conseguiu interpretar), mas nunca lança exceção não tratada de volta ao Claude
Code.
"""
import json
import os
import sys
from pathlib import Path

ESPELHOS = (".claude/skills", ".grok/skills")
FONTE = ".agents/skills"


def _raiz_projeto() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve(strict=False)


def _partes_relativas(file_path: str) -> tuple[str, ...] | None:
    """Devolve as partes do caminho relativas à raiz do projeto, ou `None` se não
    for possível determinar (caminho ausente ou fora do projeto) — falha fechada
    para o lado de PERMITIR, nunca para o de negar algo que não foi entendido."""
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    raiz = _raiz_projeto()
    # Mesmo tratamento de `guarda_segredo.py`: o Claude pode emitir separador do
    # Windows mesmo dentro do Git Bash.
    candidato = Path(file_path.replace("\\", "/"))
    if not candidato.is_absolute():
        candidato = raiz / candidato
    try:
        caminho = candidato.resolve(strict=False)
        relativo = caminho.relative_to(raiz)
    except (ValueError, OSError):
        return None
    return relativo.parts


def _espelho_alvo(partes: tuple[str, ...]) -> str | None:
    """Se `partes` cai sob um dos dois espelhos, devolve o prefixo do espelho
    (`claude/skills` ou `grok/skills`); caso contrário `None`."""
    posix = "/".join(partes)
    for espelho in ESPELHOS:
        if posix == espelho or posix.startswith(espelho + "/"):
            return espelho
    return None


def _caminho_na_fonte(partes: tuple[str, ...], espelho: str) -> str:
    resto = "/".join(partes[len(espelho.split("/")):])
    return f"{FONTE}/{resto}" if resto else FONTE


def _arquivo_do_payload(tool_input: dict) -> str | None:
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        return file_path
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            sys.exit(0)
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            sys.exit(0)

        file_path = _arquivo_do_payload(tool_input)
        if file_path is None:
            sys.exit(0)

        partes = _partes_relativas(file_path)
        if partes is None:
            sys.exit(0)

        espelho = _espelho_alvo(partes)
        if espelho is None:
            sys.exit(0)

        caminho_fonte = _caminho_na_fonte(partes, espelho)
        print(
            f"Bloqueado: {file_path} é espelho gerado ({espelho}/), não a fonte. "
            f"Edite {caminho_fonte} e rode `python tools/sync_skills.py` para "
            "reproduzir a mudança nos espelhos.",
            file=sys.stderr,
        )
        sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        # Payload malformado não derruba o hook nem bloqueia uma escrita que não
        # foi entendida — quem barra escrita não inspecionada é guarda_segredo.py.
        sys.exit(0)


if __name__ == "__main__":
    main()
