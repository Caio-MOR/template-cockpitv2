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

## Onde vive cada coisa

Só o que o `AGENTS.md` não cobre: um utilitário ou protótipo pequeno nasce em
`apps/<nome>/` neste repositório; quando ganha usuários, publicação própria ou
ciclo de release, vira repositório próprio (a partir do template do tipo
correspondente, se existir) — e aqui fica só a linha do router apontando para
ele. Skill nova segue o modelo em `.claude/skills/_exemplo-skill/`.

## Memória do agente

O que for duradouro (decisão do usuário, regra de negócio, fato que a próxima
sessão precisa) se registra na mesma sessão em `.claude-memory/` (quando o
repositório a versiona) ou em `.specs/STATE.md`. O que é só desta conversa não
se registra. Nunca guardar segredos.

## Segredos

Ficam em `.env` (já ignorado pelo git) — nunca em código, log, commit ou
mensagem. O hook `pre-push` roda o gitleaks local quando ele existe na máquina e
o CI de PR (`gitleaks.yml`) varre o histórico inteiro em toda pull request.

## Entrega com evidência

Rode os gates antes de abrir a PR. Vermelho se conserta antes de entregar,
nunca se explica depois. Cole a saída dos gates, não a afirmação de que
passaram.

---

Estas são regras de convivência num repositório compartilhado, não de
técnica — a técnica é sua.
