# Workflows — router

Uma pasta por rotina, autocontida: `workflow.md` (SOP + grafo Mermaid com `%% formato:` declarado), `scripts/` (o que executa) e `logs/` (evidência estruturada, markers e log humano — fora do git; só o `.gitkeep` é versionado). **Antes de mexer em qualquer uma, leia o `workflow.md` da pasta.** O gate `tests/test_criacao_nova.py` reprova pasta nova sem `workflow.md`, sem bloco mermaid ou sem formato.

| Workflow | O que é | Gatilho |
|---|---|---|
| `_exemplo-rotina/` | Rotina-modelo executável: SOP, grafo cadeia, lock/idempotência, retry com prazo, evidência atômica/redigida e wrappers (`.py`, `.bat`, `.vbs`). Copiar e renomear para criar uma rotina nova | Manual (exemplo) |

Agendamentos ao vivo ficam no agendador da máquina (Task Scheduler, cron, launchd), nunca só neste arquivo.
