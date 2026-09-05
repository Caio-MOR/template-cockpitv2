# Template v2 Validation

**Date**: 2026-09-05  
**Spec**: `.specs/features/template-v2/spec.md`  
**Diff range**: `main..236cdefd6a92588783249166a918e33d8588c929`
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
- `python tools/gate_veredito.py`: 217 passed; independent guards and both canaries behaved as required.
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

## Scope and Quality

- The final diff is restricted to the approved portable control, CI, documentation, test, and template-bootstrap surface.
- `git diff --check main..HEAD` found no new whitespace error.
- The optional Codex profile is example-only: `.codex/config.example.toml`; `tests/test_runner_sincronizado.py:80` asserts no tracked active profile.
- No waived or skipped tests were used. The tracked tree contains no personal runner configuration, absolute personal filesystem path, or tracked `.gitleaksignore`; policy and CI checks cover those conditions.
- The only historical copied name is the canonical eval owner in the documented, SHA-pinned synchronization attestation; it is required by the specification.
