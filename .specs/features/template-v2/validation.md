# Template v2 Validation

**Date**: 2026-09-05  
**Spec**: `.specs/features/template-v2/spec.md`  
**Diff range**: `main..21bcf45b469c2f7983322fd827aff974af7d5a1b`
**Verifier**: independent verifier (author != verifier)

## Validation

**Result**: PASS

## Task Completion

T1–T8 have implementation and outcome coverage in the final 216-test suite. The T3 integration checkbox is stale in `tasks.md`; the required final integration outcomes were reproduced below.

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | Evidence | Result |
| --- | --- | --- | --- |
| P1 baseline 1 | Bounded retry, exclusive locking, atomic evidence, and redaction exist and behave safely. | `tests/test_cockpit_runtime.py:105` — `lock.acquire()`; `tests/test_cockpit_runtime.py:108` — `assert len(stale_files) == 1`; `tests/test_cockpit_runtime.py:137` — `assert result == "done"`; `tests/test_cockpit_runtime.py:230` — `assert payload["fields"]["token"] == "[REDACTED]"`. | PASS |
| P1 baseline 2 | Doctor exposes configuration names only and emits a stable verdict. | `tests/test_cockpit_runtime.py:43` — `assert "top-secret" not in output`; `tests/test_doctor.py:119` — `assert result.returncode == 0`. | PASS |
| P1 baseline 3 | Operational audit reports `operational score: 10.0/10.0` and path-only missing-control findings. | `tests/test_operational_audit.py:29` — `assert report.score == 10.0`; reproduced command returned `operational score: 10.0/10.0`. | PASS |
| P1 baseline 4 | Gold audit reports `placar: 10.0/10` in template mode and in an initialized, resolved instance without template mode. | `tests/test_padrao_ouro.py:29` — `assert "placar: 10.0/10" in resultado.stdout`; fresh-instance `tools/validate_new_instance.py` completed its non-template gold gate. | PASS |
| P1 baseline 5 | Tracked secrets or unsafe environment policy exit nonzero without echoing secret values. | `tests/test_policy_check.py:36` — `assert any(".env.local" in finding for finding in findings)`; `tests/test_policy_check.py:48` — `assert "secret-value" not in rendered`. | PASS |
| Verifiable delivery 1 | External verdict passes only after its guard, both canaries, and suite pass. | `tools/gate_veredito.py:64`; reproduced result: guards OK, red canary rejected, green canary accepted, 216 passed. | PASS |
| Verifiable delivery 2 | CI uses hash-locked dependencies and runs verdict, router lint, policy, operational, and template gold gates. | `tests/test_ci_pinado.py:216`, `tests/test_ci_pinado.py:259`; workflow assertions passed in the 216-test gate. | PASS |
| Verifiable delivery 3 | Third-party actions are full-SHA pinned and checkout credentials are disabled. | `tests/test_ci_pinado.py:104`, `tests/test_ci_pinado.py:127`. | PASS |
| Portable agent 1 | Luna is conditional on model-selection support; fallback is harness default or inline execution with independent verification. | `.claude/rules/delegacao-barata.md:3`; `tests/test_runner_sincronizado.py:76`. | PASS |
| Portable agent 2 | Canonical eval-runner ownership and the supplied immutable upstream commit are documented and pinned. | `tests/test_runner_sincronizado.py:37`, `tests/test_runner_sincronizado.py:63`; pin is `666dbad10c7429138cfda7752afeccbdafd333e7`. | PASS |
| Bootstrap 1 | Initialization is dry-run-first, allowlisted, non-destructive to customized state, and symlink-safe. | `tools/initialize_template.py:14`, `tools/initialize_template.py:72`; `tests/test_new_instance.py:42`, `tests/test_new_instance.py:76`. | PASS |
| Bootstrap 2 | Validation requires resolved declared placeholders and executes runtime/CI/eval ownership plus all green local gates. | `tools/validate_new_instance.py:15`, `tools/validate_new_instance.py:50`; fresh cloned instance passed `validate_new_instance.py`. | PASS |
| Bootstrap 3 | Contamination or unresolved placeholders fail with paths and no deletion of user files. | `tools/validate_new_instance.py:25`, `tests/test_new_instance.py:59`, `tests/test_new_instance.py:76`. | PASS |

## Fresh Generated Instance

A clean local clone at `4a1f0329a682774d5f9f9d23c6ba8a2f6e62e136` was placed on a named branch. The documented dry run listed only `.specs/features/template-v2` and `.specs/STATE.md`; apply removed that directory and created local state. Replacing exactly the six declared values in `AGENTS.md`, `README.md`, and `.github/CODEOWNERS` then produced `validate_new_instance: APROVADO`. That command includes doctor, policy, operational audit, router lint, external verdict, and non-template gold audit.

## Gate Check

- Python environment: 3.12.13.
- `python tools/gate_veredito.py`: 220 passed; independent guards and both canaries behaved as required.
- `python tools/doctor.py`: `doctor: APROVADO`.
- `python tools/policy_check.py .`: `policy_check: APROVADO`.
- `python tools/operational_audit.py .`: `operational score: 10.0/10.0`.
- `python tools/padrao_ouro_audit.py --tipo cockpit --template .`: `placar: 10.0/10`.
- `python tools/lint_routers.py`: `lint_routers: 0 erro(s)`.
- CI-equivalent `bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows`: clean.
- `pip-audit --strict --progress-spinner off`: `No known vulnerabilities found`.
- No skipped tests were reported; no test count decreased in the final gate.

## Discrimination Sensor

Six behavior-level mutations were made only in disposable git worktrees; the real-tree porcelain matched its captured baseline after cleanup.

| Mutation | File:line | Targeted test result |
| --- | --- | --- |
| Disabled stale-lock reacquisition | `tools/cockpit_runtime.py:284` | Killed by `tests/test_cockpit_runtime.py:99`. |
| Allowed custom state to be overwritten | `tools/initialize_template.py:72` | Killed by `tests/test_new_instance.py:76`. |
| Disabled secret-content inspection | `.claude/hooks/guarda_segredo.py:133` | Killed by `tests/test_hooks.py:190`. |
| Allowed tracked `.env.*` files | `tools/policy_check.py:80` | Killed by `tests/test_policy_check.py:30`. |
| Ignored v2 build-record contamination | `tools/validate_new_instance.py:26` | Killed by `tests/test_new_instance.py:59`. |
| Disabled documented per-line placeholder exemption | `tools/validate_new_instance.py:13` | Killed by `tests/test_new_instance.py:59`. |

**Sensor result**: 6/6 killed; PASS.

## Post-publication Windows Runtime Re-verification

Commit `236cdef` addresses the Windows 2025 failure in which `actions/setup-python` did not provide the exact `3.12.13` patch declared by `.python-version`. Linux and macOS retain the pinned `actions/setup-python` step. Windows now uses the full-SHA-pinned `astral-sh/setup-uv` action, reads the repository pin, creates a managed `.venv`, and runs both the hash-locked install and external verdict through `.venv\Scripts\python.exe` (`.github/workflows/tests.yml:62`, `.github/workflows/tests.yml:70`, `.github/workflows/tests.yml:79`, `.github/workflows/tests.yml:92`).

`tests/test_ci_pinado.py:278`–`tests/test_ci_pinado.py:283` asserts every part of that Windows contract. The focused test passed and the independent verdict reported 217 passing tests. A disposable-worktree mutation that removed `--managed-python` from `.github/workflows/tests.yml:71` was killed by the assertion at `tests/test_ci_pinado.py:281`; the real worktree porcelain matched its baseline after cleanup.

## Post-publication Windows Lock Re-verification

Commit `59f37e87007981a5afd886624fca90b074ea7879` removes the Windows use of `os.kill(pid, 0)`: on Windows this emits `CTRL_C_EVENT` to the shared console rather than providing the POSIX liveness probe. `_windows_process_state` uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`, declares `HANDLE`/`DWORD` argument and result types, reads `GetExitCodeProcess`, and closes every non-null handle in `finally` (`tools/cockpit_runtime.py:42`, `tools/cockpit_runtime.py:58`, `tools/cockpit_runtime.py:67`). Only invalid PID (`ERROR_INVALID_PARAMETER`) is dead; access-denied, query failure, and unknown states return indeterminate, which `_pid_is_alive` treats as alive (`tools/cockpit_runtime.py:60`, `tools/cockpit_runtime.py:76`). POSIX retains `os.kill(pid, 0)` (`tools/cockpit_runtime.py:78`).

`tests/test_cockpit_runtime.py:101`–`tests/test_cockpit_runtime.py:110` parameterizes live, dead, and indeterminate Windows process states and asserts no `os.kill` call. The focused test reported 3 passing cases and the full independent verdict reported 220 passing tests. A disposable-worktree mutation changing fail-closed indeterminate handling to dead was killed by `tests/test_cockpit_runtime.py:109`; the real worktree porcelain matched its baseline after cleanup.

## Post-publication Windows Marker Re-verification

Commit `7c5690d3898f9430ddb57e92f90e55cebdf16cb0` fixes the real Windows failure caused by calling `fsync` on a read-only `rb` descriptor, which returns `EBADF`. The marker is still written first, then reopened with writable binary access (`r+b`) for durable flush before the existing atomic `os.replace` (`workflows/_exemplo-rotina/scripts/rotina_exemplo.py:83`, `workflows/_exemplo-rotina/scripts/rotina_exemplo.py:89`). The workflow error contract documents the Windows-specific durable-marker failure without changing idempotency or rename semantics (`workflows/_exemplo-rotina/workflow.md:55`).

Focused proof: `tests/test_rotina_exemplo_runtime.py:113` — `test_atomic_marker_fault_preserves_previous_marker` passed. The patch is limited to the writable flush descriptor and its workflow documentation.

## Final UTF-8 and macOS Runtime Re-verification

Commit `a62e63eabe327f3e696712def444aaf8e7aa2186` makes all workflow-runtime test reads explicit UTF-8 (`tests/test_rotina_exemplo_runtime.py:33`, `tests/test_rotina_exemplo_runtime.py:44`, `tests/test_rotina_exemplo_runtime.py:117`), fixing Windows decoding under its locale-dependent default encoding without changing test outcomes.

Commit `a6f313de252d33e31d0696095babb9da8ba740ff` applies the already-reviewed exact managed-Python strategy to both macOS jobs after the macOS arm64 runner lacked `3.12.13`: two full-SHA-pinned `setup-uv` steps, `.python-version` driven managed environments, hash-locked installation, and `.venv` executables for every gate (`.github/workflows/tests-macos.yml:30`, `.github/workflows/tests-macos.yml:36`, `.github/workflows/tests-macos.yml:58`, `.github/workflows/tests-macos.yml:64`). The shared declarative gate asserts both Windows and macOS contracts (`tests/test_ci_pinado.py:271`–`tests/test_ci_pinado.py:294`).

Targeted proof ran all workflow-runtime tests and the shared CI portability assertion: 6 passed. The external verdict remained green with 220 passing tests. The worktree was clean before this report update.

## Final Windows Git-Path Hook Re-verification

Commit `21bcf45b469c2f7983322fd827aff974af7d5a1b` fixes the Windows parser failure where POSIX `shlex` consumed backslashes in `git -C C:\\...` targets. Windows now uses non-POSIX tokenization and removes only surrounding quote delimiters; POSIX keeps its previous tokenization (`.claude/hooks/guarda_bash.py:94`–`.claude/hooks/guarda_bash.py:98`). The parsed `-C` target still feeds the existing branch check, so `main` and `master` remain blocked (`.claude/hooks/guarda_bash.py:112`–`.claude/hooks/guarda_bash.py:137`). Malformed tokenization continues to add an unknown directory and fail closed (`.claude/hooks/guarda_bash.py:99`–`.claude/hooks/guarda_bash.py:102`).

Focused proof: the hook suite reported 49 passing tests. An isolated platform-mocked parser probe preserved `C:\\tmp\\repo`, classified its branch as `main`, and blocked the commit without mutating global `os.name`; an unterminated quoted command also failed closed. The external verdict remained green with 220 passing tests. The worktree was clean before this report update.

## Scope and Quality

- The final diff is restricted to the approved portable control, CI, documentation, test, and template-bootstrap surface.
- `git diff --check main..HEAD` found no new whitespace error.
- The optional Codex profile is example-only: `.codex/config.example.toml`; `tests/test_runner_sincronizado.py:80` asserts no tracked active profile.
- No waived or skipped tests were used. The tracked tree contains no personal runner configuration, absolute personal filesystem path, or tracked `.gitleaksignore`; policy and CI checks cover those conditions.
- The only historical copied name is the canonical eval owner in the documented, SHA-pinned synchronization attestation; it is required by the specification.

## Local-first Amendment Independent Re-verification

**Date**: 2026-09-05
**Diff range**: `b016698..04f978905e4e4066b3599f3661e6d4a704eb9722`
**Verifier**: independent verifier (author != verifier)
**Result**: PASS

The current branch was checked locally only. No hosted workflow was dispatched and no
automatic trigger was restored. All four workflow files declare only
`workflow_dispatch`; the retained manual test fallback still names both
`ubuntu-24.04` and `windows-2025`
(`tests/test_ci_pinado.py:168`–`tests/test_ci_pinado.py:179`;
`.github/workflows/tests.yml:10`–`tests.yml:28`). The historical hosted
cross-platform reports above describe earlier revisions only and are not evidence for
this amendment.

The local canonical-environment requirement is explicit in
`AGENTS.md:50`–`AGENTS.md:53` and the README requires recorded commit, OS, Python,
and each command result while blocking unavailable or failed commands
(`README.md:27`–`README.md:48`). It supplies executable POSIX and PowerShell
bindings and the Windows managed-`uv` recipe
(`README.md:11`–`README.md:32`). Security, audit, and evidence are local
contracts: the auditor rejects missing local commands
(`tools/operational_audit.py:196`–`tools/operational_audit.py:205`,
`tools/operational_audit.py:228`–`tools/operational_audit.py:235`) and the
ten-category assertion is outcome-tested at `tests/test_operational_audit.py:24`–`tests/test_operational_audit.py:30`.

### Fresh initialized-instance proof

A fresh local clone at `04f978905e4e4066b3599f3661e6d4a704eb9722` used a new
3.12.13 virtual environment created with the documented `uv` commands and
hash-locked installation. After replacing only the six documented instance
placeholders, the documented dry run listed only
`.specs/features/template-v2` and `.specs/STATE.md`; initialization applied those
allowlisted changes. On a named fixture branch,
`validate_new_instance: APROVADO` passed, including its non-template gold audit and
all bootstrap gates.

### Local evidence

Environment: macOS 26.6.2, Python 3.12.13, commit
`04f978905e4e4066b3599f3661e6d4a704eb9722`.

| Command | Result |
| --- | --- |
| `PY tools/gate_veredito.py` | `veredito: VERDE`; 223 passed, with both canaries and independent guards green |
| `PY tools/doctor.py` | `doctor: APROVADO` |
| `PY tools/policy_check.py .` | `policy_check: APROVADO` |
| `PY tools/operational_audit.py .` | `operational score: 10.0/10.0` |
| `PY tools/lint_routers.py` | `0 erro(s)` |
| `PY tools/padrao_ouro_audit.py --tipo cockpit --template .` | `placar: 10.0/10` |
| `PY -m ruff check .` | passed |
| `PY -m pip_audit --strict --progress-spinner off` | `No known vulnerabilities found` |
| `PY -m bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows` | passed |
| checksum-verified Gitleaks v8.30.1 `detect --source . --no-banner --redact --verbose` | archive checksum passed; 60 commits scanned; no leaks found |

### Discrimination sensor

Three behavior-level faults were injected only into isolated throwaway worktrees. The
real source-tree porcelain matched its baseline afterward.

| Mutation | Targeted command | Result |
| --- | --- | --- |
| Added `push:` beside `workflow_dispatch` in `.github/workflows/tests.yml` | `tests/test_ci_pinado.py::test_workflows_sao_apenas_fallback_manual_e_matriz_cobre_windows` | Killed: assertion at `tests/test_ci_pinado.py:174` rejected the trigger |
| Removed the required local Bandit command from `README.md` | `tests/test_operational_audit.py::test_current_checkout_is_a_complete_local_ten` | Killed: local score fell to 9.0 |
| Removed the structured-evidence category from the operational audit | `tests/test_operational_audit.py::test_current_checkout_is_a_complete_local_ten` | Killed: local score fell to 9.0 |

**Sensor result**: 3/3 killed; PASS. No specification-precision gap or surviving
mutation was found, so no lesson entry was created.
