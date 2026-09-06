# Threat model

## Assets

- API credentials and external service sessions.
- Private source, instructions, workflow state, logs, and personal data.
- GitHub repository integrity and Actions credentials.
- Automation outputs and evidence used to decide whether work completed.
- Dependency, action, plugin, and agent-instruction integrity.

## Trust boundaries

1. Pull-request content entering an ephemeral GitHub runner.
2. Agent or editor tool requests entering the local filesystem and shell.
3. Local secret storage entering a workflow subprocess or network client.
4. External dependencies, actions, and plugins entering trusted execution.
5. Untrusted input entering prompts, parsers, logs, or downstream services.
6. Local operational state crossing into encrypted backup storage.

## Principal threats and controls

| Threat | Preventive controls | Detection/recovery |
|---|---|---|
| Accidental secret commit | deny-by-default ignore, fail-closed hooks, `policy_check.py` | full-history Gitleaks, revoke-and-rotate runbook |
| Malicious or compromised PR | local verification evidence, protected history, pinned optional hosted actions | reviewed merge and native GitHub protections |
| Dependency/action substitution | hash-locked Python dependencies, full-SHA action pins, fixed runtimes | Dependabot, `pip-audit`, Bandit, static gates |
| Agent/editor bypass | vendor-neutral local policy gate; hooks are defense in depth | mutation tests and complete-history scan |
| Duplicate or overlapping run | deterministic key and exclusive lock | structured SKIP evidence and stale-lock forensics |
| Partial success or crash | atomic completion marker written last | reconciliation using run ID, digest, and external state |
| Infinite retry or retry storm | transient classification, deadline, capped exponential backoff and jitter | exhausted-run evidence and circuit-breaker policy |
| Log or evidence leakage | recursive redaction; no environment/header dumps | scanning, retention, incident response |
| Lost or corrupted local state | encrypted backups and checksummed manifest | isolated restore drill with RPO/RTO |
| Prompt or content injection | deterministic tools own side effects; explicit schemas and allowlists | adversarial tests and human review for new capabilities |

## Accepted constraints

- A sole-maintainer private repository cannot require an independent human approval
  without making routine maintenance impossible. Conversation resolution, protected
  history, CODEOWNERS, and recorded local verification evidence are the compensating controls.
- Editor hooks cannot secure arbitrary local programs. Local tests and human review
  are the default verification boundary; GitHub PR protections remain separate controls.
- Pattern scanners cannot recognize every possible secret. Least privilege, short
  lifetimes, rotation, and rapid revocation remain mandatory.
- Native GitHub secret scanning, CodeQL, and dependency review are unavailable on the
  repository's current plan/type; local Gitleaks, local policy scanning, `pip-audit`, and
  Bandit compensate for them.
