# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or paste a
credential into a pull request. Contact the repository owner privately through
the channel through which repository access was granted. If that is unavailable,
use the verified contact links on [Caio-MOR's GitHub profile](https://github.com/Caio-MOR).
Include the affected file or component, reproduction steps, impact, and a safe way
to follow up. Redact tokens, personal data, and other secrets.

Reports are acknowledged as soon as practical and triaged according to impact.
This repository is a private cockpit instance; it does not provide an SLA or a bounty.

## Credential handling

- Store local credentials in an untracked `.env` file or an approved secret
  manager; never commit values to Git.
- Use the least privilege and shortest practical lifetime for each credential.
- If a credential may have been exposed, revoke it immediately with its
  provider, replace it, and record the rotation in the relevant workflow log
  without recording the value.
- The repository hooks and CI scanners are defense-in-depth controls, not a
  guarantee that every secret format will be detected.

## Supported versions

Only the default branch and the latest reviewed copy are maintained. Security
fixes should be proposed through a reviewed pull request unless the issue is
being handled privately with the owner.
