# Cobertura por agente — o que este repositório NÃO entrega

O `AGENTS.md` é lido pelos quatro agentes suportados, e as skills chegam aos três que procuram skill em disco. O resto do harness não é portável, e este documento diz exatamente o quê, por quê, e o que seria preciso — para ninguém descobrir a lacuna no meio de um incidente.

A regra que organiza tudo abaixo: **guardrail contornado é pior que guardrail ausente.** Nada aqui é entregue pela metade só para a tabela ficar cheia.

## O que é portável

| Peça | Como chega em cada agente |
|---|---|
| Instruções (`AGENTS.md`) | nativo em Codex, Cursor e Grok Build; por `@AGENTS.md` no `CLAUDE.md` para o Claude Code |
| Skills | fonte em `.agents/skills/` (lida nativamente pelo Codex), espelhada por `tools/sync_skills.py` em `.claude/skills/` e `.grok/skills/` |
| Gates de teste e lint | `.githooks/pre-commit`, `.githooks/pre-push` e `.github/workflows/` — git e CI não sabem qual agente escreveu o código, então valem para todos |

## O que não é portável, e por quê

### Hooks de runtime (`.claude/settings.json` + `.claude/hooks/`)

Só valem no Claude Code. Os três guardas (`guarda_bash.py`, `guarda_segredo.py`, `guarda_espelho.py`) leem o payload de `PreToolUse` do Claude Code: `tool_input.command` para Bash, `tool_input.file_path` para Edit/Write/MultiEdit. Codex e Cursor têm eventos e schema próprios, em arquivos de hook que vivem na configuração de cada um (no Codex, um hooks.json sob .codex/; no Cursor, sob .cursor/) e que este repositório não traz.

**O que seria preciso:** um adaptador por vendor que traduza o payload nativo para o shape que os guardas já consomem. A lógica de negócio dos três scripts é Python puro e não muda — só a extração do payload é acoplada, e ela cabe em poucas linhas.

**Por que não foi feito:** não é verificável na máquina onde o template foi construído, que não tem Codex nem Cursor instalados. Um hook de segurança que ninguém executou é pior do que nenhum, porque cria confiança sem cobertura. Entra quando alguém usar um desses agentes de verdade, numa máquina onde dê para testar.

**Enquanto isso:** quem trabalha fora do Claude Code não tem bloqueio em runtime para commit direto na branch principal, `--no-verify` ou segredo escrito em arquivo. A disciplina escrita em `.claude/rules/conduta-colaborador.md` é a única proteção, e o `pre-push` continua sendo a rede — desde que `git config core.hooksPath .githooks` esteja ativo no clone.

### Sub-agente e commands (`.claude/agents/`, `.claude/commands/`)

O sub-agente `verificador` e os commands `gates` e `verificar` são formato do Claude Code. O Codex define sub-agente em TOML sob .codex/agents/; o Cursor guarda comando em .cursor/commands/; no Grok Build, skill "user-invocable" já vira comando de barra sozinha. Nenhum desses caminhos existe aqui.

**O que seria preciso:** converter os dois commands em skills — o caminho que a própria Anthropic tomou ao fundir commands em skills — e assim eles passam a chegar aos três agentes pelo mesmo espelho das skills. O sub-agente exigiria uma definição por vendor.

**Por que não foi feito:** conversão de command em skill é mudança de contrato de uso (nome, invocação, evals próprios), não renomeação de arquivo. Vira trabalho próprio, com spec.

### Regras (`.claude/rules/`)

Carregam sozinhas no Claude Code e no Grok Build, que lê `.claude/rules/` por compatibilidade. Codex e Cursor não carregam.

**O que seria preciso:** nada de mecanismo — o `AGENTS.md` já cita cada regra por caminho no router de topo, que é o que um agente sem autocarregamento precisa para chegar nelas.

**Enquanto isso:** em Codex e Cursor, leia a regra citada antes de agir na área que ela cobre. O router de topo existe para isso.

## Como manter este documento honesto

Ele descreve ausências, e ausência não tem gate que a prove. A cada vez que uma peça passar a ser portável, a linha correspondente sai daqui e entra na tabela de cobertura do `AGENTS.md` no mesmo commit. Documento que lista uma lacuna já fechada é pior que documento nenhum, pela mesma razão que router desatualizado é pior que router nenhum.
