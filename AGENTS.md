# {{NOME_DO_REPO}} — Instruções para Agentes

tipo: cockpit

Arquivo único de instrução deste repositório, no formato aberto [agents.md](https://agents.md/). Codex, Cursor e Grok Build leem este arquivo direto; o Claude Code chega por `CLAUDE.md`, que só o importa. Edite AQUI, nunca duplique lá.

## Cobertura por agente

O que cada agente carrega sozinho. O que ele não carrega, você alcança pelo caminho citado no router abaixo — leia à mão antes de agir.

| Peça | Claude Code | Codex | Cursor | Grok Build |
|---|---|---|---|---|
| Este arquivo | por `CLAUDE.md` | nativo | nativo | nativo |
| Skills (fonte em `.agents/skills/`) | pelo espelho `.claude/skills/` | nativo | nativo | pelo espelho `.grok/skills/` |
| Regras de `.claude/rules/` | carregadas na abertura | não carrega | não carrega | carregadas |
| Sub-agente `.claude/agents/verificador.md` e commands `.claude/commands/` | sim | não carrega | não carrega | não carrega |
| Hooks de `.claude/settings.json` (enforcement em runtime) | sim | não carrega | não carrega | não carrega |

Os gates de `.githooks/` e de `.github/workflows/` valem para todo mundo: é onde a verificação não depende de vendor. Quem não carrega hook não tem guarda em runtime — a disciplina escrita aqui é a única que lhe resta. O que cada agente não recebe, por que, e o que seria preciso: `docs/COBERTURA-VENDOR.md`.

## Arquitetura WAT (Workflows, Agents, Tools)

- **Workflows** — SOPs em Markdown em `workflows/`, uma pasta por rotina. Cada `workflow.md` define objetivo, inputs, outputs, tratamento de erros, grafo do fluxo e freios.
- **Agents** — o seu papel: ler o workflow, executar as tools na sequência certa, tratar falhas com elegância, perguntar quando necessário.
- **Tools** — scripts Python em `tools/` que fazem o trabalho (APIs, transformações, arquivos, banco). Credenciais em `.env`, nunca no código.

## Estrutura de Diretórios (router)

Categorias com conteúdo variável têm router local (`CLAUDE.md` dentro da pasta — o Claude Code o carrega ao trabalhar em arquivos dela; outros agentes devem lê-lo antes de mexer). Este é o mapa de topo — **todo destino versionado aparece aqui**:

| Procurando... | Vá para |
|---|---|
| Rotina/automação agendada (SOP, grafo, scripts, logs) | `workflows/` (router lá; `_exemplo-rotina/` é o modelo a copiar) |
| Skill (instrução sob demanda) | `.agents/skills/` é a **fonte**; `.claude/skills/` e `.grok/skills/` são espelhos gerados por `tools/sync_skills.py` — nunca edite um espelho, o hook nega |
| Eval de comportamento de uma skill (prova de que ela dispara/fica quieta) | `evals/_exemplo-skill/` (formato oficial de `claude plugin eval`: `prompt.md` + `graders/`), rodado por `tools/eval_runner.py --skills-dir .agents/skills`; `_exemplo-skill` é o modelo a copiar |
| Script reutilizável (cliente de API, parser, gate) | `tools/` (router lá) |
| App web solto (protótipo/utilitário) | `apps/` — uma pasta por app (router lá; nasce vazia — app com usuários e publicação própria vira repositório próprio na organização, e aqui fica só esta linha) |
| Referência durável, handoff, dossiê, spec de design | `docs/` (router lá: `docs/CLAUDE.md`); operação em `docs/OPERATIONS.md`, ameaças em `docs/THREAT_MODEL.md`, régua de qualidade de repositório em `docs/padrao-ouro/PADRAO.md` |
| Teste automatizado (gates, tools, sensores) | `tests/` — um arquivo por gate ou tool; configuração em `pytest.ini` + `conftest.py` na raiz |
| Spec de feature em andamento e log de decisões | `.specs/` — `STATE.md` (decisões AD-nnn + handoff), `LESSONS.md`, uma pasta por feature quando houver |
| Regras carregadas na abertura da sessão | `.claude/rules/` — `como-operar.md`, `conduta-colaborador.md`, `delegacao-barata.md`, `estrutura-e-logging.md`, `graph-engineering.md`, `loop-engineering.md` |
| Sub-agente, commands e hooks | `.claude/agents/verificador.md` (verificação independente), `.claude/commands/gates.md` e `.claude/commands/verificar.md`, `.claude/hooks/` (guarda de bash, de segredo e de espelho — enforcement em runtime), `.claude/settings.json` (`permissions` + hooks; também registra o marketplace de plugins de processo, caio-mor) |
| Política de segurança e divulgação | `SECURITY.md` |
| Gates antes do push e rede por PR | `.githooks/pre-push` e `.githooks/pre-commit` (hooks versionados; ativar com `git config core.hooksPath .githooks`), `.github/workflows/` (`tests.yml` e `gitleaks.yml` em `pull_request`; `tests-macos.yml` e `security.yml` sob demanda) — mesmos gates nos dois; comandos e evidência no `README.md` |
| Configuração de gate e de ambiente | `conftest.py` (réguas da suíte), `pytest.ini`, `requirements.txt`, `.python-version` (3.12.13), `.codex/config.example.toml` (perfil Codex opcional), `.gitignore` (allowlist nega-tudo), `.gitattributes`, `LICENSE`, `.mcp.json`, `.pre-commit-config.yaml` |
| Instruções para agentes e porta de entrada humana | `AGENTS.md` (fonte única), `CLAUDE.md` (importa este), `README.md` (humanos) |

**Escopo por máquina:** o git versiona só o esqueleto (gitignore em allowlist). Logs, dados de rotina e `.env` vivem na máquina e podem não existir num clone — conferir antes de concluir que algo sumiu.

**Regra do router:** mudou o conteúdo de uma categoria, atualize o router dela na mesma sessão — router desatualizado é pior que nenhum. O lint de routers reprova referência morta e pasta/script sem menção.

## Hard Rules (disciplina inegociável)

1. **Pense antes de codar.** Explicite suposições; em caso de ambiguidade, **pergunte em vez de assumir**. Nunca escolha silenciosamente uma interpretação e siga com ela.
2. **Simplicidade primeiro.** Resolva exatamente o que foi pedido. Nada de over-engineering ou abstração "à prova de futuro" quando o pedido é um ajuste pequeno.
3. **Mudanças cirúrgicas.** Nunca modifique arquivos não mencionados na tarefa nem mude formatação/estilo de arquivos intocados. Confirme o escopo antes de editar mais de 3 arquivos. Nunca refatore "de passagem".
4. **Guiado por objetivo + verificação.** Antes de tarefa multi-etapa, declare o plano. Havendo critério verificável (teste, build, script, screenshot), itere até passar e entregue a **evidência** — não a afirmação de "pronto".

## Verificação

- `python tools/gate_veredito.py` — veredito da suíte: guarda de conteúdo (AST do `conftest.py` e dos gates) + canário + suíte, em subprocessos de ambiente limpo. Esperado: `veredito: VERDE`. `pytest -q` direto não substitui: quem julga a suíte não pode ser o próprio pytest.
- `python tools/lint_routers.py` — referências de todo `CLAUDE.md` (e `AGENTS.md`/`README.md`) contra o índice git, mais cobertura reversa de `workflows/` e `tools/`. Esperado: `0 erro(s)`.
- `python tools/sync_skills.py --check` — espelhos de skill idênticos à fonte. Esperado: sem divergência.
- `python tools/eval_runner.py --skills-dir .agents/skills` — evals de comportamento (prova de que uma skill dispara/fica quieta), gate **local** (sem credencial de subscription). `tests/test_evals_estrutura.py` (sem LLM) e `tests/test_criacao_nova.py` integram a suíte local e exigem que toda skill nova venha com uma pasta `evals/` (uma subpasta com o nome da skill, ver `evals/_exemplo-skill/`) (>= 1 positivo + 1 negativo).

Antes de entregar qualquer mudança, execute as verificações locais do `README.md` e cole a saída, não a afirmação. O hook `.githooks/pre-push` roda os mesmos gates antes de todo push (bloqueia se um reprovar); o CI de PR (`.github/workflows/tests.yml`) é a rede e roda os mesmos gates uma vez por pull request. Uma ferramenta ausente ou uma falha deixa a entrega bloqueada, nunca aprovada por suposição.

## Regras globais

- Fale em **{{IDIOMA}}** por padrão.
- Ao encontrar um erro, documente a solução no workflow relevante. Não crie ou sobrescreva workflows sem perguntar.
- **Graph engineering:** toda automação/rotina/skill nova nasce com o grafo do fluxo (Mermaid no `workflow.md`), formato declarado e wait test aplicado — mecânica em `.claude/rules/graph-engineering.md`; gate em `tests/test_criacao_nova.py`.
- **Loop engineering:** todo laço (retry, polling, rotina LLM) declara teto de iterações, detector de estagnação e escreve marker de evidência só após sucesso — `.claude/rules/loop-engineering.md`.
- **Conduta no repositório:** versionamento em branch + PR, tom sem jargão, memória e segredos — `.claude/rules/conduta-colaborador.md`.
- **Como operar:** sessão enxuta, corte por fase, delegação de leitura — `.claude/rules/como-operar.md`; quem executa o quê e com qual modelo — `.claude/rules/delegacao-barata.md`.
- **Estrutura e logging:** formato de log e motivo-no-log — `.claude/rules/estrutura-e-logging.md`.
- Arquivos locais servem para processamento; entregáveis vão para a nuvem (e-mail, banco, planilha compartilhada). `.tmp/` é descartável.
- **Skills de processo** vêm do marketplace `caio-mor` (Caio-MOR/plugins): construir algo novo usa a skill de spec; bug de causa desconhecida usa a de depuração; auditoria de organização usa a de auditoria. Skill de domínio deste repo tem precedência sobre skill de processo.
