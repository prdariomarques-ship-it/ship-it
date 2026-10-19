# market-bots

Dois bots de Telegram de mercado, num único pacote Python (stdlib apenas, Python >= 3.11, sem chaves de API):

| id | Bot | Conteúdo |
|---|---|---|
| `national` | Mercado Brasil | Ibovespa/IBX/ETFs, câmbio (USD/EUR/GBP/CNY/JPY/ARS + DXY), ouro (R$/g, onça, GOLD11), Selic/CDI/IPCA/IGP-M (BCB SGS), Focus, maiores altas/baixas da B3, Fatos Relevantes (CVM), alertas |
| `global` | Mercado Global | Ásia, Europa, EUA, Américas (Brasil, México, Argentina, Chile, Peru, América Latina, Panamá), macro (ouro, prata, petróleo, cobre, DXY, Treasuries, BTC), alertas |

Tudo é configurado em `profiles.toml` (seções, tickers, horários, janelas de alerta, limites). Nenhum código muda para adicionar um ativo.

## Rodar

Mesmo artefato no PC e na VPS (imagem multi-arch, sem dependências nativas).

```bash
# Dentro do compose do Dario OS (docker/):
docker compose up -d --build market-bots
docker compose logs -f market-bots

# Sem Docker:
cd market-bots
python -m market_bots check-config
python -m market_bots once national          # imprime o boletim, não envia
python -m market_bots once global asia       # só uma seção
python -m market_bots run                    # loop (agenda + alertas + comandos)
```

Padrão seguro: `MB_SEND=off` (dry-run). Os envios são gravados no outbox em `MB_STATE_DIR` e nada sai para o Telegram.

## Ativar um bot de verdade

1. No @BotFather, crie o bot e copie o token (nunca commite).
2. Descubra o `chat_id` autorizado (o único chat que pode usar o bot; qualquer outro é ignorado — fail-closed).
3. Em `docker/.env`: `MB_NATIONAL_BOT_TOKEN`, `MB_NATIONAL_CHAT_ID` (e/ou `MB_GLOBAL_*`), depois `MB_SEND=on`.
4. `MB_PROFILES=national` roda só um bot.

Regra: **um único poller por token.** Se o mesmo token rodar em dois lugares (PC e VPS), o Telegram responde 409 e o bot aborta o polling em vez de brigar. Escolha onde cada bot roda (ex.: VPS em produção, PC só em dry-run).

## Comandos do bot

`/mercado` (boletim completo), um comando por seção do perfil (ex.: `/indices`, `/ouro`, `/juros`, `/asia`), `/altas` (maiores altas e quedas), `/fatos` (CVM), `/alertas` (regras ativas), `/cotacao SIMBOLO` (ex.: `/cotacao PETR4.SA`), `/ajuda`. Ids de seção não podem colidir com esses nomes reservados.

## Estado e idempotência

`MB_STATE_DIR` (volume `market_bots_data` no compose) guarda: slots já enviados (idempotência por horário, com progresso por parte de mensagem), último estado de alertas (confirmado só após entrega) e baseline de Fatos Relevantes (primeira execução não dispara histórico).

## Lacunas conhecidas

- **Curva de juros DI (futuro)**: não há fonte gratuita e estável (Tesouro Direto JSON → HTTP 410; Tesouro Transparente → erro de certificado; B3 ajustes → vazio). O bot não estima nem exibe curva inventada; mostra Selic, CDI, Focus e ^TNX. Requer decisão de fonte (ex.: credencial ANBIMA).
- **América Central**: sem índice gratuito confiável; Panamá via ETF `CPA` como proxy. Colômbia (ICOL/GXG) indisponível no Yahoo.
- Alguns tickers B3 não existem no Yahoo (ex.: ELET3, JBSS3, BRFS3, MRFG3); ficaram fora da lista de maiores altas/baixas.
- Fatos Relevantes (CVM IPE): parser testado com fixtures; download real ainda não validado em produção.

## Testes

```bash
cd market-bots && pip install pytest ruff && pytest -q && ruff check .
```
