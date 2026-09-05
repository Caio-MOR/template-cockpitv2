"""Gate de sincronia do runner de eval: esta cópia não mudou sem revisão.

**Isto é atestação, não prova.** O gate compara o `sha256` da cópia local com uma
constante pinada aqui. Ele garante que ninguém editou o espelho sem atualizar a
constante no mesmo PR. Ele NÃO garante que a cópia ainda bate com a canônica: o CI
não tem rede por desenho, então buscar o arquivo upstream para comparar está fora de
alcance. `COMMIT_UPSTREAM` registra de qual commit da canônica esta cópia saiu, e é o
que um humano usa para conferir à mão quando quiser.

Portão que se apresenta como prova sendo atestação é pior que portão nenhum, porque
compra confiança que não tem lastro. Daí este parágrafo.

**Fim de linha.** O hash é do conteúdo normalizado em LF, não dos bytes do disco. O
`.gitattributes` declara `* text=auto`, então a árvore de trabalho recebe CRLF no
Windows e LF no Linux: hash sobre os bytes do disco seria vermelho num SO e verde no
outro. O conteúdo normalizado é exatamente o que o git guarda no blob, medido em
2026-09-04: `git cat-file blob HEAD:tools/eval_runner.py | sha256sum` devolve a mesma
constante de `SHA_CANONICO`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUNNER = RAIZ / "tools" / "eval_runner.py"
REGRA_DELEGACAO = RAIZ / ".claude" / "rules" / "delegacao-barata.md"
CONFIG_CODEX_EXEMPLO = RAIZ / ".codex" / "config.example.toml"

CRLF = bytes((13, 10))
LF = bytes((10,))

# Cópia canônica: Caio-MOR/plugins -> tools/eval_runner.py.
# `sha256` do conteúdo normalizado em LF, e o commit da canônica de onde a cópia saiu.
# Atualizar os dois no mesmo PR que propaga a cópia; o procedimento está na mensagem
# de falha de `_divergencia`, para não depender de ninguém lembrar dele.
SHA_CANONICO = "7f7943e2ff7336586ed406bf017cd8da3d3290f49a57f1c7646d6e312c5340cb"
COMMIT_UPSTREAM = "666dbad10c7429138cfda7752afeccbdafd333e7"


def _sha_normalizado(arquivo: Path) -> str:
    return hashlib.sha256(arquivo.read_bytes().replace(CRLF, LF)).hexdigest()


def _divergencia(arquivo: Path, sha_esperado: str, commit_upstream: str) -> str | None:
    """Mensagem de falha, ou None quando bate. A mensagem ensina o procedimento:
    reconstruir de cabeça o que fazer é justamente o que ninguém acerta às 18h."""
    atual = _sha_normalizado(arquivo)
    if atual == sha_esperado:
        return None
    return (
        f"{arquivo.name} divergiu da cópia canônica.\n"
        f"  esperado: {sha_esperado}\n"
        f"  atual:    {atual}\n"
        f"  pinado a partir de Caio-MOR/plugins@{commit_upstream}\n"
        "Procedimento, na ordem: 1) atualize a cópia local a partir de "
        "Caio-MOR/plugins:tools/eval_runner.py (a edição vai NA canônica, nunca aqui); "
        "2) recalcule o sha e atualize SHA_CANONICO neste arquivo; "
        "3) atualize COMMIT_UPSTREAM para o commit da canônica de onde a cópia saiu."
    )


def test_runner_bate_com_o_sha_canonico_pinado():
    """A cópia local é a que foi revisada, byte a byte."""
    problema = _divergencia(RUNNER, SHA_CANONICO, COMMIT_UPSTREAM)
    assert problema is None, problema


def test_commit_upstream_e_sha_completo_de_git():
    """`COMMIT_UPSTREAM` é hash de 40 hex. Hash curto apodrece: deixa de resolver
    sozinho quando o histórico da canônica cresce."""
    assert len(COMMIT_UPSTREAM) == 40, f"COMMIT_UPSTREAM tem {len(COMMIT_UPSTREAM)} chars"
    assert all(c in "0123456789abcdef" for c in COMMIT_UPSTREAM), COMMIT_UPSTREAM


def test_delegacao_codex_e_opcional_e_condicional():
    """O perfil é um exemplo opt-in e a regra não pressupõe suporte do harness."""
    regra = REGRA_DELEGACAO.read_text(encoding="utf-8")
    config = CONFIG_CODEX_EXEMPLO.read_text(encoding="utf-8")
    assert not (RAIZ / ".codex" / "config.toml").exists()
    assert "model selection" in regra and "offers `gpt-5.6-luna`" in regra
    assert "harness default or execute inline" in regra
    assert 'default_subagent_model = "gpt-5.6-luna"' in config


def test_cabecalho_declara_a_natureza_de_atestacao():
    """A declaração de atestação é asserida, não só escrita.

    Sem esta asserção, apagar o parágrafo deixaria a suíte verde — e o gate
    voltaria a se apresentar como prova. A verificação da Fase 1 apontou a
    assimetria: no repo `plugins` o requisito gêmeo de docstring já é asserido.
    """
    doc = __doc__ or ""
    assert "atestação, não prova" in doc, (
        "o cabeçalho não declara que este gate é atestação, não prova"
    )
    assert "não tem rede" in doc, "o cabeçalho não diz por que não é prova"


def test_sintetico_um_byte_diferente_reprova(tmp_path):
    """O gate morde: um byte trocado reprova, e a mensagem ensina o conserto.

    Sem este teste, `SHA_CANONICO` poderia estar pinado no hash de outra coisa e o
    gate ficaria verde para sempre, que é o modo de falha caro.
    """
    assert _sha_normalizado(RUNNER) == SHA_CANONICO
    bytes_originais = RUNNER.read_bytes().replace(CRLF, LF)

    adulterado = tmp_path / "eval_runner.py"
    # Um espaço no fim: nem sequer muda o comportamento do módulo.
    adulterado.write_bytes(bytes_originais + b" ")

    problema = _divergencia(adulterado, SHA_CANONICO, COMMIT_UPSTREAM)
    assert problema is not None, "um byte a mais passou pelo gate"
    assert "atualize a cópia local" in problema
    assert "recalcule o sha e atualize SHA_CANONICO" in problema
    assert "atualize COMMIT_UPSTREAM" in problema
    assert SHA_CANONICO in problema and COMMIT_UPSTREAM in problema


def test_sintetico_fim_de_linha_nao_muda_o_hash(tmp_path):
    """CRLF e LF do mesmo conteúdo dão o mesmo hash.

    É o que permite uma constante só ficar verde no Windows e no ubuntu do CI,
    apesar de `* text=auto` entregar árvores de trabalho diferentes.
    """
    em_lf = tmp_path / "lf.py"
    em_crlf = tmp_path / "crlf.py"
    corpo = RUNNER.read_bytes().replace(CRLF, LF)
    em_lf.write_bytes(corpo)
    em_crlf.write_bytes(corpo.replace(LF, CRLF))

    assert em_lf.read_bytes() != em_crlf.read_bytes(), "os dois arquivos deviam diferir"
    assert _sha_normalizado(em_lf) == _sha_normalizado(em_crlf) == SHA_CANONICO
