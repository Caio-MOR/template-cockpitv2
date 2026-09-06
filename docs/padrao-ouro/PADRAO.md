# Padrão ouro de repositório para trabalhar com Claude Code — norma v1

**O que é:** a lista de exigências que um repositório precisa cumprir para que um agente de código (Claude Code ou outro que leia `AGENTS.md`) trabalhe nele com contexto certo, verificação mecânica e sem vazar segredo ou caminho de máquina. Vale para três tipos de repo: **cockpit** (hub pessoal de automações, tools e docs), **app** (aplicação web) e **skills** (repo de plugin com skills, agentes e commands compartilháveis).

**Como se mede:** cada exigência abaixo tem um check que uma máquina executa. O auditor `padrao_ouro_audit.py` implementa exatamente esses checks e devolve um placar de 0 a 10 com uma casa decimal:

```
placar = soma dos pesos das exigências aprovadas ÷ soma dos pesos aplicáveis ao tipo × 10
```

Exigência que não tem check mecânico **não entra na tabela**: vai para a seção "Orientativo, não medido". Está no padrão quem tem placar **≥ 9,0**. O que reprova sai listado como `id  arquivo:linha  motivo`, para o conserto ter endereço.

**Como se roda:**

```
python padrao_ouro_audit.py --tipo cockpit .          # tipo explícito
python padrao_ouro_audit.py .                         # tipo lido de `tipo:` no AGENTS.md
python padrao_ouro_audit.py --tipo app --template .   # num repo-template (placeholders permitidos)
```

Exit 0 = placar ≥ 9; 1 = placar < 9; 2 = tipo não detectado ou raiz inexistente.

**O que conta como "versionado":** o índice git (`git ls-files`) quando a raiz é um repositório; caso contrário o disco inteiro, com o aviso `sem índice git; medindo o disco`. Arquivos binários (imagem, planilha, pdf, zip, fontes) ficam fora dos checks de conteúdo.

---

## Exigências medidas

| Id | Tipos | Peso | Exigência | Check mecânico |
|---|---|---|---|---|
| PO-A01 | todos | 1 | Fonte única de instruções com tipo declarado | `AGENTS.md` na raiz contém uma linha `tipo: cockpit`, `tipo: app` ou `tipo: skills` |
| PO-A02 | todos | 1 | O arquivo do Claude importa a fonte única, não a duplica | `CLAUDE.md` na raiz; a primeira linha não vazia é exatamente `@AGENTS.md` |
| PO-A03 | todos | 0,5 | Instruções enxutas | `AGENTS.md` e `CLAUDE.md` têm no máximo 200 linhas cada |
| PO-A04 | todos | 0,5 | Receita de ambiente escrita | `README.md` tem um título `##` contendo "Ambiente" ou "Como rodar" |
| PO-B01 | todos | 0,5 | Regras modulares, fora do arquivo principal | `.claude/rules/` contém ao menos um `.md` |
| PO-B02 | todos | 0,5 | Autor nunca é o verificador | `.claude/agents/verificador.md` existe |
| PO-C01 | todos | 1 | Verificação roda sem depender de memória humana | ao menos um arquivo em `.github/workflows/*.yml` ou `*.yaml` com gatilho `push` ou `pull_request` em `on:` (`workflow_dispatch` sozinho não conta: quem dispara à mão é memória humana), **e** `.githooks/pre-push` versionado (os gates rodam antes do push, na máquina de quem empurra) |
| PO-C02 | todos | 1 | CI não confia em tag móvel nem em permissão implícita | em todo workflow, cada `uses:` termina em `@` + 40 caracteres hexadecimais, e há uma chave `permissions:` no nível do workflow ou de cada job |
| PO-C03 | todos | 1 | Segredo não entra no histórico sem alarme | algum workflow contém a palavra `gitleaks` |
| PO-D01 | todos | 0,5 | Decisões sobrevivem à sessão | `.specs/STATE.md` existe |
| PO-E01 | todos | 0,5 | O git versiona o que se libera, não o que se esquece de negar | `.gitignore` existe e a primeira regra não comentada é `/*` ou `*` (allowlist) |
| PO-E02 | todos | 0,25 | Fim de linha não depende da máquina | `.gitattributes` contém `text=auto` |
| PO-F01 | todos | 1 | Nenhum `.env` no repo | nenhum arquivo versionado se chama `.env` ou `.env.*` (exceto `.env.example`), e `.gitignore` contém uma linha `.env` |
| PO-F02 | todos | 1 | Zero caminho absoluto de máquina | nenhum arquivo versionado de texto contém `X:\Users\` (qualquer letra, barra ou contrabarra), `/Users/nome/`, `/home/nome/` ou `\\servidor\pasta` (UNC); linha com `padrao-ouro:ignorar` fica de fora <!-- padrao-ouro:ignorar --> |
| PO-F04 | todos | 0,25 | Sem peso morto | nenhum arquivo versionado tem mais de 200 KB |
| PO-G01 | todos | 0,5 | Repo instanciado não tem placeholder esquecido | nenhum `{{nome}}` (`{{` seguido de letra ou `_`, sem `$` antes) em arquivo de doc ou config (`.md .yml .yaml .json .toml .ini .cfg .txt` e sem extensão — código fica fora, `{{x}}` ali é templating legítimo); **isento com `--template`** <!-- padrao-ouro:ignorar --> |
| PO-K01 | cockpit | 1 | Cada categoria tem router local | `workflows/CLAUDE.md`, `tools/CLAUDE.md` e `docs/CLAUDE.md` existem |
| PO-K02 | cockpit | 0,5 | Toda rotina nasce com grafo e formato declarado | todo `workflows/*/workflow.md` tem um bloco ```` ```mermaid ```` e uma linha `%% formato:` |
| PO-K03 | cockpit | 0,5 | A suíte tem piso de coleta fora de `tests/` | `conftest.py` na raiz contém `PISO_COLETA`, e `tests/` tem ao menos um `test_*.py` |
| PO-K04 | cockpit | 1 | Quem julga a suíte não é o pytest, e o router é lintado | `tools/gate_veredito.py` e `tools/lint_routers.py` existem, e algum workflow cita os dois |
| PO-P01 | app | 0,5 | Variáveis de ambiente documentadas sem valor | `.env.example` existe |
| PO-P02 | app | 1 | Tipo, teste e build são travas do CI | algum workflow tem passo com `tsc`, com `vitest`/`jest`/`pytest` e com `build` |
| PO-S01 | skills | 1 | O repo é instalável como plugin | `.claude-plugin/marketplace.json` é JSON válido com a lista `plugins` não vazia |
| PO-S02 | skills | 1 | Cada plugin se identifica e versiona | cada `source` listado tem `.claude-plugin/plugin.json` com `name` e `version` |
| PO-S03 | skills | 1 | Toda skill declara o que é e que forma tem | todo `SKILL.md` tem frontmatter com `name` igual ao nome da pasta, `description` e `formato` |

**Aviso (peso 0, não reprova):** PO-F03 — caminho versionado com mais de 100 caracteres. O auditor imprime o mais longo; `git worktree add` no Windows quebra com caminho longo.

**Pesos:** 1 = a falta muda como o agente trabalha ou expõe segredo; 0,5 = a falta degrada; 0,25 = higiene. Soma aplicável: cockpit 14,0 · app 12,5 · skills 14,0.

---

## Orientativo, não medido

O que a documentação oficial recomenda e a experiência confirma, mas que não se prova por máquina sem falso positivo. Entra no template e na revisão humana, não no placar.

- **`CLAUDE.md` passa no teste da linha:** "remover isto faria o agente errar?" Se não, sai. Arquivo inchado faz o agente ignorar as instruções reais.
- **Instruções descrevem o que não se lê do código:** comandos, convenções que divergem do default, etiqueta do repo, gotchas. Nunca descrição arquivo a arquivo.
- **Conhecimento de domínio vive em skills** (progressive disclosure em três níveis), nunca no `CLAUDE.md`.
- **Todo trabalho de agente termina com evidência executável**, não com "pronto": saída de teste, hash de commit, id de run.
- **Hooks para o inegociável, texto para o orientativo:** instrução é consultiva, hook é determinístico.
- **Todo loop tem teto de iterações e detector de estagnação** (3 por default). Estourou = falha explícita, nunca "tenta de novo".
- **Grafo antes de código:** automação nova nasce com o fluxo desenhado (cadeia por default), formato declarado e dependências reais testadas.
- **Memória do agente fora do repo compartilhado**, ligada por junction/symlink por máquina, e nunca com lock ou PID versionado.
- **Revisão adversarial em sessão separada** para entrega importante: quem escreveu não revisa.
- **Sem `IMPORTANT` em toda linha:** se tudo grita, nada se destaca.

---

## Fontes

Condensado da pesquisa de 30/08/2026 registrada no plano do padrão ouro: documentação oficial do Claude Code (best practices, memory, plugins, skills, hooks), [agents.md](https://agents.md/), [agentskills.io](https://agentskills.io/), GitHub Spec Kit, HumanLayer (ACE-FCA e 12-factor-agents), e as decisões AD-007, AD-008 e AD-009 do `.specs/STATE.md`.

## Versão

- **v1 — 02/09/2026.** Primeira norma medível. Auditor de referência: `tools/padrao_ouro_audit.py`.
- **v1.1 — 05/09/2026.** PO-C01 deixa de aceitar "existe um arquivo de workflow": passa a exigir gatilho `push` ou `pull_request` (um workflow só com `workflow_dispatch` é verificação que depende de alguém lembrar de disparar) e, junto, o hook `.githooks/pre-push` versionado — a primeira linha roda antes do push, o CI de PR é a rede. Motivo: uma versão do template trocou os gatilhos por `workflow_dispatch` para poupar minutos e reescreveu a régua para não ser punida; a régua não afrouxa para acomodar o custo, o modelo muda. `--versao` imprime `1.1`.
