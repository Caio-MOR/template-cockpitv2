---
paths:
  - "workflows/**"
  - "tools/**"
  - ".agents/skills/**"
---

# Padrão de Logging

Todo script automatizado escreve em `logs/log.txt` (na pasta da própria rotina) no formato TSV: `TIMESTAMP\tETAPA\tSTATUS\tDETALHE`. Status possíveis: `OK`, `ERRO`, `WARN`, `START`, `DONE`. Um formato só, em todas as rotinas, é o que permite um leitor consolidado (dashboard, vigia) ler todos os logs sem parser por script.

**O motivo da reprovação vai no log, não no stdout.** Quando um script tem portão de aceite (testes de integridade, validação, conferência) que impede a publicação de um artefato, o `detalhe` do `ERRO` precisa dizer **qual** checagem quebrou. Os wrappers `.bat`/`.vbs` das tasks agendadas não capturam stdout: relatório impresso na tela morre com o processo e sobra um "falhou" que não diz o que conferir.
