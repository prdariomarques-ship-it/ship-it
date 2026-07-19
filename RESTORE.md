# Restore — Dario OS

`scripts/restore.sh` automatiza a restauração de PostgreSQL e Qdrant a partir dos backups que `scripts/backup.sh` gera (ver `BACKUP.md`). Exige digitar uma frase de confirmação antes de sobrescrever qualquer coisa — não tem flag `--yes`/`--force` de propósito. Verificado ao vivo (restauração de uma coleção Qdrant a partir de um snapshot real, ponta a ponta) durante a correção do achado P0 de `PLATFORM_READINESS_REPORT_v1.3.1.md`.

```bash
scripts/restore.sh --postgres /caminho/para/darioos-YYYYMMDD-HHMMSS.sql.gz
scripts/restore.sh --qdrant /caminho/para/qdrant-darioos_memory-YYYYMMDD-HHMMSS.snapshot
scripts/restore.sh --postgres X.sql.gz --qdrant Y.snapshot   # os dois de uma vez
```

## Antes de começar

1. Confirme a integridade do backup (`gunzip -t arquivo.sql.gz` pro Postgres — o script já faz isso sozinho antes de restaurar).
2. Avise os usuários/operador: o sistema ficará indisponível durante a restauração do Postgres (o backend é parado e religado pelo script).
3. Se possível, rode `scripts/backup.sh` uma última vez antes de sobrescrever (mesmo que o estado atual esteja corrompido/desatualizado — evita perder qualquer coisa recuperável).

## O que o script faz

- **PostgreSQL**: para o backend, recria o banco vazio, restaura o dump, sobe o backend de novo (que roda `alembic upgrade head` automaticamente — se o dump for de uma versão de schema mais antiga, as migrações pendentes são aplicadas nesse momento).
- **Qdrant**: copia o arquivo de snapshot pra dentro do container (`docker cp` — a porta do Qdrant não é publicada pro host) e chama a própria API de recuperação de snapshot do Qdrant (`PUT /collections/{coleção}/snapshots/recover`), que reconstrói a coleção inteira a partir dele. O nome da coleção é extraído do próprio nome do arquivo (`qdrant-<coleção>-<timestamp>.snapshot` — o formato que `backup.sh` já usa).

**Sem um backup do Qdrant**: não há como recuperar embeddings/memória semântica perdida — o histórico estruturado (mensagens, contatos) no Postgres continua intacto, mas a busca semântica e o contexto de longo prazo dos agentes ficam vazios a partir desse ponto. O sistema continua funcionando (a busca semântica falha graciosamente — ver `docs/architecture.md`), só sem o contexto acumulado.

Depois de restaurar o Postgres, confirme com `GET /health/ready` que está `ok` e que `alembic upgrade head` não falhou (`docker compose logs backend`).

## Restaurar a sessão do WhatsApp (OpenWA)

Se você tem um snapshot do volume `openwa_data` (ver `BACKUP.md`):

```bash
cd docker
docker compose stop openwa
docker run --rm -v darioos_openwa_data:/data -v /caminho/do/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/openwa-session.tar.gz -C /data"
docker compose start openwa
```

**Sem um snapshot** (o caso mais comum, já que não há backup automático desse volume): a sessão precisa ser re-autenticada do zero — suba o container normalmente e re-escaneie o QR code pelo fluxo padrão do OpenWA. O número de WhatsApp fica temporariamente indisponível até esse passo manual.

## Restaurar n8n (workflows)

```bash
cd docker
docker compose stop n8n
docker run --rm -v darioos_n8n_data:/data -v /caminho/do/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/n8n-data.tar.gz -C /data"
docker compose start n8n
```

Sem snapshot: os workflows configurados no n8n precisam ser recriados manualmente. Não afeta o fluxo nativo do Cognitive Pipeline (que não depende do n8n).

## Verificação pós-restore

Checklist mínimo depois de qualquer restauração:

1. `GET /health/ready` retorna `status: "ok"` (ou `"degraded"` apenas nos componentes esperados, nunca `"unavailable"`).
2. Login no dashboard funciona com uma conta existente.
3. `GET /api/contacts` (autenticado) retorna dados esperados — confirma que o Postgres foi restaurado corretamente.
4. Enviar uma mensagem de teste pelo WhatsApp e confirmar que o auto-reply funciona ponta a ponta — confirma que o provider/sessão está ativo.
5. Conferir `docker compose logs backend` por qualquer erro de migração ou de conexão.

## Teste de restore

**Qdrant**: testado ao vivo ponta a ponta — snapshot real gerado por `scripts/backup.sh`, restaurado pela coleção com `scripts/restore.sh --qdrant`, `points_count` conferido igual antes/depois.

**PostgreSQL**: o script automatiza os mesmos passos manuais já documentados aqui antes (`DROP DATABASE`/restaurar dump/subir backend) — não foi executado de ponta a ponta contra o banco de produção real nesta sessão (isso apagaria o banco atual só pra provar o script, um risco desproporcional ao que estava sendo validado). Recomenda-se validar isso pelo menos uma vez contra um dump real, num ambiente onde apagar o banco não tem custo, antes de depender do script num incidente de verdade.
