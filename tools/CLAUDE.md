# Tools — router

8 scripts Python na raiz desta pasta, mais o par de canários. Só `eval_runner.py` usa PyYAML; os controles críticos rodam com a stdlib.

- `padrao_ouro_audit.py` — auditor do padrão ouro: mede este repo (ou qualquer outro) contra a norma, por tipo (`cockpit`, `app`, `skills`), e devolve placar 0–10 com as reprovações em `id  arquivo:linha  motivo`. `--template` libera os placeholders `{{...}}`; `--versao` imprime a versão da norma. Gate em `tests/test_padrao_ouro.py`.
- `gate_veredito.py` — o veredito dos gates (guarda de conteúdo por AST + canário + suíte, cada um em subprocesso). É o comando do CI; `pytest -q` direto não o substitui.
- `lint_routers.py` — lint de routers: referências de todo `CLAUDE.md` (e `AGENTS.md`/`README.md` da raiz) contra o índice git, cobertura reversa de `workflows/` e desta pasta.
- `eval_runner.py` — runner de bolso para evals de comportamento (formato oficial de `claude plugin eval`, early access ainda fechado): lê `evals/_exemplo-skill/positivo-modelo-minimo/prompt.md` (uma pasta por skill, uma subpasta por caso) + `graders/`, roda via `claude -p --skills-dir .claude/skills`, isolando a skill sob teste num `.claude/skills/` temporário. Gate estrutural (sem LLM) em `tests/test_evals_estrutura.py`; parser e graders em `tests/test_eval_runner.py`; execução real é gate local, não CI.
- `policy_check.py` — gate vendor-neutral que varre o índice Git em busca de `.env` rastreado e padrões de segredo; não imprime valores. Gate em `tests/test_policy_check.py`.
- `doctor.py` — diagnóstico local de Python, Git, política e contrato de nomes em `.env.example`; nunca devolve valores. Gate em `tests/test_doctor.py`.
- `cockpit_runtime.py` — primitivas sem fornecedor para configuração tipada, redaction, lock/idempotência, retry limitado, evidência atômica e verificação de backup/restore. Gates em `tests/test_cockpit_runtime.py` e `tests/test_rotina_exemplo_runtime.py`.
- `operational_audit.py` — auditor determinístico dos dez contratos operacionais; saída humana ou JSON, com controles remotos separados. Gate em `tests/test_operational_audit.py`.
- `canario_gate/` — instrumento do veredito, não teste da suíte: `canario_vermelho.py` tem que reprovar e `canario_verde.py` tem que passar (nome fora do padrão de arquivo de teste, de propósito).

Ao adicionar um script aqui: uma linha nesta lista e a contagem acima atualizada — o lint reprova o esquecimento.
