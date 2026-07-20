# Technical Debt — Dario OS

Itens reais, documentados durante as auditorias das sprints anteriores —
não uma lista aspiracional. Cada item aponta a fonte onde foi originalmente
registrado. Para o que é uma limitação de comportamento observável pelo
usuário (não debt de código), ver `KNOWN_LIMITATIONS.md`.

## Prioridade consolidada (fechamento do ciclo v1.4 / release Next.js 16, 2026-07-20)

Todo item aberto neste arquivo, reclassificado numa escala única. Itens
resolvidos (`~~riscado~~`) permanecem nas seções abaixo apenas como
histórico e não entram nesta lista.

**Alta prioridade**

1. Restore do Postgres nunca testado ponta a ponta contra dado real
   (seção "Backup / disaster recovery") — maior risco real: se o restore
   falhar no momento em que for de fato necessário, a lacuna só será
   descoberta tarde demais.
2. Sem circuit breaker/bulkhead em nenhum provider externo (Google, LLM,
   WhatsApp) — sistema depende fortemente de APIs de terceiros sem
   isolamento de falha.
3. CSP ausente no Caddyfile — bloqueado por fator externo (precisa de
   domínio real com HTTPS), mas é a única lacuna de segurança em aberto
   com HSTS/demais headers já presentes.
4. RBAC: `contacts`/`church`/`store` não são `user_scoped` — risco reduzido
   após o fechamento do registro público, mas a lacuna de granularidade
   permanece caso o modelo de confiança mude.
5. Validação funcional autenticada (login/logout com sessão real) pendente
   desde a migração do Next.js 16 — não é falha de código, mas é a
   validação mais próxima de virar ação concreta (só depende de
   credenciais válidas).

**Média prioridade**

6. Sem fluxo de "esqueci minha senha" — já causou intervenção manual direta
   no banco antes (ver `BOOTSTRAP_ADMIN.md`).
7. Sem tabela de auditoria de execução por agente/tool — contadores
   Prometheus são cumulativos, sem histórico consultável.
8. Semântica de cancelamento sob Postgres/asyncpg real não testada (o
   timeout global de job foi testado só contra SQLite).
9. Google OAuth nunca validado ponta a ponta contra credenciais reais —
   bloqueado por ação externa (setup no Google Cloud Console do Dário).
10. GitHub Issue #2 (`getConnectionState()` `TypeError`) — não bloqueia
    (fallback via `isConnected()` funciona), causa raiz já identificada.
11. `VERSION.json` do backend desatualizado (commit `2a9d643`, anterior a
    todo o ciclo v1.4) — higiene de release, não afeta funcionamento.

**Baixa prioridade**

12. QR Code do WhatsApp não exposto no Dashboard Administrativo.
13. "Última sincronização" só existe para o Google Drive (Gmail/Calendar/
    Contacts são *read-through*, sem dado de sync para expor).
14. Lighthouse nunca medido contra build de produção real.
15. Ambiente de sandbox isolado (CI ou local, fora da máquina de produção)
    nunca rodou o stack completo — bloqueado pela política de rede de
    cada sandbox.
16. `@next/bundle-analyzer` não validado contra Turbopack desde o upgrade
    do Next.js 16 (ferramenta opt-in, sem uso no caminho crítico).

## Achados do audit final de fechamento da Release 1.3.1 (2026-07-19)

Consolidado do audit de produção final antes de fechar a v1.3.1
(`RELEASE_1_3_1_POSTMORTEM.md`). Nenhum item classificado como P0 —
os dois achados P0 do audit anterior (registro público aberto, corrida de
execução duplicada de job) já foram corrigidos e fecham a v1.3.1.

**P1**

- **`docker-compose.yml` ainda tem `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dario}`**
  — mesmo padrão de fallback silencioso pra credencial fraca que acabou de
  ser corrigido no Grafana (`GF_SECURITY_ADMIN_PASSWORD:?...`), ainda não
  aplicado aqui. O valor real em `.env` já foi rotacionado pra um valor
  forte, mas o compose file em si não falha-fechado — se essa linha do
  `.env` for perdida, o Postgres sobe silenciosamente com a senha fraca
  `dario`. Correção: trocar pra `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}`,
  mesmo padrão já usado em `JWT_SECRET`/`WEBHOOK_SECRET`/`GF_SECURITY_ADMIN_PASSWORD`.
- **`chat_router` e `workflows_router` sem nenhuma cobertura de teste** —
  ambos montados e acessíveis em `main.py`, confirmado zero arquivo de teste
  para nenhum dos dois. `chat` é a funcionalidade central de IA conversacional,
  não um caminho secundário.
- **Caddy não roteia `/health/ready` corretamente** — ver
  `docs/issues/caddy-health-ready-routing.md` para problema/causa
  raiz/correção sugerida completos. Alvo: v1.4.

**P2**

- **RBAC**: `contacts`/`church`/`store` não são `user_scoped` — qualquer
  usuário autenticado (não só admin) lê/escreve todos os registros. Risco
  reduzido depois do fechamento do registro público (só admin cria contas
  agora), mas a lacuna de granularidade permanece caso o modelo de
  confiança mude.
- ~~`backend/business/models.py`~~ **Resolvido no v1.4** — removido
  (`models.py`, `schemas.py`, `__init__.py`, pacote inteiro). Decisão:
  nenhum plano existia em lugar nenhum pra construir essa feature CRM;
  conectá-la seria uma feature nova, fora do escopo de limpeza do v1.4.
  Confirmado zero referência fora do próprio pacote antes de remover.
  As 5 migrations (`MIG-001` a `MIG-005`) e as tabelas já existentes num
  banco real **não foram tocadas** — `alembic/env.py` só importa `models`
  (não `business`), então essas tabelas nunca fizeram parte do
  `Base.metadata` pra autogenerate; removê-las do banco de verdade, se
  algum dia for necessário, é uma migration nova e separada, não coberta
  aqui (sem risco adicional — já estavam desconectadas do ORM antes disso).
- ~~Sem timeout por chamada individual a provider LLM~~ **Resolvido no
  v1.4** — `llm_request_timeout_seconds`, aplicado a openai/anthropic/
  gemini (glm/ollama herdam via `OpenAIProvider`). O timeout global
  por job (fechado na v1.3.1, ver P0-2 no postmortem) bound o tempo
  total de execução, mas não localiza qual chamada específica ficou lenta.
- **Sem fluxo de "esqueci minha senha"** — só existe troca de senha
  autenticada (`POST /auth/change-password`); já causou intervenção manual
  direta no banco antes (ver `BOOTSTRAP_ADMIN.md`).

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
- ~~Sem métrica Prometheus dedicada para "job atingiu o timeout global de
  execução"~~ **Resolvido no v1.4** — `darioos_job_timeouts_total`
  (contador, label `name`), incrementado no mesmo ponto que já
  distinguia um timeout de qualquer outra falha (`jobs/worker.py`).
  Testes confirmam que incrementa só num timeout de verdade, nunca numa
  falha comum (`RuntimeError`).
- **GitHub Issue #2** (`getConnectionState()` lança `TypeError`) segue
  aberta — não bloqueia (fallback via `isConnected()` funciona), causa raiz
  já identificada (mudança de formato interno do WhatsApp Web).

## Segurança

- **CSP ausente no `Caddyfile`.** `Strict-Transport-Security` já está
  configurada (`docker/caddy/Caddyfile`), junto com
  `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`; falta apenas
  `Content-Security-Policy`. Continua não adicionada: o ambiente disponível
  até agora é sempre `DOMAIN=localhost` (HTTP local), nunca um domínio real
  com HTTPS e os domínios de asset reais de produção — testar uma CSP às
  cegas contra isso arrisca quebrar o frontend silenciosamente em produção.
  Ver `SECURITY_AUDIT.md`.
- ~~CVEs em dependências do frontend (`next@14.2.35`)~~ **Resolvido —
  upgrade para `next@16.2.10` concluído e em produção.** Branch isolada,
  PR #4, merge `1ea265b`, suíte de regressão completa (lint/typecheck/268
  testes/build) e deploy validado com smoke test. Ver
  `RELEASE_REPORT_NEXTJS16.md`.

## Confiabilidade de integrações externas

- ~~Sem retry/backoff configurável para os providers Google~~ **Resolvido
  no fechamento da v1.3.1** — `providers/google_http.py`, com respeito a
  `Retry-After` incluso. Ver `RELEASE_1_3_1_POSTMORTEM.md`.
- **Sem circuit breaker, nem bulkhead** em nenhum provider (Google, LLM,
  WhatsApp) — o respeito a `Retry-After` já existe para o Google (acima) e
  para o WhatsApp; circuit breaker/bulkhead seguem ausentes em todos.
- **Sem timeout por chamada individual a provider LLM** (ver seção do
  audit de fechamento no topo deste arquivo) — o timeout global por job
  cobre o caso mais grave (execução duplicada), mas não localiza qual
  chamada específica ficou lenta.
- **Semântica de cancelamento sob Postgres/asyncpg real não testada** — o
  timeout global de job (`jobs/worker.py`) usa `asyncio.wait_for`, testado
  contra SQLite; o comportamento de uma conexão asyncpg real sendo
  cancelada a meio de uma operação não foi verificado neste ciclo.

## Backup / disaster recovery

- ~~Volume do Qdrant sem backup automatizado~~ **Resolvido no fechamento da
  v1.3.1** — `scripts/backup.sh` agora cobre Postgres e Qdrant, com timer
  systemd (03:00) e watchdog de verificação (03:15). Ver `BACKUP.md`,
  `RELEASE_1_3_1_POSTMORTEM.md`.
- **Restore do Postgres nunca testado ponta a ponta contra dado real** —
  `scripts/restore.sh` automatiza os passos, mas rodá-lo de verdade
  apagaria o banco atual só para provar o script, risco desproporcional ao
  que estava sendo validado. O restore do Qdrant já foi testado ao vivo
  (ver `RESTORE.md`); o do Postgres segue como validação pendente.

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
- **GoalManager**: UI do dashboard (`/metas`) tem criação e aprovação, mas
  não tem edição/cancelamento, gerenciamento de dependências, nem
  atualização de progresso; recorrência não copia dependências para a
  próxima ocorrência; nenhuma automação transiciona um Goal para
  `IN_PROGRESS`/`COMPLETED` sozinha — sempre ação explícita via API/tool.
  Ver `docs/GOALS.md`.
- **Cognitive Pipeline**: o Planner não gera nem compara planos
  alternativos, nem detecta contradições entre etapas do mesmo plano;
  custo/tempo de um plano são medidos depois da execução, nunca estimados
  antes; nenhum mecanismo realimenta falhas passadas em decisões de
  planejamento futuras (`LearningEngine` só atualiza categorias do
  contato). Ver `docs/architecture.md` ("Cognitive Pipeline: mapeamento
  completo").

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
- **`docker compose up` completo já validado em produção** (atualiza este
  item, antes desatualizado): os 12 containers rodam de fato em produção
  (`~/projects/dario-os`), incluindo múltiplos ciclos de rebuild +
  redeploy do `backend`/`openwa` ao longo de sessões de engenharia,
  `/health/ready` confirmado `ok` para todas as dependências, e migrações
  Alembic aplicadas ao vivo contra o Postgres real. O que **continua**
  sem validação: um ambiente de sandbox isolado (CI ou local, fora da
  máquina de produção) nunca rodou o stack completo — bloqueado pela
  política de rede de cada sandbox (pull de imagem do Docker Hub). Ver
  `OPERATIONS_RUNBOOK.md`.
