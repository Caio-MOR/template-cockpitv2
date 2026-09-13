"""Gate de criação nova em `.claude/` e `workflows/`.

A regra `.claude/rules/graph-engineering.md` se chama "obrigatório em criações novas";
este arquivo a torna mecânica. Skill nova exige frontmatter (`name` = pasta,
`description`), declaração de `formato` e refs internas vivas; workflow novo exige
`workflow.md` com bloco mermaid, `%% formato:` válido e a palavra `teto` se declarar
loop; agente exige `name`/`description`/`tools`; command exige `description`.

As listas de isenção de legado nascem VAZIAS neste template e só encolhem: entrada que
já cumpre o contrato (ou que sumiu do índice) reprova como isenção morta — isenção sem
sensor apodrece em silêncio.

Convenções herdadas dos outros gates: existência é medida no **índice git**, nunca no
disco; parse de frontmatter é por linha porque `pyyaml` não está no `requirements.txt`;
cada teste varre todos os artefatos e nomeia todos os infratores de uma vez.

Cada contrato é uma função pura que recebe o índice e um leitor. Os testes "reais" passam
o índice git e o disco; os testes "sintéticos" passam um índice de brinquedo e textos de
mentira, para que enfraquecer um contrato reprove mesmo com todos os artefatos reais
conformes.
"""
import functools
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = ".agents/skills/"
AGENTES = ".claude/agents/"
COMMANDS = ".claude/commands/"
WORKFLOWS = "workflows/"
EVALS = "evals/"
TETO_SUBPROC = 120

# Os cinco formatos da regra graph-engineering (híbrido aceita "(...)" logo depois).
VALORES_FORMATO = r"(cadeia|diamante|branch|loop|h[ií]brido)\b"
# Declaração em SKILL.md: uma linha, prefixos `%%`, `-`, `>` e `**` tolerados, e o valor
# obrigatoriamente um dos cinco. Sem o valor, "formato de pagamento" casaria.
RE_FORMATO_SKILL = re.compile(
    r"^\s*(?:%%|-|>|\*\*)*\s*\**formato\**\s*:\s*\**\s*" + VALORES_FORMATO, re.IGNORECASE
)
# Declaração em workflow.md: dentro do primeiro bloco mermaid, linha cujo primeiro texto
# não-branco é `%% formato:` (indentação tolerada).
RE_FORMATO_MERMAID = re.compile(r"^\s*%%\s*formato\s*:\s*" + VALORES_FORMATO, re.IGNORECASE)
RE_BLOCO_MERMAID = re.compile(r"^```\s*mermaid\s*$(.*?)^```", re.MULTILINE | re.DOTALL)
# `*`, não `+`: ref a pasta nua (`` `scripts/` ``) também é caminho.
RE_REF_INTERNA = re.compile(r"`((?:scripts|references|assets)/[^`\n]*)`")
RE_CHAVE = re.compile(r"^([A-Za-z][\w-]*):[ \t]*(.*)$")
RE_LOOP = re.compile(r"\bloop\b", re.IGNORECASE)
# A **palavra** `teto`: "arquiteto" não conta.
RE_TETO = re.compile(r"\bteto\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Listas de isenção. Vazias no template; só encolhem (ver os testes de isenção morta).
# Ao declarar o formato de um artefato isento, tirar o nome daqui no mesmo commit.
LEGADO_SEM_FORMATO_SKILLS: frozenset[str] = frozenset()
LEGADO_SEM_FORMATO_WORKFLOWS: frozenset[str] = frozenset()
LEGADO_NOME: frozenset[str] = frozenset()
LEGADO_SEM_EVALS_SKILLS: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Leitura


@functools.lru_cache(maxsize=None)
def _indice() -> frozenset:
    """Caminhos no índice git, com `/`. Sem git = falha alta, nunca cair para o disco."""
    saida = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=RAIZ, capture_output=True, check=True, timeout=TETO_SUBPROC,
    )
    return frozenset(p for p in saida.stdout.decode("utf-8").split("\0") if p)


def _ler(rel: str) -> str:
    return (RAIZ / rel).read_text(encoding="utf-8-sig")


def _pastas(indice, prefixo: str) -> set:
    """Pastas de 1º nível sob `prefixo` que têm pelo menos um arquivo no índice."""
    n = prefixo.count("/")
    return {p.split("/")[n] for p in indice if p.startswith(prefixo) and p.count("/") > n}


def _frontmatter(texto: str):
    """Chaves do frontmatter (parse por linha) ou None se não há `---` na linha 1 e fecho.

    `splitlines()` engole o `\\r`, então CRLF é tratado igual a LF. Valor vazio na linha
    da chave com continuação indentada logo abaixo conta como preenchido.
    """
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return None
    chaves: dict[str, str] = {}
    for i, linha in enumerate(linhas[1:], start=1):
        if linha.strip() == "---":
            return chaves
        achado = RE_CHAVE.match(linha)
        if achado:
            valor = achado.group(2).strip()
            if not valor and i + 1 < len(linhas) and linhas[i + 1].startswith((" ", "\t")):
                valor = linhas[i + 1].strip()
            chaves[achado.group(1)] = valor
    return None


def _primeiro_mermaid(texto: str):
    achado = RE_BLOCO_MERMAID.search(texto)
    return achado.group(1) if achado else None


def _declaracao_mermaid(texto: str):
    """A linha `%% formato:` válida do primeiro bloco mermaid, ou None."""
    bloco = _primeiro_mermaid(texto)
    if bloco is None:
        return None
    for linha in bloco.splitlines():
        if RE_FORMATO_MERMAID.match(linha):
            return linha
    return None


def _skill_declara_formato(texto: str) -> bool:
    return any(RE_FORMATO_SKILL.match(linha) for linha in texto.splitlines())


# ---------------------------------------------------------------------------
# Contratos: funções puras sobre (indice, ler). Devolvem os infratores, nomeados.


def _pastas_sem_arquivo(indice, prefixo: str, arquivo: str) -> list:
    return sorted(
        pasta for pasta in _pastas(indice, prefixo)
        if f"{prefixo}{pasta}/{arquivo}" not in indice
    )


def _skills(indice) -> list:
    return sorted(pasta for pasta in _pastas(indice, SKILLS) if f"{SKILLS}{pasta}/SKILL.md" in indice)


def _workflows(indice) -> list:
    return sorted(
        pasta for pasta in _pastas(indice, WORKFLOWS) if f"{WORKFLOWS}{pasta}/workflow.md" in indice
    )


def _arquivos(indice, prefixo: str) -> list:
    return sorted(p for p in indice if p.startswith(prefixo) and p.endswith(".md") and p.count("/") == prefixo.count("/"))


def _faltas_frontmatter(texto: str, obrigatorias) -> list:
    chaves = _frontmatter(texto)
    if chaves is None:
        return ["frontmatter ausente ou sem fecho (`---` na linha 1 e outro `---` depois)"]
    return [f"chave `{c}:` ausente ou vazia" for c in obrigatorias if not chaves.get(c)]


def _skills_com_frontmatter_incompleto(indice, ler) -> dict:
    return {
        skill: f for skill in _skills(indice)
        if (f := _faltas_frontmatter(ler(f"{SKILLS}{skill}/SKILL.md"), ("name", "description")))
    }


def _skills_com_name_divergente(indice, ler, legado) -> dict:
    divergentes = {}
    for skill in _skills(indice):
        if skill in legado:
            continue
        chaves = _frontmatter(ler(f"{SKILLS}{skill}/SKILL.md")) or {}
        if chaves.get("name") != skill:
            divergentes[skill] = chaves.get("name")
    return divergentes


def _skills_sem_formato(indice, ler, legado) -> list:
    return [
        skill for skill in _skills(indice)
        if skill not in legado and not _skill_declara_formato(ler(f"{SKILLS}{skill}/SKILL.md"))
    ]


def _refs_internas_mortas(indice, skill: str, texto: str) -> list:
    mortas = []
    for ref in RE_REF_INTERNA.findall(texto):
        if any(c in ref for c in "*<>{}[]"):
            continue  # glob ou placeholder, não é caminho
        alvo = f"{SKILLS}{skill}/{ref}"
        existe = (
            any(p.startswith(alvo) for p in indice) if ref.endswith("/") else alvo in indice
        )
        if not existe:
            mortas.append(ref)
    return mortas


def _skills_com_refs_mortas(indice, ler) -> dict:
    return {
        skill: m for skill in _skills(indice)
        if (m := _refs_internas_mortas(indice, skill, ler(f"{SKILLS}{skill}/SKILL.md")))
    }


def _workflows_sem_mermaid(indice, ler) -> list:
    return [wf for wf in _workflows(indice) if _primeiro_mermaid(ler(f"{WORKFLOWS}{wf}/workflow.md")) is None]


def _workflows_sem_formato(indice, ler, legado) -> list:
    return [
        wf for wf in _workflows(indice)
        if wf not in legado and _declaracao_mermaid(ler(f"{WORKFLOWS}{wf}/workflow.md")) is None
    ]


def _workflows_com_loop_sem_teto(indice, ler) -> list:
    sem_teto = []
    for wf in _workflows(indice):
        texto = ler(f"{WORKFLOWS}{wf}/workflow.md")
        declaracao = _declaracao_mermaid(texto) or ""
        if RE_LOOP.search(declaracao) and not RE_TETO.search(texto):
            sem_teto.append(wf)
    return sem_teto


def _casos_evals(indice, skill: str) -> list:
    """Nomes das pastas de caso sob `evals/<skill>/`, a partir do índice git."""
    prefixo = f"{EVALS}{skill}/"
    n = prefixo.count("/")
    return sorted({p.split("/")[n] for p in indice if p.startswith(prefixo) and p.count("/") > n})


def _skills_sem_evals_completos(indice, ler, legado) -> dict:
    """Skill nova (fora de LEGADO_SEM_EVALS_SKILLS) precisa de `evals/<skill>/` com pelo
    menos 1 caso com `positivo` nas tags e 1 com `negativo` (R18: o gate de criação nova
    ganha a porta de disparo — ver `docs/evals.md` e o marketplace `caio-mor`, que exige
    3+3). Tags são lidas cru do frontmatter (parse por linha, sem pyyaml)."""
    problemas = {}
    for skill in _skills(indice):
        if skill in legado:
            continue
        casos = _casos_evals(indice, skill)
        if not casos:
            problemas[skill] = ["sem pasta evals/<skill>/ com casos"]
            continue
        positivos = negativos = 0
        for caso in casos:
            rel = f"{EVALS}{skill}/{caso}/prompt.md"
            if rel not in indice:
                continue
            chaves = _frontmatter(ler(rel)) or {}
            tags = str(chaves.get("tags", ""))
            positivos += "positivo" in tags
            negativos += "negativo" in tags
        faltas = []
        if positivos < 1:
            faltas.append("sem caso positivo")
        if negativos < 1:
            faltas.append("sem caso negativo")
        if faltas:
            problemas[skill] = faltas
    return problemas


def _evals_isencoes_mortas(indice, ler, legado) -> list:
    completos = _skills_sem_evals_completos(indice, ler, frozenset())
    return [
        f"LEGADO_SEM_EVALS_SKILLS: {skill} já tem evals completos (1 positivo + 1 negativo)"
        for skill in sorted(legado)
        if f"{SKILLS}{skill}/SKILL.md" in indice and skill not in completos
    ]


def _evals_isencoes_fantasmas(indice, legado) -> list:
    return [f"skill {s}" for s in sorted(legado) if f"{SKILLS}{s}/SKILL.md" not in indice]


def _agentes_fora_do_contrato(indice, ler) -> dict:
    problemas = {}
    for rel in _arquivos(indice, AGENTES):
        texto = ler(rel)
        faltas = _faltas_frontmatter(texto, ("name", "description", "tools"))
        stem = rel.rsplit("/", 1)[1][:-3]
        chaves = _frontmatter(texto) or {}
        if "name" in chaves and chaves["name"] != stem:
            faltas.append(f"name `{chaves['name']}` != arquivo `{stem}`")
        if faltas:
            problemas[rel] = faltas
    return problemas


def _commands_fora_do_contrato(indice, ler) -> dict:
    return {
        rel: f for rel in _arquivos(indice, COMMANDS)
        if (f := _faltas_frontmatter(ler(rel), ("description",)))
    }


def _isencoes_mortas(indice, ler, legado_skills, legado_workflows, legado_nome) -> list:
    mortas = []
    for skill in sorted(legado_skills):
        if f"{SKILLS}{skill}/SKILL.md" in indice and _skill_declara_formato(ler(f"{SKILLS}{skill}/SKILL.md")):
            mortas.append(f"LEGADO_SEM_FORMATO_SKILLS: {skill} já declara formato")
    for wf in sorted(legado_workflows):
        if f"{WORKFLOWS}{wf}/workflow.md" in indice and _declaracao_mermaid(ler(f"{WORKFLOWS}{wf}/workflow.md")):
            mortas.append(f"LEGADO_SEM_FORMATO_WORKFLOWS: {wf} já declara %% formato:")
    for skill in sorted(legado_nome):
        if f"{SKILLS}{skill}/SKILL.md" in indice:
            chaves = _frontmatter(ler(f"{SKILLS}{skill}/SKILL.md")) or {}
            if chaves.get("name") == skill:
                mortas.append(f"LEGADO_NOME: {skill} já tem name = pasta")
    return mortas


def _isencoes_fantasmas(indice, legado_skills, legado_workflows, legado_nome) -> list:
    return (
        [f"skill {s}" for s in sorted(legado_skills | legado_nome) if f"{SKILLS}{s}/SKILL.md" not in indice]
        + [f"workflow {w}" for w in sorted(legado_workflows) if f"{WORKFLOWS}{w}/workflow.md" not in indice]
    )


# ---------------------------------------------------------------------------
# Skill nova nasce com contrato — artefatos reais


def test_toda_pasta_de_skill_tem_skill_md():
    """Pasta em `.claude/skills/` no índice sem `SKILL.md` reprova nomeando a pasta."""
    assert _pastas_sem_arquivo(_indice(), SKILLS, "SKILL.md") == []


def test_skill_md_tem_frontmatter_com_name_e_description():
    """`---` na linha 1, fecho, `name:` e `description:` não vazios."""
    faltas = _skills_com_frontmatter_incompleto(_indice(), _ler)
    assert faltas == {}, f"skills com frontmatter incompleto: {faltas}"


def test_name_da_skill_e_o_nome_da_pasta():
    """`name` do frontmatter = nome da pasta, salvo LEGADO_NOME."""
    divergentes = _skills_com_name_divergente(_indice(), _ler, LEGADO_NOME)
    assert divergentes == {}, f"name do frontmatter != pasta: {divergentes}"


def test_skill_nova_declara_formato():
    """Skill fora de LEGADO_SEM_FORMATO_SKILLS sem `formato: <um dos 5>` reprova.

    Regra: graph-engineering.md — skill trivial declara só o formato em uma linha;
    multi-etapa declara formato (e grafo se tiver ramos/loops).
    """
    sem = _skills_sem_formato(_indice(), _ler, LEGADO_SEM_FORMATO_SKILLS)
    assert sem == [], (
        f"skills novas sem declaração de formato (cadeia|diamante|branch|loop|híbrido): {sem}"
    )


def test_refs_internas_da_skill_existem_no_indice():
    """Ref em backtick a `scripts/`, `references/` ou `assets/` da própria skill que não
    está no índice git reprova nomeando a ref."""
    mortas = _skills_com_refs_mortas(_indice(), _ler)
    assert mortas == {}, f"refs internas mortas: {mortas}"


def test_skill_nova_tem_evals_de_disparo_positivo_e_negativo():
    """Skill fora de LEGADO_SEM_EVALS_SKILLS sem `evals/<skill>/` com >= 1 caso
    positivo e >= 1 negativo reprova, nomeada (R18 — a mesma prova de disparo que o
    marketplace `caio-mor` exige, versão modelo: 1+1 em vez de 3+3)."""
    faltas = _skills_sem_evals_completos(_indice(), _ler, LEGADO_SEM_EVALS_SKILLS)
    assert faltas == {}, f"skills sem evals de disparo completos (1 positivo + 1 negativo): {faltas}"


# ---------------------------------------------------------------------------
# Workflow novo nasce com grafo declarado — artefatos reais


def test_toda_pasta_de_workflow_tem_workflow_md():
    """Pasta de 1º nível em `workflows/` no índice sem `workflow.md` reprova."""
    assert _pastas_sem_arquivo(_indice(), WORKFLOWS, "workflow.md") == []


def test_workflow_md_tem_bloco_mermaid():
    """`workflow.md` sem bloco ```mermaid reprova nomeando o arquivo."""
    sem = _workflows_sem_mermaid(_indice(), _ler)
    assert sem == [], f"workflow.md sem bloco mermaid: {sem}"


def test_workflow_novo_declara_formato_no_mermaid():
    """Fora de LEGADO_SEM_FORMATO_WORKFLOWS, o primeiro bloco mermaid precisa de uma
    linha `%% formato: <um dos 5>` (indentação tolerada)."""
    sem = _workflows_sem_formato(_indice(), _ler, LEGADO_SEM_FORMATO_WORKFLOWS)
    assert sem == [], f"workflows novos sem `%% formato:` válido no bloco mermaid: {sem}"


def test_loop_declarado_exige_teto():
    """Declaração que cita `loop` exige a palavra `teto` no workflow.md.

    Guardrail da graph-engineering ("loop sempre com teto de iterações"). "sem loop"
    também dispara, de propósito: a palavra `teto` custa nada e negação por grafia é
    jogo que não converge.
    """
    sem_teto = _workflows_com_loop_sem_teto(_indice(), _ler)
    assert sem_teto == [], f"workflows com loop declarado e sem teto: {sem_teto}"


# ---------------------------------------------------------------------------
# Agente e command novos com frontmatter — artefatos reais


def test_agente_tem_frontmatter_minimo_e_name_igual_ao_arquivo():
    """`.claude/agents/*.md` com `name`, `description`, `tools` e name = stem."""
    problemas = _agentes_fora_do_contrato(_indice(), _ler)
    assert problemas == {}, f"agentes fora do contrato: {problemas}"


def test_command_tem_description():
    """`.claude/commands/*.md` com frontmatter e `description:` não vazia."""
    problemas = _commands_fora_do_contrato(_indice(), _ler)
    assert problemas == {}, f"commands fora do contrato: {problemas}"


# ---------------------------------------------------------------------------
# A isenção só encolhe — artefatos reais


def test_isencao_morta_reprova():
    """Entrada de lista de isenção que já cumpre o contrato reprova, nomeada."""
    mortas = _isencoes_mortas(
        _indice(), _ler, LEGADO_SEM_FORMATO_SKILLS, LEGADO_SEM_FORMATO_WORKFLOWS, LEGADO_NOME
    )
    assert mortas == [], f"isenções mortas — tirar da lista: {mortas}"


def test_isencao_aponta_para_artefato_no_indice():
    """Nome em lista de isenção que não existe no índice git reprova."""
    fantasmas = _isencoes_fantasmas(
        _indice(), LEGADO_SEM_FORMATO_SKILLS, LEGADO_SEM_FORMATO_WORKFLOWS, LEGADO_NOME
    )
    assert fantasmas == [], f"isenções para artefatos que não existem: {fantasmas}"


def test_isencao_de_evals_morta_reprova():
    """Entrada de LEGADO_SEM_EVALS_SKILLS cuja skill já tem 1 positivo + 1 negativo reprova."""
    mortas = _evals_isencoes_mortas(_indice(), _ler, LEGADO_SEM_EVALS_SKILLS)
    assert mortas == [], f"isenções de evals mortas — tirar da lista: {mortas}"


def test_isencao_de_evals_aponta_para_skill_no_indice():
    """Nome em LEGADO_SEM_EVALS_SKILLS que não existe no índice reprova."""
    fantasmas = _evals_isencoes_fantasmas(_indice(), LEGADO_SEM_EVALS_SKILLS)
    assert fantasmas == [], f"isenções de evals para skills que não existem: {fantasmas}"


# ---------------------------------------------------------------------------
# Registro no conftest: o gate está protegido e os números do conftest são reais


def test_gate_registrado_em_gates_obrigatorios():
    """Este arquivo está em GATES_OBRIGATORIOS com mínimo <= testes reais."""
    import conftest

    minimo = conftest.GATES_OBRIGATORIOS.get("tests/test_criacao_nova.py")
    reais = sum(1 for nome in globals() if nome.startswith("test_"))
    assert minimo is not None, "tests/test_criacao_nova.py fora de GATES_OBRIGATORIOS no conftest.py"
    assert minimo <= reais, f"mínimo {minimo} em GATES_OBRIGATORIOS > {reais} testes reais"


def test_coleta_medida_e_piso_batem_com_a_coleta_real():
    """`COLETA_MEDIDA` é conferida contra `pytest --collect-only`; número solto apodrece.
    `PISO_COLETA` tem de ser a metade inteira da coleta medida — folga que absorve remoção
    pontual sem esconder o sumiço de um arquivo."""
    import conftest

    saida = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
        env={k: v for k, v in __import__("os").environ.items() if k != "PYTEST_ADDOPTS"},
        timeout=TETO_SUBPROC,
    )
    achado = re.search(r"(\d+) tests? collected", saida.stdout)
    assert achado, saida.stdout + saida.stderr
    real = int(achado.group(1))
    assert conftest.COLETA_MEDIDA == real, (
        f"COLETA_MEDIDA={conftest.COLETA_MEDIDA} no conftest.py, coleta real é {real}: "
        f"atualize o número (e PISO_COLETA = metade inteira) no mesmo commit"
    )
    assert conftest.PISO_COLETA == real // 2, (
        f"PISO_COLETA={conftest.PISO_COLETA}, esperado {real // 2} (metade inteira de {real})"
    )


# ---------------------------------------------------------------------------
# Os mesmos contratos sobre artefatos sintéticos infratores: é o que faz enfraquecer um
# contrato reprovar mesmo com o repo inteiro conformante. Um teste por contrato.

SKILL_OK = "---\nname: {nome}\ndescription: faz algo\n---\n\nformato: cadeia\n\ncorpo\n"
WF_OK = "# wf\n\n```mermaid\n%% formato: cadeia — linear\nflowchart TD\n    A --> B\n```\n"


def _leitor(arquivos: dict):
    return lambda rel: arquivos[rel]


def test_sintetico_skill_sem_frontmatter_ou_sem_description_reprova():
    """Sem `---` na linha 1, sem fecho, ou sem `description:`."""
    indice = frozenset({f"{SKILLS}a/SKILL.md", f"{SKILLS}b/SKILL.md", f"{SKILLS}c/SKILL.md", f"{SKILLS}d/SKILL.md"})
    ler = _leitor({
        f"{SKILLS}a/SKILL.md": "name: a\ndescription: x\n---\n",          # sem `---` na linha 1
        f"{SKILLS}b/SKILL.md": "---\nname: b\ndescription: x\n",          # sem fecho
        f"{SKILLS}c/SKILL.md": "---\nname: c\n---\n",                     # sem description
        f"{SKILLS}d/SKILL.md": SKILL_OK.format(nome="d"),
    })
    faltas = _skills_com_frontmatter_incompleto(indice, ler)
    assert set(faltas) == {"a", "b", "c"}
    assert faltas["a"] == faltas["b"] == ["frontmatter ausente ou sem fecho (`---` na linha 1 e outro `---` depois)"]
    assert faltas["c"] == ["chave `description:` ausente ou vazia"]


def test_sintetico_name_diferente_da_pasta_reprova_salvo_legado():
    """`name: outra` na pasta `x` reprova nomeando `x`; em LEGADO_NOME, passa."""
    indice = frozenset({f"{SKILLS}x/SKILL.md"})
    ler = _leitor({f"{SKILLS}x/SKILL.md": "---\nname: outra\ndescription: d\n---\n"})
    assert _skills_com_name_divergente(indice, ler, frozenset()) == {"x": "outra"}
    assert _skills_com_name_divergente(indice, ler, frozenset({"x"})) == {}


def test_sintetico_skill_nova_sem_formato_ou_com_formato_invalido_reprova():
    """Sem declaração, ou com valor fora dos cinco, reprova; no legado, passa."""
    indice = frozenset({f"{SKILLS}nova/SKILL.md", f"{SKILLS}banana/SKILL.md", f"{SKILLS}ok/SKILL.md"})
    ler = _leitor({
        f"{SKILLS}nova/SKILL.md": "---\nname: nova\ndescription: d\n---\nFormato de pagamento: 30 dias\n",
        f"{SKILLS}banana/SKILL.md": "---\nname: banana\ndescription: d\n---\n%% formato: banana\n",
        f"{SKILLS}ok/SKILL.md": SKILL_OK.format(nome="ok"),
    })
    assert _skills_sem_formato(indice, ler, frozenset()) == ["banana", "nova"]
    assert _skills_sem_formato(indice, ler, frozenset({"nova", "banana"})) == []
    assert not RE_FORMATO_SKILL.match("formato: banana")


def test_sintetico_ref_interna_morta_reprova_e_glob_e_ignorado():
    """`scripts/nao_existe.py` fora do índice reprova nomeando a ref."""
    indice = frozenset({f"{SKILLS}s/SKILL.md", f"{SKILLS}s/scripts/existe.py"})
    texto = "use `scripts/existe.py`, `scripts/nao_existe.py`, `references/*.md` e `assets/`"
    assert _refs_internas_mortas(indice, "s", texto) == ["scripts/nao_existe.py", "assets/"]
    assert _skills_com_refs_mortas(indice, _leitor({f"{SKILLS}s/SKILL.md": texto})) == {
        "s": ["scripts/nao_existe.py", "assets/"]
    }


def test_sintetico_skill_sem_evals_ou_sem_positivo_ou_negativo_reprova():
    """Sem `evals/<skill>/`, só com positivo, ou completa (1+1) — mutação do contrato."""
    indice = frozenset({
        f"{SKILLS}a/SKILL.md",
        f"{SKILLS}b/SKILL.md", f"{EVALS}b/so-positivo/prompt.md",
        f"{SKILLS}c/SKILL.md", f"{EVALS}c/pos/prompt.md", f"{EVALS}c/neg/prompt.md",
    })
    ler = _leitor({
        f"{EVALS}b/so-positivo/prompt.md": "---\nname: so-positivo\ntags: [positivo]\n---\n",
        f"{EVALS}c/pos/prompt.md": "---\nname: pos\ntags: [positivo]\n---\n",
        f"{EVALS}c/neg/prompt.md": "---\nname: neg\ntags: [negativo]\n---\n",
    })
    faltas = _skills_sem_evals_completos(indice, ler, frozenset())
    assert faltas == {
        "a": ["sem pasta evals/<skill>/ com casos"],
        "b": ["sem caso negativo"],
    }
    assert _skills_sem_evals_completos(indice, ler, frozenset({"a", "b"})) == {}


def test_sintetico_isencao_de_evals_morta_e_fantasma_reprovam():
    indice = frozenset({
        f"{SKILLS}viva/SKILL.md", f"{EVALS}viva/pos/prompt.md", f"{EVALS}viva/neg/prompt.md",
    })
    ler = _leitor({
        f"{EVALS}viva/pos/prompt.md": "---\nname: pos\ntags: [positivo]\n---\n",
        f"{EVALS}viva/neg/prompt.md": "---\nname: neg\ntags: [negativo]\n---\n",
    })
    assert _evals_isencoes_mortas(indice, ler, frozenset({"viva"})) == [
        "LEGADO_SEM_EVALS_SKILLS: viva já tem evals completos (1 positivo + 1 negativo)"
    ]
    assert _evals_isencoes_fantasmas(indice, frozenset({"sumiu"})) == ["skill sumiu"]


def test_sintetico_workflow_sem_mermaid_ou_sem_formato_valido_reprova():
    """Sem bloco, sem `%% formato:` ou com valor inválido."""
    indice = frozenset({f"{WORKFLOWS}a/workflow.md", f"{WORKFLOWS}b/workflow.md", f"{WORKFLOWS}c/workflow.md", f"{WORKFLOWS}d/workflow.md"})
    ler = _leitor({
        f"{WORKFLOWS}a/workflow.md": "# a\nsem grafo\n",
        f"{WORKFLOWS}b/workflow.md": "```mermaid\nflowchart TD\n  A --> B\n```\n",
        f"{WORKFLOWS}c/workflow.md": "```mermaid\n%% formato: banana\nflowchart TD\n```\n",
        f"{WORKFLOWS}d/workflow.md": WF_OK,
    })
    assert _workflows_sem_mermaid(indice, ler) == ["a"]
    assert _workflows_sem_formato(indice, ler, frozenset()) == ["a", "b", "c"]
    assert _workflows_sem_formato(indice, ler, frozenset({"a", "b", "c"})) == []


def test_sintetico_loop_sem_teto_reprova_e_arquiteto_nao_conta():
    """`loop` na declaração sem a palavra `teto` reprova; `arquiteto` não é `teto`."""
    indice = frozenset({f"{WORKFLOWS}l/workflow.md", f"{WORKFLOWS}m/workflow.md", f"{WORKFLOWS}n/workflow.md"})
    ler = _leitor({
        f"{WORKFLOWS}l/workflow.md": "```mermaid\n%% formato: loop — gera e avalia\nflowchart TD\n```\nretry ate passar\n",
        f"{WORKFLOWS}m/workflow.md": "```mermaid\n%% formato: loop\nflowchart TD\n```\nrevisado pelo arquiteto\n",
        f"{WORKFLOWS}n/workflow.md": "```mermaid\n%% formato: loop\nflowchart TD\n```\nTeto: 3 iteracoes\n",
    })
    assert _workflows_com_loop_sem_teto(indice, ler) == ["l", "m"]


def test_sintetico_agente_sem_tools_ou_name_divergente_reprova():
    """Agente sem `tools:` e agente com `name` != arquivo reprovam, nomeados."""
    indice = frozenset({f"{AGENTES}a.md", f"{AGENTES}b.md", f"{AGENTES}c.md"})
    ler = _leitor({
        f"{AGENTES}a.md": "---\nname: a\ndescription: d\n---\n",
        f"{AGENTES}b.md": "---\nname: outro\ndescription: d\ntools: Read\n---\n",
        f"{AGENTES}c.md": "---\nname: c\ndescription: d\ntools: Read\n---\n",
    })
    assert _agentes_fora_do_contrato(indice, ler) == {
        f"{AGENTES}a.md": ["chave `tools:` ausente ou vazia"],
        f"{AGENTES}b.md": ["name `outro` != arquivo `b`"],
    }


def test_sintetico_command_sem_description_reprova():
    """Command sem frontmatter ou com `description:` vazia reprova, nomeado."""
    indice = frozenset({f"{COMMANDS}a.md", f"{COMMANDS}b.md", f"{COMMANDS}c.md"})
    ler = _leitor({
        f"{COMMANDS}a.md": "Sem frontmatter.\n",
        f"{COMMANDS}b.md": "---\ndescription:\n---\n",
        f"{COMMANDS}c.md": "---\ndescription: roda algo\n---\n",
    })
    assert _commands_fora_do_contrato(indice, ler) == {
        f"{COMMANDS}a.md": ["frontmatter ausente ou sem fecho (`---` na linha 1 e outro `---` depois)"],
        f"{COMMANDS}b.md": ["chave `description:` ausente ou vazia"],
    }


def test_sintetico_isencao_morta_e_fantasma_reprovam():
    """Skill isenta que já declara formato = morta; nome fora do índice = fantasma."""
    indice = frozenset({f"{SKILLS}viva/SKILL.md", f"{WORKFLOWS}wf/workflow.md"})
    ler = _leitor({f"{SKILLS}viva/SKILL.md": SKILL_OK.format(nome="viva"), f"{WORKFLOWS}wf/workflow.md": WF_OK})
    assert _isencoes_mortas(indice, ler, frozenset({"viva"}), frozenset({"wf"}), frozenset({"viva"})) == [
        "LEGADO_SEM_FORMATO_SKILLS: viva já declara formato",
        "LEGADO_SEM_FORMATO_WORKFLOWS: wf já declara %% formato:",
        "LEGADO_NOME: viva já tem name = pasta",
    ]
    assert _isencoes_fantasmas(indice, frozenset({"sumiu"}), frozenset({"tambem"}), frozenset()) == [
        "skill sumiu", "workflow tambem",
    ]


# ---------------------------------------------------------------------------
# Casos de borda


def test_frontmatter_crlf_e_tratado_como_lf():
    """`---\\r` é cerca de frontmatter: arquivo salvo em CRLF não vira infrator."""
    chaves = _frontmatter("---\r\nname: x\r\ndescription: y\r\n---\r\ncorpo\r\n")
    assert chaves == {"name": "x", "description": "y"}


def test_hibrido_com_parenteses_e_aceito():
    """`híbrido(...)` da regra é valor válido, em SKILL.md e no bloco mermaid."""
    assert RE_FORMATO_SKILL.match("%% formato: híbrido(cadeia + loop com teto 3)")
    assert _declaracao_mermaid("```mermaid\n%% formato: híbrido(diamante sobre cadeia)\nflowchart TD\n```\n")


def test_git_indisponivel_falha_alto(monkeypatch):
    """Sem `git ls-files`, o gate falha — nunca cai para o filesystem."""
    _indice.cache_clear()

    def _sem_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _sem_git)
    try:
        with pytest.raises(FileNotFoundError):
            _indice()
    finally:
        _indice.cache_clear()


def test_pasta_de_skill_so_com_references_reprova():
    """Pasta com arquivos mas sem SKILL.md é achado da checagem de skills."""
    indice = frozenset({f"{SKILLS}orfa/references/x.md", f"{SKILLS}ok/SKILL.md"})
    assert _pastas_sem_arquivo(indice, SKILLS, "SKILL.md") == ["orfa"]
