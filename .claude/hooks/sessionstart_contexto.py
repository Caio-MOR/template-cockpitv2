#!/usr/bin/env python3
"""Hook `SessionStart` (matcher `compact`) — lembrete pós-compactação.

%% formato: cadeia — sem stdin relevante, imprime o texto fixo e sai 0.

Este script substitui o `echo '...'` que antes vivia inline no `command` de
`.claude/settings.json`. O texto abaixo é IDÊNTICO, palavra por palavra e
acento por acento, ao que estava embutido ali — é instrução de preservação de
contexto de sessão, não prosa para reescrever.
"""
import sys

TEXTO = (
    "Contexto recem-compactado. Antes de prosseguir, confirme que o resumo "
    "preservou: (1) arquivos modificados na sessao, (2) decisoes-chave tomadas, "
    "(3) comandos de verificacao/teste em aberto. Se algo se perdeu, recupere via "
    "git status, .specs/STATE.md ou logs do workflow antes de continuar."
)


def main() -> None:
    print(TEXTO)
    sys.exit(0)


if __name__ == "__main__":
    main()
