"""O template passa na própria régua — e o repo instanciado a partir dele também.

`tools/padrao_ouro_audit.py` implementa a norma do padrão ouro (exigências com id, peso
e check mecânico). Este teste roda o auditor sobre a raiz deste repo em modo template
(placeholders `{{...}}` permitidos) e exige placar >= 9. Depois de instanciar e trocar os
placeholders, rode sem `--template`: o mesmo número tem que sair.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools import padrao_ouro_audit as auditor

RAIZ = Path(__file__).resolve().parents[1]
AUDITOR = RAIZ / "tools" / "padrao_ouro_audit.py"
TETO = 120


def _rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(AUDITOR), *args], capture_output=True,
                          text=True, encoding="utf-8", timeout=TETO, check=False)


def test_auditor_da_placar_minimo_9_no_template():
    r = _rodar("--tipo", "cockpit", "--template", str(RAIZ))
    primeira = r.stdout.splitlines()[0] if r.stdout else ""
    assert primeira.startswith("placar: "), r.stdout + r.stderr
    placar = float(primeira.split("placar: ")[1].split("/")[0])
    assert placar >= 9.0, r.stdout


def test_auditor_sai_com_zero_no_template():
    r = _rodar("--tipo", "cockpit", "--template", str(RAIZ))
    assert r.returncode == 0, r.stdout + r.stderr


def test_tipo_e_lido_do_agents_md_sem_flag():
    r = _rodar("--template", str(RAIZ))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "(tipo cockpit," in r.stdout


# ---------------------------------------------------------------- PO-C01 (sintético)
# A norma v1.1 exige gatilho automático E hook pre-push versionado. Os testes abaixo
# montam repos de brinquedo para provar que cada metade reprova sozinha — a v2 do
# template tinha trocado tudo para `workflow_dispatch` e reescrito a régua para não
# ser punida; é exatamente esse afrouxamento que estes testes impedem de voltar.

WF_DISPATCH = "name: t\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs: {}\n"
WF_PR = "name: t\non:\n  pull_request:\npermissions:\n  contents: read\njobs: {}\n"
HOOK = "#!/bin/sh\nexit 0\n"


def _repo(textos: dict[str, str]) -> auditor.Repo:
    return auditor.Repo(raiz=RAIZ, arquivos=sorted(textos), avisos=[], _textos=dict(textos))


def test_gatilhos_do_workflow_le_as_tres_grafias():
    assert auditor.gatilhos_do_workflow("on: push\n") == {"push"}
    assert auditor.gatilhos_do_workflow("on: [push, pull_request]\n") == {"push", "pull_request"}
    bloco = "name: x\non:\n  pull_request:\n    paths-ignore:\n      - '**.md'\n  push:\n    branches: [main]\npermissions:\n  contents: read\n"
    assert auditor.gatilhos_do_workflow(bloco) == {"pull_request", "push"}
    assert auditor.gatilhos_do_workflow(WF_DISPATCH) == {"workflow_dispatch"}
    assert auditor.gatilhos_do_workflow("name: x\njobs: {}\n") == set()


def test_c01_reprova_workflow_so_com_workflow_dispatch():
    repo = _repo({".github/workflows/tests.yml": WF_DISPATCH, ".githooks/pre-push": HOOK})
    motivos = [r.motivo for r in auditor.chk_c01(repo, "cockpit", True)]
    assert any("workflow_dispatch" in m for m in motivos), motivos


def test_c01_reprova_sem_hook_pre_push_mesmo_com_ci_automatico():
    repo = _repo({".github/workflows/tests.yml": WF_PR})
    reps = auditor.chk_c01(repo, "cockpit", True)
    assert [r.arquivo for r in reps] == [".githooks/pre-push"], reps


def test_c01_aprova_com_gatilho_automatico_e_hook():
    repo = _repo({".github/workflows/tests.yml": WF_PR, ".githooks/pre-push": HOOK})
    assert auditor.chk_c01(repo, "cockpit", True) == []


def test_c03_e_k04_medem_workflows_nao_o_readme():
    """Voltar a medir o README seria aceitar texto como prova de execução."""
    so_readme = _repo({"README.md": "GITLEAKS detect gate_veredito.py lint_routers.py",
                       ".github/workflows/t.yml": WF_PR})
    assert auditor.chk_c03(so_readme, "cockpit", True), "gitleaks só no README passou"
    assert auditor.chk_k04(so_readme, "cockpit", True), "gates só no README passaram"
    no_ci = _repo({".github/workflows/t.yml": WF_PR + "# gitleaks gate_veredito.py lint_routers.py\n",
                   "tools/gate_veredito.py": "", "tools/lint_routers.py": ""})
    assert auditor.chk_c03(no_ci, "cockpit", True) == []
    assert auditor.chk_k04(no_ci, "cockpit", True) == []


def test_versao_da_norma_e_1_1():
    r = _rodar("--versao")
    assert r.stdout.strip() == "1.1", r.stdout
