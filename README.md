# {{NOME_DO_REPO}}

{{DESCRICAO}}

Cockpit de automações no framework WAT (Workflows, Agents, Tools): SOPs em Markdown, scripts determinísticos, um agente orquestrando — com gates mecânicos que impedem o repo de mentir sobre o próprio estado. Instruções para agentes em `AGENTS.md`.

## Como rodar (ambiente)

Python is fixed at 3.12.13 (`.python-version`). A root `.venv` is each machine's canonical interpreter; workflow wrappers find it by relative path.

**Windows** (install `uv` first):

```
uv python install 3.12.13
uv venv --managed-python --python 3.12.13 .venv
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements.txt
```

**Mac/Linux** (install `uv` first):

```
uv python install 3.12.13
uv venv .venv --python 3.12.13
uv pip install --require-hashes -r requirements.txt
```

The root `.venv` is the only interpreter for repository commands. In the command list
below, `PY` and `GITLEAKS` are metavariables, not literal shell commands. On Mac/Linux,
run `PY=.venv/bin/python` and then `"$PY" tools/gate_veredito.py`. In PowerShell, run
`$PY = '.venv\Scripts\python.exe'` and then `& $PY tools/gate_veredito.py`. Bind
`GITLEAKS` the same way and invoke it as `"$GITLEAKS" detect ...` on POSIX or
`& $GITLEAKS detect ...` in PowerShell. Do not substitute a system Python, `ruff`,
`pip-audit`, or `bandit` executable.

## Verificar: hook antes do push, CI de PR como rede

O modelo tem três linhas:

1. **O hook bloqueia o push.** `.githooks/pre-push` (versionado) roda os gates na sua máquina antes de todo `git push`; um gate vermelho recusa o push e diz qual. Ativação: `git config core.hooksPath .githooks` (o inicializador faz; `PY tools/doctor.py` reprova o clone que não fez). `git push --no-verify` é a brecha assumida — e o hook do Claude Code a bloqueia para o agente.
2. **O CI de PR é a rede.** `.github/workflows/tests.yml` e `gitleaks.yml` rodam uma vez por pull request, num só runner Linux, com actions pinadas em SHA e binário do gitleaks conferido por checksum. Custo quase zero de minutos: nada dispara em push ou agenda; `tests-macos.yml` e `security.yml` são opcionais, sob demanda (`workflow_dispatch`).
3. **Os gates são os mesmos nos dois.** `tests/test_pre_push_hook.py` mede a paridade; mudou um gate no hook, muda no workflow no mesmo PR.

Os comandos abaixo são o que o hook e o CI executam (mais os de segurança de dependências, que precisam de rede e ficam sob demanda). Rode-os antes de entregar e cole a saída, com commit, SO e versão do Python; ferramenta ausente ou comando vermelho bloqueia a entrega, nunca vira "passou por suposição".

- `PY tools/gate_veredito.py` — esperado `veredito: VERDE` (guarda de conteúdo + canário + suíte).
- `PY tools/lint_routers.py` — esperado `0 erro(s)`.
- `PY tools/doctor.py`, `PY tools/policy_check.py .`, `PY tools/operational_audit.py .`, `PY tools/lint_routers.py` e `PY tools/gate_veredito.py` — os cinco gates locais; todos precisam passar.
- `PY tools/padrao_ouro_audit.py --tipo cockpit .` — auditor do padrão ouro: placar 0–10 e a lista do que falta, com arquivo e linha. No template ele roda com `--template` (placeholders permitidos); no repo instanciado, sem a flag. Está no padrão quem mede 9 ou mais.
- `PY -m ruff check .` — style gate.
- `PY -m pip_audit --strict --progress-spinner off` — dependency vulnerability audit.
- `PY -m bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows` — static security analysis.
- `GITLEAKS detect --source . --no-banner --redact --verbose` — full-history secret scan. `GITLEAKS` must name a checksum-verified v8.30.1 binary, never an arbitrary installed tool. On Linux x64, use the exact archive and SHA-256 from `.github/workflows/gitleaks.yml`; on another platform, download the matching v8.30.1 archive and its official `gitleaks_8.30.1_checksums.txt` (fora do git), verify the archive checksum before extracting it, then set `GITLEAKS` to the extracted executable.

Secret scanning nativo do GitHub, push protection e alertas do Dependabot são controles separados do GitHub e não consomem minutos de Actions.

## O que é cada peça e por quê

- `AGENTS.md` — fonte única de instruções, multi-vendor: um arquivo que todo agente lê, em vez de um por ferramenta.
- `CLAUDE.md` — só importa o `AGENTS.md` e guarda adendos do Claude Code: duplicar instruções é ter duas versões e nenhuma certa.
- `README.md` — porta de entrada humana; o lint confere as referências dele também, porque drift aqui envenena igual.
- `.gitignore` em allowlist — o git versiona o que se libera, não o que se esquece de negar; arquivo novo nunca entra por acidente.
- `.gitattributes` — LF no repo, nativo na máquina; `.bat`/`.vbs` em CRLF porque o interpretador do Windows exige.
- `.python-version` / `requirements.txt` — máquina local, hook e CI usam a mesma versão exata de Python e o mesmo lock com hashes.
- `pytest.ini` / `conftest.py` — réguas da suíte fora de `tests/`: guarda que mora dentro do que vigia some junto.
- `tools/` — scripts determinísticos com router próprio; o veredito e o lint moram aqui porque são ferramentas, não testes.
- `tests/` — um arquivo por gate; cada gate tem teste sintético que prova que ele REPROVA, não só que passa.
- `workflows/` — uma pasta por rotina (SOP + grafo + scripts + logs locais); `_exemplo-rotina/` é o modelo com freios e marker de evidência.
- `docs/` — referência durável com router; começa vazia de propósito.
- `.specs/` — decisões (`STATE.md`) e lições (`LESSONS.md`) versionadas: o porquê é o que a próxima sessão não reconstrói sozinha.
- `.claude/` — rules que carregam na sessão, sub-agente verificador (autor ≠ verificador), commands de gate e hooks de aviso de compactação.
- `.githooks/` — hook `pre-push` versionado: a primeira linha dos gates, na máquina de quem empurra (`git config core.hooksPath .githooks` liga; `tools/doctor.py` confere).
- `.github/` — a rede: `tests.yml` e `gitleaks.yml` por pull request com actions pinadas em SHA e binário do gitleaks conferido por checksum; `tests-macos.yml` e `security.yml` sob demanda.

## Memória do agente (opcional)

A memória automática do Claude Code vive **fora do repo**, no diretório de memória da máquina. Se quiser versioná-la, o caminho é ligar esse diretório a uma pasta do repo por junction (Windows) ou symlink (Mac/Linux) — e essa ligação é **escolha por máquina, nunca versionada**: o que entra no git é o conteúdo, não o link. Nunca versione arquivo de lock da memória: lock de uma máquina bloqueia a outra. Se a pasta entrar no git, libere-a explicitamente no `.gitignore` (allowlist) e considere `merge=union` no `.gitattributes` para ela, porque duas máquinas escrevem no mesmo dia.

## Como instanciar

## Bootstrap

The first agent session replaces the declared placeholders, initializes the project
state, and verifies the new repository before project work begins.

```
gh repo create <novo-repo> --template {{DONO}}/template-cockpitv2 --private
```

Depois, no clone novo, é o **agente** quem executa este checklist ao abrir a primeira sessão — o humano só decide nome, descrição e idioma:

1. Ask for the project name, short description, default language, GitHub owner, and the template owner. Replace only the declared instance placeholders in `AGENTS.md` (`{{NOME_DO_REPO}}`, `{{IDIOMA}}`), `README.md` (`{{NOME_DO_REPO}}`, `{{DESCRICAO}}`, `{{DONO}}`), and `.github/CODEOWNERS` (`{{GITHUB_OWNER}}`). Do not perform a repository-wide placeholder replacement: code and tests may contain deliberate template-like strings. <!-- padrao-ouro:ignorar -->
2. Criar o `.venv` conforme a seção "Como rodar" acima.
3. If using Codex subagents, copy `.codex/config.example.toml` to `.codex/config.toml` (local, fora do git); otherwise leave the example untouched.
4. With the canonical `PY` binding above, execute `PY tools/initialize_template.py --dry-run .`, review the list, then execute `PY tools/initialize_template.py .` — além de limpar os registros de build do template, isso ativa o hook `pre-push` (`git config core.hooksPath .githooks`); `PY tools/doctor.py` confirma.
5. Rodar os cinco gates e o auditor do padrão ouro **sem** `--template` (a instância real não tem mais placeholder para desculpar; o hook e o CI já trocam de modo sozinhos ao sumir o placeholder do `AGENTS.md`).
6. Instalar as skills de processo do marketplace `caio-mor` (já registrado em `.claude/settings.json`, mas registro não instala sozinho — cada plugin precisa de comando explícito):
   ```
   claude plugin install tlc-spec-driven@caio-mor
   claude plugin install systematic-debugging@caio-mor
   claude plugin install os-audit@caio-mor
   ```
   Conferir com `claude plugin list` e colar a saída na entrega.
7. Primeiro commit em branch + PR: o hook roda os gates no push, o CI de PR repete como rede. Cole a saída dos comandos acima (commit, SO, versão do Python) na entrega; comando ausente ou vermelho não vira "passou".

## O que o Claude Code bloqueia sozinho neste repo

As regras acima (segredo só em `.env`, nunca commit direto na `main`) deixaram de ser só texto: `.claude/settings.json` tem `permissions.deny`/`allow` e dois hooks `PreToolUse` em `.claude/hooks/` que mordem de verdade, em qualquer SO com Git Bash.

- **`guarda_bash.py`** (todo comando `Bash`): bloqueia `git commit` direto em `main`/`master`, `git push --force`/`-f`/`--force-with-lease`, qualquer `--no-verify` e `git push` com destino explícito `main`/`master`.
- **`guarda_segredo.py`** (todo `Edit`/`Write`/`MultiEdit`): bloqueia escrita em `.env` e em qualquer variante `.env.algo` (exceto `.env.example`) e conteúdo que casa com padrão de chave/segredo conhecido (AWS, GitHub, chave privada, JWT, Supabase, `x-api-key`).

Both hooks fail closed. The interpreter wrapper (`.claude/hooks/run_hook.sh`) selects the repository `.venv` before falling back to system `python3` or `python`. `tests/test_hooks.py` proves the block and pass paths locally; run the full contract on each operating system the owner chooses to support.

---

Criado por Caio Kohn
