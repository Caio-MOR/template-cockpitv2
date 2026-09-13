#!/usr/bin/env python3
"""Lint determinístico de routers contra o índice git.

O que valida:

- Referências path-like (backticks e links markdown) de todo CLAUDE.md
  versionado e, na raiz, de AGENTS.md e README.md (fonte única e porta de
  entrada — drift lá envenena igual).
- Skills `/nome` contra .claude/skills/<nome>/SKILL.md.
- Cobertura reversa: pasta de 1º nível em workflows/ e script tools/*.py
  precisam aparecer no router da categoria.
- Contagem declarada ("N scripts") no router de tools.

Existência = índice git (git ls-files), nunca o filesystem: é a única forma
de distinguir "sumiu" de "é da outra máquina" (gitignore em allowlist).
Referência ausente do índice é isenta quando a linha carrega marcação de
escopo/estado (MARCACOES) ou quando o caminho é ignorado pelo gitignore
(fora do git por design).

Exit codes: 0 = limpo; 1 = ERRO(s) encontrados; 2 = uso inválido.
Motivo por linha na saída (regra estrutura-e-logging aplicada ao CI).
Zero dependências third-party.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

# Marcações que isentam a referência. Todas dizem ONDE A COISA ESTÁ (ou que ela não
# está mais em lugar nenhum) — nunca em que estado está o projeto que ela descreve.
# Palavras sobre o PROJETO (`arquivado`, `aposentado`, `a criar`, `nada implementado`,
# `ainda não` genérico) ficam de fora de propósito: usadas sobre o projeto, isentavam
# de carona o arquivo que o descreve — que existe, versionado, justamente por isso.
# (A linha inteira fora de tabela; só a célula dentro dela — ver _tem_marcacao.)
MARCACOES = re.compile(
    "|".join(
        [
            r"fora do git",
            r"fora deste git",
            r"s[oó] no windows",
            # `no windows` solto era largo demais: "fechar no Windows" isentava TODAS
            # as referências da linha. Marcação tem de falar de onde o arquivo está,
            # não de onde o trabalho acontece.
            r"(?:existe|vive|fica|mora|est[aá])m? (?:s[oó] )?no windows",
            r"m[aá]quina de origem",
            r"local por m[aá]quina",
            r"hist[oó]rico git",
            r"n[aã]o existe mais",
            # `ainda não` só quando fala do ARTEFATO ("ainda não gerado"), nunca do
            # projeto ("projeto ainda não implementado") — a mesma distinção acima.
            r"ainda n[aã]o (?:existe|foi gerad|gerad|criad|escrit|rodou)",
            r"removid[oa] do repo",
            r"s[oó] este router [eé] versionado",
        ]
    ),
    re.IGNORECASE,
)

# Extensões que tornam um token sem barra verificável (basename).
EXTENSOES = (
    ".md", ".py", ".json", ".sh", ".ps1", ".vbs", ".bat", ".cmd",
    ".xlsx", ".txt", ".yml", ".yaml", ".html", ".csv", ".ini", ".toml",
    ".gitignore", ".gitattributes",
)

# Comandos nativos do Claude Code que têm cara de skill mas não são.
SKILLS_BUILTIN = {"/clear", "/compact", "/config", "/init", "/code-review", "/help"}

# Categorias com cobertura reversa de pastas de 1º nível.
CATEGORIAS_REVERSAS = ("workflows",)

# Teto de duração de todo subprocesso do lint (segundos). Freio obrigatório da regra
# `loop-engineering`: `subprocess.run` sem `timeout` pendura o gate em vez de
# reprová-lo, e gate que não responde é pior que gate que reprova.
TETO_GIT = 120

# Alvos da raiz. `CLAUDE.md` está aqui além de casar com o glob dos routers porque
# a checagem de "alvo fora do índice" precisa dele nominalmente — sem isso, o router
# raiz podia sair do índice sem alarme.
ALVOS_RAIZ = ("CLAUDE.md", "AGENTS.md", "README.md")

# Alvos que o lint TEM de vigiar, versionado — não derivado do índice nem do HEAD.
# As duas derivações se auto-desligam: `git rm docs/CLAUDE.md` **com commit** tira o
# arquivo do índice E do HEAD ao mesmo tempo, e a vigilância desaparece junto com o
# alvo — "0 erro(s) em 5 arquivo(s)" lê-se igual a "0 erro(s) em 6". Pior: apagar
# `tools/CLAUDE.md` leva a cobertura reversa dos scripts embora, também em silêncio.
# Mesma disciplina de GATES_OBRIGATORIOS no `conftest.py`: apagar um router de
# categoria passa a exigir editar ESTA lista e o set espelho de
# `tests/test_lint_routers.py`, no mesmo PR. Remover proteção é decisão, nunca
# efeito colateral.
# A impressão digital NÃO pode conter nenhum dos alvos protegidos: se contivesse,
# apagar o alvo desligaria justamente a checagem que o protege.
IMPRESSAO_DIGITAL = (
    "pytest.ini", "conftest.py", "requirements.txt", "tools/lint_routers.py",
)
ALVOS_OBRIGATORIOS = (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "workflows/CLAUDE.md",
    "tools/CLAUDE.md",
    "docs/CLAUDE.md",
)

# Regras catch-all de allowlist: casam com todo caminho de 1º nível não liberado.
# Isentam quando o candidato é canônico (o caminho realmente está fora deste git),
# nunca quando é palpite — palpite isento blinda referência quebrada.
PADROES_CATCH_ALL = frozenset({"/*", "*", "/**", "**"})

RE_BACKTICK = re.compile(r"`([^`]+)`")
RE_LINK_MD = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
RE_DOMINIO = re.compile(r"^[\w.-]+\.(com|com\.br|org|net|io|dev|cloud|online|ai)(/|$)")
RE_SKILL = re.compile(r"^/[A-Za-z0-9][A-Za-z0-9_-]*$")
RE_CONTAGEM = re.compile(r"(\d+)\s+scripts", re.IGNORECASE)
# Token que é só uma extensão: a doc usa a extensão como substantivo.
RE_SO_EXTENSAO = re.compile(r"^\.[A-Za-z0-9]+$")
# Primeiro token de uma linha de comando — o resto são argumentos, não caminhos.
RUNNERS = frozenset({
    "python", "python3", "py", "pytest", "node", "npm", "npx", "bash", "sh",
    "zsh", "pwsh", "powershell", "git", "gh", "uv", "pip", "cmd", "wscript",
    "cscript", "curl", "docker",
})

Achado = tuple  # (arquivo, linha, ref, motivo)


def _indice_git(root: Path) -> set[str]:
    # -z + quotepath=false: caminho com acento vem literal, nunca escapado. O
    # encoding explícito impede o locale (cp1252 no Windows) de corromper a saída.
    saida = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
    timeout=TETO_GIT)
    return {l for l in saida.stdout.split("\0") if l}


def _candidato_inseguro(c: str) -> bool:
    """Candidato que faz o `git check-ignore` recusar a checagem INTEIRA.

    Caminho fora do repo — absoluto de máquina ou começando em `..` — faz o git
    sair com 128 e stdout vazio. Como a ausência de saída é lida como "nenhuma
    isenção", TODO pendente viraria ERRO de uma vez. O candidato canônico
    (resolvido contra o diretório do router) não tem `..` e continua sendo checado —
    quem sai é só o palpite que escapa da árvore. Gate que grita por nada é gate que
    alguém desliga.
    """
    if _abs_de_maquina(c):
        return True
    normalizado = c.replace(BARRA_INVERTIDA, "/")
    return normalizado == ".." or normalizado.startswith("../")


def _gitignores_versionados(root: Path) -> frozenset[str]:
    """Os `.gitignore` que estão no índice — as únicas fontes de isenção legítimas."""
    saida = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.gitignore"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=TETO_GIT,
    )
    return frozenset(c.replace("\\", "/") for c in saida.stdout.split("\0") if c)


def _fonte_versionada(fonte: str, versionados: frozenset[str]) -> bool:
    """A regra que casou veio de um `.gitignore` que está no git?

    `.git/info/exclude` e o `core.excludesFile` global não estão, e não podem decidir
    o veredito de um gate: a máquina de quem roda passaria a mandar no resultado.
    """
    return fonte.replace("\\", "/") in versionados


def _ignorados_git(root: Path, candidatos: list[str]) -> dict[str, str]:
    """{candidato ignorado: padrão do gitignore que o ignorou}.

    `-v` para saber QUAL regra casou, e não só que casou. Quatro armadilhas dele —
    o que o `check-ignore` devolve nem sempre é uma regra, e quando é, nem sempre é
    uma regra **versionada**:

    1. Ele reporta também a regra de **negação** (`!padrão`) — o caso em que o
       caminho justamente NÃO é ignorado. Ler isso como "fora do git por design"
       reintroduz a isenção falsa exatamente sobre os arquivos que a allowlist
       libera um a um. Daí o filtro do `!`.
    2. Quem decide o que fazer com a catch-all da raiz é o `lint()`, que sabe se o
       candidato é canônico ou palpite (ver `_candidatos_ignore`).
    3. Padrão **vazio** (linha em branco do `.gitignore`) não é regra — só aparece em
       clone novo, que é a condição do CI.
    4. A **fonte** pode não estar no git: `.git/info/exclude` e o `core.excludesFile`
       global isentam de verdade e não são versionados — o CI, que não os tem, veria
       outro veredito. Gate cujo resultado depende da máquina não é gate.

    -z nos dois sentidos: em modo texto o Windows traduz LF em CRLF ao escrever na
    stdin, o git devolveria o caminho com CR no fim e nenhum candidato casaria.
    """
    candidatos = [c for c in candidatos if not _candidato_inseguro(c)]
    if not candidatos:
        return {}
    saida = subprocess.run(
        ["git", "check-ignore", "-v", "-z", "--stdin"],
        cwd=root, input="\0".join(candidatos), capture_output=True, text=True, encoding="utf-8",
        timeout=TETO_GIT,
    )
    versionados = _gitignores_versionados(root)
    # -v -z emite quatro campos por casamento: fonte, linha, padrão, caminho.
    campos = saida.stdout.split("\0")
    return {
        campos[i + 3]: campos[i + 2]
        for i in range(0, len(campos) - 3, 4)
        # Padrão VAZIO também sai (armadilha 3) e regra de negação também (armadilha 1).
        if campos[i + 2] and not campos[i + 2].startswith("!")
        # E a FONTE tem que estar no git — armadilha 4.
        and _fonte_versionada(campos[i], versionados)
    }


def extrair_refs_tipadas(texto: str) -> list[tuple[int, str, str]]:
    """(nº da linha 1-based, referência, tipo) — tipo em {"backtick", "link"}.

    A distinção importa na hora de resolver. Link markdown é endereço: `[x](y)`
    promete que `y` existe relativo ao arquivo, e link que não resolve é link
    quebrado. Backtick é prosa: `build.py` cita um nome de arquivo, e o que se quer
    saber é se esse nome existe em algum lugar do repo.
    """
    refs: list[tuple[int, str, str]] = []
    for n, linha in enumerate(texto.splitlines(), start=1):
        for m in RE_BACKTICK.finditer(linha):
            refs.append((n, m.group(1).strip(), "backtick"))
        for m in RE_LINK_MD.finditer(linha):
            refs.append((n, m.group(1).strip(), "link"))
    return refs


def extrair_refs(texto: str) -> list[tuple[int, str]]:
    """(nº da linha, referência) — atalho para quem não precisa do tipo."""
    return [(n, ref) for n, ref, _ in extrair_refs_tipadas(texto)]


BARRA_INVERTIDA = chr(92)


def _abs_de_maquina(ref: str) -> bool:
    """Caminho absoluto de máquina: letra de unidade (`X:` + barra) ou UNC."""
    if ref[:2] == BARRA_INVERTIDA * 2:            # UNC: servidor + share
        return True
    return (len(ref) > 2 and ref[0].isalpha() and ref[1] == ":"
            and ref[2] in (BARRA_INVERTIDA, "/"))


def ignorar_ref(ref: str) -> bool:
    """Classes não verificáveis neste clone."""
    if not ref:
        # `` ` ` `` (par de backticks com só espaço) chegava aqui vazio e o
        # `ref.split()[0]` estourava IndexError: traceback em vez de linha ERRO.
        return True
    if "://" in ref or ref.startswith(("~", "/")) or "\\" in ref:
        return True  # URL, home, caminho absoluto (máquina-local) ou Windows
    if _abs_de_maquina(ref):
        # Absoluto de máquina escrito com barra normal: mesma classe do `~` e do `/`,
        # e precisa sair ANTES de virar candidato do `git check-ignore` — caminho fora
        # do repo faz o git recusar a checagem inteira.
        return True
    if RE_DOMINIO.match(ref):
        return True
    if RE_SO_EXTENSAO.match(ref):
        return True  # a extensão usada como substantivo ("o wrapper `.vbs`")
    if ref.split()[0] in RUNNERS:
        return True  # linha de comando, não caminho ("`python3 tools/x.py`")
    if " " in ref:
        # comando com flags/argumentos — exceto nome de arquivo com espaço
        if " -" in ref or not ref.endswith(EXTENSOES):
            return True
    if "/" not in ref and not ref.endswith(EXTENSOES) and "*" not in ref:
        # token solto sem cara de caminho (nome de task, memória, config etc.)
        return True
    return False


def _normalizar_barras(ref: str) -> str:
    r"""`dados\planilha.xlsx` é `dados/planilha.xlsx` — não é ref inverificável.

    `ignorar_ref` descarta QUALQUER referência que contenha `\`. Absoluto é
    inverificável; **relativo com barra invertida não** — e ele é o acidente mais
    provável em máquina Windows: trocar `/` por `\` numa ref tirava a referência da
    vigilância inteira. Absoluto de máquina (letra de unidade ou UNC) segue
    inverificável e continua ignorado.
    """
    if _abs_de_maquina(ref):
        return ref
    return ref.replace(BARRA_INVERTIDA, "/")


def _normalizar(ref: str) -> str:
    """Forma canônica de uma referência: sem âncora, sem `./`, com `..` resolvido.

    Três idiomas de markdown que seriam tratados como caminho literal e acusados por
    engano: `[x](./guia.md)`, `` `../tools/x.py` `` e `[x](guia.md#secao)`. Gate que
    grita por nada gasta a confiança igual ao que cala.
    """
    antes, _, _ = ref.partition("#")
    # Só corta no `#` quando o que vem antes já tem cara de arquivo: `nota#1.md` é
    # nome de arquivo legítimo, e cortar nele criaria falso positivo.
    limpo = (antes if antes.endswith(EXTENSOES) else ref).rstrip("/")
    if not limpo:
        return ref.rstrip("/")
    partes: list[str] = []
    for parte in limpo.split("/"):
        if parte in ("", "."):
            continue
        if parte == ".." and partes and partes[-1] != "..":
            partes.pop()
        else:
            partes.append(parte)
    return "/".join(partes) or limpo


def _tem_marcacao(linha: str, ref: str) -> bool:
    """A marcação de escopo/estado cobre ESTA referência?

    Fora de tabela, a linha é a unidade natural de contexto e vale inteira. Dentro de
    tabela markdown não é: a linha é um registro com vários campos, e a marcação de um
    campo isentava as referências de todos os outros.
    """
    if "|" not in linha:
        return bool(MARCACOES.search(linha))
    celulas = linha.split("|")
    if any(MARCACOES.search(c) for c in celulas if ref in c):
        return True  # a marcação está no próprio campo
    # A linha de tabela é um registro SOBRE a primeira célula: marcação em qualquer
    # campo descreve o assunto. O que ela não faz é um campo isentar o outro.
    # O assunto é o PRIMEIRO campo, mesmo vazio: pular campo em branco faria o
    # assunto deslizar para a coluna seguinte.
    assunto = celulas[1] if linha.lstrip().startswith("|") and len(celulas) > 1 else celulas[0]
    if ref in assunto:
        return bool(MARCACOES.search(linha))
    return False


def _existe(ref: str, base_rel: str, index: set[str], busca_por_nome: bool = True) -> bool:
    """Resolve contra o índice: relativo à raiz, ao dir do arquivo e — só na prosa — por nome.

    `busca_por_nome=False` para link markdown. Link é endereço: `[x](y)` promete
    que `y` existe relativo ao arquivo, e aceitar um homônimo em outra pasta é
    dizer que o link funciona quando ele está quebrado.

    Na prosa a busca por nome continua sendo o certo: `` `build.py` `` num router
    quer dizer "existe um build.py neste repo", não "existe em tal caminho".
    """
    limpo = _normalizar(ref)
    # Link markdown resolve relativo ao arquivo, e só. Testar também a raiz aceitaria
    # `[x](README.md)` escrito de um router em `docs/` — link quebrado que o gate
    # diria estar bom.
    candidatos = [] if (base_rel and not busca_por_nome) else [limpo]
    if base_rel:
        candidatos.append(_normalizar(f"{base_rel}/{limpo}"))
    for cand in candidatos:
        for entrada in index:
            if entrada == cand or entrada.startswith(cand + "/"):
                return True
    if not busca_por_nome:
        return False
    if any(entrada.endswith("/" + limpo) for entrada in index):
        return True
    if ref.endswith("/"):
        # diretório citado pelo nome ("cada rotina tem `scripts/`")
        return any(f"/{limpo}/" in entrada for entrada in index)
    return False


def _glob_existe(ref: str, base_rel: str, index: set[str]) -> bool:
    """Glob casa se algum item do índice (caminho ou basename) bate."""
    padroes = [ref + "*"] if ref.endswith("/") else [ref]  # glob de diretório
    escopo = [e for e in index if e.startswith(base_rel + "/")] if base_rel else list(index)
    for entrada in escopo or index:
        for padrao in padroes:
            if fnmatch(entrada, padrao) or fnmatch(entrada.rsplit("/", 1)[-1], padrao):
                return True
    return False


def _candidatos_ignore(ref: str, base_rel: str) -> list[tuple[str, bool]]:
    """[(candidato, é_canônico)] para a conferência no gitignore.

    Canônico é o candidato resolvido contra o diretório do próprio arquivo (ou a
    raiz, quando o arquivo já está na raiz). O outro é palpite — e era ele que a
    allowlist da raiz transformava em isenção universal: `specs/design.md`, citado
    de um router em `docs/`, casava com `/*` e virava "fora do git por design"
    mesmo com o arquivo tendo sumido do índice.
    """
    # A barra final é preservada de propósito: `git check-ignore` decide se um
    # padrão de diretório (`.tmp/`) casa olhando o DISCO, e um clone novo não tem
    # os diretórios ignorados. Com ela, o git sabe que é diretório e a resposta
    # para de depender do que existe ali.
    barra = "/" if ref.endswith("/") else ""
    limpo = _normalizar(ref) + barra
    if not base_rel:
        return [(limpo, True)]
    return [(_normalizar(f"{base_rel}/{limpo}") + barra, True), (limpo, False)]


def _checar_arquivo(
    rel: str, texto: str, index: set[str]
) -> tuple[list[Achado], list[tuple[Achado, list[tuple[str, bool]]]]]:
    """Achados diretos + pendentes de conferência no gitignore.

    Pendentes: (achado, candidatos) — só viram ERRO se nenhum candidato for
    ignorado pelo gitignore (decidido em lote pelo chamador).
    """
    achados: list[Achado] = []
    pendentes: list[tuple[Achado, list[tuple[str, bool]]]] = []
    base_rel = str(Path(rel).parent)
    if base_rel == ".":
        base_rel = ""
    linhas = texto.splitlines()

    for n, ref_bruta, tipo in extrair_refs_tipadas(texto):
        ref = _normalizar_barras(ref_bruta)
        linha = linhas[n - 1] if n - 1 < len(linhas) else ""
        if RE_SKILL.match(ref):
            if ref in SKILLS_BUILTIN:
                continue
            alvo = f".claude/skills/{ref[1:]}/SKILL.md"
            if alvo not in index and not _tem_marcacao(linha, ref):
                achados.append((rel, n, ref, f"skill sem {alvo} no índice git"))
            continue
        if ignorar_ref(ref):
            continue
        if "*" in ref:
            # a barra final distingue glob de diretório e a normalização a remove
            glob = _normalizar(ref) + ("/" if ref.endswith("/") else "")
            if not _glob_existe(glob, base_rel, index) and not _tem_marcacao(linha, ref):
                achados.append((rel, n, ref, "glob sem nenhum match no índice git"))
            continue
        if not _existe(ref, base_rel, index, busca_por_nome=(tipo == "backtick")):
            if _tem_marcacao(linha, ref):
                continue
            motivo = "não existe no índice git e a linha não tem marcação de escopo/estado"
            pendentes.append(((rel, n, ref, motivo), _candidatos_ignore(ref, base_rel)))
    return achados, pendentes


def _cobertura_reversa(root: Path, index: set[str]) -> list[Achado]:
    achados: list[Achado] = []
    for cat in CATEGORIAS_REVERSAS:
        router = f"{cat}/CLAUDE.md"
        if router not in index:
            continue
        try:
            texto = (root / router).read_text(encoding="utf-8")
        except OSError:
            continue  # ilegível já reportado no passe principal
        pastas = {
            e.split("/")[1]
            for e in index
            if e.startswith(cat + "/") and e.count("/") >= 2
        }
        for pasta in sorted(pastas):
            if pasta not in texto:
                achados.append(
                    (router, 0, f"{cat}/{pasta}/",
                     "pasta versionada de 1º nível sem menção no router (cobertura reversa)")
                )
    router = "tools/CLAUDE.md"
    if router in index:
        try:
            texto = (root / router).read_text(encoding="utf-8")
        except OSError:
            texto = ""
        globs = [g for _, g in extrair_refs(texto) if "*" in g]
        scripts = [
            e.rsplit("/", 1)[-1]
            for e in index
            if e.startswith("tools/") and e.endswith(".py") and e.count("/") == 1
        ]
        for nome in sorted(scripts):
            stem = nome[: -len(".py")]
            if nome in texto or stem in texto or any(fnmatch(nome, g) for g in globs):
                continue
            achados.append(
                (router, 0, f"tools/{nome}",
                 "script versionado sem menção literal ou glob no router (cobertura reversa)")
            )
        m = RE_CONTAGEM.search(texto)
        if m and int(m.group(1)) != len(scripts):
            achados.append(
                (router, 0, m.group(0),
                 f"contagem declarada ({m.group(1)}) difere do índice git ({len(scripts)})")
            )
    return achados


def _e_o_repo_raiz(index: set[str]) -> bool:
    """Este índice é o do repo que carrega este lint, e não um repo sintético de teste?

    `ALVOS_OBRIGATORIOS` é a lista de routers DESTE repo: exigi-la de qualquer
    árvore quebraria o uso do lint em repo pequeno (e os testes que montam
    repo-laboratório com um `CLAUDE.md` só). A impressão digital são quatro
    arquivos que só existem juntos aqui, nenhum deles na lista protegida, e
    nenhum deles escapatória: `conftest.py` derruba a suíte inteira,
    `pytest.ini` muda os `testpaths`, `requirements.txt` quebra o CI e
    `tools/lint_routers.py` é o próprio gate.
    """
    return all(e in index for e in IMPRESSAO_DIGITAL)


def _dirs_do_head(root: Path) -> set[str]:
    """Diretórios de 1º nível no último commit — a lista de categorias que NÃO se
    auto-desliga quando o índice é mutado (ver `_alvos_fora_do_indice`)."""
    try:
        saida = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-tree", "-d", "-z", "--name-only", "HEAD"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
        timeout=TETO_GIT)
    except (subprocess.CalledProcessError, OSError):
        return set()  # repo sem commit ainda: o índice basta
    return {d for d in saida.stdout.split("\0") if d}


def _alvos_fora_do_indice(
    root: Path, index: set[str], dirs_historicos: set[str] | None = None
) -> list[Achado]:
    """Alvo que existe no disco e saiu do índice git — o silêncio mais perigoso do lint.

    A lista de alvos é montada A PARTIR do índice, então bastaria um `git rm --cached`
    para o arquivo sair da vigilância sem uma linha de aviso: a contagem final apenas
    encolhe, e "0 erro(s) em 5 arquivo(s)" lê-se igual a "0 erro(s) em 6".

    As categorias vêm do índice **unido ao último commit**. Só o índice não serve: uma
    categoria com um único arquivo versionado deixaria de ser categoria no instante em
    que esse arquivo saísse — a checagem se auto-desligaria justamente no caso que ela
    existe para pegar.

    Categoria que nunca esteve neste git fica de fora de propósito: repos aninhados
    (clones de outros projetos dentro deste) têm `CLAUDE.md` próprio e não pertencem a
    este repositório — acusá-los seria ruído garantido na máquina que os tem clonados.
    `.claude-memory/` também fica fora: memória do agente não é router.
    """
    do_indice = {
        e.split("/")[0] for e in index
        if "/" in e and not e.startswith(".claude-memory/")
    }
    categorias = sorted(
        (do_indice | {d for d in (dirs_historicos or set()) if d != ".claude-memory"})
    )
    achados: list[Achado] = []
    vistos: set[str] = set()
    for rel in (ALVOS_OBRIGATORIOS if _e_o_repo_raiz(index) else ()):
        if rel not in index:
            vistos.add(rel)
            achados.append((
                rel, 0, rel,
                "alvo obrigatório do lint não está no índice git "
                "(ALVOS_OBRIGATORIOS em tools/lint_routers.py)",
            ))
    for rel in list(ALVOS_RAIZ) + [f"{c}/CLAUDE.md" for c in categorias]:
        if rel in vistos:
            continue
        if rel not in index and (root / rel).is_file():
            achados.append(
                (rel, 0, rel, "alvo do lint existe no disco e está fora do índice git")
            )
    return achados


def lint(root: Path, index: set[str], ignorados,
         dirs_historicos: set[str] | None = None) -> list[Achado]:
    """Núcleo puro: `ignorados(candidatos) -> set` decide o 'fora do git por design'."""
    achados: list[Achado] = []
    pendentes: list[tuple[Achado, list[tuple[str, bool]]]] = []

    # .claude-memory/ fica fora: um .md de memória que case com *CLAUDE.md é memória,
    # nunca router.
    alvos = sorted(
        e for e in index
        if e.endswith("CLAUDE.md") and not e.startswith(".claude-memory/")
    )
    alvos.extend(e for e in ALVOS_RAIZ if e in index and e not in alvos)

    for rel in alvos:
        try:
            texto = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            achados.append((rel, 0, "-", f"arquivo ilegível: {type(exc).__name__}"))
            continue
        a, p = _checar_arquivo(rel, texto, index)
        achados += a
        pendentes += p

    todos_cands = sorted({c for _, cands in pendentes for c, _ in cands})
    fora_por_design = ignorados(todos_cands)
    for achado, cands in pendentes:
        # A catch-all só isenta quando a referência é mesmo um CAMINHO: um nome solto
        # ("historico.json") não denota nada na raiz, e aceitar `/*` para ele deixaria
        # sumir em silêncio qualquer arquivo citado pelo nome. Regra específica isenta
        # em qualquer forma, porque ali o gitignore falou do caminho de verdade.
        e_caminho = "/" in achado[2].rstrip("/")
        isento = any(
            c in fora_por_design
            and (fora_por_design[c] not in PADROES_CATCH_ALL or (canonico and e_caminho))
            for c, canonico in cands
        )
        if not isento:
            achados.append(achado)

    achados += _cobertura_reversa(root, index)
    achados += _alvos_fora_do_indice(root, index, dirs_historicos)
    return achados


def preparar_saida(fluxo) -> bool:
    """Força UTF-8 quando a saída é capturada por outro processo (CI, wrapper de task,
    pipe): sem isso o Windows grava "não" em cp1252 e o Linux em UTF-8 — mesmo texto,
    bytes diferentes. Devolve se reconfigurou.

    Console interativo fica intocado (viraria mojibake em terminal legado), e fluxo
    ausente ou que não aceita reconfiguração passa batido: sob `pythonw.exe` — como
    rodam os wrappers das tasks — `sys.stdout` é None, e sob `redirect_stdout` é um
    `StringIO`, que não tem `reconfigure`.

    Vale em qualquer SO de propósito: no Linux com `LANG=C` a saída sairia em ASCII,
    e o ponto é o byte ser o mesmo em toda máquina. Chamado só a partir do `main` —
    importar este módulo não mexe na saída de ninguém."""
    if fluxo is None or not hasattr(fluxo, "reconfigure") or not hasattr(fluxo, "isatty"):
        return False
    try:
        if fluxo.isatty():
            return False
        fluxo.reconfigure(encoding="utf-8", errors="replace")
        return True
    except (ValueError, OSError, TypeError):
        # TypeError: fluxo de terceiro com assinatura própria de reconfigure. Saída
        # em bytes diferentes é ruim; gate que morre por causa disso é pior.
        return False


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        preparar_saida(fluxo)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="raiz do repo (default: git toplevel do cwd)")
    args = parser.parse_args(argv)

    try:
        if args.root:
            root = Path(args.root).resolve()
            subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root,
                           capture_output=True, check=True, timeout=TETO_GIT)
        else:
            saida = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                   capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=TETO_GIT)
            root = Path(saida.stdout.strip())
        index = _indice_git(root)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"lint_routers: uso inválido — não é um repo git legível ({exc})", file=sys.stderr)
        return 2

    achados = lint(root, index, lambda cands: _ignorados_git(root, cands),
                   dirs_historicos=_dirs_do_head(root))
    for arquivo, linha, ref, motivo in achados:
        print(f"ERRO\t{arquivo}:{linha}\t{ref}\t{motivo}")
    n_alvos = sum(1 for e in index
                  if (e.endswith("CLAUDE.md") and not e.startswith(".claude-memory/"))
                  or e in ALVOS_RAIZ)
    print(f"lint_routers: {len(achados)} erro(s) em {n_alvos} arquivo(s) verificados")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
