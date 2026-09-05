# Template v2 Specification

## Problem Statement

`template-cockpit` predates the portable runtime, security, audit, and CI controls now used by the maintained cockpit. A new public template must carry those controls without inheriting one operator's runners, exceptions, or past feature records.

## Goals

- [ ] Give every repository generated from v2 deterministic local and CI validation for its portable controls.
- [ ] Keep the agent delegation policy portable and able to choose an inexpensive Codex worker when available.
- [ ] Prove a newly generated instance starts clean and passes its bootstrap validation without private configuration.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Changing `Caio-MOR/template-cockpit` | v1 remains a supported, separate template. |
| Personal self-hosted runners, `CODEOWNERS`, or gitleaks allowlist entries | They encode one organization or machine rather than a reusable template. |
| Importing historical `.specs` decisions, lessons, or completed feature records | Generated repositories must begin with their own history. |
| Replacing the canonical plugin eval runner | Its upstream ownership remains outside this template. |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| v2 repository ownership and visibility | Create it later as `Caio-MOR/template-cockpitv2`, public, matching v1 | The user chose a parallel public template under the same owner. | yes |
| Runtime baseline | Port only controls that execute with declared, locked dependencies and no personal paths | A template must work on an arbitrary clean checkout. | yes |
| Delegation | Codex delegation is opt-in; when model selection supports `gpt-5.6-luna`, use it for bounded mechanical work, otherwise use the harness default or work inline and keep the main session accountable | Cheap delegation must be possible without making a specific harness or model available. | yes |
| Eval runner | Keep plugin-repository ownership, pin the immutable canonical commit supplied by its pending upstream change, and enforce the documented synchronization contract | A copied runner must not silently become a competing source of truth or copy an unmerged local instance. | yes |
| Bootstrap cleanup | Generated instances remove or archive v2-build feature records before their first project feature | Build planning is review evidence, not template user history. | yes |

**Open questions:** none - all resolved or logged above.

## User Stories

### P1: Portable control baseline

**User Story**: As a maintainer generating a cockpit repository, I want portable runtime, security, doctor, audit, and CI controls so that a clean clone is guarded before project work begins.

**Why P1**: It is the safety and operability baseline of the new template.

**Acceptance Criteria**:

1. The template SHALL contain portable runtime guards for bounded retries, process locking, atomic evidence writes, and redacted diagnostics.
2. WHEN `python tools/doctor.py` runs in a clean generated repository THEN the template SHALL report only configuration names and a stable pass or fail verdict without printing environment values.
3. WHEN `python tools/operational_audit.py .` runs against the template or a generated instance THEN the audit SHALL report `operational score: 10.0/10.0` and report every missing portable control by path.
4. WHEN `python tools/padrao_ouro_audit.py --tipo cockpit --template .` runs against the template THEN it SHALL report `placar: 10.0/10` while accepting documented placeholders, and WHEN it runs without `--template` against an initialized instance THEN it SHALL report `placar: 10.0/10` with those placeholders resolved.
5. IF a tracked file contains a non-synthetic secret or an unsafe environment-file policy THEN `python tools/policy_check.py .` SHALL exit nonzero without echoing the secret value.

**Independent Test**: Create a clean generated instance, run doctor, policy check, operational audit, both relevant gold-audit modes, router lint, and the external verdict; then introduce a synthetic policy violation and observe the policy check fail.

### P1: Verifiable delivery

**User Story**: As a contributor, I want the validation suite and CI to judge the controls independently so that weakened tests or platform drift cannot pass unnoticed.

**Why P1**: Controls without an independent verdict are only documentation.

**Acceptance Criteria**:

1. WHEN the full suite runs THEN `python tools/gate_veredito.py` SHALL pass only after its independent guards, canaries, and pytest suite pass.
2. WHEN CI runs for a push, pull request, or merge group THEN it SHALL install only the hash-locked dependency set and execute the external verdict, router lint, policy check, operational audit, and the template-mode gold audit.
3. WHILE a workflow definition uses a third-party action THEN the workflow SHALL pin that action to an approved full commit SHA and disable persisted checkout credentials.

**Independent Test**: Run the verdict locally and inspect workflow tests that reject direct pytest CI calls, mutable action references, and unpinned dependencies.

### P2: Portable agent and eval conventions

**User Story**: As an agent working in a generated repository, I want clear cheap-delegation and eval-runner rules so that execution is economical and eval ownership remains unambiguous.

**Why P2**: The template should guide capable agents without binding users to a private setup.

**Acceptance Criteria**:

1. WHERE a Codex harness supports model selection and offers `gpt-5.6-luna`, the delegation guidance SHALL name it as the default for bounded mechanical work, and IF either condition is absent THEN the guidance SHALL use the harness default or inline execution while requiring independent verification for material changes.
2. The template SHALL document the plugin repository as the canonical owner of the eval runner, pin the immutable upstream commit supplied for v2, and require an explicit synchronized-copy update when its local runner changes.

**Independent Test**: Inspect the portable delegation rule and eval synchronization test/documentation in a clean generated instance.

### P1: Clean generated-instance bootstrap

**User Story**: As a user of the GitHub template, I want the first checkout to be free of build-specific history so that its first specification and audit belong to my project.

**Why P1**: A reusable template must not claim completed work from the template build.

**Acceptance Criteria**:

1. WHEN the documented initialization command runs in a generated repository then it SHALL use an explicit path allowlist, offer a dry run, remove only v2-build specification evidence, and initialize the project-local specification state.
2. WHEN new-instance validation runs then it SHALL require resolved instance placeholders, runtime guards, locked dependencies, CI workflows, canonical eval ownership note, and the five green local gates.
3. IF new-instance validation finds baseline contamination or an unresolved required placeholder THEN it SHALL exit nonzero and identify the artifact path without deleting user files.

**Independent Test**: Copy the finished template to a temporary directory, run the dry-run and initialization recipe, resolve placeholders, and validate the instance; add a v2-build record or unresolved placeholder in turn and observe failure. `CODEOWNERS` and a gitleaks exception added after initialization are not baseline-contamination failures.

## Edge Cases

- IF a local `.env` file is outside the repository or is a symlink THEN doctor SHALL fail closed without exposing its path target or contents.
- IF a retry reaches its deadline or attempt ceiling THEN the runtime SHALL raise a deterministic exhaustion error rather than continue looping.
- IF the gold audit is run without `--template` on placeholders THEN it SHALL report the missing instance-specific configuration.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| TV2-01 | P1: Portable control baseline | Design | Pending |
| TV2-02 | P1: Portable control baseline | Design | Pending |
| TV2-03 | P1: Portable control baseline | Design | Pending |
| TV2-04 | P1: Portable control baseline | Design | Pending |
| TV2-05 | P1: Verifiable delivery | Design | Pending |
| TV2-06 | P1: Verifiable delivery | Design | Pending |
| TV2-07 | P2: Portable agent and eval conventions | Design | Pending |
| TV2-08 | P2: Portable agent and eval conventions | Design | Pending |
| TV2-09 | P1: Clean generated-instance bootstrap | Design | Pending |

**Coverage:** 9 total, 9 mapped to tasks, 0 unmapped.

## Success Criteria

- [ ] Template mode reports operational 10.0/10.0 and gold 10.0/10; an initialized instance reports the same scores without gold template mode.
- [ ] A clean generated instance passes `doctor`, `policy_check`, `operational_audit`, `lint_routers`, and `gate_veredito`.
- [ ] Every portable control has an outcome-focused test and CI invokes the external verdict.
- [ ] Bootstrap validation rejects private-instance artifacts and accepts the prepared clean instance.
