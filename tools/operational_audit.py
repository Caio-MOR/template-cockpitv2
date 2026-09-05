#!/usr/bin/env python3
"""Local operational-maturity audit for a WAT cockpit.

The auditor is intentionally provider-neutral and deterministic.  It measures ten
local contracts (one point each) from files on disk; it never treats a comment,
badge, or a claimed setting as proof of a control.  Hosting-provider controls that
cannot be established from a checkout are reported as ``REMOTE`` advisories and do
not change the local score.

Usage::

    python tools/operational_audit.py [ROOT]
    python tools/operational_audit.py --json [ROOT]

Exit status is 0 only for a complete 10.0 local score, 1 for a measured shortfall,
and 2 for an invalid root or an unreadable repository.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

VERSION = "1"
TITLES = (
    "deterministic architecture",
    "anti-fraud verification",
    "secrets/security",
    "reproducible supply chain",
    "vendor-neutral policy",
    "config/doctor contract",
    "structured evidence",
    "idempotency/retry/resilience",
    "backup/restore verification",
    "onboarding/maintenance",
)
_TEXT_EXTENSIONS = {"", ".md", ".py", ".json", ".ini", ".toml", ".txt", ".yml", ".yaml", ".sh", ".bat", ".vbs"}
_IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".tmp"}


@dataclass(frozen=True)
class Finding:
    """A safe finding containing paths and control names, never secret values."""

    check: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.check}  {self.path}  {self.message}"


@dataclass(frozen=True)
class CategoryResult:
    name: str
    ok: bool
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class RemoteCheck:
    check: str
    recommendation: str


@dataclass(frozen=True)
class AuditResult:
    score: float
    categories: tuple[CategoryResult, ...]
    remote_checks: tuple[RemoteCheck, ...] = ()

    @property
    def ok(self) -> bool:
        return self.score == 10.0

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(f for category in self.categories for f in category.findings)


@dataclass
class Repo:
    """A read-only snapshot, making every check pure and easy to mutate in tests."""

    root: Path
    files: frozenset[str]
    texts: dict[str, str | None] = field(default_factory=dict)

    def exists(self, path: str) -> bool:
        # Directory requirements are represented by a trailing slash; snapshots
        # contain files only, so test membership by prefix for those entries.
        return path in self.files or (path.endswith("/") and any(item.startswith(path) for item in self.files))

    def text(self, path: str) -> str | None:
        if path not in self.files:
            return None
        if path not in self.texts:
            try:
                self.texts[path] = (self.root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                self.texts[path] = None
        return self.texts[path]

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(sorted(path for path in self.files if path.startswith(prefix)))


def _files_on_disk(root: Path) -> list[str]:
    result: list[str] = []
    for directory, names, filenames in os.walk(root):
        names[:] = [name for name in names if name not in _IGNORED_DIRS]
        for filename in filenames:
            result.append(Path(directory, filename).relative_to(root).as_posix())
    return sorted(result)


def snapshot(root: str | Path) -> Repo:
    """Build a snapshot from Git's index, falling back to the checkout."""

    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError(f"root is not a directory: {base}")
    try:
        completed = subprocess.run(
            ["git", "-C", str(base), "ls-files", "-z"],
            check=True,
            capture_output=True,
            timeout=15,
        )
        listed = [item for item in completed.stdout.decode().split("\0") if item]
        files = [item for item in listed if (base / item).is_file()]
    except (OSError, UnicodeError, subprocess.SubprocessError):
        files = _files_on_disk(base)
    # Include the working tree in addition to the index.  This makes the local
    # audit useful before the first commit of a new control, while still using
    # Git as the authoritative view once a file is removed from disk.
    files = sorted(set(files) | set(_files_on_disk(base)))
    return Repo(base, frozenset(files))


def _has(repo: Repo, path: str, *needles: str) -> bool:
    text = repo.text(path)
    return text is not None and all(needle in text for needle in needles)


def _finding(check: str, path: str, message: str) -> list[Finding]:
    return [Finding(check, path, message)]


def _all_exist(repo: Repo, check: str, paths: Iterable[str]) -> list[Finding]:
    return [Finding(check, path, "required artifact is absent") for path in paths if not repo.exists(path)]


def _architecture(repo: Repo) -> list[Finding]:
    check = "ARCH"
    findings = _all_exist(repo, check, ("AGENTS.md", "workflows/CLAUDE.md", "tools/CLAUDE.md", "tests/"))
    agents = repo.text("AGENTS.md") or ""
    if not all(term in agents for term in ("Workflows", "Agents", "Tools", "WAT")):
        findings += _finding(check, "AGENTS.md", "WAT responsibilities are not declared")
    workflow = repo.text("workflows/_exemplo-rotina/workflow.md") or ""
    if not all(term in workflow for term in ("## Objetivo", "## Inputs", "## Outputs", "## Erros", "## Freios", "```mermaid")):
        findings += _finding(check, "workflows/_exemplo-rotina/workflow.md", "SOP lacks objective, contract, graph, or brakes")
    scripts = [path for path in repo.paths("workflows/") if "/scripts/" in path]
    if not scripts:
        findings += _finding(check, "workflows/", "workflow has no executable script")
    for path in repo.paths("tools/"):
        if path.endswith(".py") and path.count("/") == 1 and path != "tools/cockpit_runtime.py" and not (
            _has(repo, path, "if __name__ == \"__main__\":") or _has(repo, path, "if __name__ == '__main__':")
        ):
            findings += _finding(check, path, "top-level tool has no executable entry point")
    return findings


def _anti_fraud(repo: Repo) -> list[Finding]:
    check = "VERIFY"
    findings = _all_exist(repo, check, ("tools/gate_veredito.py", "tools/canario_gate/canario_vermelho.py", "tools/canario_gate/canario_verde.py", "conftest.py"))
    gate = repo.text("tools/gate_veredito.py") or ""
    for needle in ("ambiente_limpo", "roda_canario", "pytest", "subprocess"):
        if needle not in gate:
            findings += _finding(check, "tools/gate_veredito.py", f"verdict gate lacks independent {needle} control")
    conftest = repo.text("conftest.py") or ""
    for needle in ("PISO_COLETA", "GATES_OBRIGATORIOS", "pytest_collection_modifyitems"):
        if needle not in conftest:
            findings += _finding(check, "conftest.py", f"suite integrity contract lacks {needle}")
    ini = repo.text("pytest.ini") or ""
    if "xfail_strict = true" not in ini:
        findings += _finding(check, "pytest.ini", "non-strict xfail would hide regressions")
    readme = repo.text("README.md") or ""
    for command in (
        "python tools/gate_veredito.py",
        "python tools/lint_routers.py",
        "python tools/operational_audit.py .",
        "python tools/padrao_ouro_audit.py --tipo cockpit .",
        "ruff check .",
    ):
        if command not in readme:
            findings += _finding(check, "README.md", f"local contract omits {command}")
    return findings


def _security(repo: Repo) -> list[Finding]:
    check = "SECRETS"
    findings = _all_exist(repo, check, ("tools/policy_check.py", "tests/test_policy_check.py", ".env.example", "SECURITY.md"))
    ignore = repo.text(".gitignore") or ""
    for rule in ("/*", ".env", ".env.*", "!/.env.example"):
        if rule not in ignore:
            findings += _finding(check, ".gitignore", f"missing secret boundary {rule}")
    policy = repo.text("tools/policy_check.py") or ""
    if not all(term in policy for term in ("git", "ls-files", "return 1", "return 2")):
        findings += _finding(check, "tools/policy_check.py", "policy gate does not inspect tracked files and fail distinctly")
    for hook in (".claude/hooks/guarda_bash.py", ".claude/hooks/guarda_segredo.py", ".claude/hooks/run_hook.sh"):
        text = repo.text(hook) or ""
        if "exit 2" not in text and "sys.exit(2)" not in text:
            findings += _finding(check, hook, "hook does not fail closed")
    settings = repo.text(".claude/settings.json") or ""
    if not all(term in settings for term in (".env", "guarda_bash.py", "guarda_segredo.py")):
        findings += _finding(check, ".claude/settings.json", "editor policy does not deny secret files and commands")
    if not _has(repo, "SECURITY.md", "revoke", "replace", "secret"):
        findings += _finding(check, "SECURITY.md", "security policy lacks rotation guidance")
    readme = repo.text("README.md") or ""
    for command in (
        "python tools/policy_check.py .",
        "bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows",
        "gitleaks detect --source . --no-banner --redact --verbose",
    ):
        if command not in readme:
            findings += _finding(check, "README.md", f"local contract omits {command}")
    workflows = "\n".join(repo.text(path) or "" for path in repo.paths(".github/workflows/"))
    if "paths-ignore:" in workflows:
        findings += _finding(check, ".github/workflows/", "path-only changes can bypass a required workflow")
    return findings


def _supply_chain(repo: Repo) -> list[Finding]:
    check = "SUPPLY"
    findings = _all_exist(repo, check, ("requirements.in", "requirements.txt", ".python-version", ".github/dependabot.yml"))
    lock = repo.text("requirements.txt") or ""
    direct = repo.text("requirements.in") or ""
    entries = [line for line in lock.splitlines() if line and not line.startswith(("#", " ", "\t"))]
    if not entries or any("==" not in line for line in entries):
        findings += _finding(check, "requirements.txt", "lock must use exact versions")
    # Every lock entry is a header followed by continuation/hash lines until the
    # next header.  Comments and resolver annotations are not entries.
    blocks: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in lock.splitlines():
        is_header = bool(line and not line.startswith(("#", " ", "\t")) and "==" in line)
        if is_header:
            current = (line, [])
            blocks.append(current)
        elif current is not None:
            current[1].append(line)
    for header, continuation in blocks:
        if not any("--hash=sha256:" in line for line in continuation):
            findings += _finding(check, "requirements.txt", f"lock entry lacks sha256 hash: {header.split('==')[0]}")
    direct_names = {re.split(r"[<>=!~ ]", line.strip(), maxsplit=1)[0].lower() for line in direct.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    lock_names = {line.split("==", 1)[0].lower() for line in entries if "==" in line}
    if not direct_names <= lock_names:
        findings += _finding(check, "requirements.in", "direct dependencies are absent from the lock")
    version = (repo.text(".python-version") or "").strip()
    if not re.fullmatch(r"3\.12\.\d+", version):
        findings += _finding(check, ".python-version", "Python patch version is not exact")
    for path in repo.paths(".github/workflows/"):
        text = repo.text(path) or ""
        if re.search(r"runs-on:.*latest", text):
            findings += _finding(check, path, "moving runner label is not reproducible")
        if "persist-credentials: false" not in text and "actions/checkout@" in text:
            findings += _finding(check, path, "checkout leaves credentials persisted")
        if "uses:" in text and re.search(r"uses:\s*[^\s@]+@(?:v\d|main|master)", text):
            findings += _finding(check, path, "workflow action is not pinned to a commit SHA")
        if "pip install" in text and "--require-hashes" not in text:
            findings += _finding(check, path, "pip install does not require lock hashes")
    readme = repo.text("README.md") or ""
    if "pip-audit --strict --progress-spinner off" not in readme:
        findings += _finding(check, "README.md", "local dependency vulnerability audit is absent")
    return findings


def _vendor_neutral(repo: Repo) -> list[Finding]:
    check = "VENDOR"
    findings = _all_exist(repo, check, ("tools/policy_check.py", "tests/test_policy_check.py"))
    path = "tools/policy_check.py"
    try:
        tree = ast.parse(repo.text(path) or "")
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        stdlib = getattr(sys, "stdlib_module_names", frozenset()) | {"__future__"}
        third_party = []
        for node in imports:
            module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            if module.split(".")[0] not in stdlib and not (isinstance(node, ast.ImportFrom) and node.level):
                third_party.append(node)
        if third_party:
            findings += _finding(check, path, "policy gate imports a provider or third-party runtime")
    except SyntaxError:
        findings += _finding(check, path, "policy gate is not valid Python")
    text = repo.text(path) or ""
    if "CLAUDE" in text or "claude" in text:
        findings += _finding(check, path, "vendor-neutral policy must not depend on one agent")
    return findings


def _config(repo: Repo) -> list[Finding]:
    check = "CONFIG"
    findings = _all_exist(
        repo,
        check,
        ("tools/cockpit_runtime.py", "tools/doctor.py", "tests/test_cockpit_runtime.py", "tests/test_doctor.py", ".env.example"),
    )
    runtime = repo.text("tools/cockpit_runtime.py") or ""
    for symbol in ("ConfigField", "DoctorReport", "def doctor(", "missing", "invalid_type"):
        if symbol not in runtime:
            findings += _finding(check, "tools/cockpit_runtime.py", f"typed doctor contract lacks {symbol}")
    if "secret" not in runtime or "render" not in runtime:
        findings += _finding(check, "tools/cockpit_runtime.py", "doctor contract does not make safe reporting explicit")
    doctor = repo.text("tools/doctor.py") or ""
    for symbol in ("parse_env_schema", "missing_required", "policy_check", "version_mismatch"):
        if symbol not in doctor:
            findings += _finding(check, "tools/doctor.py", f"local doctor lacks {symbol}")
    readme = repo.text("README.md") or ""
    if not all(term in readme for term in (".env.example", ".venv", "requirements.txt")):
        findings += _finding(check, "README.md", "onboarding does not describe environment setup")
    return findings


def _evidence(repo: Repo) -> list[Finding]:
    check = "EVIDENCE"
    findings = _all_exist(repo, check, ("tools/cockpit_runtime.py", "tests/test_cockpit_runtime.py", "workflows/_exemplo-rotina/workflow.md"))
    runtime = repo.text("tools/cockpit_runtime.py") or ""
    for symbol in ("EvidenceLog", "atomic_write_json", "os.fsync", "REDACTED"):
        if symbol not in runtime:
            findings += _finding(check, "tools/cockpit_runtime.py", f"durable evidence lacks {symbol}")
    workflow = repo.text("workflows/_exemplo-rotina/workflow.md") or ""
    if not all(term in workflow for term in ("evidence", "marker", "fsync", "completed")):
        findings += _finding(check, "workflows/_exemplo-rotina/workflow.md", "SOP does not define durable success evidence")
    script = repo.text("workflows/_exemplo-rotina/scripts/rotina_exemplo.py") or ""
    if not all(term in script for term in ("EvidenceLog", "_write_marker", "completed")):
        findings += _finding(check, "workflows/_exemplo-rotina/scripts/rotina_exemplo.py", "workflow does not emit post-success evidence")
    return findings


def _resilience(repo: Repo) -> list[Finding]:
    check = "RESILIENCE"
    findings = _all_exist(repo, check, ("tools/cockpit_runtime.py", "tests/test_cockpit_runtime.py", "workflows/_exemplo-rotina/scripts/rotina_exemplo.py"))
    runtime = repo.text("tools/cockpit_runtime.py") or ""
    for symbol in ("IdempotencyLock", "RetryPolicy", "run_with_retry", "stale_after_seconds", "deadline_seconds"):
        if symbol not in runtime:
            findings += _finding(check, "tools/cockpit_runtime.py", f"runtime lacks bounded resilience primitive {symbol}")
    script = repo.text("workflows/_exemplo-rotina/scripts/rotina_exemplo.py") or ""
    if not all(term in script for term in ("IdempotencyLock", "RetryPolicy", "LockBusyError", "finally:")):
        findings += _finding(check, "workflows/_exemplo-rotina/scripts/rotina_exemplo.py", "example workflow does not apply lock/retry cleanup")
    workflow = repo.text("workflows/_exemplo-rotina/workflow.md") or ""
    if not all(term in workflow for term in ("Teto de tentativas", "Estagnação", "Concorrência")):
        findings += _finding(check, "workflows/_exemplo-rotina/workflow.md", "SOP does not document retry, stagnation, and concurrency brakes")
    return findings


def _backup(repo: Repo) -> list[Finding]:
    check = "BACKUP"
    findings = _all_exist(repo, check, ("tools/cockpit_runtime.py", "tests/test_cockpit_runtime.py"))
    runtime = repo.text("tools/cockpit_runtime.py") or ""
    for symbol in ("BackupPolicy", "create_backup_manifest", "verify_restore", "sha256", "path_traversal", "encryption"):
        if symbol not in runtime:
            findings += _finding(check, "tools/cockpit_runtime.py", f"backup contract lacks {symbol}")
    tests = repo.text("tests/test_cockpit_runtime.py") or ""
    if not all(term in tests for term in ("create_backup_manifest", "verify_restore", "hash_mismatch")):
        findings += _finding(check, "tests/test_cockpit_runtime.py", "backup restore verification lacks fault-injection coverage")
    operations = repo.text("docs/OPERATIONS.md") or ""
    for term in ("RPO", "RTO", "encrypted", "restore", "quarterly"):
        if term not in operations:
            findings += _finding(check, "docs/OPERATIONS.md", f"recovery runbook lacks {term}")
    return findings


def _onboarding(repo: Repo) -> list[Finding]:
    check = "OPERATE"
    findings = _all_exist(repo, check, ("README.md", "AGENTS.md", ".specs/STATE.md", ".specs/LESSONS.md", "SECURITY.md", "docs/OPERATIONS.md", "docs/THREAT_MODEL.md", ".github/CODEOWNERS", ".github/dependabot.yml", "pyproject.toml"))
    readme = repo.text("README.md") or ""
    for term in ("Como rodar", "Verificar", "Bootstrap", "git", "branch"):
        if term not in readme:
            findings += _finding(check, "README.md", f"onboarding lacks {term}")
    agents = repo.text("AGENTS.md") or ""
    if not all(term in agents for term in ("Verificação", "router", "Hard Rules")):
        findings += _finding(check, "AGENTS.md", "agent operating contract lacks verification and discipline")
    pyproject = repo.text("pyproject.toml") or ""
    if "ruff" not in pyproject:
        findings += _finding(check, "pyproject.toml", "maintenance lacks an explicit linter contract")
    return findings


_CHECKS: tuple[tuple[str, Callable[[Repo], list[Finding]]], ...] = (
    (TITLES[0], _architecture),
    (TITLES[1], _anti_fraud),
    (TITLES[2], _security),
    (TITLES[3], _supply_chain),
    (TITLES[4], _vendor_neutral),
    (TITLES[5], _config),
    (TITLES[6], _evidence),
    (TITLES[7], _resilience),
    (TITLES[8], _backup),
    (TITLES[9], _onboarding),
)


def _remote_checks() -> tuple[RemoteCheck, ...]:
    return (
        RemoteCheck("REMOTE-BRANCH", "Require pull requests, required checks, no bypass, resolved discussions, and independent approval when the repository has another maintainer."),
        RemoteCheck("REMOTE-SECRETS", "Enable secret scanning and push protection where the repository plan supports them."),
        RemoteCheck("REMOTE-DEPENDABOT", "Enable dependency alerts and review update pull requests for both pip and Actions."),
        RemoteCheck("REMOTE-RECOVERY", "Confirm backup retention, restore drills, and account recovery contacts outside this checkout."),
    )


def audit(root: str | Path) -> AuditResult:
    """Return the ten-category local result without network calls."""

    repo = snapshot(root) if not isinstance(root, Repo) else root
    categories = tuple(CategoryResult(name, not (findings := tuple(check(repo))), findings) for name, check in _CHECKS)
    score = round(float(sum(category.ok for category in categories)), 1)
    return AuditResult(score, categories, _remote_checks())


def format_result(result: AuditResult) -> str:
    lines = [f"operational score: {result.score:.1f}/10.0"]
    for category in result.categories:
        lines.append(f"{'OK' if category.ok else 'FAIL'}  {category.name}")
        lines.extend(f"  {finding.render()}" for finding in category.findings)
    lines.append("REMOTE checks (not included in local score):")
    lines.extend(f"  {check.check}  {check.recommendation}" for check in result.remote_checks)
    return "\n".join(lines)


def _json_result(result: AuditResult) -> dict[str, object]:
    return {
        "score": result.score,
        "categories": [
            {"name": category.name, "ok": category.ok, "findings": [finding.__dict__ for finding in category.findings]}
            for category in result.categories
        ],
        "remote_checks": [check.__dict__ for check in result.remote_checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable JSON")
    parser.add_argument("--version", action="store_true", help="print auditor version")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    try:
        result = audit(args.root)
    except (OSError, ValueError) as exc:
        print(f"operational_audit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_json_result(result), ensure_ascii=False, indent=2) if args.as_json else format_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
