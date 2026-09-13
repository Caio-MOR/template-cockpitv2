# STATE

Log de decisões do repo (append-only) e snapshot de handoff. Uma decisão por item, com data e motivo — o porquê é o que a próxima sessão não consegue reconstruir sozinha.

## Decisions

<!-- Formato de cada entrada (uma por decisão, mais recente por último):
- **AD-nnn (AAAA-MM-DD):** o que foi decidido, em uma frase; o motivo em outra.
  Quem decidiu (dono do repo em chat, agente por regra X) e o que fica em aberto.
-->

- **AD-001 (2026-09-05):** verificação = hook `pre-push` obrigatório (`.githooks/`, ativado por `git config core.hooksPath .githooks`) + CI hospedado só em `pull_request` (`tests.yml`, `gitleaks.yml`), mesmos gates nos dois; a régua do padrão ouro não afrouxa (PO-C01 v1.1 exige gatilho automático E hook).
  Motivo: minutos do GitHub Actions — a versão anterior deste template trocou os quatro workflows para `workflow_dispatch` e reescreveu PO-C01/C02/C03 para não ser punida; isso devolvia a verificação à memória humana. Decisão do dono do repo em chat; agente aplicou. Em aberto: `tests-macos.yml` e `security.yml` ficam sob demanda até alguém precisar deles em PR.

- **AD-002 (2026-09-12):** fechar o `harness-score` em 108/108 (36/36 checks aprovados), tratando cada conserto como mecanismo que executa (LICENSE real, `.mcp.json` com convenção de credencial documentada, `mypy` rodando nos dois gates, hooks `PreCompact`/`SessionStart` virando script versionado, hook `PostToolUse` que roda o linter, `.githooks/pre-commit` + `.pre-commit-config.yaml` bloqueando commit sujo) — nunca só presença de arquivo para agradar o scanner.
  Motivo: o dono pediu nota auditável sem ponto cego escondido; um placar que sobe sem o repo melhorar de fato é pior que não medir. Ressalva honesta: dois dos seis checks fechados são ponto cego do próprio scanner, não lacuna real que ele soube apontar — HKS-05 lia o hook `PreCompact`/`SessionStart` inline como "script faltando" (o conteúdo sempre existiu, só não em arquivo separado) e HYG-08 penaliza a ausência de um `.mcp.json` declarado, não o uso inseguro de MCP (um `.mcp.json` vazio aprova o check sem que o repo tenha ganhado governança de credencial nova). O `pre-commit` (a ferramenta Python) foi adotado porque o scanner não reconhece `core.hooksPath=.githooks` como gate válido, embora o repo já rodasse a checagem equivalente no `pre-push`; o `.pre-commit-config.yaml` chama o mesmo `.githooks/pre-commit`, não duplica a lista. Decisão do dono do repo em chat; agente aplicou. Em aberto: nada — a nota mede presença e execução de mecanismo, não decide sozinha se o mecanismo é suficiente.

## Handoff snapshot

