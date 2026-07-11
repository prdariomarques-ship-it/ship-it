# Observability Guide — Sprint 5

## Correlation ID / Request ID

`backend/observability/request_context.py` — `RequestIDMiddleware`
(Starlette `BaseHTTPMiddleware`) gera um UUID por requisição (ou reusa o
`X-Request-ID` enviado pelo cliente), expõe via `ContextVar` acessível em
qualquer ponto do código com `get_request_id()`, e devolve o mesmo valor
no header de resposta `X-Request-ID`. Registrado como o middleware mais
externo em `backend/main.py`, para cobrir toda a stack (inclusive
respostas 429 do rate limiter e erros não tratados).

```
curl -i http://localhost:8000/health
# X-Request-ID: <uuid gerado ou ecoado do cliente>
```

## Structured logging (JSON)

`backend/utils/logging.py` — `JsonFormatter` (pré-existente) agora inclui
`request_id` em toda entrada de log quando a requisição está em contexto,
via `RequestIDFilter` (novo) aplicado tanto ao formatter JSON quanto ao
texto legível (`TEXT_FORMAT`, placeholder `[%(request_id)s]`, `-` quando
fora de uma requisição). Configurável via `configure_logging(json_output=True)`.

## Tracing (OpenTelemetry)

`backend/observability/tracing.py` — `setup_tracing(app, enabled, otlp_endpoint, service_name)`.

- **Desligado por padrão** (`OTEL_ENABLED=false`) — zero overhead, zero
  dependência de infraestrutura externa até ser explicitamente ligado.
- Quando ligado sem `OTEL_EXPORTER_OTLP_ENDPOINT`: exporta para
  `ConsoleSpanExporter` (útil em dev/debug local).
- Quando ligado com endpoint: exporta via OTLP HTTP para o backend de
  tracing configurado (Jaeger, Tempo, etc.).
- Auto-instrumenta FastAPI, SQLAlchemy (queries) e httpx (chamadas a
  provedores externos) — sem precisar instrumentar cada rota manualmente.
- Idempotente: uma segunda chamada a `setup_tracing` (ex.: `create_app()`
  chamado de novo em testes) não duplica instrumentação nem levanta erro.
- Import de `opentelemetry.*` é `try/except` — se os pacotes não estiverem
  instalados, `setup_tracing` vira um no-op seguro em vez de derrubar a
  aplicação.

Novas dependências (opcionais, só carregadas se `OTEL_ENABLED=true`):
`opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx}`,
`opentelemetry-exporter-otlp-proto-http` — `backend/requirements.txt`.

## Métricas (Prometheus) — já existentes, confirmadas nesta auditoria

`backend/observability/metrics.py` (pré-existente, Fase 4.2) já cobre os
quatro níveis pedidos pela Fase 2 desta sprint — nenhuma métrica nova foi
necessária:

- **Por endpoint**: `darioos_http_requests_total{method,path,status}`
- **Por Agent**: `darioos_agent_runs_total{agent,provider,status}`,
  `darioos_agent_run_duration_seconds{agent}`
- **Por Tool**: `darioos_agent_tool_calls_total{tool,status}`
- **Por Provider**: `darioos_whatsapp_provider_requests_total{provider,status}`,
  `darioos_agent_tokens_total{provider,kind}`

Exposto em `/metrics` (formato Prometheus text, confirmado via smoke test
nesta sessão).

## Health checks

`backend/observability/health.py` (pré-existente, confirmado nesta
auditoria, sem alteração):

- `/health` — liveness simples (`status: ok`).
- `/health/live` — idêntico, para uso em probes Kubernetes/Docker.
- `/health/ready` — readiness real: banco de dados é obrigatório
  (indisponibilidade = `503`); Redis, Qdrant e WhatsApp degradam
  graciosamente (aparecem como `error: ...` no corpo, mas não derrubam o
  probe) — comportamento correto para um readiness probe que não deve
  ficar "flapping" por causa de uma integração opcional fora do ar.

```json
{"status":"degraded","checks":{"database":"ok","redis":"ok","qdrant":"error: ...","whatsapp":"error: ..."}}
```

(exemplo real, capturado neste sandbox sem servidor Qdrant/WhatsApp disponível)

## Como usar isto em produção

1. Ligar `OTEL_ENABLED=true` e apontar `OTEL_EXPORTER_OTLP_ENDPOINT` para o
   coletor OTLP do ambiente.
2. Ligar `configure_logging(json_output=True)` (ou equivalente via env) para
   que o `request_id` apareça em todo log agregado, permitindo correlacionar
   uma requisição específica através de logs, métricas e traces pelo mesmo
   ID (o `X-Request-ID` retornado ao cliente é o mesmo em todos os três).
3. Apontar o scraper Prometheus para `/metrics` e os probes de
   liveness/readiness do orquestrador (Kubernetes, Docker Swarm, etc.) para
   `/health/live` e `/health/ready` respectivamente.
