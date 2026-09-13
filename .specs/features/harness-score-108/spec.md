# harness-score 108/108 Specification

## Problem Statement

O scanner `harness-score` v1.6.5 pontua este repo em 92/108 (nível L4, o teto da régua). Os 16 pontos que faltam vêm de 6 checks reprovados: três são lacunas reais do repo (sem hook de feedback, sem type-checker, sem LICENSE), dois são ponto cego do scanner (hook inline lido como script faltando, ausência de MCP penalizada) e um é mecanismo equivalente que o scanner não reconhece (gate roda no `pre-push`, não no `pre-commit`). O dono decidiu fechar 108/108 sem deixar ponto cego de fora. O risco a evitar é o teatro de métrica: cada conserto tem de deixar o repo mecanicamente melhor, não só mudar o placar.

## Goals

- [ ] `npx harness-score` reporta 108/108 (36/36 checks aprovados) no repo, medido por execução com saída salva
- [ ] Nenhum gate existente do repo regride: `pytest -q`, `tools/lint_routers.py`, `tools/gate_veredito.py`, `tools/padrao_ouro_audit.py`, `tools/policy_check.py`, `tools/operational_audit.py` e `ruff check .` continuam verdes
- [ ] Todo artefato criado para satisfazer um check tem função mecânica real (executa, é testado, ou documenta convenção), nunca apenas presença de arquivo

## Out of Scope

Explicitamente excluído. Documentado para evitar scope creep.

| Feature | Reason |
| --- | --- |
| Rodar `harness-eval` (trilha A/B/C) | É o segundo audit, decisão separada do dono; esta spec cobre só o scanner determinístico |
| Propagar as mudanças para o cockpit `Cloud Cowork ptbr` | O dono pediu instalar no clone do template, não no cockpit |
| Adotar `pre-commit` (a ferramenta Python) como runner obrigatório do repo | Conflita com `core.hooksPath=.githooks` já documentado; o config declara, o `.githooks/pre-commit` executa |
| Tornar o type-check estrito (`strict = true`) em toda a base | Estrito de largada reprova código legado e vira `# type: ignore` em massa; a spec entrega o gate rodando, o aperto é decisão futura |
| Declarar servidores MCP concretos (Slack, Supabase, etc.) | Escolha da instância, não do template; o template entrega o arquivo e a convenção |
| Alterar `.env.example` | Escrita em `.env*` é bloqueada por `permissions.deny` do próprio repo; nada nesta spec exige variável nova para funcionar |

---

## Assumptions & Open Questions

Toda ambiguidade está resolvida ou registrada aqui.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Licença do template | MIT, copyright "Caio Kohn" | É o que o ecossistema usa para template e o que o próprio `harness-score` usa; troca custa um commit | n |
| Conteúdo do `.mcp.json` | `{"mcpServers": {}}` e a convenção documentada no README | Servidor concreto é escolha da instância; o arquivo existe para declarar o ponto de extensão e a regra de credencial por `${VAR}` | n |
| Ferramenta de type-check | mypy via `[tool.mypy]` no `pyproject.toml` | `pyright` exigiria stack Node, que o repo não tem; `mypy.ini` criaria arquivo novo na raiz sem ganho | n |
| Rigor inicial do mypy | Não-estrito, escopo `tools/` e `tests/`, `ignore_missing_imports = true` | O gate precisa nascer verde para virar rede; estrito de largada seria desligado no primeiro atrito | n |
| O que o `pre-commit` roda | `ruff check` nos arquivos staged + `tools/policy_check.py` | Commit precisa ser rápido; a suíte inteira continua no `pre-push` | n |
| Onde o hook de feedback age | `PostToolUse` em `Edit\|Write\|MultiEdit`, rodando ruff no arquivo tocado | É o par exato do `guarda_segredo.py` (que é o `PreToolUse` dos mesmos matchers): um vigia antes, o outro devolve o resultado depois | n |
| Comportamento sem `ruff` instalado | Hook sai 0 em silêncio | `ruff.exe` está bloqueado por antivírus na máquina Windows do dono; hook que quebra a sessão dele seria desinstalado no mesmo dia | n |
| Branch de trabalho | Branch nova a partir de `workshop`, commits atômicos, sem merge | `workshop` é a branch viva do evento; PR mantém o histórico revisável | n |

**Open questions: none** — todas resolvidas ou registradas acima.

---

## User Stories

### P1: Fechar os 6 checks reprovados sem quebrar gate existente ⭐ MVP

**User Story**: Como dono do template, quero que o `harness-score` aprove os 36 checks para que o repo sirva de referência auditável do padrão que eu prego, sem que o placar esconda guardrail de mentira.

**Why P1**: É o pedido inteiro. Cada check abaixo é independentemente verificável pela saída do próprio scanner.

**Acceptance Criteria** (cada linha é um padrão EARS):

1. WHEN `npx harness-score` roda na raiz do repo THEN o scanner SHALL reportar `108/108` e `36` checks aprovados <!-- event-driven -->
2. WHEN o scanner avalia HYG-05 THEN o repo SHALL conter um arquivo `LICENSE` na raiz, versionado no índice git <!-- event-driven -->
3. WHEN o scanner avalia HYG-08 THEN o repo SHALL conter `.mcp.json` versionado, JSON válido, sem nenhum valor literal com assinatura de credencial <!-- event-driven -->
4. WHEN o scanner avalia SNS-03 THEN `pyproject.toml` SHALL conter a seção `[tool.mypy]` <!-- event-driven -->
5. WHEN o scanner avalia CI-04 THEN o repo SHALL conter `.pre-commit-config.yaml` versionado na raiz <!-- event-driven -->
6. WHEN o scanner avalia HKS-04 THEN `.claude/settings.json` SHALL registrar pelo menos um hook no evento `PostToolUse` <!-- event-driven -->
7. WHEN o scanner avalia HKS-05 THEN nenhum `command` de hook em `.claude/settings.json` SHALL conter token com `/` que não resolva para arquivo existente no índice git <!-- event-driven -->
8. The system SHALL manter `.claude/settings.json` como JSON válido com todo hook declarando `type` e `command` <!-- ubiquitous -->
9. IF qualquer arquivo novo desta feature ficar fora da allowlist do `.gitignore` THEN o arquivo SHALL ser acrescentado à seção de raiz do `.gitignore` no mesmo commit <!-- unwanted-behavior -->

**Independent Test**: rodar `npx harness-score` e ler `108/108`; conferir `git ls-files` para cada arquivo novo.

---

### P1: Cada conserto vira mecanismo que executa ⭐ MVP

**User Story**: Como dono do template, quero que o que eu adicionei rode de verdade, para que ninguém herde um repo com guardrail decorativo.

**Why P1**: É a diferença entre subir o placar e melhorar o repo. Sem isto, o P1 anterior é fraude com nota alta.

**Acceptance Criteria**:

1. WHEN um arquivo `.py` é editado e `ruff` está instalado e acusa erro THEN o hook `PostToolUse` SHALL devolver o texto do erro ao agente sem bloquear a edição <!-- event-driven -->
2. IF `ruff` não estiver instalado ou falhar ao executar THEN o hook `PostToolUse` SHALL sair com código 0 e sem saída <!-- unwanted-behavior -->
3. WHEN o hook `PreCompact` dispara THEN a instrução de contexto SHALL vir de script versionado em `.claude/hooks/`, não de string inline no `settings.json` <!-- event-driven -->
4. WHEN o hook `SessionStart` com matcher `compact` dispara THEN a instrução SHALL vir de script versionado em `.claude/hooks/` <!-- event-driven -->
5. WHEN `run_hook.sh` recebe nome de script fora da sua allowlist THEN o wrapper SHALL recusar a execução <!-- event-driven -->
6. WHEN `git commit` roda com `core.hooksPath=.githooks` ativo THEN `.githooks/pre-commit` SHALL rodar `ruff check` nos arquivos staged e `tools/policy_check.py`, e SHALL bloquear o commit se algum reprovar <!-- event-driven -->
7. IF `ruff` não estiver instalado THEN `.githooks/pre-commit` SHALL avisar e seguir sem reprovar o commit <!-- unwanted-behavior -->
8. WHEN `.pre-commit-config.yaml` é usado por quem adota a ferramenta `pre-commit` THEN o config SHALL invocar o mesmo `.githooks/pre-commit`, sem duplicar a lista de checagens <!-- event-driven -->
9. WHEN o type-check roda THEN `mypy` SHALL cobrir `tools/` e `tests/` e SHALL terminar sem erro na base atual <!-- event-driven -->
10. The system SHALL rodar o type-check tanto em `.githooks/pre-push` quanto em `.github/workflows/tests.yml` <!-- ubiquitous -->
11. The system SHALL cobrir cada hook e gate novo por teste automatizado em `tests/` <!-- ubiquitous -->

**Independent Test**: rodar `pytest -q` e ver os testes novos passando; rodar `.githooks/pre-commit` com arquivo sujo staged e ver o commit ser recusado.

---

### P2: Deixar rastro para quem herdar o repo

**User Story**: Como quem instancia este template, quero achar no router e no README o que foi acrescentado, para não descobrir guardrail por acidente.

**Why P2**: Não altera o placar, mas router desatualizado é regra explícita do repo.

**Acceptance Criteria**:

1. WHEN um arquivo novo é acrescentado à raiz THEN a tabela de estrutura do `AGENTS.md` SHALL citá-lo na linha de configuração correspondente <!-- event-driven -->
2. WHEN o README descreve o que o Claude Code faz sozinho no repo THEN a seção SHALL incluir o hook de feedback `PostToolUse` e a convenção de credencial do `.mcp.json` <!-- event-driven -->
3. WHEN a suíte ganha testes novos THEN `conftest.py` SHALL ter `COLETA_MEDIDA` atualizado para a coleta real <!-- event-driven -->
4. The system SHALL registrar a decisão desta feature em `.specs/STATE.md` como `AD-002` <!-- ubiquitous -->

**Independent Test**: `python tools/lint_routers.py` sai 0 e `pytest -q` não acusa divergência de coleta.

---

## Edge Cases

- IF a edição do `.claude/settings.json` quebrar o JSON THEN os checks HKS-01 e HKS-02 (hoje aprovados, 6 pontos) SHALL reprovar — validar o JSON antes de cada commit que toca o arquivo
- IF o `.mcp.json` receber qualquer valor parecido com credencial literal (`sk-`, `ghp_`, `AKIA`) THEN HYG-04 e HYG-06 (hoje aprovados, 6 pontos) SHALL reprovar
- IF o `command` de um hook contiver token com `/` apontando para caminho inexistente THEN HKS-05 SHALL reprovar mesmo que o hook funcione
- IF `mypy` acusar erro na base atual THEN o escopo ou as opções SHALL ser ajustados até o gate ficar verde, sem `# type: ignore` espalhado
- IF a instalação de `mypy` exigir recompilar `requirements.txt` com hashes e a ferramenta de compilação não existir THEN o type-check SHALL ser instalado no CI por versão pinada, e a limitação registrada na spec
- WHEN arquivos novos entram na raiz THEN o `.gitignore` em allowlist SHALL ser atualizado antes do `git add`, senão o arquivo some do `git status` em silêncio

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| HS108-01 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-02 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-03 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-04 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-05 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-06 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-07 | P1: Fechar os 6 checks | Tasks | Pending |
| HS108-08 | P1: Cada conserto executa | Tasks | Pending |
| HS108-09 | P1: Cada conserto executa | Tasks | Pending |
| HS108-10 | P1: Cada conserto executa | Tasks | Pending |
| HS108-11 | P1: Cada conserto executa | Tasks | Pending |
| HS108-12 | P2: Rastro para quem herda | Tasks | Pending |
| HS108-13 | P2: Rastro para quem herda | Tasks | Pending |

---

## Success Criteria

- [ ] `npx harness-score` reporta 108/108 e 36 checks aprovados, com saída salva como evidência
- [ ] `pytest -q` verde, com `COLETA_MEDIDA` batendo a coleta real
- [ ] `python tools/lint_routers.py` sai 0
- [ ] `.githooks/pre-push` verde ponta a ponta na máquina Windows do dono
- [ ] Zero arquivo criado cuja única função seja existir para o scanner
