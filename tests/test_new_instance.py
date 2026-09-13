"""Temporary-copy proof for explicit template initialization.

A cópia usada nos testes recebe o `STATE.md` DO TEMPLATE (`TEMPLATE_STATE`), não o
do disco: o que está sob prova é o inicializador sobre o estado que o template
entrega, e o `STATE.md` real de uma instância acumula decisões (AD-nnn) desde a
primeira sessão. Sem isso a primeira decisão registrada numa instância quebrava
este arquivo inteiro — o inicializador recusa STATE que não seja o do template, e
era exatamente o que a cópia carregava.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import initialize_template  # noqa: E402
import validate_new_instance  # noqa: E402


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, check=True)


def _copy_template(tmp_path: Path, source: Path = RAIZ) -> Path:
    """Cópia do template como repositório git próprio — é o que `gh repo create
    --template` entrega, e é onde o inicializador ativa `core.hooksPath`. O
    `STATE.md` da cópia é sempre o do template (ver docstring do módulo)."""
    instance = tmp_path / "instance"
    shutil.copytree(source, instance, ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", ".ruff_cache", ".tmp", "__pycache__"))
    (instance / ".specs" / "STATE.md").write_text(initialize_template.TEMPLATE_STATE, encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=instance)
    _git("config", "user.email", "t@t.invalid", cwd=instance)
    _git("config", "user.name", "t", cwd=instance)
    _git("add", "-A", cwd=instance)
    _git("commit", "-q", "-m", "instancia", cwd=instance)
    return instance


def _add_v2_build_records(instance: Path) -> None:
    record = instance / ".specs" / "features" / "template-v2"
    record.mkdir(parents=True, exist_ok=True)
    (record / "spec.md").write_text("build evidence", encoding="utf-8")


def _resolve_declared_placeholders(instance: Path) -> None:
    replacements = {
        "AGENTS.md": {"{{NOME_DO_REPO}}": "resolved", "{{IDIOMA}}": "English"},
        "README.md": {"{{NOME_DO_REPO}}": "resolved", "{{DESCRICAO}}": "description", "{{DONO}}": "owner"},
        ".github/CODEOWNERS": {"{{GITHUB_OWNER}}": "owner"},
    }
    for relative, values in replacements.items():
        path = instance / relative
        text = path.read_text(encoding="utf-8")
        for old, new in values.items():
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def test_dry_run_is_non_mutating_and_apply_is_allowlisted(tmp_path):
    instance = _copy_template(tmp_path)
    _add_v2_build_records(instance)
    unrelated = instance / ".specs" / "features" / "user-work" / "note.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    before = (instance / ".specs" / "STATE.md").read_text(encoding="utf-8")

    assert initialize_template.initialize(instance, dry_run=True) == 0
    assert (instance / ".specs" / "features" / "template-v2").is_dir()
    assert (instance / ".specs" / "STATE.md").read_text(encoding="utf-8") == before

    assert initialize_template.initialize(instance, dry_run=False) == 0
    assert not (instance / ".specs" / "features" / "template-v2").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (instance / ".specs" / "STATE.md").read_text(encoding="utf-8") == initialize_template.INITIAL_STATE
    # A ativação do hook faz parte da inicialização: sem ela o clone empurra sem gate.
    assert _git("config", "--get", "core.hooksPath", cwd=instance).stdout.strip() == ".githooks"


def test_suite_of_an_instance_with_its_own_decisions_still_proves_the_initializer(tmp_path):
    """Reprodução do defeito da primeira instância real: o repo de onde a suíte roda
    já tem uma decisão em `.specs/STATE.md`. A cópia de teste não pode herdar isso,
    senão `initialize` devolve 1 e a suíte da instância fica vermelha para sempre."""
    instance_with_decision = tmp_path / "source"
    shutil.copytree(RAIZ, instance_with_decision, ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", ".ruff_cache", ".tmp", "__pycache__"))
    state = instance_with_decision / ".specs" / "STATE.md"
    state.write_text(
        initialize_template.INITIAL_STATE + "- **AD-001 (2026-09-13):** primeira decisão da instância.\n",
        encoding="utf-8",
    )

    copy = _copy_template(tmp_path, source=instance_with_decision)
    assert (copy / ".specs" / "STATE.md").read_text(encoding="utf-8") == initialize_template.TEMPLATE_STATE
    assert initialize_template.initialize(copy, dry_run=False) == 0
    # A decisão da instância de origem fica intocada: a cópia é que foi normalizada.
    assert "AD-001 (2026-09-13)" in state.read_text(encoding="utf-8")


def test_initializer_fails_when_the_hook_cannot_be_activated(tmp_path):
    """Pasta que não é repositório git não tem onde guardar `core.hooksPath`: o
    inicializador diz isso (exit 1) em vez de fingir que o hook está ativo."""
    instance = tmp_path / "sem-git"
    shutil.copytree(RAIZ / ".specs", instance / ".specs")
    assert initialize_template.initialize(instance, dry_run=True) == 0
    assert initialize_template.initialize(instance, dry_run=False) == 1


def test_validator_rejects_build_records_and_placeholders_but_allows_later_files(tmp_path):
    instance = _copy_template(tmp_path)
    _add_v2_build_records(instance)
    (instance / "AGENTS.md").write_text("{{NOME_DO_REPO}}", encoding="utf-8")
    findings = validate_new_instance.static_findings(instance)
    assert ".specs/features/template-v2" in findings
    assert "AGENTS.md" in findings

    assert initialize_template.initialize(instance, dry_run=False) == 0
    _resolve_declared_placeholders(instance)
    (instance / ".gitleaksignore").write_text("known-fingerprint\n", encoding="utf-8")
    assert validate_new_instance.static_findings(instance) == []

    (instance / ".specs" / "features" / "template-v2").mkdir(parents=True)
    assert ".specs/features/template-v2" in validate_new_instance.static_findings(instance)


def test_initializer_preserves_custom_state(tmp_path):
    """Estado já customizado não é sobrescrito; a rejeição de alvo symlinkado está em
    `tests/test_symlink_privilegio.py` (symlink exige privilégio no Windows)."""
    instance = _copy_template(tmp_path)
    _add_v2_build_records(instance)
    state = instance / ".specs" / "STATE.md"
    state.write_text(initialize_template.TEMPLATE_STATE + "\n- custom", encoding="utf-8")
    assert initialize_template.initialize(instance, dry_run=False) == 1
    assert state.read_text(encoding="utf-8").endswith("custom")
    assert (instance / ".specs" / "features" / "template-v2").is_dir()


def test_validator_ignores_local_venv_placeholder(tmp_path):
    instance = _copy_template(tmp_path)
    local = instance / ".venv" / "dependency.md"
    local.parent.mkdir()
    local.write_text("{{DEPENDENCY_PLACEHOLDER}}", encoding="utf-8")
    assert ".venv/dependency.md" not in validate_new_instance.static_findings(instance)
