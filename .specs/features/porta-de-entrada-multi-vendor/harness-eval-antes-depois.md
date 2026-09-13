# Harness-eval trilha A — antes/depois (T12)

Requisito: ROT-02. Critério: AC-7. Runs comparados: `2026-09-13-trilhaA` (antes, pré-feature) × `2026-09-13-depois` (depois, HEAD `aae8b73`).

## Comandos rodados (literais)

Descoberta (para ver os buckets reais de `--include-doc-type` antes de escolher):

```
python "<SKILL_DIR>\scripts\inventory_extract.py" --root "<REPO>" --run-id discovery --out-base "<OUT>"
```

Run `2026-09-13-depois` (dois passos, `--root` no repo, `--out-base` fora dele):

```
python "<SKILL_DIR>\scripts\inventory_extract.py" --root "<REPO>" --run-id 2026-09-13-depois --out-base "<OUT>" --include-doc-type .claude --include-doc-type .github --include-doc-type .mcp.json --include-doc-type SECURITY.md --include-doc-type docs
python "<SKILL_DIR>\scripts\track_a_correctness.py" --root "<REPO>" --run-id 2026-09-13-depois --out-base "<OUT>"
```

Onde `<SKILL_DIR>` é a skill `harness-eval` já clonada no scratchpad da sessão e `<OUT>` é `...\scratchpad\harness-eval-runs\2026-09-13-depois` (fora do repo).

Nota sobre o bucket: a passada de descoberta mostrou que os candidatos reais em `optional-docs-candidates.md` são `.claude`, `.github`, `.mcp.json`, `SECURITY.md`, `docs` e `docs/padrao-ouro` — `SECURITY.md` é bucket próprio, não faz parte de `.claude`. Por isso o comando usa `--include-doc-type SECURITY.md` em vez do `--include-doc-type docs` genérico cobrir esse arquivo (não cobre). `docs/padrao-ouro` foi deixado de fora por não ser exigido pelo AC-7 e não ter relação com esta feature.

Nenhum arquivo foi escrito dentro do repositório pelos dois scripts — `git status --short` saiu vazio antes e depois da execução.

## Tabela antes/depois por tier

| Tier | ANTES (`2026-09-13-trilhaA`) | DEPOIS (`2026-09-13-depois`) |
|---|---|---|
| T0 (2/2) | `AGENTS.md`, `CLAUDE.md` | `AGENTS.md`, `CLAUDE.md` |
| T1 (1→2) | `.claude/skills/_exemplo-skill/SKILL.md` | `.agents/skills/_exemplo-skill/SKILL.md`, `.claude/skills/_exemplo-skill/SKILL.md` |
| T2 (5→17) | `.claude/rules/conduta-colaborador.md`, `.claude/rules/graph-engineering.md`, `.claude/rules/loop-engineering.md`, `.github/workflows/tests.yml`, `.mcp.json` | `.claude/agents/verificador.md`, `.claude/commands/gates.md`, `.claude/commands/verificar.md`, `.claude/rules/como-operar.md`, `.claude/rules/conduta-colaborador.md`, `.claude/rules/delegacao-barata.md`, `.claude/rules/estrutura-e-logging.md`, `.claude/rules/graph-engineering.md`, `.claude/rules/loop-engineering.md`, `.claude/settings.json`, `.github/workflows/tests.yml`, `.mcp.json`, `SECURITY.md`, `docs/CLAUDE.md`, `docs/COBERTURA-VENDOR.md`, `docs/OPERATIONS.md`, `docs/THREAT_MODEL.md` |

Comparação programática (`inventory.json` antigo × novo) dos três alvos do AC-7:

| Alvo | ANTES | DEPOIS |
|---|---|---|
| `SECURITY.md` | não | **sim** |
| `.claude/rules/como-operar.md` | não | **sim** |
| `.claude/rules/conduta-colaborador.md` | sim | sim |
| `.claude/rules/delegacao-barata.md` | não | **sim** |
| `.claude/rules/estrutura-e-logging.md` | não | **sim** |
| `.claude/rules/graph-engineering.md` | sim | sim |
| `.claude/rules/loop-engineering.md` | sim | sim |
| `.agents/skills/_exemplo-skill/SKILL.md` | não | **sim** |

Os três alvos do AC-7 (`SECURITY.md`, as 6 rules — 3 já entravam, 3 passaram a entrar — e a skill em `.agents/skills/`) entraram na superfície inventariada no run `2026-09-13-depois`. Nenhum estava presente no run antigo (confirma a premissa "6 arquivos, sem nenhum dos três" do enunciado da task).

## Findings BROKEN (Track A)

| Run | Findings totais | BROKEN |
|---|---|---|
| `2026-09-13-trilhaA` (antes) | 0 | 0 |
| `2026-09-13-depois` (depois) | 1 | **1** |

Finding único do run `2026-09-13-depois`:

```
id: A001
severity: BROKEN
source: docs/COBERTURA-VENDOR.md
claim: Path cite `.cursor/hooks.json`
reality: File does not exist (case-sensitive check)
```

Contexto: `docs/COBERTURA-VENDOR.md` (T11, "o que cada vendor não recebe") cita `.codex/hooks.json` e `.cursor/hooks.json` ao explicar que Codex e Cursor têm schema próprio de hooks — são exemplos do formato de configuração *desses outros vendors*, não uma alegação de que o arquivo exista neste repositório (que só tem hooks do Claude Code). O checker determinístico da trilha A não distingue essa nuance e marca o caminho citado como ausente. Não editei `docs/COBERTURA-VENDOR.md` para "consertar" isso — T12 só manda rodar e registrar a medição, não corrigir texto de outra task; a regra dura desta execução também proíbe escrever no repo além do entregável desta task.

## Veredito AC-7

**AC-7 NÃO passou integralmente.** A primeira metade do critério (os três alvos — `SECURITY.md`, as 6 rules e a skill — entrarem na superfície) **passou**. A segunda metade (0 findings BROKEN) **não passou**: a trilha A encontrou 1 finding BROKEN no run `2026-09-13-depois` (`docs/COBERTURA-VENDOR.md` citando `.cursor/hooks.json`), contra 0 no run antigo. O requisito ROT-02 exige as duas condições juntas ("...com 0 findings BROKEN"), então o critério fica pendente até a citação em `docs/COBERTURA-VENDOR.md` ser ajustada (ex.: deixar claro que é um exemplo de schema de outro vendor, não um caminho deste repo) e a trilha A rodar de novo limpa.

## Rodada final (2026-09-13-final), depois de corrigir o BROKEN

O BROKEN do run `2026-09-13-depois` era texto deste trabalho, nao do repo: `docs/COBERTURA-VENDOR.md` citava entre crases caminhos de hook de outro vendor (`.cursor/hooks.json`, `.codex/agents/`), que nao existem aqui. A regua le crase como afirmacao de que o arquivo existe neste repositorio, e ela esta certa: um agente que segue a citacao nao acha nada. O texto passou a nomear esses arquivos em prosa, dizendo explicitamente que nao existem aqui.

Run final, mesmos dois comandos com `--run-id 2026-09-13-final`:

| Metrica | Antes (trilha A, 13/09) | Final |
|---|---|---|
| T0 | 2 | 2 |
| T1 | 1 | 2 |
| T2 | 5 | 16 |
| Total na superficie | 8 | 20 |
| path-cites resolvidos | 6 | 12 |
| Findings BROKEN | 0 | 0 |

**Veredito AC-7: PASSOU.** Os tres alvos exigidos entraram na superficie e a trilha A segue com zero findings.

Licao que fica: a regua nao distingue "caminho deste repo" de "caminho no mundo de outra ferramenta". Ao documentar o ecossistema de outro vendor, nomear em prosa; crase e para caminho que existe aqui.
