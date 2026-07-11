# Technical Debt — Dario OS

Itens reais, documentados durante as auditorias das sprints anteriores —
não uma lista aspiracional. Cada item aponta a fonte onde foi originalmente
registrado. Para o que é uma limitação de comportamento observável pelo
usuário (não debt de código), ver `KNOWN_LIMITATIONS.md`.

## Observabilidade / auditoria

- **Sem tabela de auditoria de execução por agente/tool.** Os contadores
  Prometheus (`darioos_agent_runs_total`, `darioos_agent_tool_calls_total`)
  são cumulativos e resetam a cada restart do processo — não existe um
  registro histórico consultável de "agente X rodou a tool Y às HH:MM,
  levou Zs, gastou N tokens, para o usuário W". Decisão explícita de
  escopo na Sprint 4 (instrumentar isso exigiria tocar o Orchestrator,
  fora do escopo autorizado). Ver `docs/DASHBOARD.md`.
- **QR Code do WhatsApp não exposto no Dashboard Administrativo.** Nenhum
  dos 4 providers de WhatsApp tem um método para obter o QR hoje —
  adicionar isso exigiria alterar `providers/whatsapp/`. Ver
  `docs/DASHBOARD.md`.
- **"Última sincronização" só existe para o Google Drive.** Gmail/Calendar/
  Contacts são domínios *read-through* (consultam a API a cada chamada,
  não indexam) — não há dado real de "último sync" para esses três. Ver
  `docs/DASHBOARD.md`.

## Segurança

- **CSP e HSTS ausentes no `Caddyfile`.** Nenhuma `Content-Security-Policy`
  nem `Strict-Transport-Security` configurada. Adicionar uma CSP sem poder
  testá-la contra HTTPS real e os domínios de asset reais de produção foi
  avaliado como arriscado demais para uma sprint de hardening sem esse
  ambiente disponível. Ver `SECURITY_AUDIT.md`.
- **CVEs em dependências do frontend** (`next@14.2.21`, `postcss`): a
  correção exige um upgrade major (breaking) do Next.js, fora do escopo de
  "alteração mínima e justificada" de qualquer sprint que não seja
  dedicada a esse upgrade. Ver `SECURITY_AUDIT.md`.

## Confiabilidade de integrações externas

- **Sem retry/backoff configurável para os providers Google** (Gmail,
  Calendar, Contacts, Drive) — diferente do WhatsApp, que já tem
  (`WHATSAPP_REQUEST_MAX_ATTEMPTS`/`WHATSAPP_REQUEST_BACKOFF_SECONDS`).
  Planejado para v1.3.0 — ver `ROADMAP_v2.md`.
- **Sem circuit breaker, sem respeito a `Retry-After`, sem bulkhead** em
  nenhum provider (Google, LLM, WhatsApp). Planejado para v1.3.0.

## Backup / disaster recovery

- **Volume do Qdrant sem backup automatizado.** `scripts/backup.sh` cobre
  apenas o PostgreSQL. O texto original de cada memória vive em
  `Embedding.content` (Postgres, coberto por backup), então uma
  reconstrução manual do índice Qdrant é teoricamente possível, mas não
  há script pronto para isso. Ver `DISASTER_RECOVERY.md`.

## Limitações de domínio, aceitas por decisão de escopo (não bugs)

- **Google Calendar**: sem edição de série de eventos recorrentes; um
  único provider de calendário; `search_google_calendar_events` busca uma
  agenda por chamada. Ver `docs/CALENDAR.md`.
- **Google Contacts**: `search_google_contacts` lista até 1000 contatos
  por chamada, sem paginação completa da People API (adequado a uma
  agenda de porte pessoal). Ver `docs/CONTACTS.md`.
- **Google Drive**: só lê PDF/DOCX/TXT/Markdown/CSV (Google Docs/Sheets/
  Slides recusados explicitamente); indexação em lote limitada a 20-50
  arquivos por chamada; cada arquivo indexado até ~30 pedaços (~45 mil
  caracteres) — o restante de um documento maior não é indexado. Ver
  `docs/DRIVE.md`.
- **Gmail**: somente leitura; um mailbox conectado por usuário (sem
  múltiplas contas Gmail simultâneas); corpo de mensagem cortado em 3000
  caracteres antes de ir para o modelo. Ver `docs/EMAIL.md`.
- **Dashboard Administrativo**: página Settings é somente leitura por
  decisão de escopo da Sprint 4. Ver `docs/DASHBOARD.md`.

## Performance

- **Lighthouse não medido em nenhuma sprint até agora.** As métricas de
  carregamento client-side existentes (Playwright, dev server) servem
  como proxy parcial, mas não substituem um Lighthouse CI real contra uma
  build de produção servida via HTTP. Ver `PERFORMANCE_REPORT.md`.

## Testes / validação de ambiente

- **Google OAuth nunca validado ponta a ponta contra o Google real** em
  nenhuma sessão de sandbox até agora — só validado por código/testes com
  provider falso. Ver `docs/EMAIL.md` ("O que ainda depende do fundador"),
  `SPRINT5_REPORT.md`.
- **`docker compose up` completo nunca executado** em nenhum ambiente de
  sandbox usado até agora — bloqueado pela política de rede de cada
  sandbox (pull de imagem do Docker Hub). Estrutura do compose validada
  (`docker compose config`), subida real nunca confirmada fora de
  produção. Ver `OPERATIONS_RUNBOOK.md`.
