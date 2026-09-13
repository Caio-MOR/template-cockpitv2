# Loop Engineering (freios e evidência de execução)

Complemento da regra `graph-engineering.md` — que cuida do **desenho** dos fluxos (formatos, wait test, guardrails de grafo). Esta regra cuida do **runtime** de qualquer laço (retry, espera, polling, rotina LLM) e do contrato de evidência que um vigia externo consome.

## Os três freios (obrigatórios em todo loop)

| Freio | Regra | Ao estourar |
|---|---|---|
| **Teto de iterações** | Todo retry/espera/polling declara nº máximo de tentativas (default 3) OU duração máxima. `while True` sem contador/deadline é proibido. | Falha explícita: `ERRO` no log TSV dizendo em qual iteração parou. Nunca re-tentar além do teto. |
| **Detector de estagnação** | N execuções consecutivas sem progresso mensurável (default 3) = parar, não insistir. Vale entre runs: 3 exceções consecutivas da mesma rotina = a rotina **para** até conserto humano. | Alerta com instrução de parada; conserto humano antes de reativar. |
| **Orçamento por run (rotinas LLM)** | Proxy: teto de tentativas + duração máxima declarados no `SKILL.md`/`workflow.md` (token de subscription não é mensurável por rotina). | Encerrar o run com `ERRO`; a rotina nunca estende o próprio orçamento. |

## Contrato de evidência (o que um vigia externo lê)

- Marker escrito **somente após o sucesso completo da entrega**, contendo a **janela/data coberta** — nunca no início do run, nunca em falha parcial.
- O vigia compara a **janela**, não a existência do arquivo. Marker de semana passada = sem evidência.
- "Rodou e não tinha nada a fazer" **também escreve marker** — silêncio legítimo é diferente de morte.
- Evidência preferencial = marker; `DONE` no log TSV só onde o formato foi verificado.
- Rotina sem evidência legível é adaptada **antes** de entrar na lista de um vigia.

Referências: formatos e guardrails de grafo → `graph-engineering.md`; formato do log TSV e motivo-no-log → `estrutura-e-logging.md`; modelo de rotina com freios e marker → `workflows/_exemplo-rotina/workflow.md`.
