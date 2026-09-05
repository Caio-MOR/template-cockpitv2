---
description: Roda os gates mecânicos do repo (veredito da suíte + lint de routers) e reporta com evidência
allowed-tools: Bash
---

Rode os dois gates mecânicos do repo e reporte o resultado com evidência (contagens e exit codes), nunca só a afirmação de "passou":

Use o interpretador canônico da máquina, não `python3` solto: `.venv/Scripts/python.exe` no Windows, `.venv/bin/python` no Mac/Linux (abaixo, `PY` = esse caminho).

1. **Veredito dos gates:** `PY tools/gate_veredito.py` — roda a guarda de conteúdo (AST do `conftest.py` e dos arquivos de gate), o canário e a suíte, cada um em subprocesso de ambiente limpo. É também o comando do fallback hospedado manual. Rodar `PY -m pytest -q` direto **não substitui** o veredito: quem julga a suíte não pode ser o próprio pytest (com um hook de resultado no `conftest.py` da raiz, o pytest devolve exit 0 com veneno ativo).
2. **Lint de routers:** `PY tools/lint_routers.py`.

Sem `.venv` na máquina (erro de coleta é o sintoma): a receita de criação por sistema operacional está no `README.md`, seção "Como rodar (ambiente)".

Se algum gate falhar, mostre a saída da falha e diagnostique a causa antes de propor conserto. O verde local é evidência da execução local; o fallback hospedado só existe quando o dono escolhe dispará-lo.
