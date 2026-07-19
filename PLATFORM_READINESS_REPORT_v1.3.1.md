# Avaliação Técnica de Maturidade — Dario OS v1.3.1

Prepared 2026-07-18, ao final da fase de Homologação Funcional (UAT). Análise crítica baseada exclusivamente em evidência observada nesta e nas sessões de engenharia anteriores documentadas no repositório (`HOMOLOGATION_REPORT.md`, `HOMOLOGATION_REPORT_v1.3.1.md`, `RELEASE_SUMMARY_v1.3.1.md`, `KNOWN_LIMITATIONS.md`, `TECHNICAL_DEBT.md`, `BACKUP.md`/`RESTORE.md`, 875 testes de backend + 241 de frontend rodados ao vivo) — não especulação. Nenhuma alteração de código foi feita para produzir este relatório.

**Nota de transparência sobre o estado do repositório neste exato momento**: as 3 correções P3 da rodada anterior (`AdminHeader.tsx`, `ExecutionTimeline.tsx`, `LogViewer.tsx` + teste) estão implementadas, testadas e **já rodando no ambiente ao vivo** (rebuild + redeploy feitos), mas **ainda não commitadas** — `git status` mostra 4 arquivos modificados não commitados no momento desta análise. Isso não muda nenhuma classificação abaixo (a avaliação é sobre o estado funcional real, que já inclui essas correções), mas é um fato observável que merece registro.

**Escopo desta avaliação**: apenas o que está construído e definido para a v1.x (`VERSION_HISTORY.md`, `ROADMAP_v2.md`). Copilot Finance, Pain Intelligence Engine, Open Finance, novos agentes e marketplace — todos fora de escopo, não avaliados.

---

## Avaliação por módulo

### Autenticação
- **Estado atual**: JWT (access + refresh), rate limiting configurável, guarda de produção que exige `JWT_SECRET`/`WEBHOOK_SECRET` fortes (`_validate_production_settings`, testado). Primeiro usuário registrado vira admin automaticamente; não existe fluxo de registro self-service além disso.
- **Estabilidade**: alta para o caminho de login em si — testado ao vivo nesta sessão (formulário real, não API direta), zero erro.
- **Cobertura de testes**: `test_auth.py`, 7 testes — fina para um módulo de segurança crítica.
- **Homologação funcional**: sim, ponta a ponta via UI, nesta sessão.
- **UX**: mínima mas funcional (e-mail/senha, sem validação client-side além do `type="email"` nativo).
- **Pendências restantes**: **não existe fluxo de reset/troca de senha** — confirmado na prática, duas vezes nesta sessão de trabalho a senha do admin precisou ser resetada via escrita direta no banco (`BOOTSTRAP_ADMIN.md` documenta o mesmo incidente antes). Sem MFA. Sem revogação de sessão/refresh token pela UI.
- **Prioridade**: **P1** (reset de senha — gap operacional real, não teórico, já causou retrabalho manual duas vezes) / P3 (MFA, fora do escopo v1.x provavelmente).
- **Classificação: 🟡 Beta**

### Dashboard (Início + AI Operator Center)
- **Estado atual**: `/` (resumo simples) e `/admin` (AI Operator, sintetiza metas/tarefas/agenda/WhatsApp/jobs). Ambos com dado real, testados.
- **Estabilidade**: alta; zero erro em qualquer visita.
- **Cobertura de testes**: `test_admin.py` (55 testes) cobre a API por trás do AI Operator.
- **Homologação funcional**: sim, desktop e mobile.
- **UX**: boa no AI Operator (cards, estados vazios bem escritos); Início é propositalmente simples.
- **Pendências restantes**: AI Operator foi a tela mais lenta medida em toda a homologação (5.2s até `networkidle`, vs. ~1.3s do resto) — agrega muita coisa numa carga só.
- **Prioridade**: P2 (performance de carregamento).
- **Classificação: 🟡 Beta**

### Conversas
- **Estado atual**: histórico de mensagens (leitura), sem composer — enviar é só via agente/API, não há "responder" na UI.
- **Estabilidade**: alta.
- **Cobertura de testes**: coberto indiretamente por `test_webhook.py`/`test_whatsapp_pipeline.py`.
- **Homologação funcional**: sim; contato agora mostra nome/telefone (corrigido nesta sessão), tabela responsiva no mobile (corrigido nesta sessão).
- **UX**: melhorada nesta sessão; ainda sem paginação na UI (backend já suporta `limit`/`offset`, frontend não expõe).
- **Pendências restantes**: sem paginação visível; sem composer.
- **Prioridade**: P2 (paginação, relevante assim que o volume de mensagens crescer) / P3 (composer, decisão de produto).
- **Classificação: 🟡 Beta**

### WhatsApp
- **Estado atual**: provider OpenWA, sessão autenticada e validada ponta a ponta nesta sessão (QR real escaneado, mensagem real enviada e confirmada recebida).
- **Estabilidade**: dois bugs reais de confiabilidade encontrados e corrigidos **nesta sessão de trabalho**: `health_check` reportava saudável mesmo com erro (`fa7c8ff`), e `send_text`/`send_image`/etc. reportavam sucesso mesmo quando o OpenWA rejeitava o envio (`9816877`, GitHub Issue #3). Um terceiro segue **aberto**: `getConnectionState()` lança `TypeError` (GitHub Issue #2, causa raiz identificada — mudança de formato interno do WhatsApp Web — mas não corrigida).
- **Cobertura de testes**: forte — `test_providers.py` (48 testes) cobre exatamente os cenários de sucesso/falha do easy-api, incluindo os dois bugs corrigidos.
- **Homologação funcional**: sim, validado com sessão e número reais.
- **UX**: QR não é exposto no dashboard (decisão de escopo documentada, não bug).
- **Pendências restantes**: Issue #2 aberta; bloqueio de licença do OpenWA para números não-contato (limitação externa, não bug).
- **Prioridade**: P2 (Issue #2 — não bloqueia o uso, `isConnected` cobre o fallback).
- **Classificação: 🟡 Beta**

### Memory (Qdrant)
- **Estado atual**: coleção `darioos_memory`, 88 pontos reais no momento da homologação. Estatística `vectors_count` corrigida nesta sessão (lia `indexed_vectors_count`, sempre 0 abaixo do threshold de indexação — parecia contraditório, não era um bug de dado).
- **Estabilidade**: alta para o que existe.
- **Cobertura de testes**: `test_admin.py` cobre o endpoint; regressão específica adicionada nesta sessão.
- **Homologação funcional**: sim.
- **UX**: painel claro após a correção.
- **Pendências restantes**: **volume do Qdrant sem backup automatizado** (confirmado em `BACKUP.md` — só Postgres é coberto).
- **Prioridade**: P1 (backup de dados de produção incompleto).
- **Classificação: 🟡 Beta**

### Analytics
- **Estado atual**: 7 cards de contagem simples (contatos, mensagens, tarefas, etc.) — mesma fonte de dado que a tela Início.
- **Estabilidade**: alta (é só leitura de contadores).
- **Cobertura de testes**: indireta, via o endpoint `/dashboard/summary`.
- **Homologação funcional**: sim; labels corrigidos para português nesta sessão (antes vinham em inglês).
- **UX**: funcional, mas não é "analytics" no sentido usual — sem série temporal, sem tendência, sem segmentação.
- **Pendências restantes**: o módulo em si é raso frente ao nome — não há gráfico, filtro por período, ou comparação.
- **Prioridade**: P2 (expectativa vs. entrega do nome do módulo).
- **Classificação: 🔴 Incompleto**

### Agenda
- **Estado atual**: lista de eventos, sem botão de criar.
- **Estabilidade**: não testável de verdade — só validado com estado vazio (nenhum evento real no ambiente).
- **Cobertura de testes**: nenhuma específica encontrada para esta tela.
- **Homologação funcional**: parcial — carregamento e navegação sim; fluxo de uso real (criar/ver/editar um evento), não.
- **UX**: básica, sem ação de criação, sobreposição conceitual não esclarecida com Calendário.
- **Pendências restantes**: sem criação pela UI; redundância com Calendário sem decisão de produto.
- **Prioridade**: P1 (sem criação, o módulo não completa um fluxo de uso real) / P2 (redundância conceitual).
- **Classificação: 🔴 Incompleto**

### Calendário
- **Estado atual**: mesma situação da Agenda — lista de eventos "organizados por dia", sem criação.
- **Estabilidade/Testes/Homologação**: idênticos à Agenda.
- **UX**: idem.
- **Pendências restantes**: idem Agenda — e a pergunta em aberto é se este módulo deveria sequer existir separado da Agenda.
- **Prioridade**: P1 / P2 (mesmos motivos da Agenda).
- **Classificação: 🔴 Incompleto**

### Tarefas
- **Estado atual**: lista de tarefas; sem criação pela UI própria, mas o **Action Center** já permite concluir/adiar tarefas existentes (criadas via agente/API).
- **Estabilidade**: alta para o que existe.
- **Cobertura de testes**: coberta indiretamente via Action Center/Daily Briefing.
- **Homologação funcional**: sim, testado; estado vazio no ambiente atual.
- **UX**: inconsistente com Metas, que tem "Nova meta" e este não tem equivalente.
- **Pendências restantes**: sem criação pela UI de Tarefas (só via agente/API/Action Center).
- **Prioridade**: P1 (gerenciar tarefas é um fluxo central do produto e a criação manual não está completa).
- **Classificação: 🟡 Beta** (a diferença de Agenda/Calendário é que Tarefas já tem uma superfície de interação real via Action Center, mesmo sem criação direta)

### Loja
- **Estado atual**: lista de clientes; criação só via tool de agente (`add_store_customer`), sem botão na UI.
- **Estabilidade**: alta para o que existe (vazio no ambiente).
- **Cobertura de testes**: cobre a tool do agente, não a tela.
- **Homologação funcional**: parcial (carregamento sim, fluxo de uso real não).
- **UX**: sem ação de criação.
- **Pendências restantes**: sem criação pela UI.
- **Prioridade**: P1.
- **Classificação: 🔴 Incompleto**

### Igreja
- **Estado atual**: mesma situação da Loja — `add_prayer_request`/`list_church_members` só via agente.
- **Estabilidade/Testes/Homologação/UX**: idênticos à Loja.
- **Pendências restantes**: idem Loja.
- **Prioridade**: P1.
- **Classificação: 🔴 Incompleto**

### Configurações
- **Estado atual**: duas telas — `/configuracoes` (sessão + info da API + links) e `/admin/settings` (providers configurados, somente leitura por decisão documentada de escopo, não bug).
- **Estabilidade**: alta.
- **Cobertura de testes**: `test_admin.py` cobre `/admin/settings`.
- **Homologação funcional**: sim; ambas corrigidas/esclarecidas nesta sessão (a primeira prometia "preferências e conexões" que não existiam; agora descreve o que realmente tem e linka para onde as conexões são geridas de fato).
- **UX**: honesta após a correção — nenhuma das duas finge ter uma capacidade que não tem.
- **Pendências restantes**: nenhuma preferência é de fato editável pela UI em lugar nenhum do produto — é uma decisão de escopo explícita (Sprint 4), não uma lacuna escondida.
- **Prioridade**: P3 (se e quando editar configuração pela UI virar prioridade de produto).
- **Classificação: 🟡 Beta**

### Administração
- **Estado atual**: a área mais madura do produto — AI Operator, Timeline, Action Center, Agents, Tools, Users, Metrics, System, Google Workspace, WhatsApp, Logs, Settings, Executions, Memory. 17 sub-rotas testadas nesta sessão, zero erro.
- **Estabilidade**: alta; drawer mobile testado de verdade (clique real, não só CSS) e funciona.
- **Cobertura de testes**: forte (`test_admin.py`, 55 testes, é o maior arquivo de teste do backend).
- **Homologação funcional**: sim, completa, incluindo mobile.
- **UX**: a mais polida do produto — cards com ícone, estados vazios bem escritos, contraste com o grupo "dashboard" mais antigo.
- **Pendências restantes**: `Commit`/`Branch`/`Tag` em System seguem "não disponível" (não corrigido — decisão consciente de não tocar infraestrutura de build sem confirmação); sem tabela de auditoria por execução de agente/tool (decisão de escopo documentada, `TECHNICAL_DEBT.md`).
- **Prioridade**: P2 (build info) / P3 (auditoria por execução, fora do escopo autorizado até agora).
- **Classificação: 🟡 Beta**

### Logs
- **Estado atual**: consolidado nesta sessão — a página antiga (`/logs`, sem filtro, inundada por ruído) agora redireciona para `/admin/logs` (filtro por nível, busca, exportar).
- **Estabilidade**: alta.
- **Cobertura de testes**: coberta via `test_admin.py`.
- **Homologação funcional**: sim; mensagem que cortava sem quebra no mobile corrigida nesta sessão.
- **UX**: boa após as duas rodadas de correção.
- **Pendências restantes**: sem paginação além do limite fixo carregado; sem retenção/arquivamento de longo prazo verificado.
- **Prioridade**: P2.
- **Classificação: 🟡 Beta**

### Execuções
- **Estado atual**: construída a partir de jobs em background + logs de agente — não existe tabela dedicada de auditoria de execução (documentado, decisão de escopo).
- **Estabilidade**: alta; o rótulo "queued" enganoso do `observation.tick` foi investigado (confirmado não ser bug — é o ciclo de vida normal do job) e a exibição corrigida nesta sessão.
- **Cobertura de testes**: `ExecutionTimeline.test.tsx`, incluindo o caso do rótulo corrigido.
- **Homologação funcional**: sim.
- **UX**: clara após a correção do rótulo.
- **Pendências restantes**: falta de tabela de auditoria dedicada (estrutural, não cosmético).
- **Prioridade**: P2.
- **Classificação: 🟡 Beta**

### Observabilidade
- **Estado atual**: Prometheus + Grafana + Jaeger + Alertmanager **rodando e saudáveis** neste ambiente (confirmado via `docker compose ps` repetidas vezes nesta sessão) — mais maduro do que `KNOWN_LIMITATIONS.md` sugere (o documento, datado da v1.2.0, descreve Prometheus como "opcional"/não configurado; neste ambiente já está).
- **Estabilidade**: containers saudáveis, sem verificação profunda do conteúdo dos dashboards do Grafana ou de regras de alerta nesta sessão.
- **Cobertura de testes**: métricas Prometheus expostas e testadas (`darioos_http_requests_total` visto ao vivo em `/admin/metrics`).
- **Homologação funcional**: parcial — confirmei que a infraestrutura sobe e responde; não confirmei dashboards/alertas configurados de fato.
- **UX**: `/admin/metrics` mostra "Coletando dados..." numa visita única (precisa de duas leituras consecutivas para calcular taxa) — comportamento esperado, não bug, mas pode confundir.
- **Pendências restantes**: OpenTelemetry/tracing distribuído desligado por padrão (`OTEL_ENABLED`, não verificado nesta sessão); Lighthouse/performance nunca medido (`TECHNICAL_DEBT.md`).
- **Prioridade**: P2 (confirmar conteúdo real do Grafana) / P3 (tracing, Lighthouse).
- **Classificação: 🟡 Beta**

### API
- **Estado atual**: FastAPI, OpenAPI em `/docs`, endpoint de versão consistente (corrigido nesta sessão), 875 testes passando.
- **Estabilidade**: dois bugs reais de confiabilidade corrigidos nesta sessão (ver WhatsApp); um terceiro segue aberto (Issue #2). Flakiness intermitente pré-existente em `test_goals.py` sob suíte completa (observado 3 vezes, confirmado não relacionado a nada alterado, nunca investigado a fundo).
- **Cobertura de testes**: forte e ampla (875 testes, múltiplos providers, admin, auth, webhooks, jobs).
- **Homologação funcional**: sim, extensivamente, incluindo ao vivo contra o gateway OpenWA real.
- **UX**: N/A (API).
- **Pendências restantes**: sem retry/circuit breaker para os providers Google (planejado para v1.3.0, nunca implementado — `ROADMAP_v2.md`/`TECHNICAL_DEBT.md`); `Retry-After` do HTTP 429 não respeitado por nenhum provider externo; CSP ausente no Caddy (decisão consciente de não testar às cegas contra `localhost`).
- **Prioridade**: P1 (retry/circuit breaker Google — planejado e não entregue) / P2 (CSP, Issue #2).
- **Classificação: 🟡 Beta**

### Banco de Dados
- **Estado atual**: PostgreSQL 16, Alembic aplicado ao vivo múltiplas vezes nesta e em sessões anteriores, pool monitorado (`/admin/system`).
- **Estabilidade**: alta em operação normal.
- **Cobertura de testes**: ampla, indiretamente (quase todo teste de backend toca o banco via fixtures).
- **Homologação funcional**: sim.
- **UX**: N/A.
- **Pendências restantes**: **backup cobre só o Postgres** (não Qdrant, Redis, ou dados de sessão do OpenWA); **sem script de restore automatizado** (`scripts/restore.sh` não existe, `RESTORE.md` é procedimento manual); agendamento do backup **não está registrado em nenhum cron** — depende de configuração manual do operador que não foi confirmada.
- **Prioridade**: **P0** — isto é o item mais sério de todo o relatório: não há evidência de que um backup automático esteja de fato rodando agora, nem de que um restore completo (além do Postgres) seja possível hoje.
- **Classificação: 🟡 Beta**

### Frontend
- **Estado atual**: Next.js 14.2.35, TypeScript, React Query. **Dois sistemas de design coexistindo** sem convergência — o grupo "dashboard" (mais antigo, CSS simples) e `/admin/*` (mais novo, Tailwind + shadcn-style) — confirmado extensivamente na homologação (estados vazios diferentes, comportamento de scroll mobile que precisou ser corrigido nos dois separadamente).
- **Estabilidade**: alta; 241 testes passando.
- **Cobertura de testes**: 241 testes, 32 arquivos, boa cobertura de componente.
- **Homologação funcional**: sim, as 17 rotas pedidas, desktop e mobile.
- **UX**: 3 rodadas de correção nesta fase (labels, navegação, tabelas, cabeçalho mobile) — o produto reagiu bem a cada uma, mas a causa raiz (dois sistemas de design) não foi endereçada, só sintomas.
- **Pendências restantes**: unificação dos dois sistemas de design (grande, não tentada); CVEs conhecidas em dependências (`next@14.2.35`, correção exige upgrade major pra `16.x`); Lighthouse nunca rodado.
- **Prioridade**: P2 (unificação de design system, dívida técnica real mas não bloqueia uso) / P2 (CVEs, ver `SECURITY_AUDIT.md` para o que já foi avaliado).
- **Classificação: 🟡 Beta**

### Infraestrutura
- **Estado atual**: Docker Compose, 11-12 serviços, Caddy com HTTPS automático (`DOMAIN=localhost` neste ambiente), HSTS configurado.
- **Estabilidade**: alta em operação — múltiplos ciclos de rebuild+redeploy nesta sessão sem incidente.
- **Cobertura de testes**: N/A direto, mas validado operacionalmente de forma repetida.
- **Homologação funcional**: `docker compose up` completo já validado em produção (múltiplas vezes, incluindo nesta sessão); **nunca validado num ambiente de sandbox isolado** (CI ou local fora da máquina de produção) — todo sandbox tentado até agora bloqueia pull de imagem do Docker Hub.
- **UX**: N/A.
- **Pendências restantes**: healthcheck do Docker configurado em só 5 dos 11 serviços (`alertmanager`, `backend`, `grafana`, `postgres`, `prometheus` — `caddy`, `frontend`, `jaeger`, `n8n`, `openwa`, `qdrant`, `redis` não têm); CSP ausente; backup incompleto (ver Banco de Dados).
- **Prioridade**: P1 (backup/DR, compartilhado com Banco de Dados) / P2 (healthchecks faltando, dificulta detectar degradação automaticamente).
- **Classificação: 🟡 Beta**

---

## Visão executiva

### 1. O que já pode ser considerado pronto para produção
- **Autenticação** (o caminho de login em si, não o ciclo de vida completo da conta).
- **API** como plataforma de engenharia (testes, padrões, versionamento) — não como conjunto de integrações 100% confiáveis.
- **Administração** como ferramenta de operação/monitoramento do próprio sistema.
- **WhatsApp** como canal de mensagens — validado ponta a ponta com sessão e número reais.
- **Infraestrutura de observabilidade** (Prometheus/Grafana/Jaeger/Alertmanager rodando e saudáveis).

### 2. O que ainda impediria colocar a plataforma em produção hoje
- **Backup/disaster recovery incompleto** (P0) — só Postgres é coberto, sem restore automatizado, sem confirmação de que o cron está de fato registrado. Perder o volume do Qdrant ou os dados de sessão do WhatsApp hoje seria irrecuperável por script.
- **Sem fluxo de reset de senha** — já causou intervenção manual duas vezes nesta única fase de trabalho; em produção real, sem acesso direto ao banco, isso trava o próprio operador.
- **5 módulos sem criação de dado pela UI** (Agenda, Calendário, Loja, Igreja, e parcialmente Tarefas) — o produto promete gerenciar essas áreas mas não entrega o fluxo completo de "adicionar algo novo" na interface.
- **GitHub Issue #2 aberta** (`getConnectionState`) — não bloqueia (há fallback), mas é um sintoma de que o provider WhatsApp não foi auditado por completo.
- **Google OAuth nunca validado contra o Google real** — só por código e teste com provider falso; é a maior integração externa do produto e nunca rodou de ponta a ponta.

### 3. Pendências que são apenas melhorias de UX
- Dois sistemas de design coexistindo (não quebra nada, mas é inconsistente).
- Analytics raso frente ao nome.
- Agenda vs. Calendário — sobreposição conceitual, decisão de produto pendente.
- `/admin/metrics` precisando de duas leituras pra mostrar taxa.
- Build info (Commit/Branch/Tag) indisponível em System.

### 4. Pendências que representam dívida técnica
- Falta de retry/circuit breaker para os 4 providers Google (planejado para v1.3.0 no `ROADMAP_v2.md`, nunca entregue — o v1.3.0 que de fato saiu mudou de escopo para o AI Operator Center em vez disso).
- Nenhum provider respeita `Retry-After` em 429.
- Sem tabela de auditoria por execução de agente/tool.
- CVEs conhecidas em dependências do frontend, só corrigíveis com upgrade major.
- CSP ausente (decisão consciente de não testar às cegas contra `localhost`, mas ainda pendente).
- Flakiness intermitente em `test_goals.py` sob suíte completa, nunca investigada a fundo.
- Dois sistemas de design no frontend nunca convergidos.

### 5. Módulos que ainda precisam de homologação funcional completa
- **Agenda, Calendário, Loja, Igreja** — só testados com estado vazio; nenhum nunca foi validado com dado real (criar → ver → editar → excluir).
- **Google Workspace** — testado por código/mock, nunca contra uma conta Google real.
- **Backup/Restore** — os procedimentos existem em documento, nenhum foi executado de ponta a ponta nesta ou em sessões anteriores para confirmar que funcionam.

---

## Tabela consolidada

| Módulo | Status | % Conclusão | Observações |
|---|---|---|---|
| Autenticação | 🟡 Beta | 70% | Login sólido; sem reset de senha (já causou retrabalho 2x) |
| Dashboard | 🟡 Beta | 80% | Funcional e testado; AI Operator lento (5.2s) |
| Conversas | 🟡 Beta | 75% | Contato/tabela corrigidos nesta sessão; sem paginação de UI |
| WhatsApp | 🟡 Beta | 75% | Validado ao vivo; 2 bugs corrigidos, 1 aberto (Issue #2) |
| Memory | 🟡 Beta | 70% | Estatística corrigida; sem backup do Qdrant |
| Analytics | 🔴 Incompleto | 50% | Labels corrigidos; módulo raso frente ao nome |
| Agenda | 🔴 Incompleto | 40% | Sem criação; nunca testado com dado real |
| Calendário | 🔴 Incompleto | 40% | Idem Agenda; redundância conceitual não resolvida |
| Tarefas | 🟡 Beta | 55% | Sem criação na UI própria; Action Center cobre parte do fluxo |
| Loja | 🔴 Incompleto | 40% | Sem criação; só via tool de agente |
| Igreja | 🔴 Incompleto | 40% | Idem Loja |
| Configurações | 🟡 Beta | 75% | Corrigida e honesta nesta sessão; read-only por decisão |
| Administração | 🟡 Beta | 85% | Área mais madura; build info ausente, sem audit trail |
| Logs | 🟡 Beta | 80% | Consolidado e corrigido nesta sessão |
| Execuções | 🟡 Beta | 75% | Rótulo corrigido; sem tabela de auditoria dedicada |
| Observabilidade | 🟡 Beta | 65% | Infra saudável; conteúdo dos dashboards não confirmado |
| API | 🟡 Beta | 78% | 875 testes; sem retry Google, Issue #2 aberta |
| Banco de Dados | 🟡 Beta | 65% | Estável em operação; backup/restore incompletos (P0) |
| Frontend | 🟡 Beta | 72% | 241 testes; dois sistemas de design não convergidos |
| Infraestrutura | 🟡 Beta | 68% | Estável; healthchecks parciais, CSP ausente, backup incompleto |

---

## Avaliação global da plataforma

- **Infraestrutura**: 68%
- **Backend**: 78%
- **Frontend**: 72%
- **UX**: 65%
- **Homologação**: 72%
- **Plataforma (escopo v1.x)**: 70%
- **Produto (escopo originalmente planejado para v1.x)**: 68%

---

## "Eu colocaria esta plataforma em produção hoje?"

**Não.** O sistema funciona e a maior parte do que testei ao vivo se comportou corretamente, mas três lacunas são bloqueantes, não cosméticas: (1) backup/disaster recovery real cobre só o Postgres, sem restore automatizado nem confirmação de que roda agendado — perder Qdrant ou a sessão do WhatsApp hoje seria irreversível; (2) não existe fluxo de reset de senha, e isso já exigiu escrita manual no banco duas vezes nesta única fase de trabalho — em produção real, sem esse acesso, o próprio operador fica travado; (3) cinco módulos de domínio (Agenda, Calendário, Loja, Igreja, parcialmente Tarefas) não têm criação de dado pela UI, então não completam o fluxo que prometem. Nenhum desses é difícil de resolver, mas todos são reais, não hipotéticos — confirmados nesta homologação, não inferidos.
