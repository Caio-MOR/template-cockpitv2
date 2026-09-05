#!/bin/sh
# Cascata de interpretador Python p/ hooks: portavel entre bash (Linux/macOS) e
# Git Bash (Windows). POSIX sh puro, sem bashismos.
# %% formato: cadeia

script="$1"
raiz="${CLAUDE_PROJECT_DIR:-.}"
dir="$raiz/.claude/hooks"

case "$script" in
    guarda_bash.py|guarda_segredo.py) ;;
    *)
        echo "run_hook.sh: script de hook não permitido" >&2
        exit 2
        ;;
esac

if [ ! -d "$dir" ]; then
    echo "run_hook.sh: diretório de hooks ausente" >&2
    exit 2
fi

if [ -x "$raiz/.venv/bin/python" ]; then
    py="$raiz/.venv/bin/python"
elif [ -x "$raiz/.venv/Scripts/python.exe" ]; then
    py="$raiz/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    py="python3"
elif command -v python >/dev/null 2>&1; then
    py="python"
else
    echo "run_hook.sh: nenhum interpretador Python encontrado; operação bloqueada" >&2
    exit 2
fi

exec "$py" "$dir/$script"
