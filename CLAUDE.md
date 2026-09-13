@AGENTS.md

# Adendos do Claude Code

- As regras em `.claude/rules/` carregam sozinhas na abertura da sessão — não precisam ser relidas.
- O sub-agente `verificador` (`.claude/agents/`) e os commands `gates` e `verificar` (`.claude/commands/`) são o caminho padrão para fechar entrega: rodar gates com evidência, depois verificação independente.
- A memória do agente vive fora do repo (diretório de memória da máquina); ligá-la por junction/symlink é escolha por máquina, nunca versionada — ver `README.md`.
