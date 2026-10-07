# Runbook de implantação — financial-worker

**Status: NÃO EXECUTADO.** Nenhum comando deste documento foi rodado contra a
VPS ou qualquer banco real. Isto é um roteiro para quem tiver acesso à VPS
(você, ou uma sessão autorizada) executar manualmente, passo a passo,
quando decidir a janela de implantação. Esta sessão de desenvolvimento não
tem acesso de rede à VPS — não é possível rodar isto a partir daqui.

Pré-requisito de leitura: `docker/financial_role_setup.sql` (desenho da
role restrita) e `docker/docker-compose.financial.yml` (serviço isolado).

## Garantias que este roteiro preserva

- **Nunca** reconstrói, reinicia ou recria os serviços `backend`,
  `openwa` (sessão do WhatsApp ativa — reiniciar esse contêiner pode
  **deslogar a sessão do WhatsApp**), `frontend`, ou qualquer outro
  serviço do projeto `darioos` existente. Todo comando abaixo nomeia
  explicitamente `financial-worker` como alvo — nunca um `up -d` ou
  `restart` sem alvo, que recriaria TODOS os serviços do compose.
- **Nunca** toca no projeto `darioos-evolution`.
- A migração (passo 2) só adiciona uma tabela nova (`financial_jobs`) e
  seus índices — não altera, não bloqueia e não lê nenhuma tabela
  existente do WhatsApp (`jobs` e demais). Mesmo assim, rodar com backup
  prévio (passo 1) e verificação pós-migração (passo 3) antes de seguir.

## Observação importante sobre o Dockerfile existente

O `CMD` do `backend` já roda `alembic upgrade head` a cada start/restart
(ver `backend/Dockerfile`). Isso significa que a migração deste pacote
**seria aplicada automaticamente** na próxima vez que o `backend` for
reiniciado por qualquer outro motivo — mesmo sem este runbook. Aplicá-la
agora, de forma controlada (passo 2, via `exec` num contêiner já rodando,
sem reiniciar nada), é mais seguro do que deixar isso acontecer
implicitamente num restart futuro não relacionado.

---

## Passo 0 — Snapshot do estado atual (antes de qualquer coisa)

```bash
cd /caminho/para/darioos  # diretório com docker-compose.yml
docker compose ps > /tmp/pre_deploy_ps.txt
docker compose exec postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" \
  -c "SELECT count(*) FROM jobs;" > /tmp/pre_deploy_jobs_count.txt
cat /tmp/pre_deploy_ps.txt /tmp/pre_deploy_jobs_count.txt
```

Guarde esses dois arquivos — são a referência para confirmar, depois de
cada passo, que nada no WhatsApp mudou.

## Passo 1 — Backup do banco

```bash
docker compose exec postgres pg_dump -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}" \
  > /caminho/seguro/backup_pre_financial_$(date +%Y%m%d_%H%M%S).sql
```

Confirme o arquivo não está vazio e tem tamanho plausível antes de seguir.

## Passo 2 — Aplicar a migração (sem reiniciar o backend)

```bash
docker compose exec backend alembic upgrade head
```

`exec` roda dentro do contêiner **já em execução** — não reinicia o
processo uvicorn, não há downtime, não afeta `openwa`.

Verificação:

```bash
docker compose exec postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" \
  -c "\d financial_jobs"
docker compose exec postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" \
  -c "SELECT count(*) FROM jobs;"   # deve ser IGUAL ao valor do passo 0
```

Se a contagem de `jobs` mudou, PARE e investigue antes de continuar — não
deveria ter mudado.

## Passo 3 — Criar a role restrita do Postgres

Edite `docker/financial_role_setup.sql` substituindo
`REPLACE_ME_BEFORE_APPLYING` por uma senha real gerada agora (ex.:
`openssl rand -base64 24`) — **nunca commite essa senha no repositório**.
Depois:

```bash
docker compose exec -T postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" \
  < docker/financial_role_setup.sql
```

Verificação (prova de isolamento — deve dar os três resultados exatos
descritos no próprio arquivo .sql, seção 4):

```bash
docker compose exec postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" -c "
SET ROLE financial_worker;
SELECT * FROM jobs LIMIT 1;             -- esperado: ERRO permission denied
"
docker compose exec postgres psql -U "${POSTGRES_USER:-dario}" -d "${POSTGRES_DB:-darioos}" -c "
SET ROLE financial_worker;
SELECT * FROM financial_jobs LIMIT 1;   -- esperado: OK
"
```

Registre o resultado desses dois comandos — é a prova viva de isolamento
que a revisão pediu.

## Passo 4 — Credenciais no .env da VPS (nunca no repositório)

No arquivo `.env` usado pelo `docker compose` na VPS (não no repo),
adicione:

```
FINANCIAL_DB_USER=financial_worker
FINANCIAL_DB_PASSWORD=<a senha real gerada no passo 3>
TELEGRAM_BOT_TOKEN_SPCX=<token real do bot Monitor SPCX Dário>
TELEGRAM_CHAT_ID_SPCX=<chat id real>
TELEGRAM_BOT_TOKEN_B3=<token real do @dariozcodebot / PMX>
TELEGRAM_CHAT_ID_B3=<chat id real>
TELEGRAM_BOT_TOKEN_MERCADO=<token real do bot Mercado/Small11>
TELEGRAM_CHAT_ID_MERCADO=<chat id real>
MARKET_MONITORS_ENABLED=false
```

`MARKET_MONITORS_ENABLED=false` no primeiro deploy é deliberado — sobe o
worker, mas ele não envia nada ainda (passo 6 confirma saúde antes de
ligar os envios).

`docker-compose.financial.yml`'s `DATABASE_URL` já referencia
`${FINANCIAL_DB_USER}`/`${FINANCIAL_DB_PASSWORD}` (não a credencial do
backend principal) e usa `:?` — se essas duas variáveis não estiverem no
`.env`, o `up` falha explicitamente em vez de cair de volta para a
credencial compartilhada. Nenhuma edição de código é necessária neste
passo, só preencher o `.env` da VPS.

## Passo 5 — Build e subir SOMENTE o financial-worker

```bash
docker compose -f docker-compose.yml -f docker-compose.financial.yml build financial-worker
docker compose -f docker-compose.yml -f docker-compose.financial.yml up -d financial-worker
```

Nunca omita `financial-worker` do final desses comandos.

Confirme que nada mais foi recriado:

```bash
docker compose ps
diff /tmp/pre_deploy_ps.txt <(docker compose ps)
```

A única diferença esperada é a linha nova do `financial-worker`.

## Passo 6 — Verificar saúde antes de ligar os envios

```bash
docker compose logs -f financial-worker          # ctrl-C depois de ver alguns ticks limpos
docker compose ps financial-worker                # STATUS deve chegar a "healthy"
docker compose exec financial-worker cat /tmp/financial_worker_heartbeat
```

O heartbeat deve mostrar `"db_ok": true` e `"healthy": true`. Com
`MARKET_MONITORS_ENABLED=false`, as três cadeias ainda são semeadas e
reagendadas normalmente, só não chegam a montar/enviar mensagem — é
esperado e seguro observar isso rodando por um tempo antes do próximo
passo.

## Passo 7 — Ligar os envios

Só depois de confirmado o passo 6:

```bash
# no .env da VPS:
MARKET_MONITORS_ENABLED=true
```

```bash
docker compose -f docker-compose.yml -f docker-compose.financial.yml up -d financial-worker
```

(recria só este serviço, porque sua env mudou — ainda nomeado
explicitamente).

Acompanhe os primeiros ciclos reais pelo Telegram antes de considerar
isto estável.

## Rollback

Parar e remover só o worker, sem tocar em nada mais:

```bash
docker compose -f docker-compose.yml -f docker-compose.financial.yml stop financial-worker
docker compose -f docker-compose.yml -f docker-compose.financial.yml rm -f financial-worker
```

A tabela `financial_jobs` pode ficar no banco sem problema (vazia ou não)
— ela não é lida por nenhum outro serviço. Reverter a migração
(`alembic downgrade -1`) é opcional e de baixo risco por ser uma tabela
isolada, mas não é necessário para parar o worker.
