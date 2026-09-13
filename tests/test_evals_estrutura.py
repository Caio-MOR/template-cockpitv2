"""Gate determinístico dos evals de comportamento no template (R11 adaptado por R17).

Roda sem LLM. O template é MODELO, não produção: exige apenas >= 1 positivo e
>= 1 negativo por skill (o marketplace `caio-mor` exige 3+3 — ver
`tools/eval_runner.py`/`docs/` de lá). A execução real com `claude -p` é gate
local (`python tools/eval_runner.py --skills-dir .agents/skills`), nunca CI.

GAT-01: `eval_runner.descobrir_skills` devolve `{}` em silêncio quando o
diretório não existe ou está vazio — sem sensor, os testes abaixo, que iteram
`_casos_por_skill()`, seguem verdes vendo zero skills. `test_fonte_de_skills_tem_ao_menos_uma_skill`
fecha esse buraco na fonte real; `test_sensor_reprova_com_fonte_vazia_ou_ausente_e_passa_com_a_real`
prova que ele reprova quando a fonte some.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import eval_runner  # noqa: E402

SKILLS_DIR = RAIZ / ".agents" / "skills"
EVALS_DIR = RAIZ / "evals"

RE_CAMINHO_MAQUINA = re.compile(
    r"(?i)[a-z]:[\\/]users[\\/]"
    r"|(?<![\w/])/(Users|home)/[A-Za-z0-9_.-]+(?=[/\s\"'`)\]]|$)"
)


# Mesma isenção de `tests/test_criacao_nova.py`: skill de terceiro adotada por
# `tools/sync_skills.py --adotar` traz o marcador e não deve evals de disparo a este repo.
VENDORIZADA = "VENDORIZADA.md"


def _skills_com_evals_exigidos(skills_dir: Path) -> dict[str, Path]:
    return {
        nome: caminho for nome, caminho in eval_runner.descobrir_skills(skills_dir).items()
        if not (caminho / VENDORIZADA).is_file()
    }


def _skills():
    return _skills_com_evals_exigidos(SKILLS_DIR)


def _exige_skills_descobertas(skills_dir: Path) -> None:
    """Sensor de GAT-01: fonte vazia ou ausente não pode passar em silêncio —
    `descobrir_skills` devolve `{}` nesses casos e este sensor reprova em vez
    de deixar os testes que iteram `_casos_por_skill()` verem zero skills."""
    descobertas = eval_runner.descobrir_skills(skills_dir)
    assert descobertas, (
        f"descobrir_skills({skills_dir}) não achou nenhuma skill — a fonte está "
        "vazia ou ausente, e os testes deste arquivo passariam vendo zero skills"
    )


def _casos_por_skill():
    return {nome: eval_runner.descobrir_casos(EVALS_DIR / nome, None) for nome in _skills()}


def test_toda_skill_tem_pasta_evals():
    faltando = [nome for nome in _skills() if not (EVALS_DIR / nome).is_dir()]
    assert faltando == [], f"skills sem evals/<skill>/: {faltando}"


def test_cada_caso_tem_prompt_valido_e_name_igual_a_pasta():
    problemas = []
    for nome, casos in _casos_por_skill().items():
        for case_dir in casos:
            try:
                caso = eval_runner.parse_caso(case_dir)
            except eval_runner.ErroCasoMalFormado as e:
                problemas.append(str(e))
                continue
            if caso["nome"] != case_dir.name:
                problemas.append(f"{case_dir}: name do frontmatter difere da pasta")
    assert problemas == [], "\n".join(problemas)


def test_cada_skill_tem_ao_menos_1_positivo_e_1_negativo():
    faltando = []
    for nome, casos in _casos_por_skill().items():
        positivos = sum(1 for c in casos if "positivo" in set(eval_runner.parse_caso(c)["tags"]))
        negativos = sum(1 for c in casos if "negativo" in set(eval_runner.parse_caso(c)["tags"]))
        if positivos < 1 or negativos < 1:
            faltando.append(f"{nome}: positivos={positivos} negativos={negativos}")
    assert faltando == [], f"skills sem 1 positivo + 1 negativo: {faltando}"


def test_todo_grader_tool_used_tem_regex_compilavel():
    problemas = []
    for nome, casos in _casos_por_skill().items():
        for case_dir in casos:
            caso = eval_runner.parse_caso(case_dir)
            for g in caso["graders"]:
                if g.get("type") == "tool_used":
                    try:
                        re.compile(g["input_match"])
                    except re.error as e:
                        problemas.append(f"{case_dir}/{g['_arquivo']}: {e}")
    assert problemas == [], "\n".join(problemas)


def test_runs_max_turns_timeout_sao_inteiros_positivos():
    for nome, casos in _casos_por_skill().items():
        for case_dir in casos:
            caso = eval_runner.parse_caso(case_dir)
            for chave in ("runs", "max_turns", "timeout_seconds"):
                assert isinstance(caso[chave], int) and caso[chave] > 0, f"{case_dir}: {chave}"


def test_prompt_sem_caminho_de_maquina():
    problemas = []
    for nome, casos in _casos_por_skill().items():
        for case_dir in casos:
            texto = (case_dir / "prompt.md").read_text(encoding="utf-8")
            for n, linha in enumerate(texto.splitlines(), start=1):
                if RE_CAMINHO_MAQUINA.search(linha):
                    problemas.append(f"{case_dir}/prompt.md:{n}: caminho de máquina")
    assert problemas == [], "\n".join(problemas)


def test_skill_vendorizada_nao_deve_evals_e_sem_marcador_deve(tmp_path):
    """Reprodução da instância: skill adotada de instalador externo, sem `evals/<skill>/`,
    reprovava `test_toda_skill_tem_pasta_evals`. O marcador da ferramenta a isenta."""
    fonte = tmp_path / ".agents" / "skills"
    for nome in ("_exemplo-skill", "tlc-spec-lean"):
        (fonte / nome).mkdir(parents=True)
        (fonte / nome / "SKILL.md").write_text(f"---\nname: {nome}\ndescription: d\n---\n", encoding="utf-8")
    assert set(_skills_com_evals_exigidos(fonte)) == {"_exemplo-skill", "tlc-spec-lean"}
    (fonte / "tlc-spec-lean" / VENDORIZADA).write_text("# vendorizada\n", encoding="utf-8")
    assert set(_skills_com_evals_exigidos(fonte)) == {"_exemplo-skill"}


def test_fonte_de_skills_tem_ao_menos_uma_skill():
    """GAT-01 — sensor real: se `SKILLS_DIR` vier vazio ou sumir, este teste
    reprova em vez de deixar os quatro testes acima passarem vendo zero skills."""
    _exige_skills_descobertas(SKILLS_DIR)


def test_sensor_reprova_com_fonte_vazia_ou_ausente_e_passa_com_a_real(tmp_path):
    """Prova de discriminação (GAT-01): o mesmo sensor de
    `test_fonte_de_skills_tem_ao_menos_uma_skill`, apontado para um diretório
    ausente e depois para um vazio, reprova nos dois casos; contra a fonte
    real (`SKILLS_DIR`), passa. Antes desta task, `descobrir_skills` devolvia
    `{}` para os dois casos e nenhum teste deste arquivo notava."""
    ausente = tmp_path / "nao-existe"
    assert eval_runner.descobrir_skills(ausente) == {}
    with pytest.raises(AssertionError, match="não achou nenhuma skill"):
        _exige_skills_descobertas(ausente)

    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert eval_runner.descobrir_skills(vazio) == {}
    with pytest.raises(AssertionError, match="não achou nenhuma skill"):
        _exige_skills_descobertas(vazio)

    _exige_skills_descobertas(SKILLS_DIR)  # fonte real: não levanta
