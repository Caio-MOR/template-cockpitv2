"""Gate dos hooks de enforcement em `.claude/hooks/`.

`.claude/settings.json` não tinha `permissions` nem hooks que mordem de verdade — só
`PreCompact`/`SessionStart` com `echo`. Este arquivo prova que `guarda_bash.py` e
`guarda_segredo.py` bloqueiam o que a spec pede (exit 2 + motivo no stderr) e deixam
passar o resto (exit 0), e que a cascata de interpretador em `run_hook.sh` funciona de
verdade via `sh` — inclusive no Windows, onde `sh` vem do Git Bash.

Os subprocessos decodificam com `errors="replace"`: no Windows o hook escreve o
motivo do bloqueio na codificação do console (cp1252) e o acento derrubava a leitura
estrita em UTF-8, deixando `stderr=None` — o teste reprovava por causa do console,
não do hook.

Repositório git temporário (`tmp_path`) simula branch `main` e branch de feature;
conteúdo sintético de segredo é sempre marcado `SINTETICO` para não acionar scanners
externos (gitleaks) sobre este próprio arquivo de teste.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HOOKS = RAIZ / ".claude" / "hooks"
RUN_HOOK = HOOKS / "run_hook.sh"
TETO = 30


def _sh() -> str:
    """`sh` é o alvo real (Git Bash no Windows); cai para `bash` se o runner não tiver."""
    return "sh" if shutil.which("sh") else "bash"


def _rodar_hook(
    hook: str, payload: dict, cwd: Path | None = None, env_extra: dict | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_sh(), str(RUN_HOOK), hook],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TETO,
        cwd=str(cwd) if cwd else None,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ), **(env_extra or {})},
    )


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TETO, check=True,
    )


@pytest.fixture()
def repo_git(tmp_path: Path) -> Path:
    """Repo git com um commit em `main` e uma branch de feature (`main` é o HEAD)."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "t@t.com", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    _git("add", "a.txt", cwd=tmp_path)
    _git("commit", "-q", "-m", "init", cwd=tmp_path)
    return tmp_path


@pytest.fixture()
def repo_git_feature(repo_git: Path) -> Path:
    _git("checkout", "-q", "-b", "feat/x", cwd=repo_git)
    return repo_git


# ---------------------------------------------------------------------------
# guarda_bash.py — bloqueia


def test_bloqueia_commit_direto_em_main(repo_git: Path):
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": "git commit -m x"}, "cwd": str(repo_git)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


def test_bloqueia_commit_com_opcao_global_em_main(repo_git: Path):
    r = _rodar_hook(
        "guarda_bash.py",
        {"tool_input": {"command": "git -C . commit -m x"}, "cwd": str(repo_git)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


def test_bloqueia_commit_direto_em_master(repo_git: Path):
    _git("branch", "-m", "master", cwd=repo_git)
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": "git commit -m x"}, "cwd": str(repo_git)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


@pytest.mark.parametrize("comando", [
    "git push --force origin feat/x",
    "git push -f",
    "git push --force-with-lease origin feat/x",
    "git -C . push --force origin feat/x",
    "git -C . push -ff origin feat/x",
])
def test_bloqueia_push_force(repo_git_feature: Path, comando: str):
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": comando}, "cwd": str(repo_git_feature)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


def test_bloqueia_no_verify(repo_git_feature: Path):
    r = _rodar_hook(
        "guarda_bash.py",
        {"tool_input": {"command": "git commit --no-verify -m x"}, "cwd": str(repo_git_feature)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


@pytest.mark.parametrize("comando", [
    "git push origin main",
    "git push origin HEAD:main",
    "git push origin master",
    "git -C . push origin main",
])
def test_bloqueia_push_destino_explicito_main_ou_master(repo_git_feature: Path, comando: str):
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": comando}, "cwd": str(repo_git_feature)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


# ---------------------------------------------------------------------------
# guarda_bash.py — permite


def test_permite_commit_em_branch_de_feature(repo_git_feature: Path):
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": "git commit -m x"}, "cwd": str(repo_git_feature)})
    assert r.returncode == 0, r.stdout + r.stderr


def test_bloqueia_commit_em_main_apontado_por_git_c(repo_git: Path):
    """O alvo de `git -C` prevalece sobre um cwd externo sem repositório."""
    r = _rodar_hook(
        "guarda_bash.py",
        {"tool_input": {"command": f"git -C {repo_git} commit -m x"}, "cwd": str(repo_git.parent)},
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_permite_commit_em_feature_apontado_por_git_c(repo_git_feature: Path):
    r = _rodar_hook(
        "guarda_bash.py",
        {"tool_input": {"command": f"git -C {repo_git_feature} commit -m x"}, "cwd": str(repo_git_feature.parent)},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_push_sem_force_para_branch_de_feature(repo_git_feature: Path):
    r = _rodar_hook(
        "guarda_bash.py",
        {"tool_input": {"command": "git push origin feat/x"}, "cwd": str(repo_git_feature)},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_comando_git_inofensivo(repo_git: Path):
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": "git status"}, "cwd": str(repo_git)})
    assert r.returncode == 0, r.stdout + r.stderr


def test_bloqueia_commit_com_branch_desconhecida(tmp_path: Path):
    """Operação de commit sem contexto verificável falha fechada."""
    r = _rodar_hook("guarda_bash.py", {"tool_input": {"command": "git commit -m x"}, "cwd": str(tmp_path)})
    assert r.returncode == 2, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# guarda_segredo.py — bloqueia


@pytest.mark.parametrize("caminho", [".env", ".env.local", ".env.producao"])
def test_bloqueia_escrita_em_env(caminho: str):
    r = _rodar_hook("guarda_segredo.py", {"tool_input": {"file_path": caminho, "content": "X=1"}})
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


@pytest.mark.parametrize("padrao,texto", [
    ("AKIA", "chave=AKIAABCDEFGHIJKLMNOP"),  # gitleaks:allow — sintético, só p/ casar a regex do hook
    ("ghp_", "tok=ghp_012345678901234567890123456789012345"),  # gitleaks:allow
    ("github_pat_", "tok=github_pat_abcdefghijklmnop"),  # gitleaks:allow
    ("sk-", "tok=sk-abcdefghijklmnopqrstuvwxyz"),  # gitleaks:allow
    ("private key", "-----BEGIN RSA PRIVATE KEY-----\nSINTETICO_FORMATO_APENAS"),  # gitleaks:allow
    ("jwt", "tok=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk"),  # gitleaks:allow
    ("supabase", "SUPABASE_SERVICE_ROLE_KEY=abcdefghijklmnopqrstuvwxyz123456"),  # gitleaks:allow
    ("x-api-key", "x-api-key: abcdefghijklmnopqrstuvwx"),  # gitleaks:allow
])
def test_bloqueia_conteudo_com_padrao_de_segredo(padrao: str, texto: str):
    r = _rodar_hook("guarda_segredo.py", {"tool_input": {"file_path": "x.py", "content": texto}})
    assert r.returncode == 2, f"{padrao}: {r.stdout + r.stderr}"
    assert r.stderr.strip()


def test_bloqueia_segredo_via_new_string_do_edit():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "x.py", "old_string": "a", "new_string": "chave=AKIAABCDEFGHIJKLMNOP"}},  # gitleaks:allow
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_bloqueia_segredo_via_edits_do_multiedit():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "x.py", "edits": [{"old_string": "a", "new_string": "b"},
                                                          {"old_string": "c", "new_string": "chave=AKIAABCDEFGHIJKLMNOP"}]}},  # gitleaks:allow
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_bloqueia_segredo_fora_de_tests_mesmo_com_sintetico_no_conteudo():
    """Fora de um módulo/fixture permitido, `SINTETICO` não isenta."""
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "app.py", "content": "chave=AKIAABCDEFGHIJKLMNOP SINTETICO"}},  # gitleaks:allow
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_bloqueia_bypass_por_traversal_de_caminho():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "tests/../app.py", "content": "AKIAABCDEFGHIJKLMNOP SINTETICO"}},  # gitleaks:allow
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_bloqueia_caminho_absoluto_fora_do_projeto(tmp_path: Path):
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": str(tmp_path / "tests" / "test_fake.py"), "content": "SINTETICO"}},
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_excecao_sintetica_exige_modulo_de_teste_ou_fixture():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "tests/not_a_test.py", "content": "AKIAABCDEFGHIJKLMNOP SINTETICO"}},  # gitleaks:allow
    )
    assert r.returncode == 2, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# guarda_segredo.py — permite


def test_permite_escrita_em_env_example():
    r = _rodar_hook("guarda_segredo.py", {"tool_input": {"file_path": ".env.example", "content": "X="}})
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_escrita_normal_sem_segredo():
    r = _rodar_hook("guarda_segredo.py", {"tool_input": {"file_path": "README.md", "content": "texto qualquer"}})
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_segredo_sintetico_dentro_de_tests():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": "tests/test_x.py", "content": "AKIA_SINTETICO_FAKE1234567890AB SINTETICO"}},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_permite_fixture_sintetico_com_separador_windows():
    r = _rodar_hook(
        "guarda_segredo.py",
        {"tool_input": {"file_path": r"tests\test_x.py", "content": "AKIA_SINTETICO_FAKE1234567890AB SINTETICO"}},
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# Falha fechada


def test_guarda_bash_bloqueia_com_stdin_invalido():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "guarda_bash.py"], input="isto nao e json",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


def test_guarda_segredo_bloqueia_com_stdin_invalido():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "guarda_segredo.py"], input="isto nao e json",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip()


def test_guarda_segredo_bloqueia_conteudo_ausente():
    r = _rodar_hook("guarda_segredo.py", {"tool_input": {"file_path": "README.md"}})
    assert r.returncode == 2, r.stdout + r.stderr


def test_run_hook_rejeita_script_fora_da_allowlist():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "../outro.py"], input="{}",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "script de hook não permitido" in r.stderr


def test_run_hook_rejeita_script_existente_fora_da_allowlist(tmp_path: Path):
    """Discrimina de verdade: usa um script que EXISTE no diretório de hooks mas não
    está na allowlist. Os dois testes acima usam nomes que também não existem como
    arquivo (`../outro.py`, `script_inexistente.py`) — se a allowlist do
    `run_hook.sh` for removida, o Python tenta rodar um caminho inexistente e sai
    com o MESMO código 2 por acidente, e o teste continuaria verde. Aqui, se a
    allowlist sumir, o script existe e RODARIA com sucesso (exit 0) em vez de ser
    recusado — por isso a cópia isolada em `tmp_path`, para não poluir
    `.claude/hooks/` do repo com um arquivo de teste."""
    hooks_copia = tmp_path / ".claude" / "hooks"
    shutil.copytree(HOOKS, hooks_copia)
    extra = hooks_copia / "extra_nao_permitido.py"
    extra.write_text("print('nao deveria rodar')\n", encoding="utf-8")
    r = subprocess.run(
        [_sh(), str(hooks_copia / "run_hook.sh"), "extra_nao_permitido.py"], input="{}",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "script de hook não permitido" in r.stderr


# ---------------------------------------------------------------------------
# settings.json — permissions e comandos de hook referenciam arquivo existente


def _settings() -> dict:
    return json.loads((RAIZ / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_settings_json_e_json_valido():
    _settings()  # levanta se malformado


def test_permissions_deny_contem_as_entradas_de_t1():
    deny = set(_settings().get("permissions", {}).get("deny", []))
    esperado = {
        "Read(./.env)", "Read(./.env.local)",
        "Edit(./.env)", "Edit(./.env.local)",
        "Write(./.env)", "Write(./.env.local)",
        "Bash(git push --force*)", "Bash(git push -f*)",
        "Bash(git commit --no-verify*)",
    }
    faltando = esperado - deny
    assert not faltando, f"permissions.deny sem: {faltando}"


def test_permissions_allow_so_tem_leitura_e_gates():
    allow = _settings().get("permissions", {}).get("allow", [])
    assert allow, "permissions.allow vazio"
    for entrada in allow:
        assert entrada.startswith("Bash("), f"entrada fora do esperado em allow: {entrada}"


RE_CAMINHO_SH = re.compile(r'"\$CLAUDE_PROJECT_DIR/([^"]+\.sh)"')
RE_SCRIPT_PY = re.compile(r'([A-Za-z0-9_]+\.py)\s*$')


def test_todo_command_de_pretooluse_referencia_arquivo_existente():
    """Cada `command` de hook PreToolUse resolve para dois arquivos que existem no
    repo: o `run_hook.sh` (via `$CLAUDE_PROJECT_DIR`) e o `.py` do hook em si
    (resolvido pela mesma cascata, dentro de `.claude/hooks/`)."""
    hooks = _settings().get("hooks", {}).get("PreToolUse", [])
    assert hooks, "settings.json sem hooks PreToolUse"
    total = 0
    for bloco in hooks:
        for h in bloco.get("hooks", []):
            comando = h.get("command", "")
            achado_sh = RE_CAMINHO_SH.search(comando)
            achado_py = RE_SCRIPT_PY.search(comando)
            assert achado_sh and achado_py, f"command fora do formato esperado: {comando}"
            caminho_sh = RAIZ / achado_sh.group(1)
            caminho_py = HOOKS / achado_py.group(1)
            assert caminho_sh.exists(), f"{caminho_sh} não existe (comando: {comando})"
            assert caminho_py.exists(), f"{caminho_py} não existe (comando: {comando})"
            total += 1
    assert total >= 2, "esperado ao menos guarda_bash.py e guarda_segredo.py registrados"


def test_hooks_pretooluse_com_matcher_bash_e_edit_write_multiedit_presentes():
    hooks = _settings().get("hooks", {}).get("PreToolUse", [])
    matchers = {bloco.get("matcher") for bloco in hooks}
    assert "Bash" in matchers, matchers
    assert any("Edit" in (m or "") and "Write" in (m or "") for m in matchers), matchers


# ---------------------------------------------------------------------------
# T4 — PreCompact/SessionStart saem de string inline e viram script versionado


TEXTO_PRECOMPACT = (
    '{"hookSpecificOutput":{"hookEventName":"PreCompact","additionalContext":'
    '"Instrucao obrigatoria para o resumo de compactacao: preserve integralmente '
    '(1) a lista de arquivos modificados na sessao, (2) as decisoes-chave tomadas '
    'e (3) os comandos de verificacao/teste ainda em aberto."}}'
)

TEXTO_SESSIONSTART_COMPACT = (
    "Contexto recem-compactado. Antes de prosseguir, confirme que o resumo "
    "preservou: (1) arquivos modificados na sessao, (2) decisoes-chave tomadas, "
    "(3) comandos de verificacao/teste em aberto. Se algo se perdeu, recupere via "
    "git status, .specs/STATE.md ou logs do workflow antes de continuar."
)


def test_precompact_contexto_emite_o_texto_exato():
    r = _rodar_hook("precompact_contexto.py", {})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.rstrip("\n") == TEXTO_PRECOMPACT


def test_sessionstart_contexto_emite_o_texto_exato():
    r = _rodar_hook("sessionstart_contexto.py", {})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.rstrip("\n") == TEXTO_SESSIONSTART_COMPACT


def test_run_hook_aceita_precompact_contexto_na_allowlist():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "precompact_contexto.py"], input="{}",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_run_hook_aceita_sessionstart_contexto_na_allowlist():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "sessionstart_contexto.py"], input="{}",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_run_hook_continua_recusando_nome_desconhecido():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "script_inexistente.py"], input="{}",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ)},
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "script de hook não permitido" in r.stderr


def test_settings_precompact_e_sessionstart_sem_json_inline():
    """Nenhum dos dois eventos volta a ter o texto embutido direto no `command` —
    ambos chamam `run_hook.sh` com o nome do script versionado."""
    precompact = _settings()["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    sessionstart = _settings()["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    for comando, script in (
        (precompact, "precompact_contexto.py"),
        (sessionstart, "sessionstart_contexto.py"),
    ):
        assert not comando.strip().startswith("echo"), comando
        assert "run_hook.sh" in comando and script in comando, comando


# ---------------------------------------------------------------------------
# T5 — ruff_feedback.py (PostToolUse): devolve achado do ruff sem bloquear


FAKE_RUFF = RAIZ / "tests" / "fixtures" / "fake_ruff.py"


def _env_fake_ruff(modo: str, timeout: str | None = None) -> dict:
    env = {
        "RUFF_FEEDBACK_CMD": f'"{sys.executable}" "{FAKE_RUFF}"',
        "FAKE_RUFF_MODE": modo,
    }
    if timeout is not None:
        env["RUFF_FEEDBACK_TIMEOUT_SEC"] = timeout
    return env


def test_ruff_feedback_devolve_achado_sem_bloquear():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "conftest.py"}},
        env_extra=_env_fake_ruff("achado"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    saida = json.loads(r.stdout)
    contexto = saida["hookSpecificOutput"]["additionalContext"]
    assert "E501" in contexto
    assert saida["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_ruff_feedback_arquivo_limpo_sai_zero_sem_saida():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "conftest.py"}},
        env_extra=_env_fake_ruff("limpo"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_ruff_ausente_degrada_em_silencio():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "conftest.py"}},
        env_extra={"RUFF_FEEDBACK_CMD": "ruff_binario_que_nao_existe_xyz"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_timeout_degrada_em_silencio():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "conftest.py"}},
        env_extra=_env_fake_ruff("timeout", timeout="0.3"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_erro_sem_stdout_nao_emite_nada():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "conftest.py"}},
        env_extra=_env_fake_ruff("erro_sem_stdout"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_json_invalido_no_stdin_degrada_em_silencio():
    r = subprocess.run(
        [_sh(), str(RUN_HOOK), "ruff_feedback.py"], input="isto nao e json",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TETO,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(RAIZ), **_env_fake_ruff("achado")},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_file_path_ausente_degrada_em_silencio():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {}},
        env_extra=_env_fake_ruff("achado"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_arquivo_fora_do_projeto_degrada_em_silencio(tmp_path: Path):
    alheio = tmp_path / "fora.py"
    alheio.write_text("x = 1\n", encoding="utf-8")
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": str(alheio)}},
        env_extra=_env_fake_ruff("achado"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_ruff_feedback_ignora_arquivo_nao_py():
    r = _rodar_hook(
        "ruff_feedback.py",
        {"tool_input": {"file_path": "README.md"}},
        env_extra=_env_fake_ruff("achado"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == ""


def test_run_hook_aceita_ruff_feedback_na_allowlist():
    r = _rodar_hook("ruff_feedback.py", {"tool_input": {}})
    assert r.returncode == 0, r.stdout + r.stderr


def test_settings_registra_posttooluse_com_matcher_edit_write_multiedit():
    hooks = _settings().get("hooks", {}).get("PostToolUse", [])
    assert hooks, "settings.json sem hooks PostToolUse"
    matchers = {bloco.get("matcher") for bloco in hooks}
    assert any("Edit" in (m or "") and "Write" in (m or "") for m in matchers), matchers
    for bloco in hooks:
        for h in bloco.get("hooks", []):
            assert h.get("type") == "command", h
            assert "run_hook.sh" in h.get("command", ""), h
