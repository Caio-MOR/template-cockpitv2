#!/usr/bin/env python3
"""Hook PreToolUse (matcher `Bash`) — bloqueia comandos git perigosos.

%% formato: cadeia — lê o JSON do stdin, decide, sai. Sem ramos que dependam de
resultado de etapa anterior; cada checagem é independente das outras.

Bloqueia (exit 2, motivo em pt-BR no stderr):
  a) `git commit` com a branch atual do cwd sendo `main`/`master`.
  b) `git push` com `--force`, `-f` ou `--force-with-lease`.
  c) qualquer comando com `--no-verify`.
  d) `git push` cujo destino explícito é `main`/`master`.

Falha fechada: entrada inválida ou exceção interna sai com exit 2. Um hook que não
conseguiu validar o comando não deve liberar uma operação potencialmente destrutiva.
"""
import json
import re
import subprocess
import sys

TETO_SUBPROC = 10


def _branch_atual(cwd: str):
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or ".", capture_output=True, text=True, timeout=TETO_SUBPROC,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _e_git_commit(cmd: str) -> bool:
    return any(subcommand == "commit" for subcommand, _ in _git_subcommands(cmd))


def _e_git_push(cmd: str) -> bool:
    return any(subcommand == "push" for subcommand, _ in _git_subcommands(cmd))


def _tem_flag_force(cmd: str) -> bool:
    # Git accepts repeated short options (``-ff``); be conservative about all
    # ``-f`` spellings and about an option assignment.  The caller only applies
    # this to an identified git push invocation.
    return bool(re.search(r"(?<!\S)(--force(?:-with-lease)?(?:=\S+)?|-f+)(?=\s|$)", cmd))


def _tem_no_verify(cmd: str) -> bool:
    return "--no-verify" in cmd


_GIT_SUBCOMMAND = re.compile(
    r"(?<![\w-])git(?:\s+\S+)*?\s+(?P<subcommand>commit|push)\b(?P<rest>.*)"
)


def _git_subcommands(cmd: str) -> list[tuple[str, str]]:
    """Find git commit/push even when global options precede the subcommand.

    Commands are inspected one shell clause at a time so a separator cannot make
    an unrelated token look like a git option.  Unknown pre-subcommand tokens are
    intentionally accepted here: conservative enforcement is preferable to
    allowing a dangerous invocation such as ``git -C repo push --force``.
    """
    found: list[tuple[str, str]] = []
    for trecho in re.split(r"&&|\|\||[;\n]", cmd):
        match = _GIT_SUBCOMMAND.search(trecho)
        if match:
            found.append((match.group("subcommand"), match.group("rest")))
    return found


def _push_destino_main_ou_master(cmd: str) -> bool:
    for subcommand, resto in _git_subcommands(cmd):
        if subcommand != "push":
            continue
        if re.search(r"(?<![\w/-])(HEAD:)?(refs/heads/)?(main|master)(?![\w/-])", resto):
            return True
    return False


def _commit_em_main_ou_master(cmd: str, cwd: str) -> bool:
    if not _e_git_commit(cmd):
        return False
    branch = _branch_atual(cwd)
    return branch in ("main", "master")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload não é um objeto JSON")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input ausente ou inválido")
        cmd = tool_input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError("command ausente ou inválido")
        cwd = payload.get("cwd") or "."
        if not isinstance(cwd, str):
            raise ValueError("cwd inválido")

        if _commit_em_main_ou_master(cmd, cwd):
            print(
                "Bloqueado: commit direto na branch main/master. Crie uma branch de "
                "feature (`git checkout -b ...`) antes de commitar.",
                file=sys.stderr,
            )
            sys.exit(2)

        if _e_git_push(cmd) and _tem_flag_force(cmd):
            print(
                "Bloqueado: `git push` com --force/-f/--force-with-lease reescreve "
                "histórico remoto. Não é permitido por hook — peça ao dono do repo.",
                file=sys.stderr,
            )
            sys.exit(2)

        if _tem_no_verify(cmd):
            print(
                "Bloqueado: --no-verify pula de propósito os hooks de verificação do "
                "git. Não é permitido neste repo.",
                file=sys.stderr,
            )
            sys.exit(2)

        if _push_destino_main_ou_master(cmd):
            print(
                "Bloqueado: push com destino explícito main/master. Abra PR a partir "
                "de uma branch de feature.",
                file=sys.stderr,
            )
            sys.exit(2)

        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        print(
            "Bloqueado: guarda_bash não conseguiu validar a solicitação "
            "(entrada inválida ou erro interno).",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
