"""Testes do parser de casos e dos graders do runner de bolso (R12).

Nada aqui chama `claude`: os graders são exercitados sobre transcrições
`stream-json` sintéticas (`tests/fixtures/`). Inclui o teste de mutação (um
grader negativo com um `tool_use` de Skill na transcrição precisa reprovar; sem
ele, aprovar) e o teste do exit code 2 com `claude` ausente do PATH.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
sys.path.insert(0, str(RAIZ / "tools"))

import eval_runner  # noqa: E402


def _carregar_transcricao(nome: str) -> list[dict]:
    texto = (FIXTURES / nome).read_text(encoding="utf-8")
    return [json.loads(l) for l in texto.splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Parser de prompt.md / graders/*.md


def test_parse_caso_le_frontmatter_e_graders(tmp_path):
    case_dir = tmp_path / "caso-x"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: caso-x\ntags: [positivo]\nruns: 3\nmax_turns: 3\n"
        "timeout_seconds: 180\n---\n\nRoda o os audit no meu projeto.\n",
        encoding="utf-8",
    )
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\n"
        "input_match: '\"skill\"\\s*:\\s*\"(?:[\\w-]+:)?os-audit\"'\nmin: 1\n---\n\njustificativa\n",
        encoding="utf-8",
    )
    caso = eval_runner.parse_caso(case_dir)
    assert caso["nome"] == "caso-x"
    assert caso["tags"] == ["positivo"]
    assert caso["runs"] == caso["max_turns"] == 3
    assert caso["timeout_seconds"] == 180
    assert caso["prompt"] == "Roda o os audit no meu projeto."
    assert len(caso["graders"]) == 1
    assert caso["graders"][0]["type"] == "tool_used"


def test_parse_caso_colapsa_quebra_de_linha_do_corpo(tmp_path):
    """Gotcha medido 2026-09-04 (Windows): um corpo de prompt quebrado em duas
    linhas (\\n ou \\r\\n) vira, sem esse colapso, um argumento com newline no
    meio — o wrapper .cmd do `claude` no Windows recebe isso como se a linha de
    comando tivesse terminado ali e sai com returncode 0 sem rodar nada (nem
    transcrição, nem erro). O `prompt` parseado precisa ser sempre uma linha só."""
    case_dir = tmp_path / "caso-quebrado"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: caso-quebrado\ntags: [positivo]\nruns: 3\nmax_turns: 3\n"
        "timeout_seconds: 180\n---\n\nPrimeira parte da frase\r\nsegunda parte da frase.\n",
        encoding="utf-8",
    )
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\n"
        "input_match: '\"skill\"\\s*:\\s*\"(?:[\\w-]+:)?os-audit\"'\nmin: 1\n---\n\njustificativa\n",
        encoding="utf-8",
    )
    caso = eval_runner.parse_caso(case_dir)
    assert "\n" not in caso["prompt"]
    assert "\r" not in caso["prompt"]
    assert caso["prompt"] == "Primeira parte da frase segunda parte da frase."


def test_parse_caso_sem_frontmatter_reprova(tmp_path):
    case_dir = tmp_path / "caso-y"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text("sem frontmatter nenhum\n", encoding="utf-8")
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\ninput_match: 'x'\nmin: 1\n---\n", encoding="utf-8"
    )
    with pytest.raises(eval_runner.ErroCasoMalFormado):
        eval_runner.parse_caso(case_dir)


def test_parse_caso_com_runs_nao_inteiro_reprova(tmp_path):
    case_dir = tmp_path / "caso-z"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: caso-z\ntags: [negativo]\nruns: tres\nmax_turns: 3\n"
        "timeout_seconds: 180\n---\n\nprompt\n", encoding="utf-8",
    )
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\ninput_match: 'x'\nmin: 0\nmax: 0\n---\n", encoding="utf-8"
    )
    with pytest.raises(eval_runner.ErroCasoMalFormado):
        eval_runner.parse_caso(case_dir)


def test_parse_caso_com_frontmatter_yaml_invalido_reprova(tmp_path):
    """YAML sintaticamente inválido reprova, em vez de virar string em silêncio.

    É o motivo de esta cópia usar `yaml.safe_load`. O parser artesanal que existia
    lia `tags: [positivo` (colchete não fechado) como a string literal "[positivo"
    e seguia adiante: caso mal formado passando por válido, no caminho de
    verificação, que é o pior lugar possível para passivo silencioso.

    A verificação da Fase 1 mostrou que trocar `safe_load` de volta pelo parser
    permissivo mantinha a suíte inteira verde. Este teste é o que mata esse mutante.
    """
    case_dir = tmp_path / "caso-w"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: caso-w\ntags: [positivo\nruns: 3\nmax_turns: 3\n"
        "timeout_seconds: 180\n---\n\nprompt\n",
        encoding="utf-8",
    )
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\ninput_match: 'x'\nmin: 1\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(eval_runner.ErroCasoMalFormado, match="YAML inválido"):
        eval_runner.parse_caso(case_dir)


@pytest.mark.parametrize("frontmatter", ["somente texto\n", "- item-1\n- item-2\n"])
def test_parse_frontmatter_nao_mapa_reprova(frontmatter):
    with pytest.raises(eval_runner.ErroCasoMalFormado, match="precisa ser um mapa"):
        eval_runner.parse_frontmatter(f"---\n{frontmatter}---\nprompt\n", "prompt.md")


def test_parse_caso_com_regex_incompilavel_reprova(tmp_path):
    case_dir = tmp_path / "caso-w"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: caso-w\ntags: [positivo]\nruns: 3\nmax_turns: 3\n"
        "timeout_seconds: 180\n---\n\nprompt\n", encoding="utf-8",
    )
    (case_dir / "graders" / "disparo.md").write_text(
        "---\ntype: tool_used\ntool: Skill\ninput_match: '(['\nmin: 1\n---\n", encoding="utf-8"
    )
    with pytest.raises(eval_runner.ErroCasoMalFormado):
        eval_runner.parse_caso(case_dir)


# ---------------------------------------------------------------------------
# Graders sobre transcrições sintéticas — mutação (o coração do R12)


def test_grader_negativo_reprova_quando_skill_disparou():
    """Mutação: transcrição COM tool_use de Skill os-audit + grader negativo => reprova."""
    linhas = _carregar_transcricao("transcript_com_skill_os_audit.jsonl")
    grader = {
        "type": "tool_used", "tool": "Skill",
        "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?os-audit"',
        "min": 0, "max": 0, "_arquivo": "disparo.md",
    }
    veredito = eval_runner.avaliar_grader(grader, linhas, Path("."))
    assert veredito["passou"] is False, "grader negativo deveria reprovar com skill disparada"


def test_grader_negativo_aprova_quando_skill_nao_disparou():
    """Sem mutação: transcrição SEM tool_use de Skill + o mesmo grader negativo => aprova."""
    linhas = _carregar_transcricao("transcript_sem_skill.jsonl")
    grader = {
        "type": "tool_used", "tool": "Skill",
        "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?os-audit"',
        "min": 0, "max": 0, "_arquivo": "disparo.md",
    }
    veredito = eval_runner.avaliar_grader(grader, linhas, Path("."))
    assert veredito["passou"] is True, "grader negativo deveria aprovar sem skill disparada"


def test_grader_positivo_aprova_quando_skill_disparou():
    linhas = _carregar_transcricao("transcript_com_skill_os_audit.jsonl")
    grader = {
        "type": "tool_used", "tool": "Skill",
        "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?os-audit"',
        "min": 1, "_arquivo": "disparo.md",
    }
    veredito = eval_runner.avaliar_grader(grader, linhas, Path("."))
    assert veredito["passou"] is True


def test_grader_positivo_reprova_quando_skill_nao_disparou():
    linhas = _carregar_transcricao("transcript_sem_skill.jsonl")
    grader = {
        "type": "tool_used", "tool": "Skill",
        "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?os-audit"',
        "min": 1, "_arquivo": "disparo.md",
    }
    veredito = eval_runner.avaliar_grader(grader, linhas, Path("."))
    assert veredito["passou"] is False


def test_grader_positivo_nao_confunde_skill_de_nome_parecido():
    """`os-audit` não pode casar com `os-audit-v2` nem o contrário — a regex é ancorada nas aspas."""
    linhas = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "os-audit-v2"}}
    ]}}]
    grader = {
        "type": "tool_used", "tool": "Skill",
        "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?os-audit"',
        "min": 1, "_arquivo": "disparo.md",
    }
    veredito = eval_runner.avaliar_grader(grader, linhas, Path("."))
    assert veredito["passou"] is False


def test_grader_regex_sobre_ultima_mensagem_do_assistente():
    linhas = _carregar_transcricao("transcript_sem_skill.jsonl")
    grader_ok = {"type": "regex", "pattern": r"sem usar nenhuma skill", "_arquivo": "r.md"}
    grader_fail = {"type": "regex", "pattern": r"isso nao aparece em lugar nenhum", "_arquivo": "r.md"}
    assert eval_runner.avaliar_grader(grader_ok, linhas, Path("."))["passou"] is True
    assert eval_runner.avaliar_grader(grader_fail, linhas, Path("."))["passou"] is False


def test_grader_file_exists(tmp_path):
    (tmp_path / "relatorio.md").write_text("ok", encoding="utf-8")
    grader_ok = {"type": "file_exists", "glob": "relatorio.md", "_arquivo": "f.md"}
    grader_fail = {"type": "file_exists", "glob": "nao-existe.md", "_arquivo": "f.md"}
    assert eval_runner.avaliar_grader(grader_ok, [], tmp_path)["passou"] is True
    assert eval_runner.avaliar_grader(grader_fail, [], tmp_path)["passou"] is False


def test_grader_tipo_nao_suportado_levanta_erro():
    with pytest.raises(eval_runner.ErroCasoMalFormado):
        eval_runner.avaliar_grader({"type": "llm", "_arquivo": "l.md"}, [], Path("."))


# ---------------------------------------------------------------------------
# `claude` ausente do PATH => exit 2


def test_main_sem_claude_no_path_retorna_2(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_runner.shutil, "which", lambda nome: None)
    ret = eval_runner.main(["--all"])
    assert ret == 2


def test_montar_comando_inclui_plugin_dir_quando_presente():
    cmd = eval_runner.montar_comando("claude", "oi", 3, Path("/tmp/plugin-x"))
    assert "--plugin-dir" in cmd
    assert str(Path("/tmp/plugin-x")) in cmd


def _criar_caso_minimo(case_dir: Path, prompt: str = "oi") -> None:
    case_dir.mkdir(parents=True)
    (case_dir / "prompt.md").write_text(
        "---\nname: " + case_dir.name + "\ntags: [positivo]\nruns: 1\n"
        "max_turns: 1\ntimeout_seconds: 5\n---\n\n" + prompt + "\n",
        encoding="utf-8",
    )
    graders_dir = case_dir / "graders"
    graders_dir.mkdir()
    (graders_dir / "disparo.md").write_text(
        "---\ntype: tool_used\ninput_match: .*\nmin: 1\n---\n\njustificativa\n",
        encoding="utf-8",
    )


def test_main_com_todos_runs_em_erro_de_infra_retorna_2(monkeypatch, tmp_path):
    """R3(3): suíte pequena (2 casos), todos os runs falham por infra (ex.: sem
    login) — não pode virar FAIL/exit 1, tem que ser exit 2 com mensagem clara."""
    skills_dir = tmp_path / ".claude" / "skills" / "minha-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("---\nname: minha-skill\n---\n", encoding="utf-8")

    _criar_caso_minimo(tmp_path / "evals" / "minha-skill" / "caso-1")
    _criar_caso_minimo(tmp_path / "evals" / "minha-skill" / "caso-2")

    monkeypatch.setattr(eval_runner.shutil, "which", lambda nome: "claude")

    def _sempre_infra(*a, **k):
        raise eval_runner.ErroInfra("não foi possível executar `claude`: falha simulada")

    monkeypatch.setattr(eval_runner, "executar_run", _sempre_infra)
    monkeypatch.chdir(tmp_path)

    ret = eval_runner.main(["--skills-dir", str(tmp_path / ".claude" / "skills")])
    assert ret == 2


def test_montar_comando_sem_plugin_dir_no_modo_skills():
    cmd = eval_runner.montar_comando("claude", "oi", 3, None)
    assert "--plugin-dir" not in cmd


# ---------------------------------------------------------------------------
# Contrato da cópia canônica (T1/SYNC-02)


def test_runner_versao_e_semantica():
    """`RUNNER_VERSAO` existe e é `major.minor.patch`.

    A constante é o que diz ao espelho do `template-cockpit` que a cópia mudou.
    String livre não serve: o procedimento de propagação lê a versão para decidir
    se a mudança é interna, de saída ou de contrato.
    """
    assert re.fullmatch(r"\d+\.\d+\.\d+", eval_runner.RUNNER_VERSAO), (
        f"RUNNER_VERSAO = {eval_runner.RUNNER_VERSAO!r} não é major.minor.patch"
    )


def test_docstring_declara_copia_canonica_e_nomeia_o_espelho():
    """A docstring declara esta cópia como canônica e nomeia o repo que a espelha.

    Sem isso, quem abre o arquivo no `template-cockpit` não tem como saber que
    editar ali é editar a cópia errada.
    """
    doc = eval_runner.__doc__ or ""
    # Rótulo do contrato, não a palavra solta: "canônica" aparece várias vezes na
    # docstring, então `"canônica" in doc` continuaria verde sem o contrato.
    assert "**Canônica**: `Caio-MOR/plugins`" in doc, (
        "docstring não rotula esta cópia como a canônica, com owner/repo"
    )
    assert "**Espelho**: `Caio-MOR/template-cockpit`" in doc, (
        "docstring não rotula o espelho com owner/repo"
    )


# ---------------------------------------------------------------------------
# Segurança, proveniência e validação de resultados


def test_ambiente_seguro_exclui_segredos_e_preserva_runtime():
    ambiente = {
        "PATH": "/bin", "HOME": "/tmp/test-home", "CLAUDE_CONFIG_DIR": "/tmp/test-home/.claude",
        "ANTHROPIC_API_KEY": "secret", "AWS_SECRET_ACCESS_KEY": "secret",
        "DATABASE_URL": "postgres://production", "GITHUB_TOKEN": "secret",
    }
    seguro = eval_runner.ambiente_seguro(ambiente)
    assert seguro["PATH"] == "/bin"
    assert seguro["HOME"] == "/tmp/test-home"
    assert seguro["CLAUDE_CONFIG_DIR"] == "/tmp/test-home/.claude"
    assert not {"ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "DATABASE_URL", "GITHUB_TOKEN"} & seguro.keys()
    assert seguro["DISABLE_AUTOUPDATER"] == "1"


def test_subprocesso_recebe_ambiente_sanitizado(monkeypatch, tmp_path):
    recebido = {}

    def fake_run(*args, **kwargs):
        recebido.update(kwargs)
        return eval_runner.subprocess.CompletedProcess(args[0], 0, "{}\n", "")

    monkeypatch.setattr(eval_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(eval_runner, "ambiente_seguro", lambda: {"PATH": "/safe"})
    eval_runner._rodar_subprocesso(["claude", "-p", "oi"], tmp_path, 5)
    assert recebido["env"] == {"PATH": "/safe"}
    assert recebido["cwd"] == str(tmp_path.resolve())


def test_rodar_caso_copia_plugin_para_cwd_descartavel(monkeypatch, tmp_path):
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "plugin.md").write_text("original", encoding="utf-8")
    caso = {"nome": "caso", "tags": [], "runs": 1, "max_turns": 1,
            "timeout_seconds": 5, "prompt": "oi", "graders": [
                {"type": "tool_used", "tool": "Skill", "input_match": ".*", "min": 1, "_arquivo": "x.md"}]}
    usados = []

    def fake_executar(*args, **kwargs):
        caminho = kwargs.get("plugin_dir", args[-1])
        usados.append(caminho)
        (caminho / "nao-vaza.txt").write_text("somente cópia", encoding="utf-8")
        return [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "x"}}]}}]

    monkeypatch.setattr(eval_runner, "executar_run", fake_executar)
    assert eval_runner.rodar_caso("claude", caso, plugin, None, None)["ok"] == 1
    assert usados and usados[0] != plugin
    assert not (plugin / "nao-vaza.txt").exists()


def _resultado_de_teste(*, finished_at: str | None = None, runs: int = 1) -> dict:
    agora = datetime.now(timezone.utc)
    return {"schema": eval_runner.RESULTADO_SCHEMA, "runner_version": eval_runner.RUNNER_VERSAO,
            "started_at": (agora - timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
            "finished_at": finished_at or agora.isoformat().replace("+00:00", "Z"),
            "git": {"commit": "a" * 40, "dirty": False},
            "case_inventory": [{"case_key": "skill/caso", "name": "caso", "plugin_or_skill": "skill",
                                "tags": [], "expected_runs": runs, "grader_count": 1}],
            "cases": [{"case_key": "skill/caso", "name": "caso", "plugin_or_skill": "skill", "tags": [],
                       "runs": [{"ok": True, "infra": None, "graders": []} for _ in range(runs)],
                       "ok": runs, "total": runs, "todos_infra": False}],
            "aggregates": {"total_casos": 1, "casos_ok": 1, "threshold": 1.0}}


def test_validar_resultado_exige_cobertura_completa_e_frescura():
    assert eval_runner.validar_resultado(_resultado_de_teste()) == []
    incompleto = _resultado_de_teste(runs=2)
    incompleto["cases"][0]["runs"].pop()
    incompleto["cases"][0]["total"] = 1
    assert any("incompleto" in erro for erro in eval_runner.validar_resultado(incompleto))
    velho = datetime.now(timezone.utc) - timedelta(days=2)
    resultado_velho = _resultado_de_teste(finished_at=velho.isoformat().replace("+00:00", "Z"))
    resultado_velho["started_at"] = (velho - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    assert any("antigo" in erro for erro in eval_runner.validar_resultado(resultado_velho))


@pytest.mark.parametrize("campo, valor", [
    ("case_inventory", ["não é objeto"]), ("cases", ["não é objeto"]),
    ("case_inventory", [{"case_key": ["lista não hashable"]}]),
    ("cases", [{"case_key": {"objeto": "não hashable"}}]),
])
def test_validar_resultado_reprova_chave_de_caso_malformada_sem_typeerror(campo, valor):
    resultado = _resultado_de_teste()
    resultado[campo] = valor
    erros = eval_runner.validar_resultado(resultado)
    assert erros
    assert any(campo in erro for erro in erros)


def test_caminho_saida_nao_pode_escapar_raiz(tmp_path):
    with pytest.raises(eval_runner.ErroInfra, match="dentro da raiz"):
        eval_runner._caminho_saida_seguro(str(tmp_path.parent / "fora.json"), tmp_path)


def test_main_gera_resultado_com_schema_inventario_e_proveniencia(monkeypatch, tmp_path):
    skills_dir = tmp_path / ".claude" / "skills" / "skill-x"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("---\nname: skill-x\n---\n", encoding="utf-8")
    _criar_caso_minimo(tmp_path / "evals" / "skill-x" / "caso-1")
    saida = tmp_path / "results.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(eval_runner.shutil, "which", lambda nome: "claude")
    monkeypatch.setattr(eval_runner, "executar_run", lambda *args: [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "x"}}]}}])
    assert eval_runner.main(["--skills-dir", str(skills_dir.parent), "--json", str(saida)]) == 0
    resultado = json.loads(saida.read_text(encoding="utf-8"))
    assert resultado["schema"] == eval_runner.RESULTADO_SCHEMA
    assert resultado["runner_version"] == eval_runner.RUNNER_VERSAO
    assert resultado["git"].keys() == {"commit", "dirty"}
    assert resultado["case_inventory"][0]["case_key"] == "skill-x/caso-1"
    assert eval_runner.validar_resultado(resultado) == []
    assert eval_runner.main(["--validate-json", str(saida)]) == 0
