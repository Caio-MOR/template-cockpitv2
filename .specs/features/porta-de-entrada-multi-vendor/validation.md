# Validacao - porta-de-entrada-multi-vendor

**Veredito: PASS**

Verificador independente (Sonnet 5). Diff verificado: main..HEAD (HEAD = aef8b47, 13 commits, bf691ec..aef8b47). Ambiente: .venv/Scripts/python.exe (Python 3.12.10). Nenhum push realizado. Mutacao testada em git worktree isolada (.tmp/verif-mutant-wt), removida ao final; git status --porcelain da arvore real ficou vazio antes e depois de toda a sessao.

## Criterios de aceitacao (AC-1..AC-11)

| AC | Evidencia | Status |
|---|---|---|
| AC-1 | `CLAUDE.md:1` = `@AGENTS.md` (reproduzido: `head -1 CLAUDE.md`). CLAUDE.md tem 7 linhas, so adendos (sub-agente/commands, memoria) - nenhuma regra canonica duplicada. | PASS |
| AC-2 | `AGENTS.md:11-17` - tabela "Cobertura por agente" com 5 linhas de conteudo (Este arquivo / Skills / Regras / Sub-agente e commands / Hooks) <= 6. `tests/test_agents_md_roteamento.py:117` mede programaticamente o mesmo teto. | PASS |
| AC-3 | `python tools/sync_skills.py --check` retornou "sync_skills --check: ok, sem divergencia" (reproduzido). Fonte em `.agents/skills/_exemplo-skill/SKILL.md`; espelhos em `.claude/skills/` e `.grok/skills/` identicos byte a byte (`tools/sync_skills.py:52-74`). | PASS |
| AC-4 | Mutante a: 1 byte alterado em `.claude/skills/_exemplo-skill/SKILL.md` (copia em worktree) fez `tests/test_sync_skills.py::test_repo_real_sem_drift` e `::test_cli_check_via_subprocesso` reprovarem citando o arquivo divergente; desfeito, voltou ao verde. Mutante b: pasta `.grok/skills/_exemplo-skill/` inteira apagada fez os mesmos testes reprovarem citando faltante. `test_sync_skills.py` esta em `conftest.py:40` (GATES_OBRIGATORIOS, minimo 10 testes). | PASS |
| AC-5 | Payload de Write simulado via stdin em `sh .claude/hooks/run_hook.sh guarda_espelho.py` (file_path apontando pro espelho) devolveu no stderr a mensagem de bloqueio citando o caminho equivalente na fonte, exit 2 (reproduzido). Registrado em PreToolUse de `.claude/settings.json:48`. | PASS |
| AC-6 | `SECURITY.md` (`AGENTS.md:43`), `README.md` (`AGENTS.md:44,46,62,66`), as 6 rules (`AGENTS.md:41`) e os 4 docs de `docs/` citados entre crases; todos existem no indice git. `tests/test_agents_md_roteamento.py:32-54,90-108` cobre 20 caminhos obrigatorios nos dois sentidos. | PASS |
| AC-7 | Reproduzido independentemente com a skill harness-eval (fora deste repo): inventory_extract.py com os 5 include-doc-type (.claude, .github, .mcp.json, SECURITY.md, docs) deu T0=2, T1=2 (inclui `.agents/skills/_exemplo-skill/SKILL.md`), T2=17 (inclui SECURITY.md e as 6 rules); track_a_correctness.py deu findings=0, broken=0. Bate com o run 2026-09-13-final documentado em `harness-eval-antes-depois.md:76-87`. O relato do proprio autor e transparente sobre uma rodada intermediaria que teve 1 BROKEN por `.cursor/hooks.json` citado entre crases em `docs/COBERTURA-VENDOR.md`; corrigido no commit aef8b47 (confirmado por grep: esse caminho so aparece em prosa agora, `docs/COBERTURA-VENDOR.md:29`). | PASS |
| AC-8 | Soma de linhas de AGENTS.md + CLAUDE.md + .claude/rules/*.md na main: 68+9+30+55+43+12+38+30 = 285. No HEAD: 78+7+30+39+43+12+38+21 = 268. 268 menor que 285 (reproduzido linha a linha nos dois commits via git show). | PASS |
| AC-9 | Mutante c: `.agents/skills` renomeado para inexistente (worktree) fez `tests/test_evals_estrutura.py::test_fonte_de_skills_tem_ao_menos_uma_skill` e `::test_sensor_reprova_com_fonte_vazia_ou_ausente_e_passa_com_a_real` reprovarem; os outros 6 testes do arquivo continuariam verdes vendo zero skills se nao fosse por este sensor (`test_evals_estrutura.py:41-49`). Restaurado, voltou ao verde. Este era o gate GAT-01 que antes passava em silencio; confirmado morto agora. | PASS |
| AC-10 | `python tools/gate_veredito.py` devolveu veredito VERDE (suite: 364 passed, 2 skipped em 85.25s, reproduzido). `python tools/lint_routers.py` devolveu 0 erro(s) em 7 arquivos (reproduzido). GAT-02 confirmado em `tools/lint_routers.py:423`. GAT-04 confirmado em `.claude/rules/estrutura-e-logging.md:3` (frontmatter paths com .agents/skills/**). | PASS |
| AC-11 | `docs/COBERTURA-VENDOR.md` existe, citado em `AGENTS.md:19` e `docs/CLAUDE.md:8`, documenta o que cada vendor nao recebe, por que, e o que seria preciso. | PASS |

## Sensor de discriminacao - 6 mutantes obrigatorios

Rodados em git worktree isolada (.tmp/verif-mutant-wt, nunca git stash, nunca a arvore real), restaurados com git checkout apos cada teste, worktree removida ao final.

| Mutante | Gate esperado | Resultado |
|---|---|---|
| a: 1 byte a mais no espelho .claude/skills/_exemplo-skill/SKILL.md | test_repo_real_sem_drift, test_cli_check_via_subprocesso | Reprovou citando divergente - morto |
| b: pasta .grok/skills/_exemplo-skill/ apagada inteira | mesmos dois testes | Reprovou citando faltante - morto |
| c: .agents/skills/ renomeada (fonte some) | test_evals_estrutura.py (2 testes do sensor GAT-01) | Reprovou (nao achou nenhuma skill) - morto |
| d: guarda_espelho.py removido da allowlist de run_hook.sh | test_guarda_espelho_esta_na_allowlist_do_run_hook, test_run_hook_executa_guarda_espelho_de_verdade | Reprovou (script de hook nao permitido, exit 2) - morto |
| e: SECURITY.md sem crase em AGENTS.md | test_agents_md_roteamento.py parametrizado para SECURITY.md | Reprovou - morto |
| f: frase sobre branch removida de conduta-colaborador.md | test_texto_sempre_carregado.py::test_frase_mantida_contra_o_plano_de_corte_segue_presente | Reprovou - morto |

Zero mutantes sobreviveram.

## Teste raso - tests/test_sync_skills.py reescrito

Comparando os commits que tocaram o arquivo: test_cli_check_via_subprocesso mudou de esperar fonte ausente com exit diferente de zero (quando .agents/skills/ ainda nao existia no repo) para esperar sem divergencia com exit zero (depois da migracao real da fonte). Nao e enfraquecimento: e reapontamento correto para o estado verdadeiro do repositorio apos a migracao ter sido de fato feita, confirmado por test_repo_real_sem_drift que compara os tres conjuntos de caminhos pelo indice git, nao pelo filesystem. Nenhuma assercao foi relaxada.

## Ceticismo declarado (item 5 do escopo)

1. Versionamento e padrao ficou porque guarda_bash.py so protege o Claude Code. Confirmado: .claude/hooks/guarda_bash.py e um hook PreToolUse que le tool_input.command do payload JSON do Claude Code, registrado so em .claude/settings.json:33. Nao existe .codex/hooks.json nem .cursor/hooks.json no repositorio. Justificativa sustentada.
2. Sete pontos de codigo citam loop-engineering como definicao de freio. Confirmado por grep recursivo em arquivos .py (excluindo .venv): tools/eval_runner.py, tools/gate_veredito.py, tools/lint_routers.py, tests/test_agents_md_roteamento.py, tests/test_lint_routers.py, tests/test_sync_skills.py, workflows/_exemplo-rotina/scripts/rotina_exemplo.py = exatamente 7 arquivos, excluindo o proprio gate que faz a alegacao. Justificativa sustentada.

## Numeros publicados (reproduzidos)

- tools/gate_veredito.py: veredito VERDE, suite 364 passed, 2 skipped em 85.25s.
- tools/lint_routers.py: 0 erro(s) em 7 arquivo(s) verificados.
- tools/operational_audit.py: operational score 10.0/10.0.
- Soma de linhas AGENTS.md + CLAUDE.md + .claude/rules/*.md: main = 285, HEAD = 268.
- Trilha A do harness-eval rodada de novo, de forma independente: T0=2, T1=2, T2=17, findings=0, broken=0.

## Lacunas (nenhuma que reprove a entrega)

Nenhum furo de gravidade alta encontrado. Duas observacoes de precisao, sem impacto no veredito:

1. Baixa - Precisao da spec em ROT-02 e AC-7. A spec exige que a superficie inventariada contenha os tres alvos com zero findings BROKEN, mas nao define qual comando e quais flags de include-doc-type produzem essa superficie; o comando correto so esta documentado no arquivo harness-eval-antes-depois.md desta feature, nao na spec nem no AGENTS.md. Sugestao: registrar o comando canonico em docs ou no AGENTS.md.
2. Informativa - AC-7 nao e gate automatizado, e medicao pontual desta sessao. Nao ha regressao automatica se alguem adicionar um caminho novo de harness sem citar entre crases, alem do que ja esta coberto pela lista fixa de test_agents_md_roteamento.py. Nao e um furo desta feature, e uma caracteristica conhecida e aceita pela propria spec.

## O que nao foi possivel verificar

- Adaptador de hooks para Codex e Cursor: fora de escopo, declarado explicitamente pela spec, nao avaliado.
- Comportamento real do Codex, Grok Build e Cursor lendo o AGENTS.md nesta maquina: nenhum desses agentes esta instalado aqui; a verificacao foi por conformidade de formato agents.md e pela trilha A do harness-eval, nao por execucao real de outro vendor.
