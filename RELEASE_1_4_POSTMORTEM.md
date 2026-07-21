# Postmortem — Fechamento da Release 1.4

**Período coberto:** 2026-07-20 a 2026-07-21
**Preparado em:** 2026-07-21, na certificação final de produção

Este documento cobre o ciclo funcional que implementou os 6 itens
Must/Should Have planejados em `ROADMAP_v1_5.md` mais 3 itens adicionais
(busca semântica de memória, módulo de Notas dedicado, busca em
Contacts/Church) — encerrado com uma auditoria completa de 9 etapas
(módulos, funcional, segurança, arquitetura, banco de dados, qualidade de
código, documentação, prontidão de produção, decisão de release).

## Timeline

| Data/Hora | Commit | O quê |
|---|---|---|
| 2026-07-20 19:56 | `6583a43` | GoalManager: edição, cancelamento, progresso, dependências, histórico |
| 2026-07-20 20:20 | `a15ddb0` | Busca semântica de memória exposta em `/admin/memory` (frontend-only) |
| 2026-07-20 20:56 | `e2e4d99` | Fluxo de "esqueci minha senha" — modelo/migração/schemas iniciais |
| 2026-07-20 23:08 | `393bac9` | Hardening do reset de senha (nunca loga token, rate limit dedicado, piso de tempo constante) + frontend |
| 2026-07-20 23:48 | `cb8632a` | Link de QR Code do WhatsApp no dashboard |
| 2026-07-21 00:28 | `a17237a` | Módulo de Notas dedicado (busca, pinned/archived, contact_id reservado) |
| 2026-07-21 00:53 | `7997634` | Busca por nome em Contacts/Church |
| 2026-07-21 01:38 | `08e7895` | Gmail: capacidade de resposta (reply-only, PROD-005) |
| 2026-07-21 02:23–02:24 | `19f8e82`, `c533ffa` | Google Calendar: edição de série recorrente |
| 2026-07-21 (pendente) | *(não commitado)* | Dashboard Settings editável — implementado e validado, aguardando aprovação explícita |
| 2026-07-21 | — | Certificação final de produção (este documento) |

## Progressão de testes ao longo do ciclo

| Ponto do ciclo | Backend | Frontend |
|---|---|---|
| `6583a43` (GoalManager) | 933 | 280 |
| `a15ddb0` (memory search) | 933 (inalterado) | 288 |
| `393bac9` (password reset) | 947 | 295 |
| `cb8632a` (WhatsApp QR) | 952 | 297 |
| `a17237a` (Notes) | 971 | 309 |
| `7997634` (Contacts/Church) | 977 | 315 |
| `08e7895` (Gmail) | 985 | 315 (inalterado, sem mudança de frontend) |
| `19f8e82`/`c533ffa` (Calendar) | 999 | 315 (inalterado, sem mudança de frontend) |
| Settings (pendente de commit) | **1016** | **317** |

Nenhuma regressão em nenhum ponto — cada feature manteve 100% dos testes
anteriores passando, cada validação rodou a suíte completa (não incremental).

## Correções principais

Nenhuma correção de incidente de produção neste ciclo (diferente do v1.3.1,
que fechou dois P0 reais) — este foi um ciclo puramente de entrega de
funcionalidade planejada. O único ajuste incidental: assinatura de mock de
`fetch` em `GoalDetails.test.tsx`, corrigida durante a validação do item de
memória semântica (erro de tipo latente, nunca disparado em produção).

## Auditoria final — achados por etapa

**Etapa 1/4 — Módulos e arquitetura (backend):** todos os 18 módulos
listados (Auth, RBAC, Dashboard, Admin, Notes, Contacts, Church, Tasks,
WhatsApp, Google Calendar, Google Contacts, Memory, Jobs, Logs, Settings,
Event Bus, Configuration, Providers) confirmados implementados, corretamente
registrados em `main.py` e cobertos por teste. Nenhum código duplicado,
nenhuma abstração desnecessária além do padrão Strategy já documentado,
nenhum código morto, nenhum endpoint órfão, nenhum repositório órfão
(`business/` já removido em `c82f9bc`), nenhuma violação no grafo de
dependências (nenhum provider importa de `agents/`/`api/`). Zero achados
bloqueantes ou não-bloqueantes; uma nota informacional (diretório
`docs/engineering/` vazio, inofensivo).

**Etapa 1 — Módulos (frontend):** toda página esperada existe. Confirmado
por design: Google Calendar e Google Contacts não têm superfície de
frontend própria (só ferramentas de agente) — `Jobs` não tem página
dedicada, está embutido no dashboard admin (`PendingJobsPanel`) — ambos
intencionais, não lacunas.

**Etapa 2 — Certificação funcional:** todos os 15 fluxos (login, forgot
password, dashboard, Notes CRUD/busca, Contacts/Church busca, Calendar,
eventos recorrentes, WhatsApp QR, Auto Reply, Admin Settings, persistência
de configuração, Jobs, Memory) rastreados ponta a ponta no código e
verificados contra teste automatizado. **Nenhum teste de navegador foi
executado — esta é uma verificação por trilha de código, não QA manual ao
vivo.** Lacunas não-bloqueantes encontradas: `app/admin/page.tsx` (dashboard
agregado) e `PendingJobsPanel` sem teste de componente dedicado; busca de
Notes sem asserção de frontend específica pro debounce/query param
(Church tem, Notes não); o efeito Auto-Reply-toggle→webhook e
configuração-persistida→boot são corretos por inspeção de código e
testados unitariamente em isolamento, mas nenhum teste único exercita a
costura completa ponta a ponta.

**Etapa 3 — Segurança:** checklist de 12 itens, todos **YES** exceto um
**PARTIAL** (rate limiting): autenticação, RBAC, ownership (padrão
PROD-005 replicado em Gmail/Calendar/Contacts/Drive), validação de input,
segredos (nenhum hardcoded, nenhum exposto em resposta), configuração
(allowlist fixa em `app_settings`), endpoints admin (3 testes de
"nunca vaza segredo" confirmados), XSS (escape real verificado no código,
não só um comentário), SQL injection (nenhuma interpolação de string SQL),
escalação de privilégio (role nunca setável por endpoint público),
logs sensíveis (nenhum token bruto logado). Achado não-bloqueante:
`/auth/login` sem freio dedicado de força bruta (só o limitador genérico),
pré-existente a este ciclo. Achado informacional: a ausência deliberada de
rate limit por chamada em `send_whatsapp_message`/`reply_to_email_thread`
não está documentada em `SECURITY.md`.

**Etapa 5 — Banco de dados:** exatamente um head (`68ff6ab67cdd`), cadeia
de 15 migrações totalmente linear, sem branch/gap/órfã. Toda FK de
propriedade (`user_id`, `contact_id`) indexada; duas FKs de "ator" sem
índice (`goal.approved_by_id`, `app_setting.updated_by`) — consistente com
o precedente já existente, informacional, não uma nova lacuna. `ondelete`
consistente e intencional em toda a base (`CASCADE` para dono, `SET NULL`
para referência/ator). Toda migração que adiciona coluna `NOT NULL` numa
tabela existente usa `server_default`. Todas as 15 migrações têm
`downgrade()` real e correto — nenhuma é um `pass` vazio. Zero achados
bloqueantes.

**Etapa 6 — Qualidade de código:** `ruff check .` limpo; `mypy
--ignore-missing-imports .` limpo (306 arquivos); `pytest` completo —
**1016 passed**, 0 falhas; `eslint`/`tsc --noEmit` limpos; `vitest` — **317
passed**, 46 arquivos; `next build` (produção, Turbopack) — compilado com
sucesso, todas as rotas geradas. Nenhuma mudança de código desde a última
validação completa (confirmado por `git status`).

## Melhorias de segurança

- Password reset: nunca loga token, rate limit dedicado (por e-mail em
  forgot, por IP em reset), piso de tempo constante contra enumeração de
  e-mail.
- Escopo mínimo do Gmail (`gmail.readonly` + `gmail.send`, nunca
  `gmail.modify`/`gmail.compose`) — narrowing deliberado documentado como
  controle de segurança, não só conveniência.
- PROD-005 (isolamento de destinatário/conta decidido em código, nunca só
  por prompt) replicado consistentemente nas duas features de escrita
  deste ciclo (Gmail reply, nenhuma nova em Calendar).
- Catálogo de configurações editáveis é uma allowlist fixa no código —
  nenhuma chave fora dela é persistível ou editável via `PATCH
  /admin/settings`.

## Melhorias de arquitetura

- `api/crud.py`'s factory genérico ganhou um parâmetro (`repository_cls`)
  reaproveitado por Contacts e Church, em vez de um endpoint de busca
  duplicado por domínio.
- `services/app_settings.py` introduz um registro pequeno e explícito
  (`SETTINGS_CATALOG`) que permite adicionar uma configuração editável
  nova no futuro sem redesenhar endpoint/tabela/repositório.
- `CalendarProvider.get_event` — um verbo novo no mesmo Strategy já
  existente (não uma tool nova exposta ao modelo), usado só para resolver
  instância↔série.

## Resumo de testes

- Backend: **1016 testes**, 0 falhas (era 933 no início deste ciclo).
- Frontend: **317 testes**, 0 falhas (era 280 no início deste ciclo).
- `ruff check .`: limpo.
- `mypy` (repositório inteiro, 306 arquivos): limpo.
- `next build` (produção): compilado com sucesso.
- Nenhuma regressão detectada em nenhum ponto do ciclo.

## Problemas remanescentes conhecidos

Nenhum bloqueante. Ver `TECHNICAL_DEBT.md` para a lista completa
classificada. Destaques relevantes a este ciclo:

- **P1** (não-bloqueante): `/auth/login` sem freio de força bruta dedicado
  — só o limitador genérico de 120 req/min/IP.
- **P2** (informacional): decisão de "sem rate limit por chamada" em tools
  de envio (WhatsApp, Gmail) não está escrita em `SECURITY.md` — só no
  código/docstrings.
- **P2** (informacional): `PendingJobsPanel`/dashboard admin agregado sem
  teste de componente dedicado.
- **P3**: "este evento e os seguintes" (Google Calendar), validação local
  de RRULE, e UI dedicada de edição de recorrência — deliberadamente fora
  de escopo, registrados em `ROADMAP_v1_4.md` (itens 27-29).
- **P3**: `jobs_enabled`/provider selection continuam somente leitura no
  Dashboard Settings — editá-los de verdade exigiria lifecycle de
  start/stop de worker ou invalidação de factory `@lru_cache`,
  deliberadamente fora de escopo.

## Lições aprendidas

1. **Um roadmap bem escopado desde o início evita retrabalho** — os 6
   itens Must/Should Have de `ROADMAP_v1_5.md` foram planejados com
   esforço estimado e justificativa de escopo *antes* da implementação;
   nenhum precisou de replanejamento a meio caminho.
2. **O padrão "Passo 1 obrigatório antes de código" (investigar, propor
   escopo, esperar aprovação) escala bem para 8 features consecutivas** —
   cada uma teve exatamente o mesmo ciclo (análise → aprovação → código →
   validação completa → relatório → aprovação → commit → push), sem atalho
   em nenhuma, e isso é o que tornou esta certificação final rápida (nada
   precisou ser re-auditado do zero).
3. **Reaproveitar em vez de criar** foi a decisão certa repetidamente: o
   parâmetro `repository_cls` no factory de CRUD, o campo `recurrence`
   nos tipos já existentes do Calendar, a tabela `app_settings` como
   allowlist mínima — nenhuma dessas features precisou de uma abstração
   nova de verdade, só uma extensão pontual de uma já existente.
4. **"Rodar a suíte completa, não incremental" continua sendo a única
   forma real de pegar regressão** — cada feature deste ciclo rodou
   `pytest`/`vitest` completos antes do commit, não só os arquivos
   tocados; isso é o que permite a tabela de progressão de testes acima
   mostrar zero regressão com confiança.
5. **Concorrência acidental em testes é real e sutil** — durante a
   validação do item de Calendar, uma segunda execução de teste disparada
   em paralelo à suíte completa (erro do operador, não do código) causou
   uma cascata de falhas espúrias por contenção de recurso; a causa raiz
   só ficou clara ao isolar um arquivo de teste e rodá-lo sozinho, e a
   suíte completa, re-executada sem nada concorrente, confirmou 100%
   limpa. Lição prática: nunca disparar uma segunda suíte/arquivo de teste
   enquanto uma suíte completa já está em andamento no mesmo ambiente.
