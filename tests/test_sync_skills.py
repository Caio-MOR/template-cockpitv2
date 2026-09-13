# -*- coding: utf-8 -*-
"""Testes de `tools/sync_skills.py` — o espelho de `.agents/skills/` (fonte única)
em `.claude/skills/` e `.grok/skills/`.

Laboratório em `tmp_path` com árvores sintéticas: prova cada motivo de divergência
(`faltante`, `órfão`, `divergente`), o modo escrita corrigindo os três, a
idempotência (rodar duas vezes não muda nada na segunda) e a fonte ausente saindo
!= 0 sem criar nada. Um smoke via subprocesso prova que a CLI (`--check`/`--root`)
entrega o mesmo contrato que a função testada diretamente.

`test_repo_real_sem_drift` (T2 — SKL-01) entra neste arquivo só depois de a fonte
real ser migrada para `.agents/skills/`; nasce em commit separado.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "tools" / "sync_skills.py"

spec = importlib.util.spec_from_file_location("sync_skills", SCRIPT)
assert spec is not None and spec.loader is not None, "spec de sync_skills.py não resolveu"
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

# Teto de duração de todo subprocesso deste gate. Freio da regra `loop-engineering`:
# subprocesso sem teto pendura o gate em vez de reprová-lo.
TETO_SUBPROC = 120


def _montar(base: Path, arquivos: dict[str, str]) -> None:
    for rel, texto in arquivos.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")


def _repo_sintetico(
    tmp_path: Path,
    fonte: dict[str, str] | None,
    claude: dict[str, str] | None,
    grok: dict[str, str] | None,
) -> Path:
    """Monta `<tmp_path>/repo` com as três árvores. `None` significa que a pasta
    nem existe (caso "faltante completo" / "fonte ausente")."""
    root = tmp_path / "repo"
    root.mkdir()
    if fonte is not None:
        _montar(root / ".agents" / "skills", fonte)
    if claude is not None:
        _montar(root / ".claude" / "skills", claude)
    if grok is not None:
        _montar(root / ".grok" / "skills", grok)
    return root


def test_espelho_identico_check_sai_zero(tmp_path):
    conteudo = {"exemplo/SKILL.md": "conteudo v1\n"}
    root = _repo_sintetico(tmp_path, conteudo, conteudo, conteudo)

    codigo, linhas = ss.sincronizar(root, check=True)

    assert codigo == 0
    assert any("sem divergência" in linha for linha in linhas), linhas


def test_arquivo_divergente_check_sai_diferente_de_zero_com_motivo(tmp_path):
    root = _repo_sintetico(
        tmp_path,
        {"exemplo/SKILL.md": "conteudo v2\n"},
        {"exemplo/SKILL.md": "conteudo v1\n"},
        {"exemplo/SKILL.md": "conteudo v2\n"},
    )

    codigo, linhas = ss.sincronizar(root, check=True)

    assert codigo != 0
    achados = [linha for linha in linhas if "divergente" in linha and "exemplo/SKILL.md" in linha]
    assert achados, linhas
    # o outro espelho (grok), idêntico, não pode aparecer como divergência
    assert not any(".grok" in linha and "divergente" in linha for linha in linhas), linhas


def test_arquivo_faltante_check_sai_diferente_de_zero_com_motivo(tmp_path):
    root = _repo_sintetico(
        tmp_path,
        {"exemplo/SKILL.md": "conteudo\n"},
        None,  # .claude/skills nem existe
        {"exemplo/SKILL.md": "conteudo\n"},
    )

    codigo, linhas = ss.sincronizar(root, check=True)

    assert codigo != 0
    achados = [linha for linha in linhas if "faltante" in linha and ".claude/skills/exemplo/SKILL.md" in linha]
    assert achados, linhas


def test_pasta_orfa_check_sai_diferente_de_zero_com_motivo(tmp_path):
    root = _repo_sintetico(
        tmp_path,
        {"exemplo/SKILL.md": "conteudo\n"},
        {"exemplo/SKILL.md": "conteudo\n", "orfa/SKILL.md": "lixo\n"},
        {"exemplo/SKILL.md": "conteudo\n"},
    )

    codigo, linhas = ss.sincronizar(root, check=True)

    assert codigo != 0
    achados = [linha for linha in linhas if "órfão" in linha and "orfa/SKILL.md" in linha]
    assert achados, linhas


def test_modo_escrita_corrige_os_tres_casos(tmp_path):
    root = _repo_sintetico(
        tmp_path,
        {"exemplo/SKILL.md": "conteudo novo\n"},
        {"exemplo/SKILL.md": "conteudo velho\n", "orfa/SKILL.md": "lixo\n"},
        None,  # .grok/skills nem existe: caso "faltante" completo
    )

    codigo, relato = ss.sincronizar(root, check=False)
    assert codigo == 0
    assert relato  # relatou pelo menos uma correção

    destino_claude = root / ".claude" / "skills"
    destino_grok = root / ".grok" / "skills"
    # divergente corrigido
    assert (destino_claude / "exemplo" / "SKILL.md").read_text(encoding="utf-8") == "conteudo novo\n"
    # órfão removido (pasta some inteira)
    assert not (destino_claude / "orfa").exists()
    # faltante criado do zero
    assert (destino_grok / "exemplo" / "SKILL.md").read_text(encoding="utf-8") == "conteudo novo\n"

    # e agora --check confirma: sincronizado
    codigo_check, linhas_check = ss.sincronizar(root, check=True)
    assert codigo_check == 0, linhas_check


def test_rodar_duas_vezes_nao_muda_nada_na_segunda(tmp_path):
    root = _repo_sintetico(tmp_path, {"exemplo/SKILL.md": "conteudo\n"}, None, None)

    codigo1, relato1 = ss.sincronizar(root, check=False)
    assert codigo1 == 0
    assert relato1  # primeira rodada copiou algo

    codigo2, relato2 = ss.sincronizar(root, check=False)
    assert codigo2 == 0
    assert relato2 == ["sync_skills: já sincronizado, nada a fazer"]


def test_fonte_ausente_sai_diferente_de_zero_sem_criar_nada(tmp_path):
    root = _repo_sintetico(tmp_path, None, None, None)

    codigo, linhas = ss.sincronizar(root, check=False)

    assert codigo != 0
    assert any("fonte ausente" in linha for linha in linhas), linhas
    assert not (root / ".claude" / "skills").exists()
    assert not (root / ".grok" / "skills").exists()


def test_cli_check_via_subprocesso():
    """A CLI (`--check`, `--root`) entrega o mesmo contrato da função — não só a
    função testada em processo."""
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(RAIZ)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TETO_SUBPROC,
    )
    # Nesta task (T1) a fonte `.agents/skills/` ainda não existe no repo real —
    # a migração é T2. O contrato exigido aqui é só "roda pela CLI e sai != 0
    # sinalizando fonte ausente", não "está sincronizado".
    assert resultado.returncode != 0
    assert "fonte ausente" in resultado.stdout
