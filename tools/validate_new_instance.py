#!/usr/bin/env python3
"""Read-only validation for an initialized cockpit-template instance."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BUILD_RECORDS = (".specs/features/template-v2",)
PLACEHOLDER = re.compile(r"(?<!\$)\{\{[A-Za-z_][\w-]*\}\}")
IGNORE_MARKER = "padrao-ouro:ignorar"
TEXT_EXTENSIONS = {"", ".md", ".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".txt"}
GATES = (
    ("doctor", ("tools/doctor.py",)),
    ("policy", ("tools/policy_check.py", ".")),
    ("operational", ("tools/operational_audit.py", ".")),
    ("routers", ("tools/lint_routers.py",)),
    ("verdict", ("tools/gate_veredito.py",)),
    ("gold", ("tools/padrao_ouro_audit.py", "--tipo", "cockpit", ".")),
)


def static_findings(root: Path) -> list[str]:
    findings = [path for path in BUILD_RECORDS if (root / path).exists()]
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    files = [root / item for item in listed.stdout.decode().split("\0") if item] if listed.returncode == 0 else root.rglob("*")
    for path in files:
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts or ".tmp" in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if any(PLACEHOLDER.search(line) and IGNORE_MARKER not in line for line in text.splitlines()):
                findings.append(path.relative_to(root).as_posix())
        except UnicodeError:
            continue
    return sorted(set(findings))


def validate(root: Path) -> int:
    root = root.resolve()
    if not root.is_dir():
        print(f"validate_new_instance: invalid root: {root}", file=sys.stderr)
        return 2
    findings = static_findings(root)
    if findings:
        print("validate_new_instance: baseline contamination or unresolved placeholder:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    failed = []
    for name, arguments in GATES:
        result = subprocess.run([sys.executable, *arguments], cwd=root, text=True, capture_output=True)
        if result.returncode:
            failed.append(name)
            print(f"[{name}]", file=sys.stderr)
            print(result.stdout + result.stderr, file=sys.stderr, end="")
    if failed:
        return 1
    print("validate_new_instance: APROVADO")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    return validate(Path(parser.parse_args(argv).root))


if __name__ == "__main__":
    raise SystemExit(main())
