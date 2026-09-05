"""Rotina-exemplo: contrato mínimo de um script agendado do cockpit.

O lock por janela torna o run idempotente e impede dois processos concorrentes. O
marker e a evidência de conclusão usam escrita durável; nenhum valor sensível vai para
o log. Sem dependência externa. Exit 0 = sucesso; exit 1 = falha.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

# The scheduler invokes this file by absolute path, so its directory (not the
# repository root) is normally ``sys.path[0]``.  Make the shared tools import
# independent of the scheduler's current working directory.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.cockpit_runtime import (  # noqa: E402 - repo root is installed above
    EvidenceLog,
    IdempotencyLock,
    LockBusyError,
    RetryExhaustedError,
    RetryPolicy,
    RunIdentity,
    SecretRedactor,
    TransientError,
    run_with_retry,
)

PASTA = Path(__file__).resolve().parents[1]
LOGS = PASTA / "logs"
LOG = LOGS / "log.txt"
MARKER = LOGS / ".last_ok"
LOCK = LOGS / ".rotina_exemplo.lock"
EVIDENCE = LOGS / "evidence"

# Freio: teto de tentativas da etapa de processamento (regra loop-engineering).
TETO_TENTATIVAS = 3
PRAZO_SEGUNDOS = 300.0

_REDACTOR = SecretRedactor()


def log_line(nivel: str, mensagem: str) -> None:
    """`data\\thora\\tNIVEL\\tmensagem` — uma linha por evento, append."""
    LOGS.mkdir(parents=True, exist_ok=True)
    agora = datetime.now()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{agora:%Y-%m-%d}\t{agora:%H:%M:%S}\t{nivel}\t{_REDACTOR.text(mensagem)}\n")


def insumo_disponivel() -> bool:
    """Numa rotina real: existe o arquivo? a API respondeu? Aqui, sempre sim."""
    return True


def processar(tentativa: int) -> bool:
    """Numa rotina real: a transformação. Devolve se deu certo nesta tentativa."""
    return True


def entregar() -> None:
    """Numa rotina real: e-mail, upload, escrita em tabela. Aqui, nada."""


def _marker_date() -> str | None:
    """Retorna a data coberta pelo marker, tratando marker interrompido como ausente."""
    try:
        value = MARKER.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _write_marker(covered_on: date) -> None:
    """Marker texto compatível, escrito em arquivo temporário + rename durável."""
    temporary = MARKER.with_name(f".{MARKER.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(f"{covered_on:%Y-%m-%d}\n", encoding="utf-8")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, MARKER)
    finally:
        temporary.unlink(missing_ok=True)
    # POSIX can fsync a directory entry; Windows does not permit opening a
    # directory this way. The rename is still atomic on both platforms.
    try:
        directory_fd = os.open(LOGS, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _process_with_retry() -> bool:
    """Run the boolean example step through the shared bounded retry primitive."""
    attempts = 0

    def attempt() -> bool:
        nonlocal attempts
        attempts += 1
        if processar(attempts):
            return True
        log_line("WARN", f"tentativa {attempts}/{TETO_TENTATIVAS} falhou")
        raise TransientError("processamento transitório")

    try:
        run_with_retry(
            attempt,
            RetryPolicy(
                max_attempts=TETO_TENTATIVAS,
                deadline_seconds=PRAZO_SEGUNDOS,
                base_delay_seconds=0.1,
                max_delay_seconds=2.0,
                jitter_ratio=0,
            ),
        )
    except RetryExhaustedError:
        log_line("ERRO", f"teto de {TETO_TENTATIVAS} tentativas estourado; parando")
        return False
    return True


def main(covered_on: date | None = None) -> int:
    covered_on = covered_on or date.today()
    run_key = covered_on.isoformat()
    identity = RunIdentity("rotina_exemplo", run_key)
    try:
        lock = IdempotencyLock(LOCK, identity, stale_after_seconds=PRAZO_SEGUNDOS)
        lock.acquire()
    except LockBusyError:
        log_line("SKIP", f"run duplicado/concurrente para {run_key}")
        return 0
    try:
        if _marker_date() == run_key:
            log_line("SKIP", f"janela {run_key} já concluída")
            return 0
        log_line("START", "rotina_exemplo iniciada")
        EvidenceLog(EVIDENCE).emit("started", workflow=identity.workflow, run_id=identity.run_id)
        if not insumo_disponivel():
            log_line("ERRO", "insumo ausente: <nome do insumo>")
            return 1
        try:
            process_status = _process_with_retry()
        except Exception as exc:
            log_line("ERRO", f"processamento falhou: {type(exc).__name__}: {exc}")
            return 1
        if not process_status:
            return 1
        log_line("OK", "processamento concluído")
        try:
            entregar()
        except Exception as exc:  # motivo no log, marker NÃO escrito
            log_line("ERRO", f"entrega falhou: {type(exc).__name__}: {exc}")
            return 1
        # Marker só aqui, depois do sucesso completo, com a data coberta.
        _write_marker(covered_on)
        EvidenceLog(EVIDENCE).emit(
            "completed", workflow=identity.workflow, run_id=identity.run_id, covered_date=run_key
        )
        log_line("DONE", f"marker escrito para {run_key}")
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
