# harness-score 108/108 Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Spec**: `.specs/features/harness-score-108/spec.md`
**Design**: none - mudanças localizadas, sem decisão arquitetural nova
**Status**: In Progress

---

## Test Coverage Matrix

> Gerada do próprio repo. Guidelines encontradas: `AGENTS.md`, `pytest.ini`, `conftest.py`, `tests/test_hooks.py`, `tests/test_pre_push_hook.py`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Hook Python (`.claude/hooks/*.py`) | unit | Todos os ramos; 1:1 com os ACs da spec; todo edge case listado tem teste | `tests/test_hooks.py` | `python -m pytest -q tests/test_hooks.py` |
| Wrapper shell (`.claude/hooks/run_hook.sh`) | unit | Allowlist: nome conhecido passa, nome fora recusa | `tests/test_hooks.py` | `python -m pytest -q tests/test_hooks.py` |
| Git hook shell (`.githooks/*`) | integration | Contrato e paridade com o CI: gate presente, ordem, falha bloqueia | `tests/test_pre_commit_hook.py`, `tests/test_pre_push_hook.py` | `python -m pytest -q tests/test_pre_commit_hook.py tests/test_pre_push_hook.py` |
| Config de raiz (`.gitignore`, `LICENSE`, `.mcp.json`, `pyproject.toml`, `.pre-commit-config.yaml`) | none | Gate only - presença e validade cobertas pelo gate build e pelo scanner | - | gate build |
| Router / docs (`AGENTS.md`, `README.md`) | none | Gate only - `lint_routers.py` | - | `python tools/lint_routers.py` |

## Gate Check Commands

> Todo comando roda com o Python do `.venv` do repo alvo, a partir da raiz do repo.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | Depois de task que só mexe em hook Python | `python -m pytest -q tests/test_hooks.py` |
| Full | Depois de task que mexe em git hook ou config de gate | `python -m pytest -q` |
| Build | Fim de fase, e toda task que mexe em config de raiz ou router | `python -m pytest -q && python tools/lint_routers.py && python tools/gate_veredito.py && ruff check .` |

---

## Execution Plan

Fases rodam em sequência; tasks dentro da fase rodam em ordem.

### Phase 1: Raiz e sensores de código

Arquivos de raiz e o type-checker. Nenhuma depende das outras, mas rodam em ordem para manter um commit por task.

```
T1 → T2 → T3
```

### Phase 2: Hooks que executam

O miolo: os três mecanismos que precisam morder de verdade.

```
T4 → T5 → T6
```

### Phase 3: Fechamento e evidência

```
T7
```

---

## Task Breakdown

### T1: LICENSE MIT na raiz, com allowlist do .gitignore

**What**: Criar `LICENSE` (MIT, copyright "Caio Kohn", ano 2026) na raiz e liberá-lo na allowlist do `.gitignore`.
**Where**: `LICENSE`, `.gitignore`
**Depends on**: None
**Reuses**: seção "Raiz — um a um" do `.gitignore` (linhas 10-23), padrão `!/NOME`
**Requirement**: HS108-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `LICENSE` existe na raiz com texto MIT completo (sem placeholder tipo `[year]`/`[fullname]`)
- [x] `.gitignore` ganhou `!/LICENSE` na seção de raiz, em ordem alfabética coerente com as linhas vizinhas
- [x] `git ls-files LICENSE` retorna `LICENSE` após o `git add`
- [x] Gate build passa

**Tests**: none (config layer - gate only)
**Gate**: build

---

### T2: .mcp.json com a convenção de credencial documentada

**What**: Criar `.mcp.json` com `{"mcpServers": {}}`, liberá-lo no `.gitignore` e documentar no README que MCP se declara ali e que credencial vai por `${VAR}`, nunca literal.
**Where**: `.mcp.json`, `.gitignore`, `README.md`
**Depends on**: T1
**Reuses**: seção `## O que o Claude Code bloqueia sozinho neste repo` do `README.md` (linha 105)
**Requirement**: HS108-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `.mcp.json` é JSON válido contendo exatamente a chave `mcpServers` com objeto vazio
- [x] Nenhum valor no arquivo casa com assinatura de credencial (`sk-`, `sk-ant-`, `ghp_`, `AKIA`, chave privada, JWT) - senão HYG-04 e HYG-06, hoje aprovados, reprovam
- [x] `.gitignore` ganhou `!/.mcp.json`
- [x] README explica, em até 3 linhas, que servidor MCP do projeto se declara em `.mcp.json` e que campo de credencial usa `${NOME_DA_VAR}`
- [x] `python tools/lint_routers.py` sai 0 (o README passa a citar `.mcp.json`, que precisa estar no índice git)
- [x] Gate build passa

**Tests**: none (config layer - gate only)
**Gate**: build

---

### T3: mypy configurado e rodando nos dois gates

**What**: Acrescentar `[tool.mypy]` ao `pyproject.toml` cobrindo `tools/` e `tests/`, deixar o type-check verde na base atual e rodá-lo em `.githooks/pre-push` e em `.github/workflows/tests.yml`.
**Where**: `pyproject.toml`, `.githooks/pre-push`, `.github/workflows/tests.yml`, `requirements.in`, `requirements.txt`
**Depends on**: T2
**Reuses**: o bloco condicional do `ruff` no `.githooks/pre-push` (passo 4) e o step "Lint de estilo (ruff)" do `tests.yml`
**Requirement**: HS108-04, HS108-11

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `pyproject.toml` tem `[tool.mypy]` com `python_version` coerente com `.python-version`, `ignore_missing_imports = true`, `files = ["tools", "tests"]` (ou equivalente), sem `strict`
- [x] `mypy` roda na base atual e termina com exit 0, sem `# type: ignore` novo espalhado pelo código (teto de 3 rodadas de ajuste de config; se sobrar erro legítimo, corrigir a anotação, não silenciar)
- [x] `.githooks/pre-push` roda o type-check depois do `ruff`, com a MESMA degradação condicional do `ruff` (não instalado = aviso e segue)
- [x] `.github/workflows/tests.yml` roda o type-check depois do step de `ruff`, e ali ele é obrigatório
- [x] `mypy` foi acrescentado às dependências pinadas. O CI instala com `--require-hashes`: se `pip-compile --generate-hashes` não estiver disponível na máquina, pinar a versão exata no step do CI e REGISTRAR essa limitação em `.specs/features/harness-score-108/tasks.md` como desvio
- [x] `tests/test_pre_push_hook.py` (paridade hook × CI) continua verde - se ele enumera os gates, incluir o novo na lista
- [x] Gate full passa

**Tests**: integration (o teste de paridade existente cobre a camada; estender, não criar arquivo novo)
**Gate**: full

---

### T4: Instruções de contexto saem do settings.json e viram scripts versionados

**What**: Extrair o conteúdo inline dos hooks `PreCompact` e `SessionStart` para scripts em `.claude/hooks/`, registrá-los na allowlist do `run_hook.sh` e apontar o `settings.json` para eles via `$CLAUDE_PROJECT_DIR`.
**Where**: `.claude/hooks/` (2 scripts novos), `.claude/hooks/run_hook.sh`, `.claude/settings.json`, `tests/test_hooks.py`
**Depends on**: None (primeira task da Fase 2; a Fase 1 já fechou)
**Reuses**: padrão de `guarda_bash.py` (stdin JSON, falha fechada) e o `case` de allowlist em `run_hook.sh:9`
**Requirement**: HS108-07, HS108-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Dois scripts novos em `.claude/hooks/` emitem o MESMO texto que hoje está inline (preservar o conteúdo palavra por palavra; é instrução de preservação de contexto, não reescrever)
- [x] `run_hook.sh` aceita os dois nomes novos na allowlist e continua recusando nome desconhecido
- [x] `.claude/settings.json` chama os dois via `sh "$CLAUDE_PROJECT_DIR/.claude/hooks/run_hook.sh" <script>`, no mesmo formato dos `PreToolUse` existentes
- [x] `.claude/settings.json` continua JSON válido e todo hook mantém `type` e `command` (HKS-01/HKS-02 valem 6 pontos hoje aprovados)
- [x] Nenhum `command` de hook contém token com `/` que não resolva para arquivo no índice git
- [x] `tests/test_hooks.py` cobre: saída de cada script novo, allowlist do wrapper (nome novo passa, nome desconhecido recusa), e que o `settings.json` não tem mais JSON inline nos dois eventos
- [x] Gate quick passa; gate full passa no fim (exceto `test_coleta_medida_e_piso_batem_com_a_coleta_real`, desvio declarado: T7 reconcilia `COLETA_MEDIDA` ao fim da Fase 2/3, fora do escopo desta task)

**Tests**: unit
**Gate**: full

---

### T5: Hook PostToolUse devolve o erro do linter ao agente

**What**: Criar hook `PostToolUse` para `Edit|Write|MultiEdit` que roda `ruff check` no arquivo tocado e devolve o resultado ao agente sem bloquear, degradando em silêncio quando `ruff` não existe.
**Where**: `.claude/hooks/` (1 script novo), `.claude/hooks/run_hook.sh`, `.claude/settings.json`, `tests/test_hooks.py`
**Depends on**: T4
**Reuses**: `guarda_segredo.py` (mesmo matcher, mesma leitura de `tool_input.file_path`), `run_hook.sh`
**Requirement**: HS108-06, HS108-08

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] O script lê o JSON do stdin, extrai o caminho do arquivo editado e só age em arquivo `.py` dentro do projeto
- [ ] Com `ruff` instalado e arquivo com erro: o hook devolve o texto do erro ao agente pelo canal documentado do `PostToolUse` e NÃO bloqueia a edição
- [ ] Com `ruff` instalado e arquivo limpo: saída vazia, exit 0
- [ ] Sem `ruff` instalado, ou se a chamada estourar: exit 0, sem saída, sem exceção vazando (a máquina Windows do dono tem `ruff.exe` bloqueado por antivírus)
- [ ] Arquivo fora do projeto, caminho ausente ou JSON inválido no stdin: exit 0 em silêncio
- [ ] `run_hook.sh` ganhou o nome novo na allowlist
- [ ] `.claude/settings.json` registra o hook no evento `PostToolUse` com matcher `Edit|Write|MultiEdit`, e segue JSON válido
- [ ] `tests/test_hooks.py` cobre os 5 ramos acima com `ruff` simulado (sem depender de `ruff` real na máquina)
- [ ] Gate full passa

**Tests**: unit
**Gate**: full

---

### T6: Gate de pre-commit que roda de verdade

**What**: Criar `.githooks/pre-commit` rodando `ruff check` nos arquivos staged e `tools/policy_check.py`, e um `.pre-commit-config.yaml` que invoca esse mesmo script em vez de duplicar a lista.
**Where**: `.githooks/pre-commit`, `.pre-commit-config.yaml`, `.gitignore`, `tests/test_pre_commit_hook.py`
**Depends on**: T5
**Reuses**: cascata de interpretador e formato de saída do `.githooks/pre-push`
**Requirement**: HS108-05, HS108-10

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `.githooks/pre-commit` roda `ruff check` só nos arquivos staged e `tools/policy_check.py`, e sai != 0 quando qualquer um reprova
- [ ] Sem `ruff` instalado: avisa e segue (exit 0) - mesma degradação do `pre-push`
- [ ] Sem arquivo staged relevante: sai 0 rápido
- [ ] `.pre-commit-config.yaml` declara um hook `repo: local` que chama `.githooks/pre-commit`, sem repetir a lista de checagens
- [ ] `.gitignore` ganhou `!/.pre-commit-config.yaml`
- [ ] `tests/test_pre_commit_hook.py` cobre: existência e bit executável, presença dos dois gates, bloqueio em arquivo sujo, degradação sem `ruff`, e paridade entre o script e o que o `.pre-commit-config.yaml` invoca
- [ ] O novo arquivo de teste entrou em `conftest.GATES_OBRIGATORIOS` com o mínimo de testes
- [ ] Gate build passa

**Tests**: integration
**Gate**: build

---

### T7: Router, coleta, decisão e a medição final

**What**: Atualizar `AGENTS.md`/`README.md`, acertar `COLETA_MEDIDA`, registrar `AD-002` no `STATE.md` e rodar `npx harness-score` salvando a saída como evidência.
**Where**: `AGENTS.md`, `README.md`, `conftest.py`, `.specs/STATE.md`, `.specs/features/harness-score-108/`
**Depends on**: None (única task da Fase 3; as Fases 1 e 2 já fecharam)
**Reuses**: tabela "Procurando... | Vá para" (`AGENTS.md:21-33`), formato `AD-nnn` do `STATE.md`
**Requirement**: HS108-01, HS108-12, HS108-13

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Tabela de estrutura do `AGENTS.md` cita `LICENSE`, `.mcp.json` e `.pre-commit-config.yaml` na linha de configuração
- [ ] README descreve o hook de feedback `PostToolUse` junto dos dois `PreToolUse` já documentados
- [ ] `conftest.COLETA_MEDIDA` bate a coleta real depois dos testes novos (`python -m pytest --collect-only -q | tail -1`)
- [ ] `.specs/STATE.md` ganhou `AD-002` datado, com o que foi decidido, o porquê e a ressalva dos checks que o scanner não sabe medir
- [ ] `npx harness-score` reporta 108/108 e 36 checks aprovados; saída salva em `.specs/features/harness-score-108/harness-score-depois.txt`
- [ ] Gate build passa
- [ ] `git status --short` limpo ao fim (tudo commitado)

**Tests**: none (docs/config - gate only)
**Gate**: build

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

Phase 1:  T1 ------→ T2 ------→ T3
Phase 2:  T4 ------→ T5 ------→ T6
Phase 3:  T7
```

---

## Desvios registrados

> Preenchido durante a execução. Todo desvio do plano acima entra aqui com o motivo.

- **T3 — lock gerado com `pip-tools`, não `uv`.** A máquina não tem `uv` instalado
  (`command not found`). `pip install pip-tools` funcionou de primeira e
  `python -m piptools compile --generate-hashes --output-file=requirements.txt
  requirements.in` reproduziu cobertura de hash equivalente à do `uv` (462 → 460
  linhas de hash antes de acrescentar o mypy; a diferença é ruído de anotação, não
  de cobertura de plataforma). Testado de ponta a ponta: `pip install
  --require-hashes -r requirements.txt` num venv novo instala os 39 pacotes sem
  erro. Um efeito colateral do resolver do pip-tools: `cachecontrol[filecache]`
  (a extra é real — `pip-audit` a declara — mas `filelock` já entra como entrada
  própria e pinada, então o sufixo é só anotação) foi normalizado de volta para
  `cachecontrol==0.14.4` para casar com `test_lock_de_dependencias_tem_versoes_e_
  hashes_exatos`, que não aceita colchete no nome do pacote.
- **T3 — `tools/eval_runner.py` excluído do mypy.** É o ESPELHO de uma cópia
  canônica (`Caio-MOR/plugins`), com gate de SHA-256 pinado
  (`tests/test_runner_sincronizado.py`) que reprova qualquer edição local feita
  fora da propagação oficial. As 5 anotações que eu cheguei a acrescentar nele
  foram revertidas assim que o gate de sincronia acusou; corrigido em
  `[tool.mypy]` com `exclude = "^tools/eval_runner\\.py$"` e comentário
  explicando o porquê. Os erros de tipo dele ficam para quem edita a canônica.
- **T3 — correções de tipo fora do "Where" declarado da task.** Fechar `mypy`
  com exit 0 exigiu tocar arquivos que a task não listava em "Where"
  (`tools/lint_routers.py`, `tools/gate_veredito.py`, `tools/operational_audit.py`,
  `tests/test_lint_routers.py`, `tests/test_criacao_nova.py`,
  `tests/test_rotina_exemplo_runtime.py`) — o próprio "Done when" da task pede
  "corrigir a anotação, não silenciar", o que implica editar onde o erro mora.
  Todas as edições foram cirúrgicas: anotações de tipo (`dict[str, Path] = {}`
  em vez de `{}`), renomeação de variável de loop reusada com tipo incompatível
  (`no` → `funcao` em `gate_veredito.py`; `plugin_dir` → `plugin_dir_real` em
  `eval_runner.py`, revertido junto com o resto do arquivo), um guard de `None`
  genuíno antes de `.split()` em `operational_audit.py` (import relativo com
  `module=None`, bug real embora nunca disparado na prática), e a correção de
  dois tipos declarados errados em `lint_routers.py` (`list[str]` que na
  verdade sempre foi `list[tuple[str, bool]]`, confirmado pelo próprio uso do
  valor três linhas abaixo). Nenhum `# type: ignore` foi usado.
- **T3 — fixture de `tests/test_pre_push_hook.py` ganhou um `pyproject.toml`
  neutro.** O repositório sintético do teste não tem config de mypy; sem alvo,
  `python -m mypy` sai com erro ("Missing target module...") mesmo sem nenhum
  problema de tipo real — não é o gate reprovando, é ausência de config. Segui
  o mesmo padrão já usado para o `ruff.toml` neutro na mesma fixture: um
  `pyproject.toml` com `[tool.mypy]` apontando `files = ["tools"]` (a mesma
  pasta com os scripts falsos triviais que o teste já cria).
