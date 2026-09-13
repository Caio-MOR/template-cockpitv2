# Validacao independente -- harness-score-108

**Veredito: PASS COM RESSALVAS**

Verificador: sessao separada do autor. Range auditado: e71b9d9..HEAD (7 commits, HEAD=4be8bbe).
Maquina: Windows 10, .venv do proprio repo, PowerShell/Git Bash.

## 1. Score real

npx --yes harness-score executado na raiz reproduziu 108/108 (100%), 36/36 checks, L4,
identico a .specs/features/harness-score-108/harness-score-depois.txt. Sem divergencia.

## 2. Gates

| Gate | Comando | Resultado |
| --- | --- | --- |
| pytest | .venv/Scripts/python.exe -m pytest -q | 265 passed, 2 skipped in 67.59s |
| lint_routers | python tools/lint_routers.py | lint_routers: 0 erro(s) em 7 arquivo(s) verificados |
| gate_veredito | python tools/gate_veredito.py | veredito: VERDE (canarios vermelho/verde OK) |
| ruff | python -m ruff check . | All checks passed! |
| mypy | python -m mypy | Success: no issues found in 29 source files |

Coleta real (pytest --collect-only -q) = 267 tests collected, batendo COLETA_MEDIDA=267 em conftest.py:20.

## 3. Integridade dos testes (e71b9d9..HEAD em tests/, conftest.py, pytest.ini)

Nenhuma assercao removida/afrouxada, nenhum xfail/skip novo, nenhum GATES_OBRIGATORIOS reduzido (so
cresceu: tests/test_pre_commit_hook.py: 9 foi adicionado). PISO_COLETA 120 para 133 e COLETA_MEDIDA 241
para 267: li tests/test_criacao_nova.py:469-490 (test_coleta_medida_e_piso_batem_com_a_coleta_real) -- o
teste exige PISO_COLETA == real // 2; com 267 testes reais coletados, o unico valor que passa e 133. A
mudanca e imposta pelo proprio teste (consequencia de 26 testes novos terem entrado na suite), nao ajuste
de conveniencia. Diffs revisados em tests/test_criacao_nova.py, tests/test_lint_routers.py,
tests/test_pre_push_hook.py, tests/test_rotina_exemplo_runtime.py: so anotacoes de tipo (para o mypy) e
fixtures novas (pyproject.toml neutro para o mypy no repo sintetico). Nada enfraquecido.

## 4. Hooks -- execucao real

- 4a ruff_feedback.py -- testado via stdin com JSON real apontando para arquivo .py com erro criado no
  scratchpad: devolveu hookSpecificOutput.additionalContext com o achado do ruff, exit 0. Arquivo limpo:
  sem saida, exit 0. JSON invalido, file_path ausente, caminho fora do projeto: exit 0 silencioso nos tres
  casos. Achado de metodologia (nao do hook): a primeira tentativa usou caminho estilo Git-Bash
  (/c/Users/...) dentro da string JSON, que o hook (corretamente) tratou como fora do projeto -- nao e bug,
  e o hook funcionando; refeito com caminho Windows real confirmou os 5 ramos.
- 4b run_hook.sh -- nome fora da allowlist (nome_malicioso.py) recusado com exit 2 e mensagem
  "script de hook nao permitido"; nome permitido (ruff_feedback.py) executa normalmente.
- 4c .githooks/pre-commit -- clone isolado (git clone para o scratchpad, core.hooksPath=.githooks),
  com COCKPIT_PYTHON apontando para o .venv real do repo (so assim o ruff esta disponivel -- um clone
  novo sem .venv degrada e deixa passar, comportamento tambem correto e documentado). Arquivo .py sujo
  staged: commit BLOQUEADO (BLOQUEADO pelo gate: lint de estilo dos arquivos staged (ruff), exit 1).
  Arquivo limpo: commit passa.
- 4d scripts de contexto -- comparacao programatica do texto extraido de
  git show e71b9d9:.claude/settings.json (echo inline) contra a constante TEXTO de
  precompact_contexto.py e sessionstart_contexto.py: match exato, byte a byte, incluindo acentuacao.
  Nota lateral, sem impacto funcional: rodar os scripts via run_hook.sh no Windows produz \r\n no stdout
  por causa do modo texto do print(); o conteudo textual e identico, so o terminador de linha muda --
  irrelevante para JSON/texto lido por hook.

## 5. Sensor de discriminacao (mutacao) -- scratch isolado (clone git no scratchpad, nunca git stash)

| Mutante | Resultado | Evidencia |
| --- | --- | --- |
| ruff_feedback.py: remover except Exception (propaga excecao em vez de degradar) | MORTO | 3 testes falharam: test_ruff_feedback_ruff_ausente_degrada_em_silencio, test_ruff_feedback_timeout_degrada_em_silencio, test_ruff_feedback_json_invalido_no_stdin_degrada_em_silencio |
| run_hook.sh: allowlist trocada por aceita-tudo | SOBREVIVEU | pytest -q tests/test_hooks.py -> 66 passed (nenhuma falha) |
| .githooks/pre-commit: falhou zerado antes do bloco de bloqueio (sai 0 mesmo reprovando) | MORTO | 2 testes falharam: test_commit_bloqueado_com_arquivo_py_sujo_staged, test_commit_bloqueado_quando_policy_check_reprova |
| sessionstart_contexto.py: trocar TEXTO por string diferente | MORTO | test_sessionstart_contexto_emite_o_texto_exato falhou |

3 mortos / 1 sobrevivente. Ao terminar: git status --short do repo real limpo e HEAD =
4be8bbe3be1a95438881ff7cc8d0ce26e135dfac, igual ao ponto de partida (clone de scratch tratado a parte,
ver secao "nao verificado").

### Achado do sensor (grave)

Os dois testes que deveriam matar o mutante do run_hook.sh
(test_run_hook_rejeita_script_fora_da_allowlist, test_run_hook_continua_recusando_nome_desconhecido, em
tests/test_hooks.py:322 e :444) usam nomes que tambem nao existem como arquivo
("../outro.py", "script_inexistente.py"). Com a allowlist inteiramente removida, o run_hook.sh tenta
executar o Python sobre um caminho que nao existe, e o Python falha com erro de arquivo nao encontrado --
que tambem sai com codigo 2, coincidindo por acaso com o codigo de recusa da allowlist (exit 2 em
run_hook.sh:14). O teste checa so r.returncode == 2, nao a mensagem de stderr (script de hook nao
permitido) nem usa um nome que exista de fato fora da allowlist. Resultado: a suite nao pega a allowlist
sendo removida -- ela pega, sem querer, arquivo inexistente, que e um evento diferente. Isso e lacuna de
teste, nao bug do run_hook.sh em producao (o run_hook.sh real, nao mutado, continua correto e foi
confirmado manualmente no item 4b).

## 6. Teatro de metrica

| Artefato | Funcao mecanica real? |
| --- | --- |
| LICENSE | Sim -- texto MIT completo, sem placeholder, satisfaz HYG-05 e e declaracao legal real |
| .mcp.json (mcpServers vazio) | Fraco, como a spec admite. Objeto vazio; funcao real limitada a declarar o ponto de extensao e a convencao de credencial (VAR interpolada) documentada no README. Confirma a autoavaliacao da propria spec: e o item mais proximo de presenca de arquivo, ainda que documentado |
| tool.mypy em pyproject.toml | Sim -- mypy roda de verdade (Success: no issues found in 29 source files), integrado a .githooks/pre-push e ao CI |
| .pre-commit-config.yaml | Sim -- invoca o mesmo .githooks/pre-commit, sem duplicar checagem |
| Hook PostToolUse (ruff_feedback.py) | Sim -- testado rodando ruff de verdade e devolvendo achado (item 4a) |
| Scripts de contexto (precompact/sessionstart) | Sim, com ressalva -- texto identico ao inline anterior (item 4d); ganho e versionamento/testabilidade, nao mudanca de comportamento |

## 7. Vazamento

gitleaks detect --source . --log-opts=e71b9d9..HEAD -> "no leaks found" (7 commits, ~135KB escaneados).
Grep por sk-, ghp_, AKIA, BEGIN PRIVATE KEY no diff: sem ocorrencia de segredo real (so a propria lista
de assinaturas citada em tasks.md como requisito de teste).

Achado (leve): caminho de maquina do usuario versionado. .specs/features/harness-score-108/
harness-score-depois.json linha 6 e harness-score-depois.txt linha 2 contem
C:\Users\caio.kohn\Documents\projetos\workshop\template-cockpitv2 -- path absoluto local com nome de
usuario, versionado no indice git. Nao e credencial, mas e o tipo de dado de maquina que o item 7 pediu
para sinalizar.

## Range do diff verificado

e71b9d9..HEAD -- 7 commits: 8ff4dcd, feb5a58, bced062, 6c54485, 287ed4a, 8f4a77e, 4be8bbe.

## Lacunas ranqueadas

1. [Media] Sensor de mutacao nao pega remocao da allowlist do run_hook.sh -- tests/test_hooks.py:322,444
   checam so returncode == 2, que tambem e o codigo de saida do Python para arquivo nao encontrado. Um
   teste que aponte para um nome existente mas fora da allowlist (ou que confira a mensagem de stderr)
   fecharia a lacuna. Achado do sensor de mutacao, nao falha do run_hook.sh em producao.
2. [Baixa] Caminho de maquina do usuario versionado nos dois arquivos de evidencia do harness-score. Sem
   risco de segredo, mas e dado especifico da maquina do dono num artefato que o template pretende ser
   referencia.
3. [Observacao, nao reprovacao] .mcp.json e o item mais fraco, como a propria spec ja diagnostica --
   objeto vazio, funcao real limitada a convencao documentada.

## O que nao foi possivel verificar

- Paridade completa do .githooks/pre-push (T3) nao foi re-executada ponta a ponta nesta sessao (so os 5
  gates individuais do item 2, que e o que a spec pede como Success Criteria); nao ha evidencia propria
  de rodar .githooks/pre-push inteiro nesta verificacao.
- CI real (gh / GitHub Actions) nao foi consultado -- toda a verificacao rodou local, na maquina Windows
  do dono. Nao confirmei o runner self-hosted nem o workflow tests.yml executando de fato em push/PR
  desta feature.
- Descarte do clone de scratch usado no sensor de mutacao: o comando rm -rf foi recusado pelo sistema de
  permissao da sessao; o clone ficou em pasta do scratchpad (fora do repo real, sem afetar git status
  ou HEAD do repo auditado, confirmados limpos). Nao obtive forma de remove-lo dentro das permissoes
  desta sessao.
