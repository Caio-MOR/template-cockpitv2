#!/usr/bin/env python3
"""Hook PreToolUse (matcher `Edit|Write|MultiEdit`) — bloqueia `.env` e segredo em texto.

%% formato: cadeia — lê o JSON do stdin, decide, sai.

Bloqueia (exit 2, motivo em pt-BR no stderr):
  - `tool_input.file_path` com basename `.env` ou começando com `.env.`
    (exceto `.env.example`, que é template público).
  - conteúdo (`content`/`new_string`, inclusive dentro de `edits[]` do MultiEdit)
    casando com padrão de chave/segredo conhecido.

Exceção de teste: apenas módulos `tests/test_*.py` ou arquivos em
`tests/fixtures/` cujo conteúdo contém a palavra `SINTETICO` passam — é como os
próprios testes deste hook geram segredo de mentira sem se autobloquear. O caminho
é canonizado antes da exceção, portanto `tests/../app.py` não consegue contorná-la.

Falha fechada: entrada inválida, caminho fora do projeto ou exceção interna bloqueiam
(exit 2). Um hook ausente não deve liberar uma escrita que não foi inspecionada.
"""
import json
import os
import re
import sys
from pathlib import Path

PADROES_SEGREDO = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ"),
    re.compile(r"SUPABASE_SERVICE_ROLE_KEY\s*=\s*\S{20,}"),
    re.compile(r"x-api-key\s*[:=]\s*['\"]?[A-Za-z0-9_-]{20,}"),
]


def _raiz_projeto() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve(strict=False)


def _caminho_canonico(file_path: str) -> Path:
    """Resolve o caminho relativo ao projeto e rejeita escapes por `..`/symlink."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path ausente ou inválido")
    raiz = _raiz_projeto()
    # Claude can emit Windows separators even when the hook is launched through
    # Git Bash; normalize them before `Path` resolves traversal and symlinks.
    candidato = Path(file_path.replace("\\", "/"))
    if not candidato.is_absolute():
        candidato = raiz / candidato
    caminho = candidato.resolve(strict=False)
    try:
        caminho.relative_to(raiz)
    except ValueError as exc:
        raise ValueError("caminho fora do projeto") from exc
    return caminho


def _e_arquivo_env_proibido(file_path: str) -> bool:
    nome = _caminho_canonico(file_path).name
    if nome == ".env.example":
        return False
    return nome == ".env" or nome.startswith(".env.")


def _conteudos(tool_input: dict) -> str:
    partes = []
    encontrou = False
    for chave in ("content", "new_string"):
        if chave not in tool_input:
            continue
        encontrou = True
        valor = tool_input[chave]
        if not isinstance(valor, str):
            raise ValueError(f"{chave} inválido")
        partes.append(valor)
    if "edits" in tool_input:
        encontrou = True
        edicoes = tool_input["edits"]
        if not isinstance(edicoes, list) or not edicoes:
            raise ValueError("edits inválido")
        for edicao in edicoes:
            if not isinstance(edicao, dict) or not isinstance(edicao.get("new_string"), str):
                raise ValueError("edição inválida")
            partes.append(edicao["new_string"])
    if not encontrou:
        raise ValueError("conteúdo de escrita ausente")
    return "\n".join(partes)


def _e_teste_sintetico(file_path: str, texto: str) -> bool:
    caminho = _caminho_canonico(file_path)
    relativo = caminho.relative_to(_raiz_projeto())
    partes = relativo.parts
    modulo_de_teste = (
        len(partes) == 2
        and partes[0] == "tests"
        and partes[1].startswith("test_")
        and partes[1].endswith(".py")
    )
    fixture = len(partes) >= 2 and partes[:2] == ("tests", "fixtures")
    return (modulo_de_teste or fixture) and "SINTETICO" in texto


def _achado_de_segredo(texto: str):
    for padrao in PADROES_SEGREDO:
        if padrao.search(texto):
            return padrao.pattern
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload não é um objeto JSON")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input ausente ou inválido")
        file_path = tool_input.get("file_path")
        caminho = _caminho_canonico(file_path)

        if _e_arquivo_env_proibido(str(caminho)):
            print(
                f"Bloqueado: escrita em {file_path or '(.env)'} — segredo só em "
                ".env, nunca gravado por ferramenta automática. Edite manualmente.",
                file=sys.stderr,
            )
            sys.exit(2)

        texto = _conteudos(tool_input)
        if texto and not _e_teste_sintetico(str(caminho), texto):
            padrao = _achado_de_segredo(texto)
            if padrao:
                print(
                    f"Bloqueado: conteúdo casa com padrão de segredo ({padrao}). "
                    "Remova a credencial do texto antes de gravar.",
                    file=sys.stderr,
                )
                sys.exit(2)

        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        print(
            "Bloqueado: guarda_segredo não conseguiu validar a solicitação "
            "(entrada inválida, caminho inseguro ou erro interno).",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
