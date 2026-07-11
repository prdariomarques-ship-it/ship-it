# Operations Runbook — Sprint 5

Entregável explícito da Sprint 5. Para procedimentos operacionais gerais
(deploy, rollback, rotação de segredos) já existentes e não alterados por
esta sprint, ver `RUNBOOK.md` e `OPERATIONS.md` — este documento cobre
especificamente o que a Sprint 5 adicionou ou validou.

## Novidades operacionais desta sprint

### 1. Correlation ID em todo incidente

Toda resposta HTTP agora carrega `X-Request-ID`. Ao investigar um erro
reportado por um usuário ou por um provider (WhatsApp, Google), peça o
`X-Request-ID` da resposta (visível no DevTools do navegador ou no header
de resposta de qualquer chamada de API) e filtre os logs estruturados por
esse valor — todo log emitido durante aquela requisição específica carrega
o mesmo `request_id`. Ver `OBSERVABILITY_GUIDE.md`.

### 2. Ligar tracing distribuído (opcional, desligado por padrão)

```bash
# No .env do backend:
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://<seu-coletor-otlp>:4318
```

Sem essas variáveis, o comportamento é idêntico ao de antes desta sprint
— zero overhead, zero dependência nova. Ver `OBSERVABILITY_GUIDE.md`.

### 3. Analisar o bundle do frontend sob demanda

```bash
cd frontend
ANALYZE=true npm run build
```

Abre um relatório visual do bundle. Não roda em builds normais.

### 4. Rodar a suíte E2E (Playwright) localmente

```bash
cd frontend
npm run e2e
```

Requer o backend rodando (`postgres`, `redis`, `uvicorn main:app`) e o
frontend em dev (`npm run dev`) apontando para ele. O `playwright.config.ts`
usa o Chromium pré-instalado do ambiente; em outro ambiente, remova o
`executablePath` fixo ou rode `npx playwright install chromium` antes.
Um usuário admin de teste precisa existir (o primeiro usuário registrado
em `/auth/register` vira admin automaticamente) — variáveis
`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` sobrescrevem as credenciais padrão
usadas pelo `e2e/global-setup.ts`.

## Docker Compose — validado nesta sessão, com uma limitação de ambiente

`docker compose config` (validação estrutural do compose file — volumes,
networks, healthchecks, restart policies) roda limpo neste sandbox. Um
`docker compose up` completo **não pôde ser executado neste ambiente
específico**: a política de rede do sandbox bloqueia o pull de imagens do
Docker Hub (`production.cloudfront.docker.com`), o mesmo bloqueio já
documentado na Sprint 4. Isso é uma restrição do ambiente de
desenvolvimento usado nesta sessão, não do `docker-compose.yml` em si —
`docker compose up -d --build` deve ser validado em um ambiente com acesso
normal ao Docker Hub (CI, ou a máquina de produção) antes do próximo
deploy real.

Confirmado por revisão estrutural (Fase 6, sprint anterior + reconfirmado
nesta): `restart: unless-stopped` em todos os serviços, volumes nomeados
para todo serviço com estado (`postgres`, `redis`, `qdrant`), rede
compartilhada `darioos`, `healthcheck:` explícito no nível do compose
apenas em `postgres` (o `backend` tem seu próprio `HEALTHCHECK` no
Dockerfile).

## Qdrant — sem servidor real neste sandbox, validado via engine embutido

Não há um servidor Qdrant acessível neste ambiente de sandbox. A
validação desta sprint (Fase 8) usou o modo embutido/in-process real do
`qdrant-client` (`AsyncQdrantClient(":memory:")`) — o mesmo código-cliente
que a aplicação usa contra um Qdrant remoto, só que sem processo de
servidor separado. Isso não substitui testar contra o Qdrant real de
produção antes de um deploy, mas é uma validação genuína do código de
busca vetorial (não um mock da lógica) — foi assim que o bug do
`AsyncQdrantClient.search()` removido (ver `PRODUCTION_READINESS.md`) foi
encontrado.

## Google OAuth — não testável ponta a ponta neste sandbox

Sem credenciais OAuth reais do Google neste ambiente. Antes do próximo
deploy, validar manualmente em staging: conectar uma conta Google real
para Gmail, Calendar, Contacts e Drive, confirmar refresh de token
automático e o fluxo de reconexão após um token revogado. Ver
`GOOGLE_PLATFORM_AUDIT.md` para o que já foi validado por código.
