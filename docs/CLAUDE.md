# Docs — router

Referências duráveis do cockpit: handoffs de frentes encerradas, dossiês, specs de design, runbooks de máquina. Cada documento novo ganha uma linha aqui dizendo o que é e quando consultar. Doc de projeto que tem repo próprio vive no repo dele, não aqui.

- `padrao-ouro/PADRAO.md` — a norma do padrão ouro (v1.1): exigências medíveis por tipo de repo (cockpit, app, skills), pesos e fórmula do placar. É o texto que `tools/padrao_ouro_audit.py` implementa; mudar a norma é mudar o auditor no mesmo commit.
- `OPERATIONS.md` — contrato operacional: runtime, configuração, credenciais, classificação de dados, backup/restore, resposta a incidentes e cadência de manutenção.
- `THREAT_MODEL.md` — ativos, fronteiras de confiança, ameaças, controles e restrições aceitas desta instância privada.
