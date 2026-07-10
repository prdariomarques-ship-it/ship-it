# Resposta a Incidentes — Dario OS

Playbooks para os cenários de falha conhecidos do sistema, baseados no comportamento real verificado em `PRODUCTION_APPROVAL.md` e nos testes automatizados. Cada seção segue: **como detectar** → **impacto real** → **o que fazer**.

## 1. PostgreSQL indisponível

**Detectar**: `GET /health/ready` retorna `503` com `status: "unavailable"` e `checks.database` = `"error: ..."`.

**Impacto**: o único caso onde o sistema fica realmente fora do ar — toda requisição que toca o banco falha. É a única dependência classificada como obrigatória.

**Ação**:
1. Verificar o container: `docker compose ps postgres`, `docker compose logs postgres`.
2. Se o container caiu, `docker compose up -d postgres` — os dados persistem no volume `postgres_data`.
3. Se o volume está corrompido, restaurar do último backup (`RESTORE.md`).
4. Depois de o Postgres voltar, o backend detecta sozinho na próxima checagem de `/health/ready` — não precisa reiniciar o backend.

## 2. Redis indisponível

**Detectar**: `checks.redis` = `"error: ..."` em `/health/ready`, mas `status` geral fica `"degraded"`, não `"unavailable"`.

**Impacto**: cache e rate limiting caem automaticamente para um fallback em memória local (`services/cache.py`, `services/rate_limit.py`) — o sistema continua respondendo normalmente. Numa instância única isso é transparente. Com múltiplas réplicas do backend, cada uma passa a ter seu próprio rate limit/cache local até o Redis voltar (ver `docs/architecture.md`).

**Ação**: `docker compose up -d redis`. Nenhuma ação no backend é necessária — ele volta a usar o Redis assim que ele responde de novo.

## 3. Qdrant indisponível

**Detectar**: `checks.qdrant` = `"error: ..."` em `/health/ready`; logs do backend mostram avisos "Semantic memory lookup skipped" ou "Memory lookup skipped".

**Impacto**: busca semântica (memória de longo prazo, conhecimento) falha graciosamente — os agentes continuam respondendo, só sem esse contexto adicional. Nenhuma mensagem é perdida; embeddings pendentes ficam retentando via a fila de jobs (`memory.embed`) até o Qdrant voltar.

**Ação**: `docker compose up -d qdrant`. Jobs `memory.embed` que falharam vão reprocessar automaticamente (retry com backoff exponencial da fila).

## 4. Provider de WhatsApp indisponível (gateway fora do ar)

**Detectar**: `checks.whatsapp` = `"error: ..."` em `/health/ready`; `darioos_whatsapp_session_status{provider}` = 0; `darioos_whatsapp_provider_requests_total{status="error"}` subindo.

**Impacto**: envio de mensagens falha; cada tentativa já tem retry com backoff exponencial embutido (`WhatsAppProvider._request`), depois o job `whatsapp.send_text` também tenta de novo pela fila. Mensagens recebidas (inbound) não são afetadas — só o envio da resposta atrasa.

**Ação**:
1. Verificar o gateway específico: `docker compose logs openwa` (ou o provider configurado).
2. Se for sessão deslogada (`AUTH_EXPIRED` nos logs, evento `whatsapp.session_changed`), é necessário **re-parear manualmente** — escanear o QR code de novo. Não existe reconexão automática para isso (é uma limitação da tecnologia WhatsApp Web, documentada em `docs/architecture.md`).
3. Mensagens que falharam ao enviar continuam na fila de jobs (`GET /api/jobs`) e serão reenviadas automaticamente quando o provider voltar — não é necessário reenviar manualmente.

## 5. Provider de LLM indisponível ou com chave inválida

**Detectar**: respostas do sistema viram a mensagem de stub (`STUB_REPLY`); se `LLM_FALLBACK_PROVIDER` estiver configurado, os logs mostram "switching to fallback provider".

**Impacto**: sem fallback configurado, o sistema continua respondendo, mas com uma mensagem genérica em vez de uma resposta real — não trava, não perde mensagens.

**Ação**:
1. Verificar a chave/endpoint do provedor configurado (`LLM_PROVIDER` e a chave correspondente em `docker/.env`).
2. Considerar configurar `LLM_FALLBACK_PROVIDER` para um segundo provedor, se ainda não estiver.
3. Depois de corrigir a variável, `docker compose restart backend` (as configurações são lidas na subida do processo).

## 6. Fila de jobs travada / acumulando

**Detectar**: `GET /api/jobs` (admin) mostra muitos jobs em `QUEUED` sem progredir, ou `darioos_job_duration_seconds` crescendo.

**Impacto**: respostas automáticas do WhatsApp, embeddings e resumos atrasam.

**Ação**:
1. Confirmar que o worker está rodando: ele roda embutido no processo do backend — `docker compose logs backend | grep -i job` para ver atividade.
2. Se o backend crashou e reiniciou, jobs que ficaram `RUNNING` são recuperados automaticamente após `JOBS_STALE_AFTER_SECONDS` (padrão 300s) — não é necessário reprocessar manualmente.
3. Se um job específico está falhando repetidamente, ver `last_error` em `GET /api/jobs/{id}` e `POST /api/jobs/{id}/cancel` se for necessário descartá-lo.

## 7. Loop ou flood de auto-reply em um contato

**Detectar**: logs com "Auto-reply throttled for contact ... (loop/flood guard)"; muitas mensagens do mesmo número em pouco tempo.

**Impacto**: nenhum — o freio (`AUTO_REPLY_MAX_PER_CONTACT_PER_MINUTE`, padrão 6/min) já contém automaticamente; mensagens continuam sendo persistidas, só o auto-reply extra é pulado.

**Ação**: geralmente nenhuma. Se for um caso legítimo precisando de mais volume, ajustar `AUTO_REPLY_MAX_PER_CONTACT_PER_MINUTE` no `.env` e reiniciar o backend.

## 8. Suspeita de abuso via webhook do WhatsApp

**Detectar**: volume anormal de requisições a `/api/webhooks/whatsapp`, ou mensagens de contatos desconhecidos com padrões suspeitos (tentativas de fazer o agente enviar mensagens para números arbitrários — isso já é bloqueado tecnicamente desde PROD-005, mas fica registrado como erro `"not authorized to..."` nos resultados de ferramenta).

**Ação**:
1. Confirmar que `WEBHOOK_SECRET` está configurado (obrigatório desde PROD-004 — se o sistema está rodando em produção, já está).
2. Revisar `GET /api/logs?source=cognitive_pipeline.learning` e os `ExecutedStep` com `status="error"` recentes para identificar tentativas bloqueadas.
3. Se necessário, desativar `AUTO_REPLY_ENABLED` temporariamente para interromper qualquer resposta automática enquanto se investiga.

## 9. Disco cheio (logs sem rotação)

**Detectar**: `docker compose logs` falhando, containers reiniciando sem motivo aparente, `df -h` no host mostrando pouco espaço livre.

**Impacto**: pode derrubar qualquer container, incluindo o Postgres — o pior caso possível.

**Ação**:
1. Identificar os maiores arquivos de log: `docker inspect --format='{{.LogPath}}' $(docker compose ps -q)`.
2. Truncar temporariamente se crítico: `truncate -s 0 <caminho-do-log>` (não apaga o container, só o arquivo de log).
3. Configurar rotação permanente — ver `MONITORING.md` e `MAINTENANCE_PLAN.md` (não configurado por padrão hoje).

## 10. Container reiniciando em loop (`unhealthy` / `restarting`)

**Detectar**: `docker compose ps` mostra o backend em `Restarting` ou `unhealthy`.

**Ação**:
1. `docker compose logs backend --tail 200` — geralmente o motivo aparece nas primeiras linhas (falha de migração, `JWT_SECRET`/`WEBHOOK_SECRET` ausente/fraco em produção — o processo recusa subir de propósito nesses casos, ver `main.py::_validate_production_settings`).
2. Se for uma migração falhando, verificar `alembic_version` no Postgres e comparar com `backend/alembic/versions/`.
3. Ver `RUNBOOK.md` para o procedimento de rollback de deploy.
