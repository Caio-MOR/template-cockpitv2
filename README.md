# {{NOME_DO_REPO}}

{{DESCRICAO}}

Cockpit de automações no framework WAT (Workflows, Agents, Tools): SOPs em Markdown, scripts determinísticos, um agente orquestrando — com gates mecânicos que impedem o repo de mentir sobre o próprio estado. Instruções para agentes em `AGENTS.md`.

## Como rodar (ambiente)

Python fixado em 3.12 (`.python-version`). Um `.venv` na raiz é o interpretador canônico de cada máquina — os wrappers das rotinas o acham por caminho relativo.

**Windows** (sem `uv`; o launcher `py` resolve):

```
py install 3.12
py -V:3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Mac/Linux** (com `uv`, ou com o Python do sistema):

```
uv venv .venv --python 3.12
uv pip install -r requirements.txt
```

ou `python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.

## Verificar

Os mesmos comandos do CI (`.github/workflows/tests.yml`), rodados com o Python do `.venv`:

- `python tools/gate_veredito.py` — esperado `veredito: VERDE` (guarda de conteúdo + canário + suíte).
- `python tools/lint_routers.py` — esperado `0 erro(s)`.
- `python tools/doctor.py`, `python tools/policy_check.py .`, `python tools/operational_audit.py .`, `python tools/lint_routers.py` e `python tools/gate_veredito.py` — os cinco gates locais; todos precisam passar.
- `python tools/padrao_ouro_audit.py --tipo cockpit .` — auditor do padrão ouro: placar 0–10 e a lista do que falta, com arquivo e linha. No template ele roda com `--template` (placeholders permitidos); no repo instanciado, sem a flag. Está no padrão quem mede 9 ou mais.

## O que é cada peça e por quê

- `AGENTS.md` — fonte única de instruções, multi-vendor: um arquivo que todo agente lê, em vez de um por ferramenta.
- `CLAUDE.md` — só importa o `AGENTS.md` e guarda adendos do Claude Code: duplicar instruções é ter duas versões e nenhuma certa.
- `README.md` — porta de entrada humana; o lint confere as referências dele também, porque drift aqui envenena igual.
- `.gitignore` em allowlist — o git versiona o que se libera, não o que se esquece de negar; arquivo novo nunca entra por acidente.
- `.gitattributes` — LF no repo, nativo na máquina; `.bat`/`.vbs` em CRLF porque o interpretador do Windows exige.
- `.python-version` / `requirements.txt` — CI e máquina limpa instalam o mesmo Python e as mesmas dependências fixadas por major (sem lock, então o patch pode variar).
- `pytest.ini` / `conftest.py` — réguas da suíte fora de `tests/`: guarda que mora dentro do que vigia some junto.
- `tools/` — scripts determinísticos com router próprio; o veredito e o lint moram aqui porque são ferramentas, não testes.
- `tests/` — um arquivo por gate; cada gate tem teste sintético que prova que ele REPROVA, não só que passa.
- `workflows/` — uma pasta por rotina (SOP + grafo + scripts + logs locais); `_exemplo-rotina/` é o modelo com freios e marker de evidência.
- `docs/` — referência durável com router; começa vazia de propósito.
- `.specs/` — decisões (`STATE.md`) e lições (`LESSONS.md`) versionadas: o porquê é o que a próxima sessão não reconstrói sozinha.
- `.claude/` — rules que carregam na sessão, sub-agente verificador (autor ≠ verificador), commands de gate e hooks de aviso de compactação.
- `.github/` — veredito + lint em matriz enxuta (`tests.yml`: ubuntu sempre, +windows só em PR) com macOS verificado semanalmente em `tests-macos.yml` (gate de um SO só é gate presumido) e varredura de segredos com binário pinado por checksum.

## Memória do agente (opcional)

A memória automática do Claude Code vive **fora do repo**, no diretório de memória da máquina. Se quiser versioná-la, o caminho é ligar esse diretório a uma pasta do repo por junction (Windows) ou symlink (Mac/Linux) — e essa ligação é **escolha por máquina, nunca versionada**: o que entra no git é o conteúdo, não o link. Nunca versione arquivo de lock da memória: lock de uma máquina bloqueia a outra. Se a pasta entrar no git, libere-a explicitamente no `.gitignore` (allowlist) e considere `merge=union` no `.gitattributes` para ela, porque duas máquinas escrevem no mesmo dia.

## Como instanciar

## Bootstrap

The first agent session replaces the declared placeholders, initializes the project
state, and verifies the new repository before project work begins.

```
gh repo create <novo-repo> --template {{DONO}}/template-cockpit --private
```

Depois, no clone novo, é o **agente** quem executa este checklist ao abrir a primeira sessão — o humano só decide nome, descrição e idioma:

1. Se houver `{{...}}` em qualquer arquivo do repo, perguntar ao usuário, em linguagem simples (sem jargão técnico), o nome do projeto, uma descrição curta e o idioma padrão — e substituir todas as ocorrências.
2. Criar o `.venv` conforme a seção "Como rodar" acima.
3. Executar `python tools/initialize_template.py --dry-run .`, revisar a lista, e então executar `python tools/initialize_template.py .`.
4. Rodar os cinco gates e o auditor do padrão ouro **sem** `--template` (a instância real não tem mais placeholder para desculpar).
4. Instalar as skills de processo do marketplace `caio-mor` (já registrado em `.claude/settings.json`, mas registro não instala sozinho — cada plugin precisa de comando explícito):
   ```
   claude plugin install tlc-spec-driven@caio-mor
   claude plugin install systematic-debugging@caio-mor
   claude plugin install os-audit@caio-mor
   ```
   Conferir com `claude plugin list` e colar a saída na entrega.
5. Primeiro commit em branch + PR, colando na entrega o veredito `VERDE`, o `0 erro(s)` do lint e o placar do auditor.

## O que o Claude Code bloqueia sozinho neste repo

As regras acima (segredo só em `.env`, nunca commit direto na `main`) deixaram de ser só texto: `.claude/settings.json` tem `permissions.deny`/`allow` e dois hooks `PreToolUse` em `.claude/hooks/` que mordem de verdade, em qualquer SO com Git Bash.

- **`guarda_bash.py`** (todo comando `Bash`): bloqueia `git commit` direto em `main`/`master`, `git push --force`/`-f`/`--force-with-lease`, qualquer `--no-verify` e `git push` com destino explícito `main`/`master`.
- **`guarda_segredo.py`** (todo `Edit`/`Write`/`MultiEdit`): bloqueia escrita em `.env` e em qualquer variante `.env.algo` (exceto `.env.example`) e conteúdo que casa com padrão de chave/segredo conhecido (AWS, GitHub, chave privada, JWT, Supabase, `x-api-key`).

Os dois falham **abertos** por decisão — bug no hook não pode travar quem não sabe depurar hook — e a cascata de interpretador (`.claude/hooks/run_hook.sh`) escolhe `.venv` do repo antes de cair para `python3`/`python` do sistema. A prova de que os hooks mordem (casos que bloqueiam e casos que passam) está em `tests/test_hooks.py`, rodado no CI em Linux e Windows a cada PR (macOS semanal).

---

Criado por Caio Kohn
