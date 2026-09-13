# Conduta com o Colaborador

Regra carregada na abertura da sessão. Regula a convivência num repositório
compartilhado — não a técnica, que é do agente.

## O usuário não precisa entender a mecânica

Git, branch, PR, ambiente virtual, gate, skill são preocupação do agente.
Pergunte ao usuário só sobre **intenção de negócio** e decisões que mudam o
resultado; nunca sobre mecânica reversível. Isso refina as Hard Rules 1 e 3 do
`AGENTS.md` (perguntar em ambiguidade / confirmar escopo acima de 3 arquivos):
valem para decisão de negócio e mudança destrutiva, não para a mecânica de
versionar. Fale sem jargão; quando um termo técnico for inevitável, explique
em uma frase.

## Versionamento é padrão, não opção

Todo trabalho nasce em branch a partir da branch principal; nunca commit
direto nela. Entrega pronta é branch empurrada + PR aberta descrevendo o que
muda e com a evidência dos gates. Merge é decisão humana — do dono do
repositório ou de quem ele indicar. Commits pequenos, mensagem no padrão
Conventional Commits, no idioma do repo. Nada de reescrever ou forçar
histórico compartilhado.

O hook `.claude/hooks/guarda_bash.py` bloqueia commit em main, force push e
`--no-verify` no ato — mas só para quem roda no Claude Code. Nos demais
agentes, esta seção é a única coisa entre você e um commit direto na branch
principal.

## Memória do agente

O que for duradouro (decisão do usuário, regra de negócio, fato que a próxima
sessão precisa) se registra na mesma sessão em `.claude-memory/` (quando o
repositório a versiona) ou em `.specs/STATE.md`. O que é só desta conversa não
se registra. Nunca guardar segredos.

## Skill nova

Segue o modelo em `.agents/skills/_exemplo-skill/` — a fonte, nunca um espelho.
