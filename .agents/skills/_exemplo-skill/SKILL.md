---
name: _exemplo-skill
description: Use quando precisar de um modelo mínimo para começar uma skill nova neste repositório.
---

formato: cadeia — três passos em sequência, cada um consome o resultado do anterior; skill trivial não precisa de grafo próprio

<!-- Copie esta pasta, renomeie (a pasta e o `name:` acima têm que ficar iguais) e troque o conteúdo abaixo. -->

## Objetivo

<!-- Uma frase: que problema esta skill resolve e quando ela dispara. -->
Modelo mínimo que passa no gate de criação nova (`tests/test_criacao_nova.py`):
frontmatter completo, formato declarado, sem referência morta.

## Passos

<!-- Troque pelos passos reais da sua skill. -->
1. Leia o que a tarefa pede e confirme o objetivo antes de agir.
2. Execute os passos determinísticos (scripts, tools, chamadas) na ordem certa.
3. Trate erro com elegância: mensagem clara, sem seguir adiante com dado ruim.

## Verificação / Saída

<!-- O que prova que a skill funcionou: um teste, um arquivo gerado, um resumo. -->
Descreva aqui o critério verificável desta skill (comando, arquivo esperado ou
saída) e o que o agente entrega ao usuário ao final.
