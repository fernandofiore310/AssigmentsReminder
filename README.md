# AssigmentsReminder

Resumo diário do bCourses (Canvas) em português, para Telegram, e-mail ou terminal.
Usa Python 3.11+ e a biblioteca padrão; não há pacotes para instalar.

## O que entra no resumo

- Disciplinas com matrícula ativa como aluno.
- Tarefas publicadas, acessíveis e ainda abertas, com vencimento nos próximos 14 dias, inclusive o limite de duas semanas. Tarefas sem prazo também aparecem. Tarefas com `due_at` vencido, `lock_at` encerrado ou `unlock_at` futuro são excluídas. Isso também exclui tarefas atrasadas mesmo que o professor aceite entrega com atraso.
- Entregas registradas e tarefas dispensadas são omitidas. Tarefas marcadas como faltantes continuam aparecendo, mesmo com nota zero.
- Anúncios publicados desde o último resumo enviado com sucesso para aquele destino, com trecho do texto. No primeiro envio, considera as últimas 24 horas. O corte avança somente depois que todas as mensagens são aceitas pelo serviço.
- O terminal e o Telegram usam o mesmo texto. Links de acesso às tarefas e anúncios não são acrescentados ao resumo; URLs escritas pelo professor no próprio anúncio podem continuar aparecendo.
- Horários de Berkeley (`America/Los_Angeles`), incluindo horário de verão.

O resumo depende dos dados disponíveis na API. Confira também o bCourses: atividades em ferramentas externas ou com configurações especiais podem não aparecer como pendentes no Canvas.

## Acessar o bCourses

Se a instituição permitir tokens pessoais, entre no bCourses e procure **Account → Settings → Approved Integrations → New Access Token**. Escolha uma validade apropriada. Caso a opção não exista, consulte o suporte do bCourses sobre acesso autorizado à API; este programa não automatiza login do CalNet nem Duo.

Configure `CANVAS_TOKEN` como segredo no serviço que executar o programa. Não coloque tokens no repositório ou no chat. Para testar no terminal sem registrar o token no histórico:

```bash
cd /workspace/AssigmentsReminder
read -rsp 'Canvas token: ' CANVAS_TOKEN
export CANVAS_TOKEN
python3 reminder.py
```

O comando apenas consulta a API e mostra o resumo. Ele não entrega, altera ou marca tarefas e anúncios como lidos. `CANVAS_BASE_URL` é opcional; o padrão é `https://bcourses.berkeley.edu`.

## Telegram

1. Instale o Telegram, crie sua conta e abra o **[@BotFather](https://t.me/BotFather)**. Envie `/newbot`, escolha um nome e um nome de usuário terminado em `bot`. Guarde o token fornecido como segredo `TELEGRAM_BOT_TOKEN` nas configurações do ambiente, nunca no chat.
2. Abra a conversa com seu bot e envie `/start`.
3. Obtenha seu `chat.id` pelo método oficial `getUpdates` da API do Telegram e configure `TELEGRAM_CHAT_ID`. Não compartilhe o token em links ou capturas de tela.
4. Teste uma entrega real:

```bash
python3 reminder.py --channel telegram
```

Ative as notificações dessa conversa no celular. Resumos longos são enviados em várias mensagens.

## E-mail

Configure `SMTP_HOST`, `SMTP_PORT` (padrão 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` e `REMINDER_EMAIL`. O servidor precisa oferecer STARTTLS; alguns provedores exigem senha de aplicativo. Execute:

```bash
python3 reminder.py --channel email
```

## Envio diário

### Nuvem: GitHub Actions

O workflow `.github/workflows/daily-digest.yml` executa em computadores do GitHub, sem depender do seu notebook ou do Publish do Codex. Para ativar no seu repositório:

1. Abra **Settings → Secrets and variables → Actions → New repository secret** e configure `CANVAS_TOKEN`, `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Os valores configurados no Codex ou no seu WSL não são transferidos automaticamente. Não coloque tokens em arquivos nem em logs.
2. Em **Actions**, habilite workflows se o GitHub solicitar. O workflow precisa poder escrever no repositório para preservar o estado; políticas da organização e regras de proteção de branches podem restringir essa operação.
3. Abra **Daily bCourses digest → Run workflow**. Antes das 08:00 de Berkeley, ele apenas verifica o horário e encerra. Depois das 08:00, envia se ainda não enviou naquele dia. Confira o resultado em Actions e a mensagem no Telegram.
4. Confira também a etapa **Persist delivery state**. Ela precisa concluir com sucesso; se enviar a mensagem mas falhar ao salvar o estado, a próxima execução pode repetir anúncios.

Os agendamentos disparam às 15:00 e 16:00 UTC. O programa verifica o fuso de Berkeley e registra a data para enviar uma única vez, a partir das 08:00 tanto no verão quanto no inverno. GitHub Actions pode atrasar ou deixar de executar agendamentos; não oferece garantia de entrega pontual. Execuções programadas só usam a branch padrão. Em repositórios públicos, agendamentos podem ser desativados após 60 dias sem atividade. Verifique os limites e eventuais custos da sua conta, especialmente em repositórios privados.

O registro fica na branch separada `reminder-state`, contendo apenas horários e identificadores de destino em hash, sem tokens ou conteúdo acadêmico. A branch é criada pelo primeiro envio bem-sucedido. Cada execução restaura esse registro antes da consulta. Em repositórios públicos, esses metadados também ficam públicos. Falhas de envio não avançam o corte dos anúncios; uma interrupção após enviar e antes de persistir o estado pode provocar repetição.

O primeiro envio na nuvem começa com as últimas 24 horas, independentemente do arquivo de estado do seu WSL. Depois de ativar na nuvem, pare qualquer agendador local com `Ctrl+C` para evitar dois serviços enviando resumos. O estado da nuvem e o local são independentes.

### Computador local / WSL

Horário escolhido: **todos os dias às 08:00 de Berkeley**, com ajuste automático ao horário de verão. Depois de configurar as três variáveis, execute:

```bash
cd /workspace/AssigmentsReminder
bash start_daily.sh
```

Nesse modo, o processo precisa rodar continuamente em um computador ou servidor ligado. Uma sessão temporária de desenvolvimento não garante notificações quando suspensa.

O arquivo local `.reminder-state.json` registra o dia e o instante do último resumo enviado com sucesso. Preserve-o entre reinícios e execute uma única instância por destino. Se iniciar depois do horário, envia o resumo daquele dia imediatamente. Falhas são repetidas a cada cinco minutos, sem avançar o corte dos anúncios. Uma interrupção durante o envio pode repetir mensagens; não há garantia de entrega exatamente uma vez. Se o estado for apagado, o próximo envio volta à janela inicial de 24 horas.

O comando de visualização no terminal não altera o estado; quando `TELEGRAM_CHAT_ID` está configurado, usa o último corte do Telegram. Um envio manual real atualiza o corte dos anúncios para o próximo resumo, mas não cancela o envio diário agendado. Estados antigos que só registravam o dia usam a janela inicial de 24 horas no primeiro envio desta versão.

Opções: `--days 30`, `--timezone America/Los_Angeles`, `--state /caminho/estado.json`. Sem `--daily-at`, executa uma vez e encerra. Não inclua arquivos com segredos no Git.

## Desenvolvimento e validação

```bash
python3 -m unittest discover -s tests -v
python3 reminder.py --help
```

Os testes usam respostas simuladas do Canvas e Telegram. Validam seleção de tarefas, fuso horário, anúncios, paginação, proteção da credencial e divisão de mensagens. A validação com uma conta real e entrega ao celular depende das credenciais do usuário. O fluxo de e-mail também precisa de teste com seu provedor SMTP.
