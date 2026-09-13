#!/usr/bin/env python3
"""Remove v2 build evidence from a generated repository and activate the pre-push hook.

Run ``python tools/initialize_template.py --dry-run .`` first. Apply mode deletes
only the explicit allowlisted build-record directory, writes a blank local state and
runs ``git config core.hooksPath .githooks`` so the versioned pre-push hook (the first
line of the gates) is active in this clone. ``tools/doctor.py`` reports a clone that
skipped this step.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BUILD_RECORDS = (".specs/features/template-v2",)
STATE = ".specs/STATE.md"
HOOKS_DIR = ".githooks"
GIT_TIMEOUT = 15
INITIAL_STATE = """# STATE

Project-local decisions and handoff state begin here.

## Decisions

## Handoff snapshot

"""
TEMPLATE_STATE = """# STATE

Log de decisões do repo (append-only) e snapshot de handoff. Uma decisão por item, com data e motivo — o porquê é o que a próxima sessão não consegue reconstruir sozinha.

## Decisions

<!-- Formato de cada entrada (uma por decisão, mais recente por último):
- **AD-nnn (AAAA-MM-DD):** o que foi decidido, em uma frase; o motivo em outra.
  Quem decidiu (dono do repo em chat, agente por regra X) e o que fica em aberto.
-->

- **AD-001 (2026-09-05):** verificação = hook `pre-push` obrigatório (`.githooks/`, ativado por `git config core.hooksPath .githooks`) + CI hospedado só em `pull_request` (`tests.yml`, `gitleaks.yml`), mesmos gates nos dois; a régua do padrão ouro não afrouxa (PO-C01 v1.1 exige gatilho automático E hook).
  Motivo: minutos do GitHub Actions — a versão anterior deste template trocou os quatro workflows para `workflow_dispatch` e reescreveu PO-C01/C02/C03 para não ser punida; isso devolvia a verificação à memória humana. Decisão do dono do repo em chat; agente aplicou. Em aberto: `tests-macos.yml` e `security.yml` ficam sob demanda até alguém precisar deles em PR.

- **AD-002 (2026-09-12):** fechar o `harness-score` em 108/108 (36/36 checks aprovados), tratando cada conserto como mecanismo que executa (LICENSE real, `.mcp.json` com convenção de credencial documentada, `mypy` rodando nos dois gates, hooks `PreCompact`/`SessionStart` virando script versionado, hook `PostToolUse` que roda o linter, `.githooks/pre-commit` + `.pre-commit-config.yaml` bloqueando commit sujo) — nunca só presença de arquivo para agradar o scanner.
  Motivo: o dono pediu nota auditável sem ponto cego escondido; um placar que sobe sem o repo melhorar de fato é pior que não medir. Ressalva honesta: dois dos seis checks fechados são ponto cego do próprio scanner, não lacuna real que ele soube apontar — HKS-05 lia o hook `PreCompact`/`SessionStart` inline como "script faltando" (o conteúdo sempre existiu, só não em arquivo separado) e HYG-08 penaliza a ausência de um `.mcp.json` declarado, não o uso inseguro de MCP (um `.mcp.json` vazio aprova o check sem que o repo tenha ganhado governança de credencial nova). O `pre-commit` (a ferramenta Python) foi adotado porque o scanner não reconhece `core.hooksPath=.githooks` como gate válido, embora o repo já rodasse a checagem equivalente no `pre-push`; o `.pre-commit-config.yaml` chama o mesmo `.githooks/pre-commit`, não duplica a lista. Decisão do dono do repo em chat; agente aplicou. Em aberto: nada — a nota mede presença e execução de mecanismo, não decide sozinha se o mecanismo é suficiente.

## Handoff snapshot

"""


def planned_paths(root: Path) -> list[Path]:
    return [root / relative for relative in (*BUILD_RECORDS, STATE) if (root / relative).exists()]


def _safe(root: Path, relative: str) -> Path | None:
    target = root / relative
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            return None
    return target


def initialize(root: Path, dry_run: bool) -> int:
    root = root.resolve()
    if not root.is_dir():
        print(f"initialize_template: invalid root: {root}", file=sys.stderr)
        return 2
    targets = [_safe(root, relative) for relative in (*BUILD_RECORDS, STATE)]
    if any(target is None for target in targets):
        print("initialize_template: allowlisted path contains a symlink", file=sys.stderr)
        return 1
    planned = planned_paths(root)
    for path in planned:
        print(path.relative_to(root).as_posix())
    print(f"git config core.hooksPath {HOOKS_DIR}")
    if dry_run:
        return 0
    state = root / STATE
    if state.exists():
        current = state.read_text(encoding="utf-8")
        if current not in (INITIAL_STATE, TEMPLATE_STATE):
            print("initialize_template: existing project STATE is not template state", file=sys.stderr)
            return 1
    for relative in BUILD_RECORDS:
        target = root / relative
        if target.exists():
            shutil.rmtree(target)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(INITIAL_STATE, encoding="utf-8")
    return activate_hooks(root)


def activate_hooks(root: Path) -> int:
    """Point ``core.hooksPath`` at the versioned hooks; 0 on success.

    A directory that is not a git repository cannot hold the setting: the call
    reports it (exit 1) instead of pretending the hook is active.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "core.hooksPath", HOOKS_DIR],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is None or result.returncode != 0:
        print(
            f"initialize_template: nao foi possivel ativar o hook (git config core.hooksPath {HOOKS_DIR}); "
            "rode o comando na raiz do clone e confira com tools/doctor.py",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    return initialize(Path(args.root), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
