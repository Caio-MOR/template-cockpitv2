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
- **AD-001 (AAAA-MM-DD):** o que foi decidido, em uma frase; o motivo em outra.
  Quem decidiu (dono do repo em chat, agente por regra X) e o que fica em aberto.
-->

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
