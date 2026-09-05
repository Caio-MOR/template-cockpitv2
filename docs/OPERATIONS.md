# Operations baseline

This document is the durable operating contract for this cockpit. A workflow is
not production-ready merely because its happy path runs; it must satisfy the
runtime, evidence, recovery, and credential rules below.

## Workflow runtime contract

Every state-changing workflow must:

1. Derive a deterministic idempotency key from the workflow name and input window.
2. Acquire an exclusive lock before reading or writing operational state.
3. Detect an already-completed window before causing an external side effect.
4. Retry only classified transient failures, with bounded attempts, a deadline,
   exponential backoff, and jitter.
5. Write completion markers atomically only after every required side effect succeeds.
6. Emit UTC, structured evidence containing a run ID, workflow name, input window,
   outcome, attempt count, elapsed time, code revision, and output digest when relevant.
7. Redact secrets recursively before writing logs or evidence.
8. Release locks on every controlled exit and preserve stale-lock evidence after crashes.

`tools/cockpit_runtime.py` provides the shared primitives. The example under
`workflows/_exemplo-rotina/` is executable reference behavior, not illustrative
pseudocode.

## Configuration and credentials

`.env.example` is the schema of variable names. Entries are required by default;
place `# optional` immediately before an entry or after its empty assignment when a
workflow can run without it. `tools/doctor.py` may inspect a local `.env`, but it
reports only variable names and error codes, never values.

For every real credential, add a row without its value:

| Variable | Provider | Owner | Minimum scope | Storage | Rotation | Revocation |
|---|---|---|---|---|---|---|
| _none yet_ | — | — | — | — | — | — |

Rules:

- Prefer an OS keychain or managed secret store for production credentials.
- Use `.env` only for local development and never add it to Git.
- Prefer short-lived, least-privilege tokens; record the owner and revocation URL.
- Never dump the process environment or credential-bearing HTTP headers.
- Rotation records contain the credential identifier and time, never the value.

## Data classification

| Class | Examples | Canonical location | Backup treatment |
|---|---|---|---|
| Source and decisions | code, SOPs, `.specs/` | private GitHub repository | Git history plus repository export |
| Secrets | API tokens, session material | keychain/secret manager or local `.env` | provider recovery; never plaintext backup |
| Operational state | locks, markers, cursors | workflow-local ignored state | encrypted backup when required for replay safety |
| Evidence | structured run records and summaries | ignored local logs plus approved external archive | encrypted, retention-limited archive |
| Deliverables | mail, database rows, shared files | destination system | destination's recovery policy |

## Backup and recovery

- Target RPO: 24 hours for non-reconstructable operational state.
- Target RTO: 4 hours for the cockpit baseline.
- Backups containing operational data must be encrypted before leaving the machine.
- `create_backup_manifest` records file sizes, SHA-256 digests, required paths,
  encryption algorithm, and key identifier. It does not encrypt data by itself.
- `verify_restore` validates a restored tree and rejects path traversal, missing files,
  encryption-policy mismatch, size changes, and digest changes.
- A backup is not trusted until a restore into an isolated temporary directory passes
  verification. Run that drill after changing backup scope and at least quarterly.
- Never restore over the live cockpit. Verify first, stop schedulers, then promote the
  reviewed state through an atomic rename or provider-supported restore.

## Incident response

For a suspected credential leak:

1. Revoke or disable the credential at the provider immediately.
2. Preserve redacted evidence and identify the exposure window.
3. Rotate the credential with equal or narrower scope.
4. Search the complete Git history and workflow artifacts.
5. Remove the material from every durable store; rewriting Git does not replace revocation.
6. Add a regression fixture that detects the leak shape without containing a real secret.
7. Record the decision and follow-up in `.specs/STATE.md`.

For corrupted or duplicate workflow state: stop the scheduler, preserve the lock and
evidence directory, verify the last completion marker, reconcile external side effects,
and resume only with a reviewed idempotency key.

## Maintenance cadence

- Every pull request: verdict gate, routers, policy check, operational audit, dependency
  vulnerability audit, Gitleaks, and Bandit static analysis.
- Weekly: dependency/action update review and the macOS verification run. For Python
  updates, edit `requirements.in`, regenerate the universal hashed `requirements.txt`
  with the command recorded in its header, and review both files in the same pull request.
- Monthly: credential inventory and failed-run review.
- Quarterly: encrypted restore drill and GitHub ruleset review.
- After any incident: immediate revocation/recovery exercise and a regression test.

## CI execution

This template uses hosted CI only. A generated repository may add a self-hosted runner
after a repository-specific security review, but no personal runner, label, owner, or
merge requirement belongs in the template.

GitHub native secret scanning, CodeQL, and dependency review are currently unavailable
for this private personal repository without GitHub Code Security/Secret Protection.
Full-history Gitleaks, the vendor-neutral policy gate, local hooks, hash-locked installs,
`pip-audit`, Bandit, Dependabot, and GitHub rules form the compensating controls. If the
native features become available, enable them without removing those layers.
