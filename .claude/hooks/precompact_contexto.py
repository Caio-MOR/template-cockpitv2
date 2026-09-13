#!/usr/bin/env python3
"""Hook `PreCompact` — instrução de preservação de contexto antes da compactação.

%% formato: cadeia — sem stdin relevante, imprime o texto fixo e sai 0.

Este script substitui o `echo '...'` que antes vivia inline no `command` de
`.claude/settings.json`. O texto abaixo é IDÊNTICO, palavra por palavra e
acento por acento, ao que estava embutido ali — é instrução de preservação de
contexto de sessão, não prosa para reescrever.
"""
import sys

TEXTO = (
    '{"hookSpecificOutput":{"hookEventName":"PreCompact","additionalContext":'
    '"Instrucao obrigatoria para o resumo de compactacao: preserve integralmente '
    '(1) a lista de arquivos modificados na sessao, (2) as decisoes-chave tomadas '
    'e (3) os comandos de verificacao/teste ainda em aberto."}}'
)


def main() -> None:
    print(TEXTO)
    sys.exit(0)


if __name__ == "__main__":
    main()
