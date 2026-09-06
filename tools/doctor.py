#!/usr/bin/env python3
"""Local, dependency-free health check for a cockpit checkout.

The doctor checks five things: the interpreter matches the complete version in
``.python-version``, Git is on a named branch, the versioned pre-push hook is
active (``core.hooksPath`` points at ``.githooks`` and the hook file exists), the
tracked-file security policy passes, and the local environment satisfies the
names declared by ``.env.example``.  It intentionally reports names and error
codes only; values from ``.env`` and ``os.environ`` never leave this module.

Environment schema convention
-----------------------------

Every non-comment line in ``.env.example`` is an assignment whose *name* is a
contract field.  Fields are required by default.  Put ``# optional`` on the
line immediately before an assignment (or after its empty assignment) to make
that one field optional, for example::

    # optional
    REPORT_URL=

    API_TOKEN=

The example file must contain empty assignments: it declares names, not sample
or real values.  The local ``.env`` may contain values, but only names present
in the example are accepted.  Values are used transiently to check presence
and are never returned, logged, or included in an exception message.

Exit codes: 0 = approved, 1 = failed checks, 2 = invalid invocation or an
inspection error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

try:  # Works both as ``python -m tools.doctor`` and ``python tools/doctor.py``.
    from tools import policy_check
except ImportError:  # pragma: no cover - exercised by direct script invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import policy_check


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_ASSIGNMENT = re.compile(
    r"^(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)
_VERSION = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
_OPTIONAL = re.compile(r"(?:^|[\s\[(])optional(?:$|[\s:\])])", re.IGNORECASE)


@dataclass(frozen=True)
class EnvField:
    """A name from ``.env.example`` and whether it must be populated."""

    name: str
    required: bool = True


@dataclass(frozen=True)
class DoctorIssue:
    """A safe issue: it can contain no environment values."""

    check: str
    code: str
    name: str | None = None


HOOKS_DIR = ".githooks"
PRE_PUSH_HOOK = f"{HOOKS_DIR}/pre-push"

# Static repair instructions per code.  They name commands and repository paths
# only, never a value from the environment.
FIXES = {
    "hooks_path_not_configured": f"git config core.hooksPath {HOOKS_DIR}",
    "hook_file_missing": f"restaure {PRE_PUSH_HOOK} a partir do repositório (git checkout -- {PRE_PUSH_HOOK})",
}


@dataclass(frozen=True)
class DoctorReport:
    """Result containing only check names, field names, and stable error codes."""

    issues: tuple[DoctorIssue, ...] = ()
    checked: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    def render(self) -> str:
        lines = [f"doctor: {'APROVADO' if self.ok else 'REPROVADO'}"]
        for issue in self.issues:
            subject = f" {issue.name}" if issue.name else ""
            fix = FIXES.get(issue.code)
            hint = f" (conserto: {fix})" if fix else ""
            lines.append(f"- {issue.check}{subject}: {issue.code}{hint}")
        return "\n".join(lines)


def _git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("git inspection failed") from exc
    return result.stdout.strip()


def _check_git(root: Path, expected_branch: str | None) -> list[DoctorIssue]:
    issues: list[DoctorIssue] = []
    try:
        if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
            return [DoctorIssue("git", "not_repository")]
    except RuntimeError:
        return [DoctorIssue("git", "not_repository")]
    try:
        branch_result = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return [DoctorIssue("git", "inspection_failed")]
    try:
        git_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    except RuntimeError:
        return [DoctorIssue("git", "inspection_failed")]
    if git_root != root.resolve():
        return [DoctorIssue("git", "root_not_repository")]
    if branch_result.returncode != 0:
        return [DoctorIssue("git", "detached_head")]
    branch = branch_result.stdout.strip()
    if not branch:
        issues.append(DoctorIssue("git", "detached_head"))
    elif expected_branch is not None and branch != expected_branch:
        issues.append(DoctorIssue("git", "unexpected_branch", "branch"))
    return issues


def _check_hooks(root: Path) -> list[DoctorIssue]:
    """The versioned pre-push hook only runs when the clone opted in.

    Git ignores ``.githooks/`` unless ``core.hooksPath`` points there, so a clone
    that skipped ``initialize_template.py`` pushes without any local gate.  The
    doctor makes that silent state visible and names the one-line repair.
    """
    issues: list[DoctorIssue] = []
    try:
        configured = _git(root, "config", "--get", "core.hooksPath")
    except RuntimeError:
        configured = ""
    expected = (root / HOOKS_DIR).resolve()
    candidate = Path(configured)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not configured or resolved != expected:
        issues.append(DoctorIssue("hooks", "hooks_path_not_configured"))
    if not (root / PRE_PUSH_HOOK).is_file():
        issues.append(DoctorIssue("hooks", "hook_file_missing"))
    return issues


def _parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(text.strip())
    if not match:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _check_python(root: Path, current_version: Sequence[int] | None) -> list[DoctorIssue]:
    path = root / ".python-version"
    try:
        configured = _parse_version(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return [DoctorIssue("python", "version_file_unreadable")]
    if configured is None:
        return [DoctorIssue("python", "version_not_exact")]
    actual = tuple(current_version or sys.version_info[:3])
    if actual != configured:
        return [DoctorIssue("python", "version_mismatch")]
    return []


def _comment_is_optional(line: str) -> bool:
    return line.lstrip().startswith("#") and bool(_OPTIONAL.search(line.lstrip()[1:]))


def _strip_inline_comment(value: str) -> tuple[str, bool]:
    """Return a value and whether its trailing comment marks it optional."""
    # The schema convention is deliberately narrow: only an empty assignment
    # may use an inline optional marker, preventing a value from being mistaken
    # for a comment.
    if value.strip().lower().endswith("# optional"):
        before = value[: value.lower().rfind("# optional")]
        return before.strip(), True
    return value.strip(), False


def parse_env_schema(path: str | Path) -> tuple[tuple[EnvField, ...], tuple[str, ...]]:
    """Parse names from an example file, returning safe structural errors."""
    fields: list[EnvField] = []
    errors: list[str] = []
    pending_optional = False
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return (), ("schema_unreadable",)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            pending_optional = _comment_is_optional(stripped)
            continue
        match = _ENV_ASSIGNMENT.fullmatch(stripped)
        if not match:
            errors.append("schema_malformed")
            pending_optional = False
            continue
        name = match.group("name")
        value, inline_optional = _strip_inline_comment(match.group("value"))
        if value:
            errors.append("schema_contains_value")
        if not _ENV_NAME.fullmatch(name):  # Kept explicit for future parser changes.
            errors.append("schema_invalid_name")
        if any(field.name == name for field in fields):
            errors.append("schema_duplicate_name")
        else:
            fields.append(EnvField(name, required=not (pending_optional or inline_optional)))
        pending_optional = False
    return tuple(fields), tuple(errors)


def _parse_local_env(path: Path) -> tuple[dict[str, str], list[str]]:
    """Parse local dotenv assignments without exposing their values."""
    if not path.exists():
        return {}, []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}, ["env_unreadable"]
    values: dict[str, str] = {}
    errors: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_ASSIGNMENT.fullmatch(stripped)
        if not match:
            errors.append("env_malformed")
            continue
        name, value = match.group("name"), match.group("value").strip()
        if name in values:
            errors.append("env_duplicate_name")
        else:
            values[name] = value
    return values, errors


def _safe_env_path(root: Path, env_file: str | Path) -> Path | None:
    """Resolve an env file only when every path component stays in ``root``.

    This check is deliberately stricter than ``Path.resolve`` alone: a symlink
    to another file inside the repository is still rejected, because it makes
    the target mutable outside the caller's stated path and is easy to turn
    into an accidental secret disclosure.
    """
    repo = root.resolve()
    requested = Path(env_file)
    candidate = requested if requested.is_absolute() else repo / requested
    try:
        absolute = Path(os.path.abspath(candidate))
        relative = absolute.relative_to(repo)
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(repo)
        current = repo
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return None
    except (OSError, RuntimeError, ValueError):
        return None
    return absolute


def _check_environment(
    root: Path,
    env_file: str | Path,
    environ: Mapping[str, str] | None,
) -> list[DoctorIssue]:
    schema, schema_errors = parse_env_schema(root / ".env.example")
    issues = [DoctorIssue("environment", error) for error in schema_errors]
    safe_path = _safe_env_path(root, env_file)
    if safe_path is None:
        return [*issues, DoctorIssue("environment", "env_file_unsafe")]
    local, local_errors = _parse_local_env(safe_path)
    issues.extend(DoctorIssue("environment", error) for error in local_errors)
    allowed = {field.name for field in schema}
    issues.extend(DoctorIssue("environment", "unknown_name", name) for name in sorted(set(local) - allowed))
    source = dict(os.environ if environ is None else environ)
    source.update(local)
    for field in schema:
        if field.required and not source.get(field.name, "").strip():
            issues.append(DoctorIssue("environment", "missing_required", field.name))
    return issues


def check(
    root: str | Path = ".",
    *,
    expected_branch: str | None = None,
    env_file: str | Path = ".env",
    environ: Mapping[str, str] | None = None,
    python_version: Sequence[int] | None = None,
) -> DoctorReport:
    """Run all checks; return no environment values or policy-file contents."""
    repo = Path(root).resolve(strict=False)
    if not repo.is_dir():
        return DoctorReport((DoctorIssue("repository", "root_not_directory"),))
    issues = _check_python(repo, python_version)
    issues.extend(_check_git(repo, expected_branch))
    issues.extend(_check_hooks(repo))
    try:
        if policy_check.check(repo):
            issues.append(DoctorIssue("security", "policy_failed"))
    except (OSError, RuntimeError, ValueError):
        issues.append(DoctorIssue("security", "policy_unavailable"))
    issues.extend(_check_environment(repo, env_file, environ))
    return DoctorReport(tuple(issues), ("python", "git", "hooks", "security", "environment"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="raiz do repositório")
    parser.add_argument("--branch", dest="expected_branch", help="exige este branch ativo")
    parser.add_argument("--env-file", default=".env", help="arquivo local de ambiente")
    args = parser.parse_args(argv)
    report = check(args.root, expected_branch=args.expected_branch, env_file=args.env_file)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
