#!/usr/bin/env python3
"""Fake de `ruff` para `tests/test_hooks.py` simular `ruff_feedback.py` sem depender
do `ruff` real instalado na máquina. Comportamento por `FAKE_RUFF_MODE`:

  - "achado": imprime uma linha de achado em stdout e sai 1 (ruff acusou erro).
  - "limpo" (default): sem saída, sai 0 (arquivo limpo).
  - "erro_sem_stdout": sai 1 sem nada em stdout (ex.: erro interno do ruff).
  - "timeout": dorme além do teto de teste para forçar `subprocess.TimeoutExpired`.
"""
import os
import sys
import time

MODO = os.environ.get("FAKE_RUFF_MODE", "limpo")

if MODO == "achado":
    print("x.py:1:1: E501 linha longa demais SINTETICO")  # gitleaks:allow
    sys.exit(1)
if MODO == "erro_sem_stdout":
    sys.exit(1)
if MODO == "timeout":
    time.sleep(5)
    sys.exit(0)
sys.exit(0)
