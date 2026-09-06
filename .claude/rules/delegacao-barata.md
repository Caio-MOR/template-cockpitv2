# Delegação barata (sessão principal orquestra, subagentes executam)

A sessão principal é dona da intenção, do escopo e do aceite final: ela pensa,
especifica, despacha, lê o resultado e conversa com o dono do repo. O trabalho
mecânico sai para subagentes quando o harness os oferece; quando não oferece, a
sessão executa inline com o mesmo contrato. Esta regra não cita modelo nem
fornecedor de propósito: isso é configuração do harness e muda mais rápido que ela.

## Regra

1. **Antes de trabalho com mais de ~3 chamadas de ferramenta, pergunte:** "um
   subagente com uma boa ordem faz isso?" Se sim, delegue. "É pequeno, faço eu" é
   justamente o raciocínio que a regra proíbe.
2. **Modelo pelo tipo de trabalho:** o mais barato que o harness oferecer para
   trabalho mecânico (explorar, aplicar edição especificada, rodar gates, atualizar
   docs); o mais forte para especificar, decidir arquitetura e depurar causa
   desconhecida. Onde o harness permite escolher o modelo por agente, fixe-o em cada
   despacho — sem isso o subagente herda o modelo caro da sessão e a delegação não
   economiza nada. O tier concreto é configuração, não doutrina: vive na variável de
   ambiente de subagente do harness e no campo de modelo do frontmatter de cada
   agente; troque esses valores conforme o harness disponível — esta regra não
   nomeia modelo nem fornecedor.
3. **Paralelize.** Frentes independentes saem numa única resposta, em background.
   Espere só quando o próximo passo depende do resultado.
4. **Verificação também é delegada, e autor ≠ verificador.** Quem escreveu não
   confere; um verificador independente reproduz a evidência em vez de acreditar nela.
   A sessão principal lê o veredito, não refaz a prova.
5. **Não polua a sessão principal com leitura.** Arquivo grande, log, transcript: um
   subagente lê e devolve a conclusão.

## O que fica na sessão principal

- Decidir, discordar, propor caminho; escrever a spec ou o prompt cirúrgico do
  subagente (a qualidade desse texto é o que autoriza descer de modelo).
- Falar com o dono do repo; ler resultados e vereditos; registrar decisões.
- Ações de um ou dois comandos cuja delegação custaria mais que a execução.

## Contrato do prompt para o executor

Repo e caminho exatos; isolamento (worktree/branch) quando outras sessões escrevem no
mesmo repo; tarefas numeradas com commit por tarefa; critério de pronto verificável
por comando; teto de rodadas em qualquer laço (3); o que **não** tocar; formato do
relatório curto. Prompt sem critério de pronto não é spec, é pedido de favor.
