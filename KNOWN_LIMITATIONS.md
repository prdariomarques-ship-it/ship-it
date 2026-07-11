# Known Limitations — Dario OS v1.2.0

Lista apenas limitações reais, verificadas no código/documentação nesta
consolidação — nada especulativo. Para o racional completo de cada item e
a fonte onde foi originalmente documentado, ver `TECHNICAL_DEBT.md`. Para
quando (se) cada uma será endereçada, ver `ROADMAP_v2.md`.

## Integrações externas

- **Retry Google ainda não implementado.** Gmail, Google Calendar, Google
  Contacts e Google Drive não têm retry/backoff configurável — uma falha
  transitória de rede ou um 5xx passageiro do Google propaga direto,
  sem nova tentativa automática.
- **Circuit Breaker inexistente.** Nenhuma integração externa (Google,
  LLM, WhatsApp) interrompe automaticamente o tráfego para um provider
  degradado — cada chamada tenta normalmente, mesmo que as últimas N
  tenham falhado.
- **`Retry-After` não é respeitado.** Uma resposta 429 de qualquer
  provider externo é tratada como erro genérico, sem usar o tempo de
  espera que o próprio serviço informa.
- **Um mailbox Gmail por usuário.** Múltiplas contas Gmail simultâneas
  para o mesmo usuário não são suportadas.
- **Google Calendar**: sem edição de série de eventos recorrentes; uma
  edição afeta só a instância retornada pela API.
- **Google Contacts**: busca lista até 1000 contatos por chamada, sem
  paginação além disso.
- **Google Drive**: só lê PDF, DOCX, TXT, Markdown e CSV — Google Docs/
  Sheets/Slides são recusados explicitamente, nunca convertidos.

## Dashboard Administrativo

- **QR Code do WhatsApp não implementado.** O painel mostra status de
  conexão real, mas não exibe o QR para parear um número — o
  re-pareamento continua sendo feito diretamente no gateway configurado.
- **Sem auditoria histórica por execução de agente/tool.** Os contadores
  de uso são cumulativos (resetam a cada restart do processo), não um
  registro consultável por execução individual.
- **Página Settings é somente leitura.**

## Observabilidade

- **Prometheus é opcional.** O endpoint `/metrics` existe e emite no
  formato Prometheus, mas nenhum scraper vem configurado por padrão — sem
  um Prometheus/Grafana apontado para ele, as métricas não são
  persistidas nem visualizadas em série temporal fora do que o Dashboard
  Administrativo já mostra como snapshot.
- **Tracing (OpenTelemetry) desligado por padrão.** Precisa ser ligado
  explicitamente (`OTEL_ENABLED=true`) e ter um coletor OTLP configurado
  para produzir traces distribuídos de verdade.

## Segurança

- **Sem CSP nem HSTS configurados no Caddy.**
- **Dependências do frontend com CVEs conhecidas** (`next@14.2.21`,
  `postcss`) — corrigir exige um upgrade major do Next.js.

## Backup

- **O volume do Qdrant não tem backup automatizado** — apenas o
  PostgreSQL é coberto por `scripts/backup.sh`.

## Ambiente de validação

- **Google OAuth nunca foi validado ponta a ponta contra o Google real**
  em nenhuma sessão de desenvolvimento até agora — apenas por código e
  testes com um provider falso.
- **`docker compose up` completo nunca foi executado** em nenhum
  ambiente de sandbox usado até agora — a estrutura do compose está
  validada, a subida real depende de um ambiente com acesso normal ao
  Docker Hub.
