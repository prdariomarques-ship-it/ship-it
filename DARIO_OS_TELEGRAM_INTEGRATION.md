# Dario OS x Telegram - auditoria e integração (somente o que está comprovado)

Data da auditoria: 2026-10-19. Branch `integration/dario-os-darius`. Nada foi enviado ao Telegram e nenhum bot foi iniciado:
a auditoria foi feita lendo código e páginas públicas; os testes usam rede simulada que **falha** se algo fora da lista permitida for chamado.

## 1. O que foi encontrado

| Bot | Onde | Função real | Dados | Disparo | Situação |
|---|---|---|---|---|---|
| Poller de comandos | `work/market_command_bot.py` + `telegram-commands.yml` | Responde `/start /help /mercado /indices /acoes /etfs /fiis /bdrs /rendafixa /cambio /derivativos /spcx` no chat autorizado. **Só `/cambio` consulta cotações**; os demais devolvem listas estáticas (sem preços) e `/spcx` um texto fixo. | AwesomeAPI (apenas `/cambio`) | cron `3/5 * * * *` (GitHub Actions) + manual | **COMPROVADO** (ativo, evidência datada) |
| Radar de câmbio | `work/send_fx_telegram.py` + `telegram-fx.yml` | Uma mensagem com USD, EUR, GBP, CHF, JPY, EUR/USD; sem cotação, só a lista de moedas. | AwesomeAPI | **somente manual** | **COMPROVADO** (código) / **sem agendamento** |
| Radar diversificado | `work/send_market_telegram.py` + `telegram-market.yml` | Uma mensagem com **nomes/símbolos** de um bloco rotativo. **Não busca nem envia preços.** | nenhuma | **somente manual** | **COMPROVADO** (código) / **sem agendamento** |
| `@Dmarques_bot` | repositório externo `agente-dmn` (README) | Gateway por long polling para o Hermes; `/start` e `/help`; encaminhamento ao Hermes é "passo futuro". | - | contínuo (processo Node) | código lido; execução **INCONCLUSIVO** |
| Monitor de renda fixa | repositório externo `renda-fixa-monitor` (`monitor_rf.py`) | Resumo diário (dia e 12 meses) de IMAB11/IRFM11/B5P211 via Yahoo; seg-sex 20:30; só envia se houver dados. | Yahoo Finance | APScheduler no próprio processo | código lido; execução **INCONCLUSIVO** |
| **Monitor SCPX** | - | Nenhum código, serviço ou especificação localizado (ship-it, `agente-dmn`, `renda-fixa-monitor`, disco local, busca web). | - | - | **INCONCLUSIVO** |

### Evidência de execução (página pública de Actions, lida em 2026-10-19; não é a API do GitHub)
- `telegram-commands.yml`: 1.411 execuções, todas as 6 mais recentes agendadas na `master`, concluídas com sucesso, a mais recente no dia da auditoria (#1411). Sucesso do workflow **não** prova que cada resposta chegou ao Telegram.
- `telegram-fx.yml`: 38 execuções, as 25 visíveis agendadas e **falhas** (14-38; última 17/07). O arquivo atual só tem `workflow_dispatch`: o agendamento foi removido depois. A causa das falhas **não foi investigada**.
- `telegram-market.yml`: 42 execuções, as 25 visíveis agendadas e **falhas** (última 17/07). Mesma situação.
- A API do GitHub não estava habilitada nesta sessão e o `gh` não existe no computador; por isso não há leitura de logs das execuções.

## 2. Riscos e o que foi corrigido

| Risco | Tratamento |
|---|---|
| Sem `TELEGRAM_CHAT_ID` o poller respondia a **qualquer chat** que encontrasse o bot (e disparava consulta externa em `/cambio`). | **Corrigido**: fail-closed - sem chat autorizado o poller não consulta nem responde nem confirma offset. Teste + mutação. |
| Execuções sobrepostas do poller (cron de 5 min, timeout de 5 min) poderiam responder o mesmo comando duas vezes ou causar 409. | **Corrigido**: `concurrency: telegram-commands`, `cancel-in-progress: false`. Teste que valida o workflow + mutação. |
| Dois consumidores de `getUpdates` com o mesmo token (Actions + agendador local Windows, ou `@Dmarques_bot`) se anulam (409). | **Guarda por teste**: apenas `market_command_bot.py` usa `getUpdates`. **Não verificado**: se existe agendador local ou se o token é compartilhado. |
| Confirmação do offset depois das respostas: queda no meio repete um comando (pelo menos uma vez). | Documentado; baixo impacto (respostas idempotentes de leitura). Não alterado para não mudar a semântica em produção. |
| O estado do offset (`.state/`) é efêmero no runner do Actions. | Funciona porque o script também confirma o offset no Telegram (segunda chamada `getUpdates`). Coberto por teste. |

## 3. Integração ao painel (somente o comprovado)

- **Backend**: `GET /api/admin/telegram/bots` (admin, **somente leitura**, sem método de escrita - 405). Fonte: `services/telegram_inventory.py`, um inventário **estático e datado**, com a evidência ao lado de cada afirmação.
- **Frontend**: aba **Telegram** em `/admin/darius`. Declara no topo que é inventário auditado (não tempo real) e que o **estado em tempo real está indisponível**; Monitor SCPX aparece como **INCONCLUSIVO**; contadores vêm do backend (status ausente não vira "0").
- **Por que estático**: o Dario OS não guarda credencial do Telegram nem lê o GitHub Actions. Mostrar "ativo" ao vivo seria inventar. Não há botão de iniciar/parar: o painel **não pode** criar uma instância duplicada.
- **Anti-deriva**: `tests/test_telegram_inventory.py` compara o inventário com os arquivos reais (comandos extraídos das rotas, gatilhos dos workflows, variáveis de ambiente lidas, arquivos existentes). Mudar um script/workflow sem atualizar o inventário falha o CI.

## 4. Testes

- `backend/tests/test_telegram_bots.py` (24): comandos e roteamento, listas sem preços, `/cambio` formatado e com fonte fora do ar (sem números), fail-closed, filtro de chat, offset (persistência/retomada/arquivo corrompido), truncamento, vazamento de token em logs, FX (um envio, bot dedicado, degradação), radar (um envio, sem preços), invariantes dos workflows. Rede simulada com lista de hosts permitidos.
- `backend/tests/test_telegram_inventory.py` (18): inventário x arquivos reais, invariantes das afirmações, sem segredos, endpoint (401/403/200/405).
- `frontend/tests/TelegramTab.test.tsx` (8): estado estático declarado, status por bot, SCPX INCONCLUSIVO, resumo vindo da API, somente leitura, erro, vazio, acessível pelo painel.
- Mutações detectadas: remover fail-closed, `cancel-in-progress: true`, não persistir offset. Mutante sobrevivente **equivalente** (`allowed_chat and ...` redundante após o fail-closed) - não é lacuna.

## 5. Como NÃO duplicar bots

1. Um único consumidor de `getUpdates` por token. Hoje: o workflow `telegram-commands`. Antes de rodar o script localmente com o mesmo token, **desative o workflow** (ou use outro bot).
2. Os scripts `send_*` são de envio único: não rodá-los em laço nem agendá-los em dois lugares.
3. Este repositório não inicia, para ou agenda bots. O painel é leitura.

## 6. Pendências (com classificação)

| Item | Classe |
|---|---|
| Poller de comandos ativo | COMPROVADO (evidência de página pública, 2026-10-19) |
| Respostas efetivamente entregues no Telegram | INCONCLUSIVO (sem logs/API) |
| Radares de câmbio/mercado agendados | AUSENTE (só manual; agendamentos antigos falhavam, causa não investigada) |
| `@Dmarques_bot` e monitor de renda fixa em execução | INCONCLUSIVO |
| Monitor SCPX | INCONCLUSIVO (nenhum código/serviço/especificação) |
| Estado em tempo real no painel | AUSENTE (exigiria leitura do GitHub/Telegram; decisão do usuário) |


## 7. Ciclo 6 - atualizacao (2026-10-19, API publica do GitHub, somente leitura)

| Item | Evidencia | Classificacao |
|---|---|---|
| Poller de comandos | workflow 312778373 `active`, 1.412 execucoes, ultima 2026-10-19T21:42:59Z, `schedule`, `success` | COMPROVADO (o workflow roda e termina sem erro). Entrega efetiva no Telegram: INCONCLUSIVO (logs exigem autenticacao) |
| Radar FX | 38 execucoes; as ultimas (2026-07-16/17, `schedule`) terminaram em `failure` no passo "Send FX radar"; hoje so `workflow_dispatch` | COMPROVADO que falhava; causa INCONCLUSIVA (sem log) |
| Radar Market | 42 execucoes; as ultimas (2026-07-16/17, `schedule`) terminaram em `failure` | COMPROVADO que falhava; causa INCONCLUSIVA |
| Monitor SCPX / Monitor Mercado | nada no repo, no Windows (nome e conteudo) nem nos workflows; rodavam no celular Z3 (Termux), fora do alcance | INCONCLUSIVO |

Nada foi reativado e nenhuma mensagem foi enviada.

### Decisao do usuario (2026-10-19, 20:10)
SCPX e Monitor Mercado nao serao ressuscitados. Serao criados **dois bots novos**: Mercado Nacional e Mercado Internacional.
Pre-requisitos que dependem do usuario: criar os bots no @BotFather (tokens como secrets, nunca no chat), informar os chat_ids e escolher onde rodam (recomendado: GitHub Actions com schedule). Construcao em modo dry-run por padrao; envio real somente com autorizacao explicita.
Verificacao no Z3 (quando ligado): `ps`, `crontab -l`, `ls ~/.termux/boot`.