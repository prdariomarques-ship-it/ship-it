# Deploy do bot no GitHub Actions

Este pacote roda o bot sem depender do computador ligado usando GitHub Actions.

## Arquivos publicados

- `work/send_market_telegram.py`: radar rotativo de mercado.
- `work/send_fx_telegram.py`: radar de cambio.
- `work/market_command_bot.py`: respostas aos comandos do Telegram.
- `.github/workflows/telegram-market.yml`: agenda o radar de mercado.
- `.github/workflows/telegram-fx.yml`: agenda o radar de cambio.
- `.github/workflows/telegram-commands.yml`: verifica comandos do Telegram.

## Secrets obrigatorios

No repositorio do GitHub, va em:

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

Crie:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Opcional, se o bot de cambio for separado:

- `TELEGRAM_FX_BOT_TOKEN`
- `TELEGRAM_FX_CHAT_ID`

Se os secrets opcionais nao forem definidos, o bot de cambio usa `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.

## Frequencia

- Mercado: a cada 15 minutos.
- Cambio: a cada 30 minutos.
- Comandos: a cada 5 minutos, que e o minimo permitido pelo GitHub Actions.

## Teste manual

No GitHub:

1. Abra `Actions`.
2. Escolha um workflow:
   - `Telegram Market Radar`
   - `Telegram FX Radar`
   - `Telegram Command Poller`
3. Clique em `Run workflow`.

## Depois que validar no GitHub

Desative as tarefas locais do Windows para evitar mensagens duplicadas:

- `MarketAgentTelegram`
- `MarketFxTelegram`
- `MarketCommandTelegram`

## Observacoes importantes

- GitHub Actions nao e um servidor sempre ligado. Ele executa tarefas agendadas.
- Agendamentos podem atrasar em horarios de alta carga.
- Para comandos instantaneos no Telegram, o melhor caminho gratuito e Cloudflare Workers com webhook.
- Antes de subir para repositorio publico, regenere o token do Telegram no BotFather se ele ja foi exposto em algum lugar.
