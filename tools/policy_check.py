#!/usr/bin/env python3
"""Vendor-neutral repository security policy gate.

The gate is deliberately independent of Claude, an editor, or a hosting provider:
it inspects the files Git would commit and rejects tracked environment files and
recognizable credential material.  It is a second boundary for cases where an
editor hook was not installed or a write happened outside the editor.

Exit codes: 0 = policy passes, 1 = violations found, 2 = invalid invocation or
repository inspection failure.  Values are never printed; findings contain only a
path and a pattern name.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_TEXT_BYTES = 2 * 1024 * 1024
ENV_EXAMPLE = ".env.example"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-classic-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github-fine-grained-token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("openai-style-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}")),
    (
        "supabase-service-role-key",
        re.compile(r"SUPABASE_SERVICE_ROLE_KEY\s*=\s*\S{20,}"),
    ),
    (
        "x-api-key",
        re.compile(r"x-api-key\s*[:=]\s*['\"]?[A-Za-z0-9_-]{20,}"),
    ),
)


def _repo_root(value: str | Path) -> Path:
    root = Path(value).resolve(strict=False)
    if not root.is_dir():
        raise ValueError("repo root is not a directory")
    return root


def _tracked_paths(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("unable to inspect tracked files") from exc
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relative = Path(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise RuntimeError("tracked path is not valid UTF-8") from exc
        candidate = (root / relative).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("tracked path escapes repository") from exc
        paths.append(candidate)
    return paths


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_forbidden_env_name(path: Path) -> bool:
    name = path.name
    return name != ENV_EXAMPLE and (name == ".env" or name.startswith(".env."))


def _is_synthetic_line(line: str) -> bool:
    """Allow only explicit, line-scoped fixtures used to test secret detectors."""
    return "gitleaks:allow" in line or "SINTETICO" in line


def _find_secret(text: str) -> str | None:
    # Keep exemptions line-scoped: a marker cannot hide a real secret elsewhere in
    # the same file.  Test fixtures must mark the exact synthetic line.
    for line in text.splitlines():
        if _is_synthetic_line(line):
            continue
        for name, pattern in PATTERNS:
            if pattern.search(line):
                return name
    return None


def _check_gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return [".gitignore: arquivo ausente"]
    lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    required = {"/*", ".env", ".env.*", "!/.env.example"}
    return [f".gitignore: regra obrigatória ausente: {item}" for item in sorted(required - lines)]


def check(root: str | Path) -> list[str]:
    """Return safe, path-only policy findings for a repository."""
    repo = _repo_root(root)
    findings = _check_gitignore(repo)
    for path in _tracked_paths(repo):
        relative = _relative(repo, path)
        if _is_forbidden_env_name(path):
            findings.append(f"{relative}: arquivo de ambiente/segredo rastreado")
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            findings.append(f"{relative}: arquivo não pôde ser inspecionado")
            continue
        if size > MAX_TEXT_BYTES:
            # Do not silently skip content beyond the bounded scanner.  A tracked
            # oversized file must be explicitly split/reviewed before the policy
            # can approve it.
            findings.append(f"{relative}: arquivo grande demais para inspeção segura")
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            findings.append(f"{relative}: arquivo não pôde ser lido")
            continue
        if b"\0" in raw:
            # Binary content has no reliable text decoding contract.  Failing
            # closed prevents a credential embedded in a binary blob from being
            # treated as a clean scan.
            findings.append(f"{relative}: arquivo binário não pode ser inspecionado")
            continue
        text = raw.decode("utf-8", errors="replace")
        pattern = _find_secret(text)
        if pattern:
            findings.append(f"{relative}: padrão de segredo detectado ({pattern})")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="raiz do repositório")
    args = parser.parse_args(argv)
    try:
        findings = check(args.root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"policy_check: erro de inspeção: {exc}", file=sys.stderr)
        return 2
    if findings:
        print("policy_check: REPROVADO")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("policy_check: APROVADO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
