# STATE

Log de decisões do repo (append-only) e snapshot de handoff. Uma decisão por item, com data e motivo — o porquê é o que a próxima sessão não consegue reconstruir sozinha.

## Decisions

<!-- Formato de cada entrada (uma por decisão, mais recente por último):
- **AD-nnn (AAAA-MM-DD):** o que foi decidido, em uma frase; o motivo em outra.
  Quem decidiu (dono do repo em chat, agente por regra X) e o que fica em aberto.
-->

- **AD-001 (2026-09-05):** verificação = hook `pre-push` obrigatório (`.githooks/`, ativado por `git config core.hooksPath .githooks`) + CI hospedado só em `pull_request` (`tests.yml`, `gitleaks.yml`), mesmos gates nos dois; a régua do padrão ouro não afrouxa (PO-C01 v1.1 exige gatilho automático E hook).
  Motivo: minutos do GitHub Actions — a versão anterior deste template trocou os quatro workflows para `workflow_dispatch` e reescreveu PO-C01/C02/C03 para não ser punida; isso devolvia a verificação à memória humana. Decisão do dono do repo em chat; agente aplicou. Em aberto: `tests-macos.yml` e `security.yml` ficam sob demanda até alguém precisar deles em PR.

## Handoff snapshot

