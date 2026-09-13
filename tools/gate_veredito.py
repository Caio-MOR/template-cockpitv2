"""O veredito dos gates do repo — e ele não é o pytest.

Por que este arquivo existe: poucas linhas no `conftest.py` da raiz — um
`pytest_runtest_call` devolvendo `force_result(None)` — deixam a suíte inteira verde,
exit 0, **com veneno ativo**. Nada reage, porque todo guarda que mede COLETA roda como
hook DENTRO do pytest: os itens continuam sendo coletados, só param de ser executados de
verdade, e um hook a mais cala todos os outros de uma vez.

A troca é de juiz. Este módulo é um processo Python comum: não é pytest, não carrega
`conftest.py`, não tem hook. Ele chama o pytest em subprocesso e julga o que voltou.

Três ramos independentes (formato diamante — nenhum consome o resultado do outro, por
isso não há early-exit):

1. **Guarda de conteúdo (AST)** — o `conftest.py` só define os hooks da allowlist, e
   nenhum arquivo de gate tem corpo de teste esvaziado. Fecha a porta de alterar o
   guarda em vez de forjar o resultado.
2. **Canário** — um teste que reprova de verdade tem que reprovar; um que passa tem que
   passar. Isto fecha a CLASSE "forjar resultado", em qualquer grafia: ler o TEXTO do
   marker (`skip`, `skipif(True)`, `xfail`, `skipif("1==1")`, `strict=False`) sempre
   deixa uma grafia nova de fora. Resultado não tem grafia.
3. **Suíte real** — `pytest -q`, ambiente limpo, com teto de duração.

Uso:  python tools/gate_veredito.py
Exit: 0 = os três ramos verdes; 1 = algum ramo reprovou; 2 = uso indevido (recursão).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Marca de recursão. O veredito roda pytest em subprocesso; se alguém apontar o CI ou um
# teste de volta para cá, o laço seria infinito e caro. Freio da regra `loop-engineering`:
# recursão é ERRO explícito, nunca "tenta de novo".
MARCA_RECURSAO = "TEMPLATE_GATE_VEREDITO"

# Tetos de duração (segundos). Sem teto, subprocesso pendurado vira gate que nunca
# responde.
TETO_CANARIO = 120
TETO_SUITE = 900

CANARIOS = RAIZ / "tools" / "canario_gate"


@dataclass(frozen=True)
class Resultado:
    """Veredito de um ramo. `detalhe` é o que se lê quando reprova."""

    ramo: str
    ok: bool
    detalhe: str


def ambiente_limpo() -> dict[str, str]:
    """Ambiente dos subprocessos: sem `PYTEST_ADDOPTS`, com a marca de recursão.

    `PYTEST_ADDOPTS` injeta opções e alvos na linha de comando **de fora do repo** e com
    isso desliga as réguas do `conftest.py`. Ele já reprova a rodada quando a variável
    existe; aqui ela simplesmente não é repassada, para que o veredito meça o repo e não
    a máquina.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    env[MARCA_RECURSAO] = "1"
    # O filho escreve em UTF-8, sempre. Sem isto, no Windows ele emite cp1252, a leitura
    # em UTF-8 devolve U+FFFD e o veredito morre com UnicodeEncodeError ao imprimir.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _pytest(raiz: Path, args: list[str], teto: int) -> tuple[int, str]:
    """Roda o pytest em subprocesso e devolve (código de saída, saída juntada).

    `encoding="utf-8"` de propósito: `text=True` sozinho decodifica com o locale e no
    Windows devolve mojibake (cp1252).
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
            cwd=raiz, capture_output=True, encoding="utf-8", errors="replace",
            env=ambiente_limpo(), timeout=teto,
        )
    except subprocess.TimeoutExpired:
        return -1, f"estourou o teto de {teto}s"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def roda_canario(raiz: Path, arquivo: str, deve_reprovar: bool,
                 teto: int = TETO_CANARIO) -> Resultado:
    """O canário: um teste cujo resultado é conhecido de antemão.

    O arquivo fica **sob a raiz do repo** para que a descoberta de conftest por
    ancestrais carregue o `conftest.py` da raiz — é essa carga que faz o canário
    enxergar o veneno. E o nome fica fora do padrão `test_*.py` para que a suíte normal
    não o colete, daí os dois `-o` que ensinam o pytest a coletá-lo só aqui.
    """
    nome = f"canário {Path(arquivo).stem}"
    codigo, saida = _pytest(
        raiz,
        ["-q", "-o", "python_files=canario_*.py", "-o", "python_functions=canario_*", arquivo],
        teto,
    )
    if codigo == -1:
        return Resultado(nome, False, saida)
    esperado = "1 failed" if deve_reprovar else "1 passed"
    if esperado not in saida:
        exigido, houve = ("reprovar", "reprovou") if deve_reprovar else ("passar", "passou")
        return Resultado(nome, False, (
            f"o canário tinha que {exigido} e não {houve} (exit {codigo}). "
            f"Isso significa que o resultado dos testes deste repo NÃO é confiável: "
            f"alguma coisa entre o pytest e o relatório está mentindo.\n"
            f"{saida.strip()[-800:]}"
        ))
    return Resultado(nome, True, f"{esperado} (exit {codigo}), como esperado")


# Os únicos hooks que o `conftest.py` da raiz pode definir. Lista fechada de propósito:
# aceitar "qualquer hook que não seja de resultado" devolveria a decisão à leitura de
# nome, que é justamente o jeito que rende grafias novas. Hook novo legítimo entra AQUI,
# no mesmo PR — instalar guarda é decisão, não efeito colateral.
HOOKS_PERMITIDOS = frozenset({"pytest_collection_modifyitems"})


def hooks_proibidos(fonte: str) -> list[str]:
    """Nomes `pytest_*` definidos ou atribuídos no `conftest.py` fora da allowlist.

    Duas portas, uma regra: `def pytest_x` em **qualquer nível** de aninhamento (hook
    escondido dentro de função ainda é hook depois que o módulo executa) e **atribuição**
    a nome `pytest_*` — que cobre de uma vez `pytest_plugins = [...]` (carregar plugin
    externo) e `pytest_runtest_call = lambda item: ...` (o hook sem `def`).

    Limite declarado, porque sensor que promete mais do que vigia é pior que sensor
    nenhum: registro por via dinâmica (`globals()[...] = f`, `setattr(mod, ...)`) não é
    visto por AST. Quem fecha essa porta é o canário, que mede o resultado e não o texto.
    """
    achados: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if no.name.startswith("pytest_") and no.name not in HOOKS_PERMITIDOS:
                achados.append(f"def {no.name}() na linha {no.lineno}")
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name) and alvo.id.startswith("pytest_"):
                    achados.append(f"atribuição a {alvo.id} na linha {no.lineno}")
        elif isinstance(no, ast.AnnAssign):
            if isinstance(no.target, ast.Name) and no.target.id.startswith("pytest_"):
                achados.append(f"atribuição a {no.target.id} na linha {no.lineno}")
    return sorted(achados)


def guarda_conftest(raiz: Path) -> Resultado:
    """Ramo 1a: o arquivo que julga a suíte é ele próprio julgado.

    O `conftest.py` da raiz é o último guarda do repo — sem isto seria o único arquivo
    que é gate e não tem guarda nenhum de conteúdo.
    """
    alvo = raiz / "conftest.py"
    if not alvo.is_file():
        return Resultado("guarda do conftest.py", False, f"{alvo} não existe")
    achados = hooks_proibidos(alvo.read_text(encoding="utf-8"))
    if achados:
        return Resultado("guarda do conftest.py", False, (
            "hook fora da allowlist no conftest.py da raiz: " + "; ".join(achados)
            + f". Permitidos: {sorted(HOOKS_PERMITIDOS)}. Hook de resultado aqui deixa a "
            f"suíte verde com veneno ativo; se o hook novo é legítimo, acrescente-o a "
            f"HOOKS_PERMITIDOS no mesmo PR."
        ))
    return Resultado("guarda do conftest.py", True,
                     f"só os hooks da allowlist ({sorted(HOOKS_PERMITIDOS)})")


def arquivos_de_gate(fonte_conftest: str) -> list[str]:
    """As chaves de `GATES_OBRIGATORIOS`, lidas por AST — sem importar o `conftest.py`.

    Importar para descobrir a lista seria executar o arquivo que está sob julgamento.
    AST lê sem executar, e de quebra transforma "alguém apagou `GATES_OBRIGATORIOS`" em
    lista vazia, que o chamador trata como falha.
    """
    for no in ast.walk(ast.parse(fonte_conftest)):
        if isinstance(no, ast.Assign) and any(
            isinstance(a, ast.Name) and a.id == "GATES_OBRIGATORIOS" for a in no.targets
        ):
            if isinstance(no.value, ast.Dict):
                return [c.value for c in no.value.keys
                        if isinstance(c, ast.Constant) and isinstance(c.value, str)]
    return []


def _sem_docstring(corpo: list[ast.stmt]) -> list[ast.stmt]:
    if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
            and isinstance(corpo[0].value.value, str):
        return corpo[1:]
    return corpo


def _e_chamada_de_skip(no: ast.stmt) -> bool:
    """`pytest.skip(...)` ou `skip(...)` como instrução solta.

    `pytest.importorskip` fica de fora de propósito: é ausência legítima de dependência.
    """
    if not (isinstance(no, ast.Expr) and isinstance(no.value, ast.Call)):
        return False
    f = no.value.func
    if isinstance(f, ast.Attribute):
        return f.attr == "skip"
    return isinstance(f, ast.Name) and f.id == "skip"


def corpos_esvaziados(fonte: str, arquivo: str) -> list[str]:
    """Funções `test_*` esvaziadas e skip de módulo, num arquivo de gate.

    O furo que isto fecha: esvaziar o **corpo** não precisa de marker nenhum — trocar o
    corpo por `pass` deixa o teste coletado, ativo, verde e cego, e nenhuma leitura de
    marker reage.

    As formas vigiadas (lista declarada, porque sensor que promete mais do que vigia é
    furo esperando): corpo só `pass`, só `...`, só `return`; `return` como primeira
    instrução executável; `pytest.skip(...)` como primeira instrução executável; e
    `pytest.skip(allow_module_level=True)` no nível do módulo.
    """
    achados: list[str] = []
    arvore = ast.parse(fonte)

    for no in arvore.body:
        if _e_chamada_de_skip(no):
            achados.append(f"{arquivo}: skip no nível do módulo (linha {no.lineno})")

    for funcao in ast.walk(arvore):
        if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not funcao.name.startswith("test_"):
            continue
        corpo = _sem_docstring(funcao.body)
        onde = f"{arquivo}::{funcao.name} (linha {funcao.lineno})"
        if not corpo:
            achados.append(f"{onde}: corpo vazio")
            continue
        primeira = corpo[0]
        if len(corpo) == 1 and isinstance(primeira, ast.Pass):
            achados.append(f"{onde}: corpo é só `pass`")
        elif len(corpo) == 1 and isinstance(primeira, ast.Expr) \
                and isinstance(primeira.value, ast.Constant) and primeira.value.value is Ellipsis:
            achados.append(f"{onde}: corpo é só `...`")
        elif isinstance(primeira, ast.Return):
            achados.append(f"{onde}: `return` antes de qualquer verificação")
        elif _e_chamada_de_skip(primeira):
            achados.append(f"{onde}: `skip()` antes de qualquer verificação")
    return achados


def guarda_arquivos_de_gate(raiz: Path) -> Resultado:
    """Ramo 1b: os arquivos de `GATES_OBRIGATORIOS` não podem ter teste oco."""
    ramo = "guarda dos arquivos de gate"
    conftest = raiz / "conftest.py"
    if not conftest.is_file():
        return Resultado(ramo, False, f"{conftest} não existe")
    arquivos = arquivos_de_gate(conftest.read_text(encoding="utf-8"))
    if not arquivos:
        return Resultado(ramo, False, (
            "GATES_OBRIGATORIOS não foi encontrado no conftest.py da raiz — sem essa "
            "lista não há o que vigiar, e apagá-la seria a forma mais barata de calar "
            "esta guarda"
        ))
    achados: list[str] = []
    for rel in arquivos:
        alvo = raiz / rel
        if not alvo.is_file():
            achados.append(f"{rel}: arquivo de gate ausente do disco")
            continue
        achados.extend(corpos_esvaziados(alvo.read_text(encoding="utf-8"), rel))
    if achados:
        return Resultado(ramo, False, "teste de gate esvaziado: " + "; ".join(achados))
    return Resultado(ramo, True, f"{len(arquivos)} arquivos de gate sem corpo oco")


def gates_pulados(saida: str, arquivos_de_gate: list[str]) -> list[str]:
    """Arquivos de gate que apareceram como SKIPPED no RESULTADO da rodada.

    A leitura de marker por TEXTO sempre tem grafia nova, porque condição-string
    arbitrária não se avalia lendo o marker. Resultado não tem grafia: o teste rodou ou
    foi pulado, e o relatório diz qual.

    Só vale porque o `conftest.py` está sob guarda de conteúdo: hook que adulterasse o
    relatório mentiria aqui também. Os dois ramos se sustentam, e por isso são dois.
    """
    pulados = set()
    for linha in saida.splitlines():
        if not linha.startswith("SKIPPED ["):
            continue
        resto = linha.split("]", 1)[1].strip()
        pulados.add(resto.split(":", 1)[0].strip().replace(chr(92), "/"))
    return sorted(a for a in arquivos_de_gate if a in pulados)


def roda_suite(raiz: Path, teto: int = TETO_SUITE) -> Resultado:
    """Ramo 3: a suíte de sempre, agora com teto e ambiente limpo.

    Ela continua sendo o gate que mede o repo; os outros dois ramos existem para que
    o veredito dela signifique alguma coisa.
    """
    codigo, saida = _pytest(raiz, ["-q", "-rs"], teto)
    if codigo == -1:
        return Resultado("suíte", False, saida)
    linhas = [linha for linha in saida.strip().splitlines() if linha.strip()]
    resumo = linhas[-1] if linhas else "(sem saída)"
    if codigo != 0:
        return Resultado("suíte", False, f"exit {codigo} — {resumo}\n{saida.strip()[-2000:]}")
    conftest = raiz / "conftest.py"
    de_gate = arquivos_de_gate(conftest.read_text(encoding="utf-8")) if conftest.is_file() else []
    pulados = gates_pulados(saida, de_gate)
    if pulados:
        return Resultado("suíte", False, (
            "arquivo de gate PULADO na rodada: " + ", ".join(pulados)
            + " — exit 0 com gate desligado não é suíte verde. Qualquer marker que "
            "desligue um gate cai aqui, inclusive condição-string que nenhuma leitura "
            "de texto avalia."
        ))
    return Resultado("suíte", True, resumo)


# Os ramos que precisam entregar veredito. Guardrail do formato diamante: fan-out em que
# um ramo pode morrer em silêncio vira verde por ausência. Aqui a ausência de um nome
# desta lista é falha, não omissão.
RAMOS_ESPERADOS = (
    "guarda do conftest.py",
    "guarda dos arquivos de gate",
    "canário canario_vermelho",
    "canário canario_verde",
    "suíte",
)


def consolida(resultados: list[Resultado]) -> tuple[int, list[str]]:
    """Converge os ramos num veredito. Sem early-exit, e sem ramo faltando."""
    linhas = [f"[{'ok ' if r.ok else 'ERRO'}] {r.ramo}: {r.detalhe}" for r in resultados]
    entregues = {r.ramo for r in resultados}
    faltando = [n for n in RAMOS_ESPERADOS if n not in entregues]
    if faltando:
        linhas.append(
            "[ERRO] ramo sem veredito: " + ", ".join(faltando)
            + " — ramo que não entrega não conta como ramo verde"
        )
    ok = not faltando and all(r.ok for r in resultados)
    return (0 if ok else 1), linhas


def executa(raiz: Path = RAIZ) -> tuple[int, list[str]]:
    """Roda os três ramos e converge.

    **Sem early-exit de propósito** (wait test do grafo: nenhum ramo consome o resultado
    do outro). Parar no primeiro erro esconderia os outros dois, e o valor deste gate é
    justamente entregar o quadro inteiro numa rodada só.
    """
    ramos = [
        guarda_conftest(raiz),
        guarda_arquivos_de_gate(raiz),
        roda_canario(raiz, "tools/canario_gate/canario_vermelho.py", deve_reprovar=True),
        roda_canario(raiz, "tools/canario_gate/canario_verde.py", deve_reprovar=False),
        roda_suite(raiz),
    ]
    return consolida(ramos)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get(MARCA_RECURSAO):
        print(
            f"gate_veredito: recusa — {MARCA_RECURSAO} já está definida, o que significa "
            f"que este veredito foi chamado de dentro de um subprocesso dele mesmo. "
            f"Rodar assim seria laço infinito.",
            file=sys.stderr,
        )
        return 2
    # A saída do veredito carrega acento e o resumo do pytest. Console cp1252 (o padrão
    # do Windows) derruba o processo no print em vez de mostrar o veredito — reprovar
    # por causa do console é o oposto do que este gate existe para fazer.
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    codigo, linhas = executa(RAIZ)
    for linha in linhas:
        print(linha)
    print("veredito: VERDE" if codigo == 0 else "veredito: REPROVADO")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
