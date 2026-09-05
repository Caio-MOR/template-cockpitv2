"""Raiz do repo no sys.path e as réguas de coleta da suíte.

As réguas moram AQUI, e não em `tests/`, de propósito: o furo que elas fecham é a
própria `tests/` desaparecer. Guarda que mora dentro do que vigia some junto — com
`tests/` fora do índice a suíte devolve exit 0 com zero testes. Este arquivo é
versionado, fica fora dos `testpaths` e o pytest o carrega sempre.
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Coleta medida da suíte. Um teste confere este número contra a coleta real: número
# solto em comentário apodrece em silêncio, número com sensor não.
COLETA_MEDIDA = 214
# Piso: a folga (metade da coleta) absorve remoção legítima pontual sem mascarar o
# desaparecimento de um arquivo inteiro. Baixar este número é decisão de PR com
# justificativa, nunca ajuste silencioso para "passar".
PISO_COLETA = 107

# Os gates que não podem sumir, e o mínimo de testes de cada. Piso total não protege
# arquivo pequeno; esta lista protege por nome. Dividir ou renomear um destes exige
# atualizar a lista no mesmo PR — remover proteção é decisão, não efeito colateral.
GATES_OBRIGATORIOS = {
    "tests/test_lint_routers.py": 9,
    "tests/test_ci_pinado.py": 8,
    "tests/test_criacao_nova.py": 33,
    "tests/test_padrao_ouro.py": 3,
    "tests/test_hooks.py": 30,
    "tests/test_evals_estrutura.py": 6,
    "tests/test_eval_runner.py": 16,
    "tests/test_runner_sincronizado.py": 5,
    "tests/test_new_instance.py": 2,
}


def _rodada_completa(config) -> bool:
    """A linha de comando pediu a suíte inteira (nenhum alvo posicional)?

    Quem já sabe separar opção de alvo é o próprio pytest (`config.option.file_or_dir`);
    reimplementar o parser da CLI aqui faria `pytest -W ignore` ler `ignore` como alvo
    e desligar o piso em silêncio.
    """
    if config.invocation_params.dir != config.rootpath:
        # `pytest` rodado de dentro de uma subpasta é rodada focada por outro caminho.
        # Reprovar por piso aqui é estorvo, e estorvo é o que faz alguém desligar o gate.
        return False
    return not config.option.file_or_dir


CONDICOES_SEMPRE_VERDADEIRAS = frozenset({"true", "1"})
# Os únicos markers que desligam um teste. `xfail` é o pior: o teste REPROVA e o marker
# converte a reprovação em `xfailed` — suíte verde tendo detectado a regressão. O
# `xfail_strict = true` do `pytest.ini` é a outra metade do conserto, e `strict=False`
# no PRÓPRIO marker sobrepõe o ini, por isso também conta como desligar.
MARKERS_QUE_DESLIGAM = frozenset({"skip", "skipif", "xfail"})


def _desliga_de_verdade(m) -> bool:
    """Este marker desliga o teste sem depender de nada revisável?

    `skip` e `xfail` sem condição desligam. `skipif`/`xfail` com condição literalmente
    verdadeira (`True`, `"1"`, `"true"`) também. `skipif` com condição de verdade
    (plataforma, dependência ausente) fica fora de propósito: ali a condição é código
    revisável.
    """
    if m.name not in MARKERS_QUE_DESLIGAM:
        return False
    if m.name == "xfail" and not (m.args or "condition" in m.kwargs):
        return True   # `xfail` sem condição: reprovação virando sucesso
    if m.name == "skip":
        return True   # o posicional de `skip` é o motivo, nunca uma condição
    if m.name == "xfail" and m.kwargs.get("strict") is False:
        return True   # `strict=False` no marker vence o `xfail_strict` do pytest.ini
    condicoes = list(m.args) + (
        [m.kwargs["condition"]] if "condition" in m.kwargs else []
    )
    for c in condicoes:
        if isinstance(c, str):
            if c.strip().lower() in CONDICOES_SEMPRE_VERDADEIRAS:
                return True   # `skipif("True", ...)`: string que sempre avalia verdadeiro
        elif bool(c):
            return True       # `skipif(True, ...)`: constante, não condição
    return False


def _ativo(item) -> bool:
    """O item vai mesmo rodar, ou está desligado por marker?

    O piso conta coletados, e pulado conta como coletado: sem esta filtragem, um
    `pytestmark = pytest.mark.skip(...)` no topo do arquivo desligava um gate inteiro
    com a suíte verde.
    """
    marcadores = getattr(item, "iter_markers", None)
    return not (marcadores and any(_desliga_de_verdade(m) for m in marcadores()))


def _contagem_por_arquivo(items) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for item in items:
        if not _ativo(item):
            continue
        arquivo = str(item.nodeid).split("::", 1)[0].replace("\\", "/")
        contagem[arquivo] = contagem.get(arquivo, 0) + 1
    return contagem


def _ambiente_adulterado() -> str | None:
    """`PYTEST_ADDOPTS` injeta opções e alvos na linha de comando, de fora do repo.

    Um alvo posicional vindo dela faz `_rodada_completa()` devolver False, e piso, gates
    obrigatórios e detector de filtro saem de cena de uma vez. A checagem vem ANTES da
    de rodada completa de propósito.
    """
    valor = os.environ.get("PYTEST_ADDOPTS", "").strip()
    return valor or None


FILTROS_QUE_DESSELECIONAM = (
    ("keyword", "-k"),
    ("markexpr", "-m"),
    ("deselect", "--deselect"),
)


def _filtro_de_desselecao(config) -> str | None:
    """Rodada completa pedida COM filtro é rodada completa só no nome.

    `-k "not x"` tira testes da rodada sem encolher a coleta, e este hook roda ANTES da
    desseleção. Quem quer focar passa um caminho (`pytest tests -k x`) — aí não é rodada
    completa e o guarda sai da frente.
    """
    for atributo, flag in FILTROS_QUE_DESSELECIONAM:
        valor = getattr(config.option, atributo, None)
        if valor:
            return f"{flag} {valor!r}"
    return None


def pytest_collection_modifyitems(session, config, items):
    """Rodada completa que encolheu, ou perdeu um gate, não é suíte verde."""
    adulterado = _ambiente_adulterado()
    if adulterado:
        raise pytest.UsageError(
            f"PYTEST_ADDOPTS está definido ({adulterado!r}): essa variável injeta "
            f"opções e alvos na linha de comando de fora do repo, e com isso as "
            f"réguas da suíte deixam de valer. Rode sem ela."
        )
    if not _rodada_completa(config):
        return
    filtro = _filtro_de_desselecao(config)
    if filtro:
        raise pytest.UsageError(
            f"rodada completa com filtro de desseleção ({filtro}): a régua da suíte "
            f"não vale, porque o filtro tira testes da conta sem encolher a coleta. "
            f"Para focar, passe um caminho junto (ex.: `pytest tests -k ...`)."
        )
    ativos = [i for i in items if _ativo(i)]
    if len(ativos) < PISO_COLETA:
        raise pytest.UsageError(
            f"suíte encolheu: {len(ativos)} testes ativos, piso versionado é {PISO_COLETA} "
            f"(conftest.py). Se a redução for legítima, baixe PISO_COLETA no mesmo PR "
            f"explicando o porquê."
        )
    contagem = _contagem_por_arquivo(items)
    faltando = {
        arquivo: (contagem.get(arquivo, 0), minimo)
        for arquivo, minimo in GATES_OBRIGATORIOS.items()
        if contagem.get(arquivo, 0) < minimo
    }
    if faltando:
        detalhe = ", ".join(
            f"{arq} tem {tem}, mínimo {minimo}" for arq, (tem, minimo) in sorted(faltando.items())
        )
        raise pytest.UsageError(
            f"gate obrigatório ausente ou encolhido: {detalhe} (GATES_OBRIGATORIOS no "
            f"conftest.py). Remover um gate é decisão de PR, não efeito colateral."
        )
