# Monitoramento — Dario OS

## O que existe hoje

### Health checks

| Endpoint | Uso | Comportamento |
| --- | --- | --- |
| `GET /health`, `GET /health/live` | Liveness — "o processo está vivo?" | Sempre `200 {"status": "ok"}` se o processo responde |
| `GET /health/ready` | Readiness — "o sistema está pronto para tráfego?" | `200` com `status: "ok"` ou `"degraded"`; `503` com `status: "unavailable"` **apenas** se o Postgres estiver inacessível. Redis, Qdrant e o provider de WhatsApp configurado são verificados mas nunca derrubam a readiness — cada um aparece em `checks.{nome}` como `"ok"` ou `"error: <tipo da exceção>"` |

O `Dockerfile` do backend já declara um `HEALTHCHECK` batendo em `/health` a cada 30s — o Docker marca o container como `unhealthy` automaticamente se parar de responder, mas isso **não** reinicia o container sozinho (não há `restart: on-unhealthy` configurado, só `restart: unless-stopped`, que reage a crash/exit, não a um healthcheck falho). Ver `INCIDENT_RESPONSE.md` para o que fazer quando isso acontece.

### Métricas Prometheus

`GET /metrics` expõe todas as métricas em formato Prometheus (`prometheus_client`). Hoje isso inclui:

| Categoria | Métricas |
| --- | --- |
| HTTP | `darioos_http_requests_total{method,path,status}`, `darioos_http_request_duration_seconds{method,path}` |
| Agentes | `darioos_agent_runs_total{agent,provider,status}`, `darioos_agent_run_duration_seconds{agent}`, `darioos_agent_tool_calls_total{tool,status}`, `darioos_agent_tokens_total{provider,kind}`, `darioos_agent_cost_usd_total{provider}` |
| Jobs | `darioos_job_duration_seconds{name}` |
| WhatsApp | `darioos_whatsapp_provider_requests_total{provider,status}`, `darioos_whatsapp_session_status{provider}` |
| Cognitive Pipeline | `darioos_pipeline_stage_duration_seconds{stage}`, `darioos_pipeline_run_duration_seconds`, `darioos_intent_classifications_total{intent}`, `darioos_priority_classifications_total{priority}`, `darioos_pipeline_validation_retries_total`, `darioos_pipeline_memory_lookups_total{kind}` |

**Importante — o que NÃO existe**: não há nenhum Prometheus, Grafana, Alertmanager ou qualquer stack de coleta/visualização no `docker/docker-compose.yml`. `/metrics` só expõe os dados; nada os coleta, armazena histórico ou dispara alertas hoje. Além disso, o `Caddyfile` não expõe `/metrics` externamente (só `/health`, `/api/*`, `/docs`, `/openapi.json` e `/n8n/*` são roteados) — isso é intencional (não expor métricas internas publicamente), mas significa que um Prometheus externo ao host precisaria alcançar a rede Docker interna, não a porta pública.

### Logs

Todos os logs vão para `stdout` (nunca arquivo), acessíveis via `docker compose logs`. Com `LOG_JSON=true` (padrão no Compose), cada linha é um objeto JSON pronto para um coletor (Loki, ELK, CloudWatch etc.) — mas nenhum coletor está configurado no repositório hoje.

**Rotação de logs**: o driver de log padrão do Docker (`json-file`) **não tem limite de tamanho por padrão** — nenhuma opção `max-size`/`max-file` está configurada em nenhum serviço do `docker-compose.yml`. Sem uma dessas duas coisas configuradas, os logs podem crescer indefinidamente e encher o disco do host. Ver `MAINTENANCE_PLAN.md` para a rotina recomendada até isso ser resolvido na configuração do Compose.

### Auditoria estruturada

Toda ação relevante (webhook recebido, sessão de WhatsApp mudou de estado, pipeline cognitivo concluído, evento de fila) é gravada na tabela `logs` do Postgres (`services/audit.py::record_log`), consultável via `GET /api/logs` (admin). Isso é auditoria de aplicação, não observabilidade de infraestrutura — não expira automaticamente (sem rotina de limpeza configurada, ver `MAINTENANCE_PLAN.md`).

## O que observar de perto (sem uma stack de alertas configurada, hoje isso é manual)

| Sinal | Onde ver | O que indica |
| --- | --- | --- |
| `checks.redis`/`checks.qdrant`/`checks.whatsapp` = `"error: ..."` em `/health/ready` | requisição manual ou script de monitoramento externo | Dependência opcional fora do ar — sistema continua respondendo, mas degradado |
| `darioos_whatsapp_session_status{provider}` = 0 | `/metrics` | Sessão de WhatsApp desconectada — precisa de re-pareamento (ver `INCIDENT_RESPONSE.md`) |
| `darioos_job_duration_seconds` crescendo, ou jobs acumulando em `QUEUED` | `GET /api/jobs` (admin) | Worker sobrecarregado ou travado |
| `darioos_agent_runs_total{status="timeout"}` subindo | `/metrics` | Provider de LLM lento/instável, ou `AGENT_RUN_TIMEOUT_SECONDS` baixo demais |
| Tamanho dos arquivos de log do Docker | `docker inspect --format='{{.LogPath}}' <container>` | Risco de disco cheio sem rotação configurada |

## Recomendação para v1.1 (não implementado neste release)

Adicionar um Prometheus + Grafana (ou equivalente gerenciado) ao `docker-compose.yml`, escaneando `backend:8000/metrics` pela rede interna `darioos`, com alertas mínimos para: `/health/ready` não-`ok` por mais de N minutos, `darioos_whatsapp_session_status` = 0, fila de jobs acumulando. Ver `ROADMAP_v1.1.md`.
