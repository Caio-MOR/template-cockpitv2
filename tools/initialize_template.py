#!/usr/bin/env python3
"""Remove v2 build evidence from a generated repository.

Run ``python tools/initialize_template.py --dry-run .`` first. Apply mode deletes
only the explicit allowlisted build-record directory and writes a blank local state.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BUILD_RECORDS = (".specs/features/template-v2",)
STATE = ".specs/STATE.md"
INITIAL_STATE = """# STATE

Project-local decisions and handoff state begin here.

## Decisions

## Handoff snapshot
"""


def planned_paths(root: Path) -> list[Path]:
    return [root / relative for relative in (*BUILD_RECORDS, STATE) if (root / relative).exists()]


def initialize(root: Path, dry_run: bool) -> int:
    root = root.resolve()
    if not root.is_dir():
        print(f"initialize_template: invalid root: {root}", file=sys.stderr)
        return 2
    planned = planned_paths(root)
    for path in planned:
        print(path.relative_to(root).as_posix())
    if dry_run:
        return 0
    for relative in BUILD_RECORDS:
        target = root / relative
        if target.exists():
            shutil.rmtree(target)
    state = root / STATE
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(INITIAL_STATE, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    return initialize(Path(args.root), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
