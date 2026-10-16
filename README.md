# AssigmentsReminder

Resumo diário do bCourses (Canvas) em português, para Telegram, e-mail ou terminal.
Usa Python 3.11+ e a biblioteca padrão; não há pacotes para instalar.

## O que entra no resumo

- Disciplinas com matrícula ativa como aluno.
- Tarefas publicadas e acessíveis: atrasadas, com vencimento nos próximos 14 dias e sem prazo.
- Entregas registradas e tarefas dispensadas são omitidas. Tarefas marcadas como faltantes continuam aparecendo, mesmo com nota zero.
- Anúncios dos últimos sete dias, com trecho do texto e link, repetidos no resumo durante esse período.
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

Horário escolhido: **todos os dias às 08:00 de Berkeley**, com ajuste automático ao horário de verão. Depois de configurar as três variáveis, execute:

```bash
cd /workspace/AssigmentsReminder
bash start_daily.sh
```

O processo precisa rodar continuamente em um computador ou servidor ligado. Uma sessão temporária de desenvolvimento não garante notificações quando suspensa. Para uso permanente, execute o comando como serviço no provedor escolhido, com reinício automático e variáveis secretas configuradas. Nenhum serviço foi publicado por este projeto.

O arquivo local `.reminder-state.json` registra o dia do último envio bem-sucedido. Preserve-o entre reinícios e execute uma única instância por destino. Se iniciar depois do horário, envia o resumo daquele dia imediatamente. Falhas são repetidas a cada cinco minutos. Uma interrupção durante o envio pode repetir mensagens; não há garantia de entrega exatamente uma vez.

Opções: `--days 30`, `--timezone America/Los_Angeles`, `--state /caminho/estado.json`. Sem `--daily-at`, executa uma vez e encerra. Não inclua arquivos com segredos no Git.

## Desenvolvimento e validação

```bash
python3 -m unittest discover -s tests -v
python3 reminder.py --help
```

Os testes usam respostas simuladas do Canvas e Telegram. Validam seleção de tarefas, fuso horário, anúncios, paginação, proteção da credencial e divisão de mensagens. A validação com uma conta real e entrega ao celular depende das credenciais do usuário. O fluxo de e-mail também precisa de teste com seu provedor SMTP.
