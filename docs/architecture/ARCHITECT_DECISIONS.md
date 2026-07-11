# ⚠️ DEPRECATED: Use ARCHITECTURE_DECISIONS.md (root) instead

**This document (AD-001 through AD-007) has been superseded by an expanded version.**

Refer to `ARCHITECTURE_DECISIONS.md` in the repository root instead. It contains:
- Complete resolution of all architectural decisions (DEC-1 through DEC-9)
- Updated decisions addressing all identified issues from ARCHITECTURE_REVIEW.md
- Final, authoritative decision framework

Related documents:
- `ARCHITECTURE_FINAL.md` (root) — Consolidated architecture incorporating all decisions
- `ARCHITECTURE_MIGRATION_PLAN.md` (root) — Implementation phases

---

# Dario Platform — Architect Decisions

Registro de decisões arquiteturais da Dario Platform, no estilo de um
log de ADRs leve. Cada decisão inclui o que foi decidido, por que, e o
que fica em aberto. Para o contexto geral, ver
`docs/architecture/MASTER_CONTEXT.md`.

Toda decisão aqui foi avaliada contra a pergunta obrigatória: **"esta
alteração aproxima ou afasta a Dario Platform da visão de longo
prazo?"**

---

## AD-001 — Monolito modular, não microsserviços

**Decisão**: a plataforma continua sendo um único backend deployável e
um único frontend deployável. Módulos são fronteiras de código e
contrato, não de rede.

**Justificativa**: microsserviços agora **afastariam** da visão —
multiplicam containers, modos de falha de rede e coordenação de deploy
sem ganho real (sem time crescendo, sem necessidade de escalar um módulo
independente do outro, operador único). Monolito modular **aproxima** —
módulos saem mais rápido e mais barato, e a opção de extrair um serviço
próprio no futuro continua aberta se a disciplina de fronteira (AD-002)
for seguida desde o início.

**Status**: decidido.

---

## AD-002 — Regra de dependência unidirecional Core → Módulo

**Decisão**: Core nunca importa de módulo. Módulo sempre pode importar
de Core. `orchestrator/`, `agents/`, `events/`, `memory/`, `providers/`
não referenciam `business/`, `investments/`, ou qualquer outro módulo,
em nenhuma linha.

**Justificativa**: o Core precisa continuar testável e deployável
isoladamente para sempre, não importa quantos módulos existam por cima.
É a regra que impede um monolito modular de virar, silenciosamente, um
monolito acoplado e irreversível.

**Produção**: candidato a lint de importação em CI (não implementado —
nomeado como item de trabalho futuro em
`docs/governance/ENGINEERING_GUIDE.md`).

**Status**: decidido.

---

## AD-003 — Comunicação entre módulos: Event Bus > Orchestrator > serviço público

**Decisão**: nenhum módulo lê a tabela de outro módulo diretamente. Três
canais permitidos, nesta ordem de preferência: Event Bus (assíncrono,
default), Orchestrator/Agent (síncrono dentro de um plano conversacional),
serviço público versionado do módulo dono do dado (último recurso).

**Justificativa**: reaplica o Repository Pattern e o Service Layer que
já existem dentro de cada domínio do Core, agora como fronteira entre
módulos. O Event Bus já foi desenhado exatamente para isso.

**Status**: decidido. Catálogo de eventos concreto em
`docs/modulos/MODULE_CATALOG.md`.

---

## AD-004 — Toda integração externa nova é Strategy+Factory

**Decisão**: nenhum router ou service de módulo importa um SDK de
terceiro diretamente. Toda integração externa (HubSpot, Canva, dados de
mercado, APIs de publicação) implementa um `Protocol` documentado dentro
de `providers/<nome>/provider.py`, resolvido por `factory.py`.

**Justificativa**: é o mesmo padrão que já resolveu WhatsApp (4 gateways)
e LLM (5 vendors) sem acoplar código de aplicação a nenhum vendor
específico. Tratado como regra de governança, não sugestão — evita que
Content Studio (o módulo com mais integrações externas previstas) vire
um emaranhado de chamadas diretas em dois anos.

**Status**: decidido.

---

## AD-005 — Uma única história de migrações, com disciplina expand-contract

**Decisão**: todos os módulos compartilham a mesma história do Alembic
(não uma por módulo). Toda migração de módulo novo é prefixada por
módulo na mensagem da revisão (`business: adiciona tabela clients`).
Migrações seguem expand-contract obrigatório: coluna nova nullable →
backfill → obrigatória em release seguinte.

**Justificativa**: menor custo operacional que múltiplas histórias de
migração, mantendo rastreabilidade por módulo pelo nome da revisão.
Expand-contract garante que uma migração ruim de um módulo nunca impede
um rollback de emergência do Core.

**Status**: decidido.

---

## AD-006 — Observabilidade: convenção estendida, gap de Flow ID identificado

**Decisão**: métricas de módulo seguem o prefixo `darioos_<módulo>_*`,
mesmo estilo de label já usado (`{agent,provider,status}`).

**Gap identificado, sem solução ainda**: o Correlation/Request ID atual
vive por requisição HTTP. Fluxos multi-etapa que atravessam Event Bus e
fila de jobs (ex.: cliente → proposta → apresentação → follow-up,
descrito em `docs/modulos/MODULE_CATALOG.md`) precisam de um **Flow ID**
que persiste através de várias mensagens de evento e execuções de job —
não é extensão trivial do Request ID de hoje.

**Status**: parcialmente decidido — convenção de métrica decidida, Flow
ID em aberto, provável junto do módulo Automation quando o Scheduler
entrar (ver `docs/roadmap/ROADMAP_24_MONTHS.md`).

---

## AD-007 — Todo módulo novo nasce atrás de feature flag

**Decisão**: módulos novos são habilitáveis/desabilitáveis por env-var
(mesmo estilo de `OTEL_ENABLED`), sem exigir novo deploy para ligar ou
desligar.

**Justificativa**: especialmente importante para Investments (módulo de
maior risco) — permite ligar em modo restrito, observar, desligar
instantaneamente sem reverter código.

**Status**: decidido.

---

## Decisões pendentes (não resolvidas por este documento)

1. **`church_agent`/`store_agent`** — evoluem para dentro de `business/`
   (aproveitando `store_customers` como seed) ou ficam como estão, fora
   da nova taxonomia? Decisão de produto/negócio, não de arquitetura —
   aguardando definição.
2. **VULN-1/BUG-1** (Sprint v1.2.1, já aprovada em
   `SPRINT_v1.2.1_PLAN.md`) — quando retomar a implementação, em relação
   ao fechamento desta visão de plataforma?
