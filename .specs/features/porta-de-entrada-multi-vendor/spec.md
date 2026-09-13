# Porta de entrada multi-vendor

## Problem Statement

O template declara ser multi-vendor, mas só entrega isso para as *instruções*. Todo o resto do harness — skills, sub-agentes, commands, hooks — fala um dialeto só, o do Claude Code. Codex, Grok Build e Cursor leem `AGENTS.md` nativamente e não carregam skill nenhuma.

Três medições desta sessão sustentam o recorte:

- **Trilha A do `harness-eval` (13/09):** 0 BROKEN, mas a régua inventariou só 6 dos 18 arquivos de texto de harness. Ela enxerga apenas o que está citado por caminho explícito a um hop de `AGENTS.md`/`CLAUDE.md`. `SECURITY.md` não é citado em lugar nenhum do harness; `README.md` aparece como nome solto; os 4 docs de `docs/` estão a 2 hops; 3 das 6 rules não são citadas. O que a régua não alcança, o agente também não alcança por roteamento.
- **Trilha C (trap PASS):** `AGENTS.md` é KEEP-CORE unânime, 0 SLIM. Duas rules saíram MIXED com plano KEEP/CUT concreto (`11-mixed-apply.md`).
- **Trilha B:** veredito formal inválido (o trap gate reprovou), mas 19 claims saíram dual-REDUNDANT e o núcleo deles em T0 é a seção "Arquitetura WAT" inteira mais a prosa motivacional. Converge com Gloaguen/Mündler et al. (ETH Zurich, arXiv 2602.11988), que mede que *repository overview* não melhora acerto e custa >20% de inferência, enquanto instrução específica é bem seguida.

O corte a fazer, portanto, não é de regra — é de exposição de motivo. O espaço economizado paga o roteamento explícito que falta.

## User Stories

- **Como pessoa que abre o template no Codex ou no Grok Build,** quero que o agente carregue as instruções e as skills do repo sem eu configurar nada, para não descobrir no meio do trabalho que metade do harness não existe para mim.
- **Como pessoa que edita uma skill,** quero um lugar só para editar e um erro claro se eu mexer no lugar errado, para não manter três cópias na mão.
- **Como agente lendo o repo pela primeira vez,** quero alcançar `SECURITY.md` e as regras por caminho citado no `AGENTS.md`, para não depender de adivinhar que existem.
- **Como dono do template,** quero o texto sempre-carregado menor do que hoje sem perder regra, porque cada linha ali custa inferência em toda sessão de todo clone.

## Objetivo

Um `AGENTS.md` na raiz que sirva os quatro agentes; skills com fonte única visível para além do dialeto `.claude/`; roteamento explícito para todo arquivo de harness; e o texto sempre-carregado menor do que é hoje.

## Decisões já tomadas (Caio, 13/09/2026)

- **D1 — Fonte única em `.agents/skills/`, espelho gerado por script** para `.claude/skills/` e `.grok/skills/`, com gate reprovando drift. Nada de symlink ou junction: o template roda em VM Windows de usuário leigo, sem Developer Mode, e link que não é criado falha em silêncio.
- **D2 — Branch nova a partir da `main`** (`porta-de-entrada-multi-vendor`), com a PR #4 já mergeada em `ba0504e`.

## Assumptions & Open Questions

- **S1 — O custo de D1 é conhecido e aceito.** A string literal `.claude/skills` aparece em 17 pontos de 8 arquivos versionados (`tests/test_criacao_nova.py:31,331,685`, `tests/test_evals_estrutura.py:6,20`, `tools/eval_runner.py:38,41,512`, `tools/lint_routers.py:9,423`, `tools/CLAUDE.md:8`, `AGENTS.md:24,54`, `.claude/rules/conduta-colaborador.md:31`, `.claude/rules/estrutura-e-logging.md:5`). Manter a fonte onde está custaria ~4 pontos. A escolha por `.agents/` é deliberada: manter a fonte em `.claude/` é continuar privilegiando um dialeto, que é exatamente o que esta feature existe para desfazer.
- **S2 — O espelho é o que os gates atuais validam.** `tests/test_criacao_nova.py` e `tools/lint_routers.py` resolvem skill contra `.claude/skills/<nome>/SKILL.md`. Como o espelho é byte a byte idêntico à fonte, validar o espelho valida a fonte — mas a referência passa a apontar para a fonte para que a intenção fique legível.
- **S3 — Hooks não são portáveis entre vendors sem adaptador.** `guarda_bash.py` e `guarda_segredo.py` leem o payload de `PreToolUse` do Claude Code (`tool_input.command`, `tool_input.file_path`). Codex e Cursor têm schema próprio. A lógica de negócio é Python puro; só a extração do payload é acoplada. Adaptar é trabalho real e **não verificável nesta máquina**, que não tem Codex nem Cursor instalados.
Open questions: none. Nenhuma aberta — as duas bifurcações (local da fonte de skills e branch base) foram decididas pelo Caio em 13/09/2026 e estão em D1 e D2.

- **S4 — Não há gate de tamanho** sobre `AGENTS.md`, `CLAUDE.md` ou `.claude/rules/*.md`. Os únicos tetos são genéricos (200 KB no `padrao_ouro_audit.py`, 2 MB no `policy_check.py`). O encolhimento é medido por contagem de linhas antes/depois, não por gate.

## Requisitos

### ENT — Porta de entrada única

- **ENT-01** — WHEN um agente que lê `AGENTS.md` nativamente (Codex, Grok Build, Cursor) abre o repositório, THE template SHALL entregar todas as instruções sempre-carregadas a partir de `AGENTS.md` na raiz, sem exigir arquivo próprio do vendor.
- **ENT-02** — WHERE o agente é o Claude Code, THE template SHALL entregar as mesmas instruções por `CLAUDE.md`, que importa `AGENTS.md` na primeira linha e não duplica conteúdo.
- **ENT-03** — THE `AGENTS.md` SHALL declarar, em uma tabela de no máximo 6 linhas, qual peça do harness cada um dos quatro agentes carrega e qual não carrega.

### SKL — Skills com fonte única e espelho verificado

- **SKL-01** — THE repositório SHALL manter a fonte de toda skill em `.agents/skills/<nome>/`, versionada.
- **SKL-02** — WHEN `python tools/sync_skills.py` roda, THE script SHALL reproduzir cada skill de `.agents/skills/` em `.claude/skills/` e `.grok/skills/`, byte a byte, e remover do espelho pasta que não exista mais na fonte.
- **SKL-03** — WHEN `python tools/sync_skills.py --check` roda e algum espelho diverge da fonte, THE script SHALL sair com código diferente de zero e nomear cada arquivo divergente, faltante ou órfão.
- **SKL-04** — WHEN a suíte roda, THE gate SHALL reprovar drift entre fonte e espelho.
- **SKL-05** — IF um agente tenta escrever em `.claude/skills/` ou `.grok/skills/`, THEN o hook `PreToolUse` SHALL negar a escrita e informar o caminho equivalente na fonte.

### ROT — Roteamento completo

- **ROT-01** — THE `AGENTS.md` SHALL citar por caminho explícito, entre crases, todo arquivo de harness que um agente precisa alcançar — incluindo `SECURITY.md`, `README.md`, cada arquivo de `.claude/rules/` e cada documento de `docs/`.
- **ROT-02** — WHEN a trilha A do `harness-eval` roda sobre o repositório após a mudança, THE superfície inventariada SHALL conter `SECURITY.md`, os 6 arquivos de `.claude/rules/` e a skill de `.agents/skills/`, com 0 findings BROKEN.

### ENX — Texto sempre-carregado enxuto

- **ENX-01** — THE `AGENTS.md` SHALL NOT conter seção cujo conteúdo seja overview de arquitetura ou justificativa motivacional sem imperativo.
- **ENX-02** — WHEN um trecho é cortado, THE corte SHALL ser justificado por (a) uma linha CUT do `11-mixed-apply.md` da trilha C, ou (b) ausência de imperativo no trecho, ou (c) enforcement equivalente já existente em gate ou hook, citado por caminho.
- **ENX-03** — THE soma de linhas de `AGENTS.md` + `CLAUDE.md` + `.claude/rules/*.md` SHALL ser menor que a da `main`, sem remover nenhuma regra que não seja aplicada por gate ou hook.

### GAT — Gates

- **GAT-01** — WHEN `tests/test_evals_estrutura.py` roda e descobre zero skills, THE teste SHALL reprovar. (Hoje passa em silêncio: `descobrir_skills` devolve `{}` quando o diretório não existe, e os quatro testes do arquivo seguem verdes vendo nada.)
- **GAT-02** — THE `tools/lint_routers.py` SHALL resolver referência de skill no formato `/nome` contra `.agents/skills/<nome>/SKILL.md`.
- **GAT-03** — WHEN `python tools/gate_veredito.py` e `python tools/lint_routers.py` rodam ao fim da feature, THE saída SHALL ser `veredito: VERDE` e `0 erro(s)`.
- **GAT-04** — THE `.claude/rules/estrutura-e-logging.md` SHALL declarar no frontmatter `paths:` o caminho da fonte de skills, para que a regra continue disparando ao editar uma skill.

### ESC — Escopo declarado

- **ESC-01** — THE repositório SHALL documentar em `docs/` quais peças do harness cada vendor NÃO recebe, por que, e o que seria preciso para fornecê-las.

## Out of Scope

- **Hooks para Codex e Cursor** (`.codex/hooks.json`, `.cursor/hooks.json`). Exigem adaptador de payload (S3) e não são verificáveis nesta máquina. Entregar guardrail que ninguém testou é pior que não entregar: guardrail contornado é pior que guardrail ausente.
- **Sub-agentes para Codex** (`.codex/agents/*.toml`). Mesmo motivo.
- **`.cursor/rules/*.mdc`.** Redundante: o Cursor lê `AGENTS.md` nativamente, e duplicar regra em dois formatos cria drift sem ganho.
- **Espelho de `.claude/commands/`.** Commands são legado no Claude Code (fundidos em skills) e o Cursor usa formato próprio. O caminho certo é converter os dois commands existentes em skills — trabalho separado.
- **Re-rodar as trilhas B e C** após a mudança. A trilha A é grátis e entra como critério (R3.2); B e C custam juízes e a B ainda está com calibração reprovada.

## Critérios de aceitação

| ID | Critério | Como verificar |
|---|---|---|
| AC-1 | `AGENTS.md` é a única fonte de instrução e `CLAUDE.md` só o importa | `head -1 CLAUDE.md` = `@AGENTS.md`; nenhuma regra existe só no `CLAUDE.md` |
| AC-2 | Tabela de cobertura por vendor presente e com no máximo 6 linhas | leitura do `AGENTS.md` |
| AC-3 | Fonte das skills em `.agents/skills/`, espelhos idênticos | `python tools/sync_skills.py --check` sai 0 |
| AC-4 | Drift é detectado | alterar um byte num espelho faz `--check` sair != 0 nomeando o arquivo; o teste do gate reprova |
| AC-5 | Escrita em espelho é negada | invocar o hook com payload de Write em `.claude/skills/x` retorna negação citando `.agents/skills/x` |
| AC-6 | Todo arquivo de harness citado por caminho | `SECURITY.md`, `README.md`, as 6 rules e os 4 docs aparecem entre crases no `AGENTS.md`, e cada caminho existe no índice git |
| AC-7 | `SECURITY.md`, as 6 rules e a skill entram na superfície; 0 BROKEN | rodar trilha A e comparar o `inventory.json` com o do run `2026-09-13-trilhaA` (6 arquivos, sem nenhum dos três) |
| AC-8 | Texto sempre-carregado encolheu | `wc -l AGENTS.md CLAUDE.md .claude/rules/*.md` menor que na `main` |
| AC-9 | Gate de evals deixa de falhar em silêncio | com `.claude/skills/` vazio, `tests/test_evals_estrutura.py` reprova |
| AC-10 | Gates verdes | `veredito: VERDE` e `0 erro(s)` |
| AC-11 | Não-objetivos documentados | arquivo em `docs/` citado pelo `AGENTS.md` |

## Requirement Traceability

| Requisito | Critério |
|---|---|
| ENT-01 | AC-1 |
| ENT-02 | AC-1 |
| ENT-03 | AC-2 |
| SKL-01 | AC-3 |
| SKL-02 | AC-3 |
| SKL-03 | AC-4 |
| SKL-04 | AC-4 |
| SKL-05 | AC-5 |
| ROT-01 | AC-6 |
| ROT-02 | AC-7 |
| ENX-01 | AC-8 |
| ENX-02 | AC-8 |
| ENX-03 | AC-8 |
| GAT-01 | AC-9 |
| GAT-02 | AC-10 |
| GAT-03 | AC-10 |
| GAT-04 | AC-10 |
| ESC-01 | AC-11 |
