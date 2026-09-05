#!/usr/bin/env python3
"""Runner de bolso para evals de comportamento (formato oficial de `claude plugin eval`).

`claude plugin eval` existe no CLI (medido no 2.1.241) mas é early access habilitado
por organização, e nesta conta responde `` `plugin eval` is currently in early access ``
e sai. Os casos deste repo, porém, já são escritos no formato oficial
(`evals/<caso>/prompt.md` + `graders/<nome>.md`) para rodarem sem alteração no dia em
que a flag abrir. Reconferir o gate a cada `claude update`: `claude plugin eval` numa
pasta vazia devolvendo `No eval cases found` significa habilitado.

Este runner lê esse mesmo formato e executa via `claude -p` com login de subscription
(regra da casa: automação LLM via subscription, não API direta) — sem nenhuma
dependência externa, só a stdlib + PyYAML (já é dependência do `validar_plugins.py`).

Cobre só o subconjunto de graders usado neste repo: `tool_used`, `regex`, `file_exists`.
`llm` e `baseline` ficam para a ferramenta oficial.

## Cópia canônica

Duas cópias byte-idênticas deste arquivo existem, e este texto é uma delas: por isso
ele nomeia os dois lados por caminho, em vez de dizer "aqui" ou "lá".

- **Canônica**: `Caio-MOR/plugins` → `tools/eval_runner.py`. É onde se edita.
- **Espelho**: `Caio-MOR/template-cockpit` → `tools/eval_runner.py`. Lá um gate compara
  o `sha256` do arquivo com uma constante pinada, então editar o espelho reprova o
  gate — que é o efeito desejado.

Consequência: mudança na canônica não está concluída enquanto não for propagada para o
espelho e o `sha256` pinado de lá não for recalculado, no mesmo PR. `RUNNER_VERSAO`
sobe junto — patch para correção interna, minor para grader ou campo de saída novo,
major para mudança de contrato de saída.

## Dois modos de descoberta

- **Marketplace** (default): lê `.claude-plugin/marketplace.json` na raiz e roda
  `evals/` de dentro de cada `plugins/<nome>/`, isolando com `--plugin-dir
  <caminho do plugin>` num cwd temporário vazio.
- **Skills-dir** (`--skills-dir <pasta>`, ex.: `.claude/skills`): para repos sem
  marketplace (o `template-cockpit`). Cada subpasta com `SKILL.md` é uma skill; os
  casos vivem em `evals/<skill>/` na raiz do repo. Isolamento: copia só a skill sob
  teste para um `.claude/skills/<skill>/` dentro do cwd temporário — nada de
  `--plugin-dir`, e nenhuma outra skill do repo real fica visível.

## Uso

    python tools/eval_runner.py [--plugin NOME ...] [--all] [--skills-dir PASTA]
                                 [--runs N] [--case GLOB] [--json ARQUIVO]
                                 [--threshold 0..1]

Exit 0 = todo caso >= threshold; 1 = algum caso abaixo; 2 = `claude` não encontrado ou
falha de autenticação (mensagem: "faça login no Claude Code antes de rodar").
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

RUNNER_VERSAO = "1.1.0"  # ver "Cópia canônica" na docstring: sobe junto da propagação
RESULTADO_SCHEMA = "eval-runner-result/v1"
TETO_CASOS_INFRA_CONSECUTIVOS = 3  # loop-engineering: nunca insistir além disso
RE_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
MARCADORES_AUTH = ("not logged in", "authentication_failed", "please run /login")
ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "SystemRoot", "WINDIR",
    "TEMP", "TMP", "TMPDIR", "PATHEXT", "ComSpec", "SHELL", "LANG", "LC_ALL",
    "LC_CTYPE", "TERM", "NO_COLOR", "CLAUDE_CONFIG_DIR", "DISABLE_AUTOUPDATER",
    "DISABLE_TELEMETRY", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
})


class ErroInfra(Exception):
    """Falha de infraestrutura (timeout, processo não sobe, auth) — não é veredito de grader."""


class ErroCasoMalFormado(Exception):
    """Caso/gráder com formato inválido (frontmatter quebrado, regex incompilável)."""


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ambiente_seguro(ambiente: dict[str, str] | None = None) -> dict[str, str]:
    """Mantém apenas as variáveis necessárias para autenticação por subscription."""
    origem = os.environ if ambiente is None else ambiente
    seguro = {nome: valor for nome, valor in origem.items() if nome in ENV_ALLOWLIST}
    seguro.setdefault("DISABLE_AUTOUPDATER", "1")
    seguro.setdefault("DISABLE_TELEMETRY", "1")
    seguro.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    return seguro


def _validar_cwd(cwd: Path) -> Path:
    caminho = Path(cwd)
    if not caminho.is_absolute() or not caminho.is_dir():
        raise ErroInfra("cwd do eval precisa ser um diretório absoluto existente")
    resolvido = caminho.resolve()
    if resolvido != caminho:
        raise ErroInfra("cwd do eval não pode ser um link simbólico")
    return resolvido


def _git_info(raiz: Path) -> dict[str, str | bool | None]:
    """Lê proveniência não sensível; ausência de git fica explícita."""
    base_env = ambiente_seguro()
    try:
        commit = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5, env=base_env,
        ).stdout.strip() or None
        status = subprocess.run(
            ["git", "-C", str(raiz), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=False, timeout=5, env=base_env,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": bool(status.strip())}


def _caminho_saida_seguro(caminho: str, raiz: Path) -> Path:
    destino = Path(caminho)
    if not destino.is_absolute():
        destino = raiz / destino
    destino = destino.resolve()
    try:
        destino.relative_to(raiz)
    except ValueError as e:
        raise ErroInfra("arquivo JSON precisa ficar dentro da raiz do repositório") from e
    if destino == raiz or destino.exists() and destino.is_dir():
        raise ErroInfra("arquivo JSON precisa ser um arquivo")
    return destino


def _escrever_json_atomico(destino: Path, dados: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except Exception:
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise


def validar_resultado(resultado: dict, *, agora: datetime | None = None,
                      max_age_seconds: int | float | None = 86_400) -> list[str]:
    """Devolve erros de frescor e cobertura completa para um resultado de eval."""
    erros: list[str] = []
    if not isinstance(resultado, dict) or resultado.get("schema") != RESULTADO_SCHEMA:
        return ["schema ausente ou incompatível"]
    for campo in ("runner_version", "started_at", "finished_at", "case_inventory", "cases", "aggregates"):
        if campo not in resultado:
            erros.append(f"campo obrigatório ausente: {campo}")
    if erros:
        return erros
    try:
        started = datetime.fromisoformat(str(resultado["started_at"]).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(resultado["finished_at"]).replace("Z", "+00:00"))
        if started.tzinfo is None or finished.tzinfo is None or finished < started:
            raise ValueError
    except (TypeError, ValueError):
        erros.append("timestamps inválidos ou fora de ordem")
        finished = None
    if finished is not None and max_age_seconds is not None:
        idade = ((agora or datetime.now(timezone.utc)) - finished).total_seconds()
        if idade < -60:
            erros.append("finished_at está no futuro")
        elif idade > max_age_seconds:
            erros.append(f"resultado antigo ({idade:.0f}s > {max_age_seconds}s)")
    inventario, casos = resultado.get("case_inventory"), resultado.get("cases")
    if not isinstance(inventario, list) or not isinstance(casos, list):
        return erros + ["case_inventory/cases precisam ser listas"]

    def extrair_chaves(itens: list, campo: str) -> list[str]:
        chaves: list[str] = []
        for indice, item in enumerate(itens):
            if not isinstance(item, dict):
                erros.append(f"{campo}[{indice}] precisa ser um objeto")
                continue
            chave = item.get("case_key")
            if not isinstance(chave, str) or not chave.strip():
                erros.append(f"{campo}[{indice}].case_key precisa ser texto não vazio")
                continue
            chaves.append(chave)
        return chaves

    chaves_inv = extrair_chaves(inventario, "case_inventory")
    chaves_res = extrair_chaves(casos, "cases")
    if len(set(chaves_inv)) != len(chaves_inv):
        erros.append("case_inventory contém casos duplicados")
    if len(set(chaves_res)) != len(chaves_res):
        erros.append("cases contém casos duplicados")
    if set(chaves_inv) != set(chaves_res) or len(chaves_res) != len(casos):
        erros.append("resultado não cobre exatamente o inventário de casos")
    esperados = {item["case_key"]: item.get("expected_runs") for item in inventario
                 if isinstance(item, dict) and isinstance(item.get("case_key"), str)}
    for caso in casos:
        if not isinstance(caso, dict):
            continue
        chave = caso.get("case_key")
        if not isinstance(chave, str) or chave not in esperados:
            continue
        runs = caso.get("runs")
        if caso.get("total") != esperados[chave] or not isinstance(runs, list) or len(runs) != esperados[chave]:
            erros.append(f"caso incompleto: {chave}")
    return erros


def resultado_valido(resultado: dict, **kwargs) -> bool:
    return not validar_resultado(resultado, **kwargs)


# ---------------------------------------------------------------------------
# Descoberta de plugins/skills e casos


def descobrir_plugins_marketplace(raiz: Path) -> dict[str, Path]:
    mkt_path = raiz / ".claude-plugin" / "marketplace.json"
    dados = json.loads(mkt_path.read_text(encoding="utf-8"))
    out: dict[str, Path] = {}
    for p in dados.get("plugins", []):
        nome = p["name"]
        fonte = str(p.get("source", "")).lstrip("./").rstrip("/")
        out[nome] = (raiz / fonte).resolve() if fonte else raiz.resolve()
    return out


def descobrir_skills(skills_dir: Path) -> dict[str, Path]:
    out = {}
    if not skills_dir.is_dir():
        return out
    for d in sorted(skills_dir.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            out[d.name] = d.resolve()
    return out


def descobrir_casos(evals_dir: Path, glob_filtro: str | None) -> list[Path]:
    casos = []
    if not evals_dir.is_dir():
        return casos
    for d in sorted(evals_dir.iterdir()):
        if not d.is_dir() or d.name == "results":
            continue
        if not (d / "prompt.md").exists():
            continue
        if glob_filtro and not fnmatch.fnmatch(d.name, glob_filtro):
            continue
        casos.append(d)
    return casos


# ---------------------------------------------------------------------------
# Parser do formato oficial (prompt.md + graders/*.md)


def parse_frontmatter(texto: str, origem: str) -> tuple[dict, str]:
    m = RE_FRONTMATTER.match(texto)
    if not m:
        raise ErroCasoMalFormado(f"{origem}: sem frontmatter (precisa começar com `---`)")
    try:
        campos = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise ErroCasoMalFormado(f"{origem}: frontmatter YAML inválido ({e})") from e
    if campos is None:
        campos = {}
    if not isinstance(campos, dict):
        raise ErroCasoMalFormado(f"{origem}: frontmatter YAML precisa ser um mapa")
    # Gotcha medido (2026-09-04, Windows): um corpo de prompt com quebra de linha
    # (parágrafo dobrado por legibilidade no .md) vira uma única entrada de
    # subprocess.run([...]), mas o CLI do claude é um wrapper .cmd — no Windows,
    # `\r\n`/`\n` no MEIO de um argumento corta a linha de comando do batch e o
    # processo sai com returncode 0 sem rodar nada (nem transcrição, nem erro).
    # Colapsar quebras/espaços internos em um único espaço deixa o prompt sempre
    # numa linha só, sem mudar o texto que o modelo recebe.
    corpo = re.sub(r"\s+", " ", texto[m.end():]).strip()
    return campos, corpo


def parse_caso(case_dir: Path) -> dict:
    texto = (case_dir / "prompt.md").read_text(encoding="utf-8")
    frontmatter, prompt = parse_frontmatter(texto, str(case_dir / "prompt.md"))
    for chave in ("runs", "max_turns", "timeout_seconds"):
        try:
            valor = int(frontmatter.get(chave))
        except (TypeError, ValueError):
            raise ErroCasoMalFormado(f"{case_dir}: `{chave}` precisa ser inteiro positivo")
        if valor <= 0:
            raise ErroCasoMalFormado(f"{case_dir}: `{chave}` precisa ser inteiro positivo")
        frontmatter[chave] = valor
    graders = []
    gdir = case_dir / "graders"
    for gf in sorted(gdir.glob("*.md")):
        gtexto = gf.read_text(encoding="utf-8")
        gcampos, gjustificativa = parse_frontmatter(gtexto, str(gf))
        gcampos["_justificativa"] = gjustificativa
        gcampos["_arquivo"] = gf.name
        if gcampos.get("type") == "tool_used":
            try:
                re.compile(gcampos.get("input_match", ""))
            except re.error as e:
                raise ErroCasoMalFormado(f"{gf}: `input_match` não compila ({e})")
        graders.append(gcampos)
    if not graders:
        raise ErroCasoMalFormado(f"{case_dir}: nenhum grader em graders/")
    return {
        "nome": case_dir.name,
        "tags": frontmatter.get("tags") or [],
        "runs": frontmatter["runs"],
        "max_turns": frontmatter["max_turns"],
        "timeout_seconds": frontmatter["timeout_seconds"],
        "prompt": prompt,
        "graders": graders,
    }


# ---------------------------------------------------------------------------
# Execução do `claude -p`


def montar_comando(caminho_claude: str, prompt: str, max_turns: int, plugin_dir: Path | None) -> list[str]:
    cmd = [
        caminho_claude, "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--max-turns", str(max_turns),
        "--setting-sources", "project",
        "--permission-mode", "dontAsk",
    ]
    if plugin_dir is not None:
        cmd += ["--plugin-dir", str(plugin_dir)]
    return cmd


def _rodar_subprocesso(cmd: list[str], cwd: Path, timeout_s: int) -> subprocess.CompletedProcess:
    cwd = _validar_cwd(cwd)
    try:
        return subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, timeout=timeout_s,
            encoding="utf-8", errors="replace", check=False, env=ambiente_seguro(),
        )
    except subprocess.TimeoutExpired as e:
        raise ErroInfra(f"timeout ({timeout_s}s) rodando `claude -p`") from e
    except OSError as e:
        raise ErroInfra(f"não foi possível executar `claude`: {e}") from e


def executar_run(caminho_claude: str, prompt: str, max_turns: int, timeout_s: int,
                  cwd: Path, plugin_dir: Path | None) -> list[dict]:
    cmd = montar_comando(caminho_claude, prompt, max_turns, plugin_dir)
    r = _rodar_subprocesso(cmd, cwd, timeout_s)
    # Gotcha medido (2026-09-04, Windows): rodar vários `claude -p` em sequência
    # rápida às vezes produz um processo que sai com returncode 0 e stdout/stderr
    # totalmente vazios — nem transcrição, nem erro de auth, nem nada (não é o
    # caminho de "not logged in", que sempre vem com texto). Isso não é uma falha
    # de grader nem de auth: é um no-op espúrio do processo. Uma única re-tentativa
    # (não conta como novo run do frontmatter, é recuperação de infra dentro do
    # mesmo run) resolve; se repetir, cai no ErroInfra normal abaixo.
    if r.returncode == 0 and not (r.stdout or "").strip() and not (r.stderr or "").strip():
        r = _rodar_subprocesso(cmd, cwd, timeout_s)

    linhas = []
    for linha in (r.stdout or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            linhas.append(json.loads(linha))
        except json.JSONDecodeError:
            continue  # linha não-JSON no stream (ruído), ignora

    texto_junto = (r.stdout or "") + (r.stderr or "")
    if any(marca in texto_junto.lower() for marca in MARCADORES_AUTH):
        raise ErroInfra(
            "faça login no Claude Code antes de rodar (`claude /login`) — "
            "autenticar o app não autentica o CLI standalone"
        )
    if not linhas:
        raise ErroInfra(f"`claude -p` não produziu stream-json legível (exit {r.returncode})")
    return linhas


# ---------------------------------------------------------------------------
# Graders


def _ultima_mensagem_assistente_texto(linhas: list[dict]) -> str:
    texto = ""
    for evento in linhas:
        if evento.get("type") == "assistant":
            blocos = (evento.get("message") or {}).get("content") or []
            partes = [b.get("text", "") for b in blocos if isinstance(b, dict) and b.get("type") == "text"]
            if partes:
                texto = "\n".join(partes)
    return texto


def _contar_tool_used(linhas: list[dict], tool: str, pattern: str) -> int:
    regex = re.compile(pattern)
    contagem = 0
    for evento in linhas:
        if evento.get("type") != "assistant":
            continue
        blocos = (evento.get("message") or {}).get("content") or []
        for b in blocos:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == tool:
                entrada = json.dumps(b.get("input", {}), ensure_ascii=False)
                if regex.search(entrada):
                    contagem += 1
    return contagem


def avaliar_grader(grader: dict, linhas: list[dict], cwd: Path) -> dict:
    tipo = grader.get("type")
    if tipo == "tool_used":
        contagem = _contar_tool_used(linhas, grader.get("tool", "Skill"), grader["input_match"])
        minimo = int(grader.get("min", 1))
        maximo = grader.get("max")
        maximo = int(maximo) if maximo is not None else None
        passou = contagem >= minimo and (maximo is None or contagem <= maximo)
        return {"tipo": tipo, "arquivo": grader["_arquivo"], "passou": passou,
                "detalhe": f"contagem={contagem} min={minimo} max={maximo}"}
    if tipo == "regex":
        texto = _ultima_mensagem_assistente_texto(linhas)
        passou = re.search(grader["pattern"], texto) is not None
        return {"tipo": tipo, "arquivo": grader["_arquivo"], "passou": passou,
                "detalhe": "última mensagem do assistente casa o padrão" if passou else "sem match"}
    if tipo == "file_exists":
        achados = list(cwd.glob(grader["glob"]))
        minimo = int(grader.get("min", 1))
        passou = len(achados) >= minimo
        return {"tipo": tipo, "arquivo": grader["_arquivo"], "passou": passou,
                "detalhe": f"achados={len(achados)} min={minimo}"}
    raise ErroCasoMalFormado(f"grader tipo `{tipo}` não suportado pelo runner de bolso "
                              f"(só tool_used, regex, file_exists — llm/baseline são da ferramenta oficial)")


# ---------------------------------------------------------------------------
# Orquestração de um caso e da suíte


def rodar_caso(caminho_claude: str, caso: dict, plugin_dir: Path | None,
               skill_copia: tuple[Path, str] | None, runs_override: int | None) -> dict:
    runs = runs_override or caso["runs"]
    resultados = []
    for _ in range(runs):
        with tempfile.TemporaryDirectory(prefix="eval_runner_") as tmp:
            cwd = Path(tmp)
            plugin_dir_exec = None
            if plugin_dir is not None:
                plugin_dir_exec = cwd / ".plugin-under-test"
                shutil.copytree(plugin_dir, plugin_dir_exec)
            if skill_copia is not None:
                origem, nome_skill = skill_copia
                destino = cwd / ".claude" / "skills" / nome_skill
                shutil.copytree(origem, destino)
            inicio = _agora_iso()
            try:
                linhas = executar_run(
                    caminho_claude, caso["prompt"], caso["max_turns"],
                    caso["timeout_seconds"], cwd, plugin_dir_exec,
                )
            except ErroInfra as e:
                resultados.append({"ok": False, "infra": str(e), "graders": [],
                                   "started_at": inicio, "finished_at": _agora_iso()})
                continue
            veredito_graders = [avaliar_grader(g, linhas, cwd) for g in caso["graders"]]
            ok = all(v["passou"] for v in veredito_graders)
            resultados.append({"ok": ok, "infra": None, "graders": veredito_graders,
                               "started_at": inicio, "finished_at": _agora_iso()})
    ok_count = sum(1 for r in resultados if r["ok"])
    return {
        "nome": caso["nome"], "tags": caso["tags"], "runs": resultados,
        "ok": ok_count, "total": len(resultados),
        "todos_infra": all(r["infra"] is not None for r in resultados),
    }


def formatar_tabela(resultados_casos: list[dict], threshold: float) -> str:
    linhas = ["caso | tag | runs ok / runs | veredito", "---- | --- | -------------- | --------"]
    for c in resultados_casos:
        frac = c["ok"] / c["total"] if c["total"] else 0.0
        veredito = "PASS" if frac >= threshold else "FAIL"
        tags = ",".join(c["tags"]) if c["tags"] else "-"
        linhas.append(f"{c['nome']} | {tags} | {c['ok']}/{c['total']} | {veredito}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plugin", action="append", default=[], help="nome do plugin (repetível)")
    ap.add_argument("--all", action="store_true", help="roda todos os plugins do marketplace")
    ap.add_argument("--skills-dir", help="modo skills-dir (sem marketplace), ex.: .claude/skills")
    ap.add_argument("--runs", type=int, default=None, help="sobrescreve `runs` do frontmatter")
    ap.add_argument("--case", default=None, help="glob de nome de caso (aplica a todos os plugins/skills selecionados)")
    ap.add_argument("--json", default=None, help="salva resultado em JSON neste caminho")
    ap.add_argument("--threshold", type=float, default=1.0, help="fração mínima de runs ok por caso (default 1.0)")
    ap.add_argument("--validate-json", default=None, help="valida um resultado JSON existente (sem chamar claude)")
    ap.add_argument("--max-age-seconds", type=float, default=86_400,
                    help="idade máxima para --validate-json (default 86400; use -1 para desabilitar)")
    args = ap.parse_args(argv)

    if args.runs is not None and args.runs <= 0:
        print("eval_runner: `--runs` precisa ser inteiro positivo", file=sys.stderr)
        return 2
    if not 0 <= args.threshold <= 1:
        print("eval_runner: `--threshold` precisa estar entre 0 e 1", file=sys.stderr)
        return 2

    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")

    if args.validate_json:
        try:
            resultado = json.loads(Path(args.validate_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"eval_runner: não foi possível ler resultado JSON: {e}", file=sys.stderr)
            return 2
        idade_max = None if args.max_age_seconds < 0 else args.max_age_seconds
        erros = validar_resultado(resultado, max_age_seconds=idade_max)
        if erros:
            print("eval_runner: resultado inválido — " + "; ".join(erros), file=sys.stderr)
            return 1
        print("eval_runner: resultado válido")
        return 0

    caminho_claude = shutil.which("claude")
    if caminho_claude is None:
        print("eval_runner: `claude` não encontrado no PATH — faça login no Claude Code "
              "antes de rodar (`claude /login`)", file=sys.stderr)
        return 2

    raiz = Path(".").resolve()

    # Monta a lista de (nome, prompt_dir_de_evals, plugin_dir_ou_None, skill_copia_ou_None)
    alvos: list[tuple[str, Path, Path | None, tuple[Path, str] | None]] = []
    if args.skills_dir:
        skills_dir = Path(args.skills_dir)
        skills = descobrir_skills(skills_dir)
        nomes = args.plugin or sorted(skills)
        for nome in nomes:
            if nome not in skills:
                print(f"eval_runner: skill `{nome}` não encontrada em {skills_dir}", file=sys.stderr)
                return 2
            evals_dir = raiz / "evals" / nome
            alvos.append((nome, evals_dir, None, (skills[nome], nome)))
    else:
        plugins = descobrir_plugins_marketplace(raiz)
        if args.all or not args.plugin:
            nomes = sorted(plugins)
        else:
            nomes = args.plugin
        for nome in nomes:
            if nome not in plugins:
                print(f"eval_runner: plugin `{nome}` não encontrado no marketplace", file=sys.stderr)
                return 2
            plugin_dir = plugins[nome]
            alvos.append((nome, plugin_dir / "evals", plugin_dir, None))

    plano: list[tuple[str, dict, Path | None, tuple[Path, str] | None, str]] = []
    inventario: list[dict] = []
    for nome, evals_dir, plugin_dir, skill_copia in alvos:
        for case_dir in descobrir_casos(evals_dir, args.case):
            try:
                caso = parse_caso(case_dir)
            except ErroCasoMalFormado as e:
                print(f"eval_runner: {e}", file=sys.stderr)
                return 2
            case_key = f"{nome}/{caso['nome']}"
            plano.append((nome, caso, plugin_dir, skill_copia, case_key))
            inventario.append({
                "case_key": case_key, "name": caso["nome"], "plugin_or_skill": nome,
                "tags": caso["tags"], "expected_runs": args.runs if args.runs is not None else caso["runs"],
                "grader_count": len(caso["graders"]),
            })
    if not plano:
        print("eval_runner: nenhum caso encontrado", file=sys.stderr)
        return 2

    resultados_casos: list[dict] = []
    casos_infra_consecutivos = 0
    inicio_suite = _agora_iso()
    for nome, caso, plugin_dir, skill_copia, case_key in plano:
        resultado = rodar_caso(caminho_claude, caso, plugin_dir, skill_copia, args.runs)
        resultado["plugin_ou_skill"] = nome
        resultado["case_key"] = case_key
        resultados_casos.append(resultado)
        if resultado["todos_infra"]:
            casos_infra_consecutivos += 1
            if casos_infra_consecutivos >= TETO_CASOS_INFRA_CONSECUTIVOS:
                print(f"eval_runner: {TETO_CASOS_INFRA_CONSECUTIVOS} casos consecutivos "
                      f"falharam por infraestrutura — abortando (não insistir)", file=sys.stderr)
                break
        else:
            casos_infra_consecutivos = 0

    fim_suite = _agora_iso()
    saida_json = {
        "schema": RESULTADO_SCHEMA, "runner_version": RUNNER_VERSAO,
        "started_at": inicio_suite, "finished_at": fim_suite, "git": _git_info(raiz),
        "case_inventory": inventario,
        "cases": [
            {"case_key": c["case_key"], "name": c["nome"], "plugin_or_skill": c["plugin_ou_skill"],
             "tags": c["tags"], "runs": c["runs"], "ok": c["ok"], "total": c["total"],
             "todos_infra": c["todos_infra"]}
            for c in resultados_casos
        ],
        "aggregates": {
                "total_casos": len(resultados_casos),
                "casos_ok": sum(1 for c in resultados_casos
                                 if (c["ok"] / c["total"] if c["total"] else 0) >= args.threshold),
                "threshold": args.threshold,
        },
    }
    if args.json:
        try:
            _escrever_json_atomico(_caminho_saida_seguro(args.json, raiz), saida_json)
        except (OSError, ErroInfra) as e:
            print(f"eval_runner: não foi possível salvar JSON: {e}", file=sys.stderr)
            return 2

    nenhuma_transcricao_valida = all(
        r["infra"] is not None for c in resultados_casos for r in c["runs"]
    )
    if nenhuma_transcricao_valida:
        print("eval_runner: nenhum run produziu transcrição válida (todos falharam por "
              "infraestrutura) — faça login no Claude Code antes de rodar (`claude /login`)",
              file=sys.stderr)
        return 2

    print(formatar_tabela(resultados_casos, args.threshold))

    algum_fail = any((c["ok"] / c["total"] if c["total"] else 0) < args.threshold for c in resultados_casos)
    return 1 if algum_fail else 0


if __name__ == "__main__":
    sys.exit(main())
