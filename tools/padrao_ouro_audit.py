#!/usr/bin/env python3
"""Auditor do padrão ouro — mede um repositório contra a norma `docs/padrao-ouro/PADRAO.md`.

A norma é a tabela de exigências; este arquivo é a implementação literal dela, uma
função por id. Mudar uma exigência lá é mudar a função aqui no mesmo commit — a
norma sem check mecânico é opinião, e o check sem norma é regra escondida.

Uso:
    python padrao_ouro_audit.py [--tipo cockpit|app|skills] [--template] [--versao] RAIZ

Saída: uma linha de placar, uma linha por reprovação (`id  arquivo[:linha]  motivo`)
e os avisos. Exit 0 = placar >= 9; 1 = placar < 9; 2 = tipo não detectado ou raiz
inexistente. Só biblioteca padrão; roda em 3.12+ em qualquer SO.

Linhas que contenham `padrao-ouro:ignorar` ficam fora dos checks de conteúdo (F02 e
G01): é o jeito de a própria norma, este arquivo e os testes citarem os padrões que
procuram sem se autorreprovarem.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

VERSAO = "1"
TIPOS = ("cockpit", "app", "skills")
PLACAR_MINIMO = 9.0
TETO_GIT = 60  # segundos; subprocesso sem teto é gate que nunca responde
MARCA_IGNORAR = "padrao-ouro:ignorar"
LIMITE_LINHAS_INSTRUCOES = 200
LIMITE_TAMANHO_KB = 200
LIMITE_CAMINHO = 100

EXT_BINARIAS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".pdf", ".xlsx", ".xlsm",
    ".xls", ".docx", ".pptx", ".zip", ".gz", ".tar", ".7z", ".rar", ".woff", ".woff2",
    ".ttf", ".otf", ".eot", ".pyc", ".exe", ".dll", ".so", ".dylib", ".bin", ".db",
    ".sqlite", ".parquet", ".mp3", ".mp4", ".mov", ".wav",
})
DIRS_IGNORADOS_NO_DISCO = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv",
                                     ".pytest_cache", ".tmp", "dist"})
# G01 só olha doc e config: em código, `{{x}}` é templating legítimo (Jinja, mustache).
EXT_DOC_CONFIG = frozenset({".md", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".txt", ""})

# padrao-ouro:ignorar — as expressões abaixo descrevem exatamente o que F02 procura.
RE_CAMINHO_MAQUINA = re.compile(
    r"(?i)[a-z]:[\\/]users[\\/]"        # unidade Windows + Users  # padrao-ouro:ignorar
    r"|(?<![\w/])/Users/[A-Za-z0-9_.-]+/"  # home do macOS  # padrao-ouro:ignorar
    r"|(?<![\w/])/home/[A-Za-z0-9_.-]+/"   # home do Linux  # padrao-ouro:ignorar
    r"|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_$.-]+"  # UNC \\servidor\share  # padrao-ouro:ignorar
)
RE_PLACEHOLDER = re.compile(r"(?<!\$)\{\{[A-Za-z_][\w-]*\}\}")  # padrao-ouro:ignorar
RE_TIPO = re.compile(r"^tipo:\s*(cockpit|app|skills)\s*$", re.MULTILINE)
RE_USES = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^'\"\s#]+)")
RE_SHA40 = re.compile(r"@[0-9a-f]{40}$")
RE_PERMISSIONS = re.compile(r"^\s*permissions:", re.MULTILINE)
RE_TITULO_AMBIENTE = re.compile(r"^##+\s.*(ambiente|como rodar)", re.IGNORECASE | re.MULTILINE)
RE_MERMAID = re.compile(r"^\s*```mermaid", re.MULTILINE)
RE_FORMATO = re.compile(r"%%\s*formato\s*:")
RE_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


@dataclass(frozen=True)
class Reprovacao:
    id: str
    arquivo: str
    motivo: str

    def linha(self) -> str:
        return f"{self.id}  {self.arquivo}  {self.motivo}"


@dataclass
class Repo:
    """O que os checks enxergam: a raiz, a lista de caminhos versionados e um cache de texto."""

    raiz: Path
    arquivos: list[str]
    avisos: list[str]
    _textos: dict[str, str | None]

    def existe(self, rel: str) -> bool:
        return rel in self.arquivos

    def texto(self, rel: str) -> str | None:
        """Conteúdo de um arquivo de texto versionado; None se não existe ou é binário.

        `newline=None` normaliza CRLF para LF na leitura: o placar não pode depender do
        SO que fez o checkout.
        """
        if rel in self._textos:
            return self._textos[rel]
        valor: str | None = None
        if rel in self.arquivos and Path(rel).suffix.lower() not in EXT_BINARIAS:
            caminho = self.raiz / rel
            try:
                with open(caminho, "r", encoding="utf-8", errors="replace", newline=None) as fh:
                    valor = fh.read()
            except (OSError, IsADirectoryError):
                valor = None
        self._textos[rel] = valor
        return valor

    def textos(self):
        for rel in self.arquivos:
            t = self.texto(rel)
            if t is not None:
                yield rel, t

    def com_prefixo(self, prefixo: str) -> list[str]:
        return [a for a in self.arquivos if a.startswith(prefixo)]

    def workflows_ci(self) -> list[str]:
        return [a for a in self.com_prefixo(".github/workflows/") if a.endswith((".yml", ".yaml"))]


def listar_versionados(raiz: Path) -> tuple[list[str], list[str]]:
    """`git ls-files` quando a raiz é repositório; senão o disco, com aviso."""
    avisos: list[str] = []
    try:
        r = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "-z"],
            capture_output=True, timeout=TETO_GIT, check=False,
        )
        if r.returncode == 0:
            itens = [p for p in r.stdout.decode("utf-8", errors="replace").split("\0") if p]
            # Só o que existe no disco: um arquivo apagado mas ainda no índice não se mede.
            return sorted(p for p in itens if (raiz / p).is_file()), avisos
    except (OSError, subprocess.TimeoutExpired):
        pass
    avisos.append("sem índice git; medindo o disco")
    itens = []
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in DIRS_IGNORADOS_NO_DISCO]
        for f in filenames:
            rel = Path(dirpath, f).relative_to(raiz).as_posix()
            itens.append(rel)
    return sorted(itens), avisos


def detectar_tipo(repo: Repo) -> str | None:
    t = repo.texto("AGENTS.md")
    if not t:
        return None
    m = RE_TIPO.search(t)
    return m.group(1) if m else None


def _linhas_validas(texto: str):
    """(nº, linha) das linhas que não pedem para ser ignoradas."""
    for n, linha in enumerate(texto.split("\n"), start=1):
        if MARCA_IGNORAR in linha:
            continue
        yield n, linha


# ---------------------------------------------------------------- checks (um por id)

def chk_a01(repo: Repo, tipo: str, template: bool) -> list[Reprovacao]:
    t = repo.texto("AGENTS.md")
    if t is None:
        return [Reprovacao("PO-A01", "AGENTS.md", "não existe na raiz")]
    if not RE_TIPO.search(t):
        return [Reprovacao("PO-A01", "AGENTS.md", "sem linha `tipo: cockpit|app|skills`")]
    return []


def chk_a02(repo, tipo, template):
    t = repo.texto("CLAUDE.md")
    if t is None:
        return [Reprovacao("PO-A02", "CLAUDE.md", "não existe na raiz")]
    primeira = next((l.strip() for l in t.split("\n") if l.strip()), "")
    if primeira != "@AGENTS.md":
        return [Reprovacao("PO-A02", "CLAUDE.md:1", "primeira linha não vazia não é `@AGENTS.md`")]
    return []


def chk_a03(repo, tipo, template):
    out = []
    for nome in ("AGENTS.md", "CLAUDE.md"):
        t = repo.texto(nome)
        if t is None:
            out.append(Reprovacao("PO-A03", nome, "não existe; nada a medir"))
            continue
        n = len(t.rstrip("\n").split("\n"))
        if n > LIMITE_LINHAS_INSTRUCOES:
            out.append(Reprovacao("PO-A03", nome, f"{n} linhas (máximo {LIMITE_LINHAS_INSTRUCOES})"))
    return out


def chk_a04(repo, tipo, template):
    t = repo.texto("README.md")
    if t is None:
        return [Reprovacao("PO-A04", "README.md", "não existe na raiz")]
    if not RE_TITULO_AMBIENTE.search(t):
        return [Reprovacao("PO-A04", "README.md", "sem título `##` contendo 'Ambiente' ou 'Como rodar'")]
    return []


def chk_b01(repo, tipo, template):
    if any(a.endswith(".md") for a in repo.com_prefixo(".claude/rules/")):
        return []
    return [Reprovacao("PO-B01", ".claude/rules/", "sem nenhuma regra `.md`")]


def chk_b02(repo, tipo, template):
    if repo.existe(".claude/agents/verificador.md"):
        return []
    return [Reprovacao("PO-B02", ".claude/agents/verificador.md", "não existe")]


def chk_c01(repo, tipo, template):
    texto = repo.texto("README.md") or ""
    comandos = (
        "PY tools/gate_veredito.py",
        "PY tools/lint_routers.py",
        "PY tools/policy_check.py .",
        "PY tools/operational_audit.py .",
        "PY tools/padrao_ouro_audit.py --tipo cockpit .",
        "PY -m ruff check .",
        "PY -m pip_audit --strict --progress-spinner off",
        "PY -m bandit --quiet --recursive --severity-level medium --confidence-level medium tools workflows",
        "GITLEAKS detect --source . --no-banner --redact --verbose",
    )
    if all(comando in texto for comando in comandos):
        return []
    return [Reprovacao("PO-C01", "README.md", "contrato de verificação local incompleto")]


def chk_c02(repo, tipo, template):
    if not repo.workflows_ci():
        return [Reprovacao("PO-C02", ".github/workflows/", "nenhum workflow; nada a pinar")]
    out = []
    for wf in repo.workflows_ci():
        t = repo.texto(wf) or ""
        for n, linha in enumerate(t.split("\n"), start=1):
            m = RE_USES.match(linha)
            if not m:
                continue
            alvo = m.group(1)
            if alvo.startswith("./") or alvo.startswith("docker://"):
                continue  # action local ou imagem: pin por SHA não se aplica
            if not RE_SHA40.search(alvo):
                out.append(Reprovacao("PO-C02", f"{wf}:{n}", f"`uses: {alvo}` sem SHA de 40 hex"))
        if not RE_PERMISSIONS.search(t):
            # Ausência não tem linha natural; cita a 1 para manter o contrato `arquivo:linha`.
            out.append(Reprovacao("PO-C02", f"{wf}:1", "sem chave `permissions:`"))
    return out


def chk_c03(repo, tipo, template):
    if "GITLEAKS detect --source . --no-banner --redact --verbose" in (repo.texto("README.md") or ""):
        return []
    return [Reprovacao("PO-C03", "README.md", "contrato local não cita gitleaks")]


def chk_d01(repo, tipo, template):
    if repo.existe(".specs/STATE.md"):
        return []
    return [Reprovacao("PO-D01", ".specs/STATE.md", "não existe")]


def chk_e01(repo, tipo, template):
    t = repo.texto(".gitignore")
    if t is None:
        return [Reprovacao("PO-E01", ".gitignore", "não existe")]
    for n, linha in enumerate(t.split("\n"), start=1):
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        if s in ("/*", "*"):
            return []
        return [Reprovacao("PO-E01", f".gitignore:{n}", f"primeira regra é `{s}`, não `/*` (allowlist)")]
    return [Reprovacao("PO-E01", ".gitignore", "vazio")]


def chk_e02(repo, tipo, template):
    t = repo.texto(".gitattributes")
    if t is None:
        return [Reprovacao("PO-E02", ".gitattributes", "não existe")]
    if "text=auto" not in t:
        return [Reprovacao("PO-E02", ".gitattributes", "sem `text=auto`")]
    return []


def chk_f01(repo, tipo, template):
    out = []
    for a in repo.arquivos:
        nome = Path(a).name
        if nome == ".env" or (nome.startswith(".env.") and nome != ".env.example"):
            out.append(Reprovacao("PO-F01", a, "arquivo de segredos versionado"))
    gi = repo.texto(".gitignore") or ""
    if not any(l.strip() == ".env" for l in gi.split("\n")):
        out.append(Reprovacao("PO-F01", ".gitignore", "sem linha `.env`"))
    return out


def chk_f02(repo, tipo, template):
    out = []
    proprio = Path(__file__).name
    for rel, t in repo.textos():
        if Path(rel).name == proprio:
            continue
        for n, linha in _linhas_validas(t):
            if RE_CAMINHO_MAQUINA.search(linha):
                out.append(Reprovacao("PO-F02", f"{rel}:{n}", "caminho absoluto de máquina"))
    return out


def chk_f04(repo, tipo, template):
    out = []
    for a in repo.arquivos:
        try:
            kb = (repo.raiz / a).stat().st_size / 1024
        except OSError:
            continue
        if kb > LIMITE_TAMANHO_KB:
            out.append(Reprovacao("PO-F04", a, f"{kb:.0f} KB (máximo {LIMITE_TAMANHO_KB} KB)"))
    return out


def chk_g01(repo, tipo, template):
    if template:
        return []
    out = []
    proprio = Path(__file__).name
    for rel, t in repo.textos():
        if Path(rel).name == proprio or Path(rel).suffix.lower() not in EXT_DOC_CONFIG:
            continue
        for n, linha in _linhas_validas(t):
            m = RE_PLACEHOLDER.search(linha)
            if m:
                out.append(Reprovacao("PO-G01", f"{rel}:{n}", f"placeholder `{m.group(0)}` remanescente"))
    return out


def chk_k01(repo, tipo, template):
    return [Reprovacao("PO-K01", r, "router não existe")
            for r in ("workflows/CLAUDE.md", "tools/CLAUDE.md", "docs/CLAUDE.md") if not repo.existe(r)]


def chk_k02(repo, tipo, template):
    out = []
    sops = [rel for rel in repo.com_prefixo("workflows/")
            if len(rel.split("/")) == 3 and rel.split("/")[2] == "workflow.md"]
    if not sops:
        return [Reprovacao("PO-K02", "workflows/", "nenhuma rotina com `workflow.md`")]
    for rel in sops:
        t = repo.texto(rel) or ""
        if not RE_MERMAID.search(t):
            out.append(Reprovacao("PO-K02", rel, "sem bloco ```mermaid"))
        elif not RE_FORMATO.search(t):
            out.append(Reprovacao("PO-K02", rel, "sem linha `%% formato:`"))
    return out


def chk_k03(repo, tipo, template):
    out = []
    t = repo.texto("conftest.py")
    if t is None or "PISO_COLETA" not in t:
        out.append(Reprovacao("PO-K03", "conftest.py", "ausente ou sem `PISO_COLETA`"))
    if not any(Path(a).name.startswith("test_") and a.endswith(".py") for a in repo.com_prefixo("tests/")):
        out.append(Reprovacao("PO-K03", "tests/", "nenhum `test_*.py`"))
    return out


def chk_k04(repo, tipo, template):
    out = [Reprovacao("PO-K04", f, "não existe")
           for f in ("tools/gate_veredito.py", "tools/lint_routers.py") if not repo.existe(f)]
    texto = repo.texto("README.md") or ""
    cita = "gate_veredito.py" in texto and "lint_routers.py" in texto
    if not cita:
        out.append(Reprovacao("PO-K04", "README.md", "contrato local não chama gate_veredito.py e lint_routers.py"))
    return out


def chk_p01(repo, tipo, template):
    return [] if repo.existe(".env.example") else [Reprovacao("PO-P01", ".env.example", "não existe")]


def chk_p02(repo, tipo, template):
    textos = " ".join(repo.texto(w) or "" for w in repo.workflows_ci())
    faltam = []
    if "tsc" not in textos:
        faltam.append("typecheck (`tsc`)")
    if not any(k in textos for k in ("vitest", "jest", "pytest")):
        faltam.append("teste (`vitest`/`jest`/`pytest`)")
    if "build" not in textos:
        faltam.append("`build`")
    return [Reprovacao("PO-P02", ".github/workflows/", "sem passo de " + ", ".join(faltam))] if faltam else []


def _marketplace(repo: Repo) -> tuple[dict | None, str | None]:
    t = repo.texto(".claude-plugin/marketplace.json")
    if t is None:
        return None, "não existe"
    try:
        dados = json.loads(t)
    except json.JSONDecodeError as e:
        return None, f"JSON inválido ({e.msg})"
    if not isinstance(dados, dict) or not isinstance(dados.get("plugins"), list) or not dados["plugins"]:
        return None, "sem lista `plugins` não vazia"
    return dados, None


def chk_s01(repo, tipo, template):
    _, erro = _marketplace(repo)
    return [Reprovacao("PO-S01", ".claude-plugin/marketplace.json", erro)] if erro else []


def chk_s02(repo, tipo, template):
    dados, erro = _marketplace(repo)
    if erro:
        return []  # já reprovado em S01
    out = []
    for p in dados["plugins"]:
        fonte = str(p.get("source", "")).lstrip("./").rstrip("/")
        manifesto = f"{fonte}/.claude-plugin/plugin.json" if fonte else ".claude-plugin/plugin.json"
        t = repo.texto(manifesto)
        if t is None:
            out.append(Reprovacao("PO-S02", manifesto, "não existe"))
            continue
        try:
            m = json.loads(t)
        except json.JSONDecodeError:
            out.append(Reprovacao("PO-S02", manifesto, "JSON inválido"))
            continue
        for chave in ("name", "version"):
            if not m.get(chave):
                out.append(Reprovacao("PO-S02", manifesto, f"sem `{chave}`"))
    return out


def chk_s03(repo, tipo, template):
    out = []
    for rel in repo.arquivos:
        if Path(rel).name != "SKILL.md":
            continue
        t = repo.texto(rel) or ""
        m = RE_FRONTMATTER.match(t)
        if not m:
            out.append(Reprovacao("PO-S03", rel, "sem frontmatter"))
            continue
        campos = {}
        for linha in m.group(1).split("\n"):
            if ":" in linha and not linha.startswith((" ", "\t")):
                k, v = linha.split(":", 1)
                campos[k.strip()] = v.strip().strip("'\"")
        pasta = Path(rel).parent.name
        if campos.get("name") != pasta:
            out.append(Reprovacao("PO-S03", rel, f"`name` ({campos.get('name')!r}) difere da pasta ({pasta!r})"))
        if not campos.get("description"):
            out.append(Reprovacao("PO-S03", rel, "sem `description`"))
        if not campos.get("formato"):
            out.append(Reprovacao("PO-S03", rel, "sem `formato`"))
    return out


@dataclass(frozen=True)
class Exigencia:
    id: str
    tipos: tuple[str, ...]
    peso: float
    check: Callable[[Repo, str, bool], list[Reprovacao]]


TODOS = TIPOS
NORMA: tuple[Exigencia, ...] = (
    Exigencia("PO-A01", TODOS, 1.0, chk_a01),
    Exigencia("PO-A02", TODOS, 1.0, chk_a02),
    Exigencia("PO-A03", TODOS, 0.5, chk_a03),
    Exigencia("PO-A04", TODOS, 0.5, chk_a04),
    Exigencia("PO-B01", TODOS, 0.5, chk_b01),
    Exigencia("PO-B02", TODOS, 0.5, chk_b02),
    Exigencia("PO-C01", TODOS, 1.0, chk_c01),
    Exigencia("PO-C02", TODOS, 1.0, chk_c02),
    Exigencia("PO-C03", TODOS, 1.0, chk_c03),
    Exigencia("PO-D01", TODOS, 0.5, chk_d01),
    Exigencia("PO-E01", TODOS, 0.5, chk_e01),
    Exigencia("PO-E02", TODOS, 0.25, chk_e02),
    Exigencia("PO-F01", TODOS, 1.0, chk_f01),
    Exigencia("PO-F02", TODOS, 1.0, chk_f02),
    Exigencia("PO-F04", TODOS, 0.25, chk_f04),
    Exigencia("PO-G01", TODOS, 0.5, chk_g01),
    Exigencia("PO-K01", ("cockpit",), 1.0, chk_k01),
    Exigencia("PO-K02", ("cockpit",), 0.5, chk_k02),
    Exigencia("PO-K03", ("cockpit",), 0.5, chk_k03),
    Exigencia("PO-K04", ("cockpit",), 1.0, chk_k04),
    Exigencia("PO-P01", ("app",), 0.5, chk_p01),
    Exigencia("PO-P02", ("app",), 1.0, chk_p02),
    Exigencia("PO-S01", ("skills",), 1.0, chk_s01),
    Exigencia("PO-S02", ("skills",), 1.0, chk_s02),
    Exigencia("PO-S03", ("skills",), 1.0, chk_s03),
)


@dataclass
class Resultado:
    tipo: str
    placar: float
    aplicaveis: int
    aprovadas: int
    reprovacoes: list[Reprovacao]
    avisos: list[str]

    @property
    def exit_code(self) -> int:
        return 0 if self.placar >= PLACAR_MINIMO else 1


def auditar(raiz: Path, tipo: str | None, template: bool = False) -> Resultado:
    """Mede a raiz. Levanta ValueError se o tipo não puder ser determinado."""
    arquivos, avisos = listar_versionados(raiz)
    repo = Repo(raiz=raiz, arquivos=arquivos, avisos=avisos, _textos={})
    tipo = tipo or detectar_tipo(repo)
    if tipo not in TIPOS:
        raise ValueError("tipo não detectado; informe --tipo")

    reprovacoes: list[Reprovacao] = []
    peso_total = peso_ok = 0.0
    aplicaveis = aprovadas = 0
    for ex in NORMA:
        if tipo not in ex.tipos:
            continue
        aplicaveis += 1
        peso_total += ex.peso
        # Repo sem nenhum arquivo não "passa" em nada: verdade vazia não é conformidade.
        if not arquivos:
            falhas = [Reprovacao(ex.id, ".", "repo vazio")]
        else:
            falhas = ex.check(repo, tipo, template)
        if falhas:
            reprovacoes.extend(falhas)
        else:
            aprovadas += 1
            peso_ok += ex.peso

    # PO-F03 é aviso: caminho longo não reprova, mas se anuncia.
    longos = [a for a in arquivos if len(a) > LIMITE_CAMINHO]
    if longos:
        pior = max(longos, key=len)
        avisos.append(f"PO-F03  {pior}  {len(pior)} caracteres (mais longo; limite {LIMITE_CAMINHO})")

    placar = round(peso_ok / peso_total * 10, 1) if peso_total else 0.0
    return Resultado(tipo, placar, aplicaveis, aprovadas, reprovacoes, avisos)


def formatar(r: Resultado) -> str:
    linhas = [f"placar: {r.placar:.1f}/10 (tipo {r.tipo}, {r.aplicaveis} exigências, {r.aprovadas} ok)"]
    linhas += [rep.linha() for rep in r.reprovacoes]
    linhas += [f"aviso: {a}" for a in r.avisos]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mede um repositório contra a norma do padrão ouro.")
    ap.add_argument("raiz", nargs="?", default=".", help="raiz do repositório (default: .)")
    ap.add_argument("--tipo", choices=TIPOS, help="tipo do repo; sem ele, lê `tipo:` do AGENTS.md")
    ap.add_argument("--template", action="store_true", help="repo-template: placeholders {{...}} permitidos")  # padrao-ouro:ignorar
    ap.add_argument("--versao", action="store_true", help="imprime a versão da norma implementada e sai")
    args = ap.parse_args(argv)

    # Saída sempre em UTF-8: o placar não pode virar mojibake conforme o console do SO.
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")

    if args.versao:
        print(VERSAO)
        return 0
    raiz = Path(args.raiz).resolve()
    if not raiz.is_dir():
        print(f"raiz inexistente: {raiz}", file=sys.stderr)
        return 2
    try:
        r = auditar(raiz, args.tipo, args.template)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(formatar(r))
    return r.exit_code


if __name__ == "__main__":
    sys.exit(main())
