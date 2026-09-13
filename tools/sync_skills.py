#!/usr/bin/env python3
"""Espelha `.agents/skills/` (fonte única) em `.claude/skills/` e `.grok/skills/`.

Por que existe: o template quer uma fonte única de skill, visível para além do
dialeto `.claude/` (Codex e Grok Build leem `AGENTS.md` nativamente e nada em
`.claude/`). Sem symlink/junction — o template roda em VM Windows de usuário leigo,
sem Developer Mode, e link que falha em silêncio é pior que arquivo duplicado — a
fonte única só se sustenta com um espelho BURRO e um gate que reprova drift entre
fonte e espelho (`tests/test_sync_skills.py`).

Contrato (design.md da feature `porta-de-entrada-multi-vendor`):

- Fonte: `.agents/skills/<nome>/` (recursivo — `SKILL.md`, `scripts/`,
  `references/`, `assets/`, o que existir).
- Destinos: `.claude/skills/<nome>/` e `.grok/skills/<nome>/`.
- Identidade por CONTEÚDO (byte a byte), nunca por mtime — mtime muda em todo
  clone/checkout e um espelho idêntico acusaria divergência falsa.
- Órfão (arquivo do destino ausente na fonte): apagado no modo escrita, listado
  no `--check`. Pasta que fica vazia depois de podar órfão também é removida.
- Idempotente: rodar duas vezes seguidas não muda nada na segunda.
- Fonte ausente: sai != 0 sem criar nada em nenhum destino.
- Zero dependência third-party, como o resto de `tools/`.

Skill instalada por ferramenta externa (ex.: `npx @tech-leads-club/agent-skills
install --skill <x>`) cai só em `.claude/skills/<x>/` — órfã para este contrato, e
o modo escrita a APAGARIA. `--adotar <x>` move a pasta do espelho para a fonte e
então espelha; é o passo documentado no README depois de instalar qualquer skill.
`tools/doctor.py` acusa órfão e espelho faltante.

Uso:
    python tools/sync_skills.py                 # escreve os espelhos
    python tools/sync_skills.py --check         # só verifica; não escreve
    python tools/sync_skills.py --adotar <x>    # move .claude/skills/<x> (ou .grok/) para a fonte e espelha

Exit: 0 = ok (sincronizado, ou já idêntico); 1 = divergência (`--check`), fonte
ausente ou skill a adotar inexistente/já na fonte; 2 = uso inválido.
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import sys
from pathlib import Path

FONTE_REL = Path(".agents") / "skills"
DESTINOS_REL = (Path(".claude") / "skills", Path(".grok") / "skills")
# Marcador que `--adotar` grava dentro da skill adotada. Skill de terceiro não é
# "skill nova" deste repo: os gates de criação (declaração de formato do grafo,
# evals de disparo em `evals/<skill>/`) leem este arquivo e a isentam — o que
# ela faz é responsabilidade de quem a publicou, e editá-la aqui é fork silencioso.
MARCADOR_VENDORIZADA = "VENDORIZADA.md"


def _arquivos_relativos(base: Path) -> set[Path]:
    """Todo caminho de ARQUIVO sob `base`, relativo a `base`.

    Pasta vazia não conta: identidade byte a byte é sobre conteúdo, e diretório
    sem arquivo dentro não tem conteúdo para divergir."""
    if not base.exists():
        return set()
    return {p.relative_to(base) for p in base.rglob("*") if p.is_file()}


def comparar(fonte: Path, destino: Path) -> list[tuple[Path, str]]:
    """Compara fonte x destino, arquivo a arquivo.

    Devolve uma divergência por caminho relativo divergente, na ordem
    faltante -> órfão -> divergente (cada grupo em ordem alfabética, para saída
    determinística):

    - `faltante`: existe na fonte, não existe no destino.
    - `órfão`: existe no destino, não existe na fonte.
    - `divergente`: existe nos dois, bytes diferentes.
    """
    arquivos_fonte = _arquivos_relativos(fonte)
    arquivos_destino = _arquivos_relativos(destino)

    divergencias: list[tuple[Path, str]] = []
    for rel in sorted(arquivos_fonte - arquivos_destino):
        divergencias.append((rel, "faltante"))
    for rel in sorted(arquivos_destino - arquivos_fonte):
        divergencias.append((rel, "órfão"))
    for rel in sorted(arquivos_fonte & arquivos_destino):
        if (fonte / rel).read_bytes() != (destino / rel).read_bytes():
            divergencias.append((rel, "divergente"))
    return divergencias


def _podar_pastas_vazias(destino: Path) -> None:
    """Remove diretório que ficou vazio depois de apagar um órfão (ex.: a pasta
    inteira de uma skill que saiu da fonte). Sem isso o espelho acumula casca
    vazia que `comparar` não vê — ele só olha arquivo — mas que suja o `git
    status` de verdade."""
    if not destino.exists():
        return
    pastas = sorted(
        (p for p in destino.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for pasta in pastas:
        try:
            next(pasta.iterdir())
        except StopIteration:
            pasta.rmdir()


def escrever_espelho(fonte: Path, destino: Path, divergencias: list[tuple[Path, str]]) -> list[str]:
    """Aplica no destino o que `comparar` apurou: copia o que falta ou diverge,
    apaga órfão. Devolve as linhas de relato, na mesma ordem das divergências."""
    relato: list[str] = []
    for rel, motivo in divergencias:
        alvo = destino / rel
        if motivo in ("faltante", "divergente"):
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fonte / rel, alvo)
            relato.append(f"copiado\t{(destino / rel).as_posix()}")
        elif motivo == "órfão":
            alvo.unlink()
            relato.append(f"removido\t{(destino / rel).as_posix()}")
    _podar_pastas_vazias(destino)
    return relato


def adotar(root: Path, nome: str) -> tuple[int, list[str]]:
    """Move `<espelho>/<nome>/` para a fonte e espelha o resultado.

    Só adota o que a fonte ainda não tem: skill já na fonte é caso de `--check`/
    escrita normal, não de adoção. Procura nos destinos na ordem declarada
    (`.claude/skills` primeiro, onde instaladores externos escrevem)."""
    if not nome or nome in (".", "..") or "/" in nome or "\\" in nome:
        return 2, [f"sync_skills --adotar: nome de skill inválido ({nome!r})"]
    fonte = root / FONTE_REL / nome
    if fonte.exists():
        return 1, [f"sync_skills --adotar: {(FONTE_REL / nome).as_posix()} já existe na fonte — rode sem --adotar"]
    for destino_rel in DESTINOS_REL:
        origem = root / destino_rel / nome
        if origem.is_dir():
            fonte.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origem), str(fonte))
            (fonte / MARCADOR_VENDORIZADA).write_text(
                f"# Skill vendorizada\n\n"
                f"`{nome}` é skill de terceiro, adotada de `{(destino_rel / nome).as_posix()}` por "
                f"`python tools/sync_skills.py --adotar {nome}` em {datetime.date.today().isoformat()}.\n"
                f"Não edite aqui (reinstale e adote de novo); os gates de skill nova "
                f"(formato do grafo, evals de disparo) não se aplicam a ela.\n",
                encoding="utf-8",
            )
            relato = [f"adotado\t{(destino_rel / nome).as_posix()} -> {(FONTE_REL / nome).as_posix()}"]
            codigo, linhas = sincronizar(root, check=False)
            return codigo, relato + linhas
    procurados = ", ".join((d / nome).as_posix() for d in DESTINOS_REL)
    return 1, [f"sync_skills --adotar: skill {nome!r} não encontrada em nenhum espelho ({procurados})"]


def sincronizar(root: Path, check: bool) -> tuple[int, list[str]]:
    """Núcleo testável: roda o contrato sobre `root`, sem tocar em `sys.argv` nem
    em stdout. Devolve (exit_code, linhas_de_relato)."""
    fonte = root / FONTE_REL
    if not fonte.exists():
        return 1, [f"sync_skills: fonte ausente ({FONTE_REL.as_posix()}) — nada a fazer"]

    if check:
        linhas: list[str] = []
        for destino_rel in DESTINOS_REL:
            destino = root / destino_rel
            for rel, motivo in comparar(fonte, destino):
                linhas.append(f"{motivo}\t{(destino_rel / rel).as_posix()}")
        if linhas:
            linhas.append(f"sync_skills --check: {len(linhas)} divergência(s)")
            return 1, linhas
        return 0, ["sync_skills --check: ok, sem divergência"]

    relato: list[str] = []
    for destino_rel in DESTINOS_REL:
        destino = root / destino_rel
        divergencias = comparar(fonte, destino)
        if divergencias:
            relato.extend(escrever_espelho(fonte, destino, divergencias))
    if not relato:
        relato.append("sync_skills: já sincronizado, nada a fazer")
    return 0, relato


def _preparar_saida(fluxo) -> None:
    """Força UTF-8 quando a saída é capturada por outro processo (CI, teste via
    subprocesso): sem isso o Windows grava "órfão"/"divergência" em cp1252 e quem
    lê esperando UTF-8 (como `tools/lint_routers.py` já faz) quebra na decodificação.
    Console interativo e fluxo sem `reconfigure` (ex.: sob `pythonw.exe`) ficam
    intocados."""
    if fluxo is None or not hasattr(fluxo, "reconfigure") or not hasattr(fluxo, "isatty"):
        return
    try:
        if fluxo.isatty():
            return
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError, TypeError):
        pass


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        _preparar_saida(fluxo)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="só verifica; não escreve nada")
    parser.add_argument("--adotar", metavar="SKILL", default=None,
                        help="move .claude/skills/SKILL (ou .grok/) para a fonte .agents/skills/ e espelha")
    parser.add_argument("--root", default=None, help="raiz do repo (default: cwd)")
    args = parser.parse_args(argv)
    if args.check and args.adotar:
        parser.error("--check e --adotar são exclusivos")

    root = Path(args.root).resolve() if args.root else Path.cwd()
    if args.adotar:
        codigo, linhas = adotar(root, args.adotar)
    else:
        codigo, linhas = sincronizar(root, check=args.check)
    for linha in linhas:
        print(linha)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
