# Dario Platform — Migration Plan

Como migrar do estado atual (Dario OS v1.2.0 em produção, arquitetura de
plataforma ainda não implementada) para a arquitetura consolidada em
`ARCHITECTURE_FINAL.md`. Dividido em fases sequenciais — cada uma só
começa depois da anterior estar em produção e validada, nunca em
paralelo (mesma disciplina já registrada em
`docs/roadmap/ROADMAP_24_MONTHS.md`).

**Nenhuma fase abaixo foi executada. Este é um plano, não um relatório
de execução.** Toda fase segue o mesmo protocolo de aprovação descrito
em `AI_GOVERNANCE.md`: nenhuma implementação começa sem aprovação
explícita, nenhum commit acontece sem autorização.

---

## Fase 0 — Consolidação documental

**Objetivo**: `ARCHITECTURE_FINAL.md` e `MODULE_CATALOG.md` (raiz)
passam a ser a fonte oficial de arquitetura, substituindo
`PLATFORM_ARCHITECTURE.md` e `docs/modulos/MODULE_CATALOG.md` como
referência corrente.

**Impacto**: nenhum em código ou comportamento — puramente
organizacional. Reduz o risco de um colaborador futuro (humano ou IA)
consultar a versão desatualizada (7 módulos, 3 canais de comunicação) em
vez da consolidada (4 módulos, 4 canais).

**Riscos**: enquanto os documentos antigos não forem formalmente
marcados como supersedidos ou removidos, a duplicação persiste
fisicamente — alguém pode editar o arquivo errado por engano.

**Rollback**: nenhum necessário — nenhuma mudança de código, reversível
por natureza (é decisão de qual documento ler, não uma migração de
dado ou sistema).

**Critérios de aceite**:
- `ARCHITECTURE_FINAL.md` aprovado por ChatGPT (papel de governança,
  ver `AI_GOVERNANCE.md`).
- `PLATFORM_ARCHITECTURE.md` e `docs/modulos/MODULE_CATALOG.md`
  marcados como supersedidos (aviso no topo do arquivo apontando para a
  versão nova) ou removidos — decisão e execução fora do escopo desta
  etapa.

---

## Fase 1 — Enforcement de fronteira no Core

**Objetivo**: transformar as regras de `ARCHITECTURE_FINAL.md` (Core
nunca importa módulo; Provider de módulo implementa `PlatformProvider`;
`manifest.py` com schema fixo) de convenção social em verificação
estrutural, antes que qualquer módulo exista para violá-las.

**Impacto**: mudança de infraestrutura de desenvolvimento (lint/CI), sem
nenhuma alteração de comportamento em produção. Nenhuma API, banco ou
regra de negócio muda.

**Riscos**: um lint de importação mal calibrado pode gerar falso
positivo e travar CI de mudanças legítimas dentro do próprio Core —
mitigado por rodar em modo relatório (não bloqueante) por um período
antes de virar gate obrigatório.

**Rollback**: desligar o lint/gate de CI — reversível em um commit,
sem efeito em código de aplicação.

**Critérios de aceite**:
- Regra de importação Core→módulo verificável em CI.
- Marcador `PlatformProvider` existe no Core, mesmo sem nenhum módulo
  implementando-o ainda.
- Suíte completa do Core (555+ testes) continua verde sem nenhuma
  alteração de comportamento.

---

## Fase 2 — Automation formalmente absorvido pelo Core

**Objetivo**: refletir em código a decisão já tomada em
`ARCHITECTURE_FINAL.md` — Automation não é módulo, é `jobs/`+
`workflows/` crescendo. Nenhuma extração, nenhuma criação de pacote
`automation/` novo.

**Impacto**: possível exposição de mais visibilidade de fila no Admin
(quantos jobs pendentes, por tipo, tempo médio de espera) — aditivo,
não modifica processamento de job existente.

**Riscos**: baixo — é a fase de menor risco de todo o plano, por
definição (não introduz módulo novo, só expõe dado que já existe).

**Rollback**: reverter o commit que adicionou a nova visibilidade no
Admin; nenhum dado migrado, nenhuma migração de schema necessária além
de, no máximo, índices para consulta mais rápida.

**Critérios de aceite**:
- Nenhuma tabela nova além de índices de performance, se necessário.
- Admin exibe estado da fila sem nenhuma mudança no comportamento do
  worker.

---

## Fase 3 — Knowledge v1

**Objetivo**: primeiro módulo de plataforma real, com tabelas próprias
(`knowledge_sources`, `prompt_templates`), atrás de feature flag.

**Impacto**: primeira vez que o padrão "módulo depende de Core, nunca o
inverso" é testado com código de verdade, não só em documento. Primeiro
uso real do marcador `PlatformProvider` e do `manifest.py`.

**Riscos**: é o primeiro módulo — qualquer falha no padrão de fronteira
(import indevido, vazamento de responsabilidade) aparece aqui primeiro.
Mitigado por ser o módulo de menor risco de negócio (não lida com
dado de cliente nem financeiro).

**Rollback**: módulo inteiro atrás de feature flag (`KNOWLEDGE_ENABLED`,
mesmo padrão de `OTEL_ENABLED`) — desligar a flag remove o módulo do ar
sem reverter código nem migração, contanto que as migrações sigam
expand-contract (tabelas novas, não alteração de tabela existente).

**Critérios de aceite**:
- Zero import de `knowledge/` dentro de qualquer pacote do Core.
- Zero leitura direta de `embeddings` fora do Memory Manager.
- Suíte própria de `knowledge/` + suíte completa do Core verdes.
- Flag `KNOWLEDGE_ENABLED=false` remove o módulo sem erro em nenhuma
  outra parte do sistema.

---

## Fase 4 — Business v1 e migração de `store_agent`

**Objetivo**: segundo módulo de plataforma, incluindo a migração
planejada de `store_agent` (Core) para `business/agents/crm_agent.py`.

**Impacto**: primeira migração de um agente do Core para um módulo —
`GET /api/agents` deixa de listar `store` e passa a listar o agente
equivalente dentro de Business (ou mantém compatibilidade — decisão de
implementação, não coberta por este plano). Primeiro uso real do canal
de job crítico (`business.generate_proposal`) — mas Content Studio ainda
não existe nesta fase, então esse job fica sem consumidor até a Fase 5.

**Riscos**: é o módulo de maior superfície de dado sensível depois de
Investments (dado de cliente) — exige que o isolamento técnico
equivalente ao PROD-005 (nunca confiar no LLM para saber "de quem é o
dado") seja replicado para "de qual cliente é o dado", não só "de qual
contato de WhatsApp".

**Rollback**: feature flag (`BUSINESS_ENABLED`); se a migração de
`store_agent` causar regressão, reverter primeiro a migração do agente
(manter `store_agent` em Core) mantendo o resto do módulo Business ativo
— migração de agente e módulo de dados são commits separados,
propositalmente, para permitir rollback parcial.

**Critérios de aceite**:
- `store_customers` → `clients` com plano de migração de dado explícito
  e testado em banco de homologação antes de produção.
- Isolamento por cliente testado com o mesmo rigor que
  `test_tool_isolation.py` já testa isolamento por contato hoje.
- Suíte própria + suíte completa do Core verdes.

---

## Fase 5 — Content Studio v1 e migração de `content_agent`

**Objetivo**: terceiro módulo, migração de `content_agent`, e primeira
vez que uma cadeia de job cross-módulo de ponta a ponta roda de verdade
(`business.generate_proposal` → processado por Content Studio →
`content_studio.presentation_generated` publicado como notificação).

**Impacto**: primeira validação real da política de eventos críticos
(`ARCHITECTURE_FINAL.md`, "Como módulos se comunicam") — até aqui era
só especificação.

**Riscos**: maior risco de todo o plano em termos de integração externa
(Canva, Adobe, Instagram, LinkedIn simultaneamente) — cada Provider novo
é uma superfície de falha externa adicional.

**Rollback**: feature flag por módulo e, adicionalmente, feature flag
por canal de publicação (`CONTENT_STUDIO_INSTAGRAM_ENABLED`, etc.) —
permite desligar um canal problemático sem desligar o módulo inteiro.

**Critérios de aceite**:
- Cadeia `business.generate_proposal` → `content_studio.presentation_generated`
  testada de ponta a ponta, incluindo o caminho de falha (job falha,
  retry, falha definitiva — mesmo padrão já testado em
  `whatsapp.process_inbound`).
- Suíte própria + suíte completa do Core e de Business verdes.

---

## Fase 6 — Investments v1 (escopo pessoal)

**Objetivo**: quarto módulo, deliberadamente escopado só para uso
pessoal de Dario (sem servir terceiros), adiando a questão regulatória
identificada em `docs/roadmap/ROADMAP_24_MONTHS.md`.

**Impacto**: primeiro módulo com dado financeiro — maior exigência de
segurança e auditoria de todo o plano até aqui.

**Riscos**: o próprio módulo é o de maior risco da plataforma (dado
sensível, peso regulatório potencial). Mitigação primária: escopo
pessoal explícito, sem RBAC de "cliente terceiro" para investimento —
se essa fronteira for cruzada no futuro (servir terceiros), é uma nova
fase, não uma extensão desta.

**Rollback**: feature flag; nenhuma migração de dado de outro módulo
está envolvida (Investments não herda seed de nenhum agente do Core),
então o rollback é o mais simples de todo o plano — desligar a flag
remove o módulo sem nenhum efeito colateral em Business, Content Studio
ou Knowledge.

**Critérios de aceite**:
- Confirmação explícita (fora deste plano, decisão de produto) de que o
  escopo permanece pessoal antes do primeiro deploy.
- Provider de dados de mercado escolhido e integrado via
  `PlatformProvider` (nenhum conectado hoje).
- Suíte própria + suíte completa do Core, Business e Content Studio
  verdes.

---

## Fase 7 — Multi-Agent e maturidade cross-módulo

**Objetivo**: com 4 módulos maduros e agentes migrados, revisitar a
capacidade de colaboração entre agentes de módulos diferentes
(`ROADMAP_v2.md`, v2.0.0) e o gatilho de escala do Planner definido em
`ARCHITECTURE_DECISIONS.md` (DEC-9, revisão em 8–10 agentes).

**Impacto**: mudança na forma como o Cognitive Planner seleciona e
coordena agentes — a fase de maior impacto arquitetural em Core desde
a Fase 4.2 (Cognitive Pipeline) do próprio Dario OS.

**Riscos**: é a única fase deste plano que efetivamente altera o Core
(Orchestrator/Planner) depois da Fase 1 — exige o mesmo rigor de
validação que qualquer mudança em `orchestrator/` já exige hoje.

**Rollback**: por ser mudança em Core, não em módulo, não há feature
flag de módulo que isole o impacto — rollback é reversão de commit no
Orchestrator, com o mesmo cuidado que qualquer mudança em código
compartilhado por todos os agentes já exige.

**Critérios de aceite**:
- Gatilho de 8–10 agentes efetivamente atingido antes de qualquer
  trabalho começar (não implementar preventivamente, conforme DEC-9).
- Suíte completa da plataforma inteira (Core + 4 módulos) verde antes e
  depois da mudança.

---

## Resumo

| Fase | Módulo/mudança | Risco | Reversível sem migração de dado? |
|---|---|---|---|
| 0 | Consolidação documental | Nenhum | Sim |
| 1 | Enforcement de fronteira no Core | Baixo | Sim |
| 2 | Automation absorvido pelo Core | Baixo | Sim |
| 3 | Knowledge v1 | Baixo-médio | Sim (flag) |
| 4 | Business v1 + migração `store_agent` | Médio-alto (dado de cliente) | Parcial (dado já migrado não reverte sozinho) |
| 5 | Content Studio v1 + migração `content_agent` | Alto (múltiplas integrações externas) | Sim (flag por canal) |
| 6 | Investments v1 | Alto (dado financeiro, risco regulatório) | Sim (flag, sem dependência de outro módulo) |
| 7 | Multi-Agent | Médio (toca Core) | Sim (reversão de commit) |
