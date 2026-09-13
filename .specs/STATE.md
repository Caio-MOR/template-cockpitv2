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

- **AD-003 (2026-09-13):** a fonte de toda skill passa a ser `.agents/skills/`, com espelho gerado por `tools/sync_skills.py` para `.claude/skills/` e `.grok/skills/`, gate de drift na suíte e hook negando escrita direta no espelho.
  Motivo: o repositório se declara multi-vendor mas só entrega isso para as instruções — Codex, Grok Build e Cursor leem `AGENTS.md` nativamente e não carregam skill nenhuma, porque o padrão agentskills.io padroniza o formato do `SKILL.md` e não o diretório (Codex procura `.agents/skills`, Grok `.grok/skills`, Claude Code `.claude/skills`). Symlink e junction foram descartados: o template roda em VM Windows de usuário leigo, sem Developer Mode, e link que não é criado falha em silêncio. Custo conhecido e aceito: a string `.claude/skills` aparece em 17 pontos de 8 arquivos versionados, contra ~4 se a fonte ficasse onde está; a escolha por `.agents/` é deliberada, porque manter a fonte em `.claude/` é continuar privilegiando um dialeto. Decisão do dono do repo em chat (opção "fonte única + espelho gerado"); agente levantou o custo antes. Em aberto: nada.

- **AD-004 (2026-09-13):** hooks e sub-agentes para Codex e Cursor ficam fora de escopo, documentados como lacuna declarada em `docs/`.
  Motivo: `guarda_bash.py` e `guarda_segredo.py` leem o payload de `PreToolUse` do Claude Code (`tool_input.command`, `tool_input.file_path`); Codex e Cursor têm schema próprio, então portar exige adaptador — trabalho real e não verificável nesta máquina, que não tem nenhum dos dois instalados. Entregar guardrail não testado é pior que não entregar: guardrail contornado é pior que guardrail ausente. Decisão do agente por regra de escopo, registrada para revisão. Em aberto: se e quando alguém usar Codex ou Cursor de verdade no template, o adaptador vira feature própria com máquina onde dê para testar.

- **AD-005 (2026-09-13):** o texto sempre-carregado (`AGENTS.md`, `CLAUDE.md`, `.claude/rules/*.md`) só guarda imperativo; overview de arquitetura e justificativa motivacional saem.
  Motivo: Gloaguen, Mündler et al. (ETH Zurich, arXiv 2602.11988) mede que arquivo de contexto não melhora acerto de forma geral e custa >20% de inferência, e isola a causa — instrução específica é bem seguida, *repository overview* não ajuda. A trilha C do `harness-eval` (trap PASS) deu o plano KEEP/CUT de duas rules; a trilha B teve o veredito formal descartado por reprovar no próprio trap gate, mas os 19 claims dual-REDUNDANT apontam exatamente a seção "Arquitetura WAT" e a prosa motivacional. Duas réguas independentes no mesmo parágrafo. Decisão do agente com base em medição, aprovada pelo dono ao pedir a reestruturação "conforme paper de ontem". Em aberto: a calibração da trilha B pressupõe harness sem enforcement mecânico e reprova em repo que aplica a política em runtime — candidato a feedback upstream para a TLC.

## Handoff snapshot

