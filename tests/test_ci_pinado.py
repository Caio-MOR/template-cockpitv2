"""Gate do CI: actions pinadas NO SHA que este repo revisou, e permissões mínimas.

Validar só a *forma* do pin (`uses: x@<40 hex> # vN`) deixa passar SHA trocado por
outro dono com o comentário de versão mantido. Por isso a tabela PINS: (action, tag) ->
SHA. Atualizar a tabela no mesmo PR que atualiza o workflow é justamente a revisão que
se quer forçar. O glob é `*.y*ml` porque o GitHub aceita `.yml` e `.yaml`.

O parse do `permissions` é por linha, e desde T3 isso é escolha e não restrição:
`pyyaml` entrou no `requirements.txt` para o runner de eval. Trocar este parse por
`yaml.safe_load` é melhoria possível, deixada de fora do escopo de T3.
"""
import ast
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SETTINGS = RAIZ / ".claude" / "settings.json"
REQUIREMENTS = RAIZ / "requirements.txt"
REQUIREMENTS_IN = RAIZ / "requirements.in"
TOOLS = RAIZ / "tools"
WORKFLOWS = sorted((RAIZ / ".github" / "workflows").glob("*.y*ml"))

# (action, tag) -> SHA revisado. Par fora da tabela reprova; par na tabela que nenhum
# workflow usa também reprova (tabela limpa).
PINS = {
    ("actions/checkout", "v7.0.1"): "3d3c42e5aac5ba805825da76410c181273ba90b1",
    ("actions/setup-python", "v7.0.0"): "5fda3b95a4ea91299a34e894583c3862153e4b97",
}

USES = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<action>[^@\s]+)@(?P<sha>[0-9a-f]{40})\s+#\s*(?P<tag>v[\w.\-]+)\s*$"
)


def _permissions_contents(texto: str) -> str | None:
    """Valor de `contents:` dentro do bloco `permissions:` de topo, ou None."""
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if linha.rstrip() != "permissions:":
            continue
        for seguinte in linhas[i + 1:]:
            if seguinte.strip() and not seguinte.startswith((" ", "\t")):
                break  # acabou o bloco indentado
            achado = re.match(r"\s+contents:\s*(\S+)\s*$", seguinte)
            if achado:
                return achado.group(1)
    return None


def _divergencias(nome: str, texto: str, pins: dict) -> list[str]:
    """Linhas `uses:` fora da forma pinada ou com SHA diferente da tabela. Função pura:
    é o que permite provar com texto sintético que o contrato reprova."""
    problemas = []
    for n, linha in enumerate(texto.splitlines(), 1):
        if "uses:" not in linha:
            continue
        achado = USES.match(linha)
        if not achado:
            problemas.append(f"{nome}:{n} action não pinada por SHA: {linha.strip()}")
            continue
        chave = (achado.group("action"), achado.group("tag"))
        esperado = pins.get(chave)
        if esperado is None:
            problemas.append(f"{nome}:{n} usa {chave[0]}@{chave[1]}, par não declarado em PINS")
        elif esperado != achado.group("sha"):
            problemas.append(
                f"{nome}:{n} {chave[0]} {chave[1]} pinada em {achado.group('sha')}, esperado {esperado}"
            )
    return problemas


def _pares_usados(texto: str) -> set:
    return {
        (m.group("action"), m.group("tag"))
        for m in (USES.match(l) for l in texto.splitlines()) if m
    }


def _blocos_de_jobs(texto: str) -> list[str]:
    """Retorna blocos de jobs de primeiro nível, sem depender de um parser YAML."""
    linhas = texto.splitlines()
    inicio_jobs = next((i for i, linha in enumerate(linhas) if linha == "jobs:"), None)
    if inicio_jobs is None:
        return []
    inicios = [
        i for i in range(inicio_jobs + 1, len(linhas))
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", linhas[i])
    ]
    return [
        "\n".join(linhas[inicio:fim])
        for inicio, fim in zip(inicios, inicios[1:] + [len(linhas)])
    ]


# ---------------------------------------------------------------- workflows reais


def test_existe_workflow_de_ci():
    assert WORKFLOWS, "nenhum workflow em .github/workflows/"


def test_toda_action_pinada_no_sha_da_tabela():
    problemas = []
    vistos = set()
    for wf in WORKFLOWS:
        texto = wf.read_text(encoding="utf-8")
        problemas += _divergencias(wf.name, texto, PINS)
        vistos |= _pares_usados(texto)
    assert not problemas, "\n".join(problemas)
    orfas = sorted(PINS.keys() - vistos)
    assert not orfas, f"PINS declara par que nenhum workflow usa (limpar a tabela): {orfas}"


def test_todo_workflow_declara_permissions_contents_read():
    """Workflow sem `permissions` herda o token amplo do repositório."""
    faltando = [
        wf.name for wf in WORKFLOWS
        if _permissions_contents(wf.read_text(encoding="utf-8")) != "read"
    ]
    assert not faltando, (
        "workflow sem `permissions:` de topo com `contents: read`: " + ", ".join(faltando)
    )


def test_todo_checkout_desativa_credenciais_e_define_profundidade():
    """O token não pode ficar no `.git/config` depois de executar o checkout.

    Todos os checkouts devem ser rasos por padrão; a única exceção deliberada é
    o gitleaks, que precisa da história inteira para detectar segredos antigos.
    """
    problemas = []
    for wf in WORKFLOWS:
        texto = wf.read_text(encoding="utf-8")
        checkouts = texto.count("uses: actions/checkout@")
        credenciais = texto.count("persist-credentials: false")
        if checkouts != credenciais:
            problemas.append(f"{wf.name}: cada checkout precisa de persist-credentials: false")
        if wf.name in {"gitleaks.yml", "self-hosted-required.yml"}:
            if "fetch-depth: 0" not in texto:
                problemas.append("gitleaks.yml: scan de história exige fetch-depth: 0")
        elif checkouts and texto.count("fetch-depth: 1") != checkouts:
            problemas.append(f"{wf.name}: checkout de CI deve usar fetch-depth: 1")
    assert problemas == [], "\n".join(problemas)


def test_python_e_runners_sao_reprodutiveis():
    """Patch de Python e imagens de runner são contratos, não defaults móveis."""
    versao = (RAIZ / ".python-version").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"3\.12\.\d+", versao), ".python-version precisa conter patch exato"
    problemas = []
    for wf in WORKFLOWS:
        texto = wf.read_text(encoding="utf-8")
        if re.search(r"^\s*runs-on:\s*[^\n]*-latest\b", texto, re.MULTILINE):
            problemas.append(f"{wf.name}: runs-on não pode usar label móvel *-latest")
        blocos = _blocos_de_jobs(texto)
        if not blocos:
            problemas.append(f"{wf.name}: nenhum job encontrado")
        for bloco in blocos:
            if "timeout-minutes:" not in bloco:
                nome = bloco.splitlines()[0].strip().rstrip(":")
                problemas.append(f"{wf.name}/{nome}: job sem timeout-minutes")
    assert problemas == [], "\n".join(problemas)


def test_merge_group_e_lint_macos_estao_cobertos():
    """A fila de merge precisa dos checks exigíveis e macOS não pode pular Ruff."""
    exigiveis = ("tests.yml", "security.yml", "gitleaks.yml")
    for nome in exigiveis:
        ci = (RAIZ / ".github" / "workflows" / nome).read_text(encoding="utf-8")
        assert re.search(r"^\s*merge_group:\s*$", ci, re.MULTILINE), nome
    matriz = (RAIZ / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'merge_group'" in matriz
    assert "windows-2025" in matriz
    macos = (RAIZ / ".github" / "workflows" / "tests-macos.yml").read_text(encoding="utf-8")
    assert "ruff check ." in macos


def test_template_workflows_do_not_require_a_personal_runner():
    """A public template cannot require a runner owned by its source repository."""
    for workflow in (RAIZ / ".github" / "workflows").glob("*.yml"):
        texto = workflow.read_text(encoding="utf-8")
        assert "self-hosted" not in texto, workflow.name
        assert "cakopit-codex" not in texto, workflow.name


def test_download_de_gitleaks_falha_sem_conexao_tls_valida():
    """Downloads do binário de segurança devem falhar fechado e exigir TLS moderno."""
    texto = (RAIZ / ".github" / "workflows" / "gitleaks.yml").read_text(encoding="utf-8")
    for opcao in ("--fail", "--proto '=https'", "--tlsv1.2", "--location"):
        assert opcao in texto, f"gitleaks.yml sem opção curl obrigatória: {opcao}"


def test_instalacoes_de_pip_usam_somente_o_lock_com_hashes():
    """Nenhum workflow pode reintroduzir instalação sem `--require-hashes`."""
    problemas = []
    for wf in WORKFLOWS:
        for numero, linha in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bpip\s+install\b", linha) and (
                "--require-hashes" not in linha or "requirements.txt" not in linha
            ):
                problemas.append(f"{wf.name}:{numero} instalação não usa lock com hashes")
    assert problemas == [], "\n".join(problemas)


def test_seguranca_estatica_e_dependencias_rodam_sem_ghas():
    """O repo privado precisa de gates locais que não dependam de GitHub Code Security."""
    texto = (RAIZ / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    assert "pip-audit --strict --progress-spinner off" in texto
    assert "bandit --quiet --recursive --severity-level medium --confidence-level medium" in texto
    assert "dependency-review-action" not in texto
    assert "github/codeql-action" not in texto


def test_lock_de_dependencias_tem_versoes_e_hashes_exatos():
    """Cada distribuição do lock precisa ser reprodutível e verificável."""
    linhas = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    entradas = []
    atual = None
    for linha in linhas:
        if linha and not linha.startswith((" ", "\t", "#")):
            if RE_NOME_DE_PACOTE.match(linha) and "==" in linha:
                atual = [linha]
                entradas.append(atual)
                continue
        if atual is not None:
            atual.append(linha)
    assert entradas, "requirements.txt sem entradas pinadas"
    problemas = []
    for entrada in entradas:
        cabecalho = entrada[0]
        nome = cabecalho.split("==", 1)[0]
        if not re.match(r"^[A-Za-z0-9._-]+==[^\s\\]+", cabecalho):
            problemas.append(f"{nome}: versão não é == exata")
        if not any("--hash=sha256:" in linha for linha in entrada):
            problemas.append(f"{nome}: sem hash sha256")
    assert problemas == [], "\n".join(problemas)


def test_lock_tem_arquivo_de_entradas_diretas():
    """Atualizadores devem editar requisitos diretos e regenerar o lock."""
    assert REQUIREMENTS_IN.exists(), "requirements.in é a fonte de dependências diretas"
    entradas = [
        linha.strip() for linha in REQUIREMENTS_IN.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.lstrip().startswith("#")
    ]
    assert entradas
    assert all(re.match(r"^[A-Za-z0-9._-]+(?:[<>=!~].*)?$", entry) for entry in entradas)
    lockados = {
        re.match(r"^([A-Za-z0-9._-]+)==", linha).group(1).lower()
        for linha in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if re.match(r"^([A-Za-z0-9._-]+)==", linha)
    }
    diretos = {re.match(r"^([A-Za-z0-9._-]+)", entry).group(1).lower() for entry in entradas}
    assert diretos <= lockados, f"entradas diretas ausentes do lock: {sorted(diretos - lockados)}"


def test_ci_chama_o_veredito_e_nao_o_pytest_direto():
    """Quem julga a suíte não pode ser o próprio pytest: o job da suíte invoca
    `tools/gate_veredito.py`, e nenhum step roda `pytest` a seco."""
    texto = (RAIZ / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "tools/gate_veredito.py" in texto
    corridas = [l.split("run:", 1)[1].strip() for l in texto.splitlines() if "run:" in l]
    assert not any(c in ("pytest -q", "pytest") for c in corridas), corridas
    assert "working-directory" not in texto, "gate rodado de subpasta não mede a árvore inteira"


def test_settings_json_parseavel():
    """settings.json quebrado derrubaria os hooks em silêncio."""
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert isinstance(dados, dict) and "hooks" in dados


# ---------------------------------------------------------------- sintético: reprova


def test_sintetico_uses_por_tag_ou_sha_de_outro_dono_reprova():
    por_tag = "steps:\n  - uses: actions/checkout@v4\n"
    assert _divergencias("x.yml", por_tag, PINS) == [
        "x.yml:2 action não pinada por SHA: - uses: actions/checkout@v4"
    ]
    sha_falso = "  - uses: actions/checkout@" + "0" * 40 + " # v7.0.1\n"
    [problema] = _divergencias("x.yml", sha_falso, PINS)
    assert "pinada em " + "0" * 40 in problema
    fora_da_tabela = "  - uses: alguem/acao@" + "a" * 40 + " # v1.0.0\n"
    assert "par não declarado em PINS" in _divergencias("x.yml", fora_da_tabela, PINS)[0]
    assert _permissions_contents("name: x\njobs:\n  a: {}\n") is None
    assert _permissions_contents("permissions:\n  contents: read\njobs: {}\n") == "read"


# ------------------------------------------------- dependência externa declarada


# Import de terceiro -> nome da distribuição no `requirements.txt`. Módulo importado
# fora deste mapa reprova: acrescentar a entrada é a revisão que se quer forçar.
MODULO_PARA_DISTRIBUICAO = {"yaml": "pyyaml"}
RE_NOME_DE_PACOTE = re.compile(r"[A-Za-z0-9._-]+")


def _imports_de_terceiro(arquivo: Path, locais: set[str]) -> set[str]:
    raizes: set[str] = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            raizes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            raizes.add(no.module.split(".")[0])
    return {r for r in raizes if r not in sys.stdlib_module_names and r not in locais}


def _distribuicoes_declaradas() -> set[str]:
    nomes: set[str] = set()
    # requirements.in é a fonte de entradas diretas; o lock inclui transitive
    # (como requests), que não devem mascarar uma importação nova dos tools.
    fonte = REQUIREMENTS_IN if REQUIREMENTS_IN.exists() else REQUIREMENTS
    for linha in fonte.read_text(encoding="utf-8").splitlines():
        sem_comentario = linha.split("#")[0].strip()
        if not sem_comentario:
            continue
        casado = re.fullmatch(r"([A-Za-z0-9._-]+)(?:[<>=!~].*)?", sem_comentario)
        if casado:
            nomes.add(casado.group(1).lower())
    return nomes


def test_toda_dependencia_externa_de_tools_declarada_no_requirements():
    """Todo import de terceiro em `tools/` aparece no `requirements.txt`.

    O furo que fecha: o runner de eval passou a importar `yaml` numa cópia vinda
    de outro repo, onde a dependência era declarada — aqui não era. Venv limpa
    quebraria no import e a suíte local passaria, porque a máquina do autor já
    tinha o pacote instalado por outro caminho.
    """
    declaradas = _distribuicoes_declaradas()
    locais = {f.stem for f in TOOLS.glob("*.py")} | {"tools"}
    faltando = []
    for arquivo in sorted(TOOLS.glob("*.py")):
        for modulo in sorted(_imports_de_terceiro(arquivo, locais)):
            distribuicao = MODULO_PARA_DISTRIBUICAO.get(modulo)
            if distribuicao is None:
                faltando.append(
                    f"{arquivo.name}: import `{modulo}` sem entrada em "
                    "MODULO_PARA_DISTRIBUICAO deste teste"
                )
            elif distribuicao.lower() not in declaradas:
                faltando.append(
                    f"{arquivo.name}: import `{modulo}` exige `{distribuicao}` "
                    "declarado no requirements.txt"
                )
    assert faltando == [], "; ".join(faltando)


def test_sintetico_import_nao_declarado_reprova(tmp_path):
    """O gate acima morde: arquivo sintético que importa pacote fora do requirements."""
    falso = tmp_path / "usa_requests.py"
    falso.write_text("""import requests
import json
""", encoding="utf-8")
    assert _imports_de_terceiro(falso, set()) == {"requests"}
    assert "requests" not in _distribuicoes_declaradas()
    assert "pyyaml" in _distribuicoes_declaradas()
