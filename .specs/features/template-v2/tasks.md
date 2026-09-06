# Template v2 Tasks

**Design**: `.specs/features/template-v2/design.md`  
**Status**: Draft

## Test Coverage Matrix

> Generated from `AGENTS.md`, `.claude/rules/`, `pytest.ini`, `conftest.py`, existing tests, and CI. Every executable control has outcome-focused tests; declarative files have a test that rejects the relevant weakened state.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Runtime and workflow example | unit and concurrency smoke | Every retry, lock, atomic-write, redaction, and workflow completion outcome in TV2-01 | `tests/test_cockpit_runtime.py`, `tests/test_rotina_exemplo_runtime.py` | `python3 tools/gate_veredito.py` |
| Security, hooks, doctor, policy, and audits | unit | Every pass/fail branch, with path-only or names-only diagnostics | `tests/test_hooks.py`, `tests/test_doctor.py`, `tests/test_policy_check.py`, `tests/test_operational_audit.py`, `tests/test_padrao_ouro.py` | `python3 tools/gate_veredito.py` |
| Verdict and CI | smoke and declarative | Both canaries, all verdict branches, hash-only installation, SHA-pinned actions, required checks | `tests/test_ci_pinado.py`, `tests/test_criacao_nova.py` | `python3 tools/gate_veredito.py` |
| Delegation and eval ownership | declarative | Harness-neutral delegation rule (orchestrate, delegate mechanical work, author != verifier, no model named) and supplied immutable canonical-runner commit | `tests/test_runner_sincronizado.py` | `python3 tools/gate_veredito.py` |
| New-instance initialization | temporary-copy integration | Dry run mutates nothing; apply removes only allowlisted v2 records; initialized copy passes all five gates and both required 10 scores | `tests/test_new_instance.py` | `python3 tools/gate_veredito.py` |

## Gate Check Commands

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After one changed executable control | `python3 -m pytest tests/test_<affected>.py -q` |
| Five local gates | Before completing every task | `python3 tools/doctor.py && python3 tools/policy_check.py . && python3 tools/operational_audit.py . && python3 tools/lint_routers.py && python3 tools/gate_veredito.py` |
| Gold template | After template placeholder changes | `python3 tools/padrao_ouro_audit.py --tipo cockpit --template .` |
| Instance | Only after T8 | `python3 tools/validate_new_instance.py .` |
| Dependency | After lock changes | `python3 -m pip install --require-hashes -r requirements.txt` |

## Execution Plan

### Phase 1: Portable baseline

```
T1 -> T2 -> T3
```

### Phase 2: Independent verification and delivery

```
T5 -> T6
```

### Phase 3: Portable agent conventions and clean instances

```
T7 -> T8 -> T4
```

### Phase 4: Local-first verification

```
T8 -> T9
```

## Phase Execution Map

```
T1 -> T2 -> T3 -> T5 -> T6 -> T7 -> T8 -> T4
                                      \
                                       -> T9
```

## Task Breakdown

### T1: Port portable runtime and workflow example

**What**: Port generic bounded retry, process lock, atomic evidence, backup manifest, and redaction helpers plus the example workflow that exercises them.
**Where**: `tools/cockpit_runtime.py`
**Files**: `tools/cockpit_runtime.py`; `workflows/_exemplo-rotina/workflow.md`; `workflows/_exemplo-rotina/`; `tests/test_cockpit_runtime.py`; `tests/test_rotina_exemplo_runtime.py`; `workflows/CLAUDE.md`
**Depends on**: None
**Reuses**: `Cakopit-codex/tools/cockpit_runtime.py`
**Requirement**: TV2-01

**Done when**:

- [x] Retry has explicit attempt and deadline ceilings, and its tests kill a permanent-error retry and an exhausted retry.
- [x] Lock recovery, atomic evidence, recursive redaction, backup tamper detection, and concurrent workflow no-op tests pass.
- [x] The workflow graph declares its format and bounded-loop behavior.

**Tests**: unit and concurrency smoke
**Gate**: `python3 tools/gate_veredito.py`

### T2: Port portable security, hooks, and guidance

**What**: Port the generic environment schema, allowlist ignore policy, line-ending policy, secret/bypass hooks, security policy, and durable operating/security guidance without personal contacts or exception lists.
**Where**: `.env.example`
**Files**: `.env.example`; `.gitignore`; `.gitattributes`; `SECURITY.md`; `.claude/hooks/guarda_bash.py`; `.claude/hooks/guarda_segredo.py`; `.claude/hooks/run_hook.sh`; `.claude/settings.json`; `.claude/rules/conduta-colaborador.md`; `.claude/rules/estrutura-e-logging.md`; `docs/OPERATIONS.md`; `docs/THREAT_MODEL.md`; `tests/test_hooks.py`; `docs/CLAUDE.md`
**Depends on**: T1
**Reuses**: portable source controls in `Cakopit-codex`
**Requirement**: TV2-03

**Done when**:

- [x] Hook tests reject direct main commits, force pushes, unsafe writes, bypasses, and recognizable synthetic secret patterns.
- [x] `.env.example` declares names only; no source file embeds a personal contact, runner, or gitleaks exception.
- [x] `python3 tools/policy_check.py .` prints only safe paths and pattern names on a synthetic violation.

**Tests**: unit
**Gate**: `python3 -m pytest tests/test_hooks.py -q`

### T3: Port health and audit controls

**What**: Port doctor, policy, operational audit, and gold audit with their tests; preserve the actual audit interfaces and template placeholder behavior.
**Where**: `tools/operational_audit.py`
**Files**: `tools/doctor.py`; `tools/policy_check.py`; `tools/operational_audit.py`; `tools/padrao_ouro_audit.py`; `docs/padrao-ouro/PADRAO.md`; `tests/test_doctor.py`; `tests/test_policy_check.py`; `tests/test_operational_audit.py`; `tests/test_padrao_ouro.py`; `tools/CLAUDE.md`
**Depends on**: T2
**Reuses**: corresponding `Cakopit-codex/tools/` controls
**Requirement**: TV2-02, TV2-04

**Done when**:

- [x] `python3 tools/doctor.py` has a stable verdict and never prints environment values.
- [x] Component tests cover doctor, policy, operational-audit, and gold-audit pass/fail behavior without asserting a whole-repository score before CI is present.
- [x] The final Phase 2 integration gate after T6 reports operational 10.0 and gold template 10.0.
- [x] Tests prove `--template` is accepted only by the gold audit, not operational audit.

**Tests**: unit
**Gate**: `python3 -m pytest tests/test_doctor.py tests/test_policy_check.py tests/test_padrao_ouro.py tests/test_operational_audit.py -k 'not current_checkout and not json_output' -q`

### T4: Preserve and integrate the independent verdict

**What**: Preserve the already-identical `gate_veredito.py`, port the matching canaries and collection guard, then recalibrate measured collection and required gate counts for v2.
**Where**: `conftest.py`
**Files**: `conftest.py`; `pytest.ini`; `tools/gate_veredito.py`; `tools/canario_gate/canario_verde.py`; `tools/canario_gate/canario_vermelho.py`; `tests/test_criacao_nova.py`; `tests/test_ci_pinado.py`
**Depends on**: T8
**Reuses**: `template-cockpit/tools/gate_veredito.py` byte-identically and `Cakopit-codex/conftest.py`
**Requirement**: TV2-05

**Done when**:

- [x] The v2 verdict file remains byte-identical to the source template version.
- [x] Measured collection and every required-gate minimum exactly match the final v2 suite.
- [x] The red canary fails, green canary passes, AST guard rejects an unauthorized pytest hook, and the real suite passes.

**Tests**: smoke and declarative
**Gate**: `python3 tools/gate_veredito.py`

### T5: Port locked portable CI

**What**: Port the dependency inputs/lock and CI workflows that run the external verdict and all supporting checks on supported hosted runners; omit self-hosted workflow and any gitleaks exception.
**Where**: `.github/workflows/tests.yml`
**Files**: `.python-version`; `requirements.in`; `requirements.txt`; `pyproject.toml`; `.github/workflows/tests.yml`; `.github/workflows/tests-macos.yml`; `.github/workflows/gitleaks.yml`; `.github/workflows/security.yml`; `tests/test_ci_pinado.py`
**Depends on**: T3
**Reuses**: portable `Cakopit-codex` lock and hosted workflows
**Requirement**: TV2-06

**Done when**:

- [x] `python3 -m pip install --require-hashes -r requirements.txt` succeeds in a clean environment.
- [x] CI uses SHA-pinned actions with persisted checkout credentials disabled and invokes `gate_veredito.py`, router lint, policy check, operational audit, and gold audit template mode.
- [x] No workflow targets a self-hosted runner and no `.gitleaksignore` is tracked.

**Tests**: declarative
**Gate**: `python3 -m pip install --require-hashes -r requirements.txt && python3 -m pytest tests/test_ci_pinado.py -q`

### T6: Port routers and template-facing documentation

**What**: Update the root and category routers, README, and workflow/tool documentation so every v2 artifact is discoverable and initialization is understandable without exposing build history.
**Where**: `AGENTS.md`
**Files**: `AGENTS.md`; `CLAUDE.md`; `README.md`; `apps/CLAUDE.md`; `docs/CLAUDE.md`; `tools/CLAUDE.md`; `workflows/CLAUDE.md`; `.specs/STATE.md`; `.specs/LESSONS.md`; `tests/test_lint_routers.py`; `tools/lint_routers.py`
**Depends on**: T5
**Reuses**: existing router lint conventions
**Requirement**: TV2-06

**Done when**:

- [x] Every versioned tool and workflow has a live router entry.
- [x] README gives the exact five local gates, gold template audit, and initialization commands.
- [x] `python3 tools/lint_routers.py` reports `0 erro(s)`.

**Tests**: declarative
**Gate**: `python3 tools/doctor.py && python3 tools/policy_check.py . && python3 tools/operational_audit.py . && python3 tools/padrao_ouro_audit.py --tipo cockpit --template . && python3 tools/lint_routers.py && python3 tools/gate_veredito.py`

### T7: Add portable cheap-delegation and canonical eval ownership

**What**: Replace the source's tool-specific delegation language with harness-neutral guidance (no model or vendor named), and synchronize the eval runner only to the immutable canonical plugin commit supplied by the upstream runner change.
**Where**: `.claude/rules/delegacao-barata.md`
**Files**: `.claude/rules/delegacao-barata.md`; `.codex/config.toml`; `tools/eval_runner.py`; `tests/test_eval_runner.py`; `tests/test_runner_sincronizado.py`; `tests/test_evals_estrutura.py`; `evals/`; `evals/CLAUDE.md`
**Depends on**: T6
**Reuses**: `Cakopit-codex/AGENTS.md` delegation rules and supplied canonical plugin commit
**Requirement**: TV2-07, TV2-08

**Done when**:

- [x] Guidance keeps main-session orchestration, cheapest-available-model delegation for mechanical work and author != verifier, names no model or vendor, and falls back to inline execution when subagents are unavailable.
- [x] Material changes require a fresh independent verifier, but no local setting falsely claims to enforce orchestration.
- [x] Runner synchronization test records the supplied immutable plugin commit and rejects an altered local copy.

**Tests**: declarative
**Gate**: `python3 tools/gate_veredito.py`

### T8: Add explicit new-instance initialization and validation

**What**: Add a documented, dry-run-first initialization command that removes only v2-build records and resets project specification state, plus read-only new-instance validation and temporary-copy proof.
**Where**: `tools/initialize_template.py`
**Files**: `tools/initialize_template.py`; `tools/validate_new_instance.py`; `tests/test_new_instance.py`; `README.md`; `.specs/features/template-v2/`; `.specs/STATE.md`; `tools/CLAUDE.md`
**Depends on**: T7
**Reuses**: audit path-reporting and atomic-write patterns
**Requirement**: TV2-09

**Done when**:

- [x] `--dry-run` changes no file and lists only allowlisted v2-build paths; apply mode changes only those paths and initialized spec state.
- [x] A temporary generated copy, after documented initialization and placeholder resolution, passes doctor, policy, operational audit at 10.0, router lint, external verdict, and non-template gold audit at 10.0.
- [x] Validation rejects remaining v2-build records and unresolved placeholders, but does not reject later legitimate `CODEOWNERS` or gitleaks-exception files.
- [x] The initialized project state contains no stale inherited completion claim; v2 build evidence is removed only by the explicit allowlisted initialization recipe.

**Tests**: temporary-copy integration
**Gate**: `python3 tools/validate_new_instance.py . && python3 tools/gate_veredito.py`

### T9: Make verification local-first

**What**: Replace automatic hosted execution with documented local verification and manual hosted fallbacks, while keeping the same deterministic security and quality commands.
**Where**: `README.md`
**Files**: `.github/workflows/`; `AGENTS.md`; `README.md`; `docs/`; `tools/operational_audit.py`; `tools/padrao_ouro_audit.py`; `tests/test_ci_pinado.py`; `tests/test_operational_audit.py`; `tests/test_padrao_ouro.py`; `.specs/features/template-v2/`
**Depends on**: T8
**Requirement**: TV2-06

**Done when**:

- [x] Every hosted workflow is dispatch-only and the manual test fallback covers Linux and Windows.
- [x] The local contract names every required gate, requires commit/SO/Python/result evidence, and blocks an unavailable command from being reported as a pass.
- [x] The operational and gold audits enforce the local contract instead of treating an automatic workflow as proof.

**Tests**: declarative and mutation
**Gate**: `python3 tools/gate_veredito.py && python3 tools/validate_new_instance.py .`

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1 | Portable runtime component | ✅ Granular |
| T2 | Portable security boundary | ✅ Granular |
| T3 | Repository-health component | ✅ Granular |
| T4 | Existing verdict integration | ✅ Granular |
| T5 | Hosted CI delivery component | ✅ Granular |
| T6 | Router/documentation integration | ✅ Granular |
| T7 | Agent/eval ownership component | ✅ Granular |
| T8 | New-instance lifecycle component | ✅ Granular |
| T9 | Local-first verification component | ✅ Granular |

## Diagram-Definition Cross-Check

| Task | Depends On | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | none | ✅ Match |
| T2 | T1 | T1 -> T2 | ✅ Match |
| T3 | T2 | T2 -> T3 | ✅ Match |
| T4 | T8 | T8 -> T4 | ✅ Match |
| T5 | T3 | T3 -> T5 | ✅ Match |
| T6 | T5 | T5 -> T6 | ✅ Match |
| T7 | T6 | T6 -> T7 | ✅ Match |
| T8 | T7 | T7 -> T8 | ✅ Match |
| T9 | T8 | T8 -> T9 | ✅ Match |

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Runtime/workflow | unit and concurrency smoke | unit and concurrency smoke | ✅ OK |
| T2 | Security/hooks | unit | unit | ✅ OK |
| T3 | Health/audit | unit | unit | ✅ OK |
| T4 | Verdict | smoke and declarative | smoke and declarative | ✅ OK |
| T5 | CI/lock | smoke and declarative | declarative | ✅ OK |
| T6 | Routers/docs | declarative | declarative | ✅ OK |
| T7 | Delegation/eval | declarative | declarative | ✅ OK |
| T8 | New instance | temporary-copy integration | temporary-copy integration | ✅ OK |
| T9 | Verification contract | declarative and mutation | declarative and mutation | ✅ OK |
