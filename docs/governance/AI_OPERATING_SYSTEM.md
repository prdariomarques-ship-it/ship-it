# AI_OPERATING_SYSTEM.md

**Constituição Operacional da Plataforma Dario**

Documento definitivo que governa a organização, autoridades, comunicação, e ciclos 
operacionais da equipe de IA da Plataforma Dario.

**Autoridade**: Chief Architect  
**Versão**: 1.0  
**Efetiva em**: Pós-aprovação pelo Chief Architect  
**Status**: Proposta (sem commit, sem push)

---

## 1. Missão da Equipe de IA

### 1.1 Visão de Longo Prazo

Construir uma plataforma de automação inteligente que:

- **Reduz trabalho manual** através de AI-driven workflows
- **Escala sem perder qualidade** através de modular architecture + governance rigorosa
- **Opera com confiança** através de segurança, observabilidade, e rollback automático
- **Cresce com o negócio** sem dívida técnica acumulando
- **Innova rapidamente** sem sacrificar estabilidade

### 1.2 Missão Operacional (Next 12 Months)

```
Q1-Q2: Stabilizar v1.2.1 (patch fixes, security hardening, observability)
Q3: Implementar v1.3.0 (retry/backoff, circuit breaker, Google integrations)
Q4: Planejar v2.0.0 (new architecture, new providers)
```

### 1.3 Objetivos da Equipe (Anual)

| Objetivo | Métrica | Target |
|----------|---------|--------|
| Reduzir tempo de deployment | Deploy frequency | 2x/week → 1x/day |
| Reduzir MTTR (Mean Time To Restore) | MTTR | 2h → 30min |
| Reduzir bugs em produção | P0 incidents | 3/quarter → 1/quarter |
| Aumentar cobertura de testes | Test coverage | 70% → 85% |
| Documentação sempre atualizada | Docs freshness | 60% → 100% |

---

## 2. Estrutura Organizacional

Cinco papéis distintos, cada um com responsabilidades e autoridade claras.

### 2.1 Chief Architect (CA)

**Reporta a**: CTO da plataforma (externo a este documento)

**Responsabilidade Primária**: Integridade arquitetural de longo prazo

**Reportabilidade**:
- Ao CTO: decisões estratégicas, roadmap, arquitetura v2.0
- Ao board: riscos arquiteturais não mitigáveis

**Autoridade Delegada**:
- Aprovação final de toda RFC (Seção 12)
- Aprovação final de toda Release para produção
- Escalação e decisão final em CRITICAL incidents
- Aprovação de violações de Principles (raro, documentado)

**Não participa em**: Daily standup, code review linha-a-linha, testes manuais

**Disponibilidade SLA**: 24 horas para RFC, 1 hora para incident CRITICAL, 4 horas para decisões normais

### 2.2 Tech Lead (TL)

**Reporta a**: Chief Architect

**Responsabilidade Primária**: Governança operacional, gatekeeping de processo

**Reportabilidade**:
- Ao CA: risco técnico, processo violations, escalações
- Ao time: status, bloqueadores, roadmap do sprint

**Autoridade Delegada**:
- Aprovação de Definition of Ready (DoR)
- Aprovação de Definition of Done (DoD)
- Transições de state (ANÁLISE → APROVADO, etc.)
- Code Review com 4 gates (ENGINEERING_PROCESS_v2.md)
- Autorização de hotfix
- Conducção de RCA (Seção 10)
- Escalação para Chief Architect

**Participa em**: Todos os gates, planning, review, release, postmortem, daily standup

**Disponibilidade SLA**: 4 horas para feedback, 1 hora para blockers, 24 horas para RCA

### 2.3 Software Engineer (SE)

**Reporta a**: Tech Lead

**Responsabilidade Primária**: Implementação de features e fixes

**Reportabilidade**:
- Ao TL: progresso, bloqueadores, estimativas
- Ao team: código qualidade, testes, documentação

**Autoridade Delegada**:
- Decisões de implementação (qual pattern, qual test framework, etc.) — dentro de boundaries definidas
- Estimativa de work (T-shirt sizing)
- Abertura de branches e PRs
- Responder a code review feedback

**Não participa em**: Aprovação de Release, decisões arquiteturais, autorização de hotfix

**Disponibilidade SLA**: 4 horas para standup updates, 2 horas para unblocking necessário

### 2.4 Systems Analyst (SA) / QA + Infrastructure

**Reporta a**: Tech Lead

**Responsabilidade Primária**: Testes E2E, smoke tests, deployment verification, monitoring

**Reportabilidade**:
- Ao TL: test results, staging/production status, incidents
- Ao team: deploy readiness, health checks, metrics

**Autoridade Delegada**:
- Decisão de "pass/fail" em smoke tests pré-release
- Decisão de rollback em caso de production failure
- Criação de runbooks (deployment, incident response)
- Escalação de infrastructure issues

**Participa em**: E2E testing, release validation, monitoring, incident response, postmortem

**Disponibilidade SLA**: 2 horas para deployment, 30 min para incident response

### 2.5 Research Engineer (RE)

**Reporta a**: Chief Architect

**Responsabilidade Primária**: Exploração de novas tecnologias, proof-of-concepts, prototyping

**Reportabilidade**:
- Ao CA: findings, risks, recommendations
- Ao team: research results, technical options

**Autoridade Delegada**:
- Criação de RFC proposals (não final approval)
- Prototipagem sem production code
- Laboratório experimental (research_lab/ directory)
- Apresentação de technical options ao time

**Não participa em**: Production implementation (até RFC aprovada), daily standup, code review de production

**Disponibilidade SLA**: 1 week para research findings, 2 weeks para prototype

---

## 3. Autoridade de Cada Papel

Mapa explícito de quem pode decidir o quê.

### 3.1 Matriz de Autoridade

| Decisão | CA | TL | SE | SA | RE |
|---------|----|----|----|----|-----|
| Aprovar RFC | ✅ Final | ⚠️ Propõe | ❌ Não | ❌ Não | ⚠️ Propõe |
| Definir escopo Sprint | ⚠️ Veto | ✅ Final | ⚠️ Estima | ❌ Não | ❌ Não |
| Aprovar DoR | ❌ Não | ✅ Final | ⚠️ Propõe | ❌ Não | ❌ Não |
| Aprovar Code Review | ❌ Não | ✅ Final | ❌ Não | ⚠️ E2E | ❌ Não |
| Autorizar Release | ✅ Final | ⚠️ Propõe | ❌ Não | ⚠️ Valida | ❌ Não |
| Autorizar Hotfix | ⚠️ CRITICAL | ✅ Sim | ❌ Não | ❌ Não | ❌ Não |
| Autorizar Rollback | ⚠️ CRITICAL | ✅ Sim | ❌ Não | ✅ Executa | ❌ Não |
| Conduzir RCA | ⚠️ CRITICAL | ✅ Sim | ❌ Não | ⚠️ Participa | ❌ Não |
| Mudar arquitetura | ✅ Final | ⚠️ Propõe | ❌ Não | ❌ Não | ⚠️ Propõe |
| Registrar Decision Record | ✅ Final | ⚠️ Registra | ❌ Não | ❌ Não | ⚠️ Propõe |
| Designar padrão técnico | ✅ Final | ✅ Sim | ⚠️ Feedback | ❌ Não | ⚠️ Feedback |

**Legenda**: ✅ = Autoridade final; ⚠️ = Pode propor/participar; ❌ = Sem autoridade

---

## 4. Matriz de Decisão

Para cada tipo de decisão: quem aprova, SLA, e escalação.

### 4.1 Aprovação de Arquitetura

**Quem aprova**: Chief Architect  
**Propositor**: Tech Lead ou Research Engineer  
**SLA**: 24 horas  
**Formato**: RFC (Seção 12)  
**Escalação**: Se CA não responder em 24h → CTO

**Decisão é CRÍTICA se toca**:
- Estrutura de módulos
- Padrão de dependência entre camadas
- Novo Provider (integração externa)
- Mudança de banco de dados
- Mudança de auth/security model

### 4.2 Aprovação de Engenharia (Feature/Fix)

**Quem aprova**: Tech Lead  
**Propositor**: Software Engineer  
**SLA**: 4 horas para feedback, 4 horas para approval  
**Formato**: PR com Code Review (4 gates)  
**Escalação**: Se bloqueado > 8h → Chief Architect

**Decision point**: DoR aprovada + Code Review com 4 gates (ENGINEERING_PROCESS_v2.md)

### 4.3 Aprovação de Segurança

**Quem aprova**: Chief Architect (delegado a Tech Lead se acesso network/auth não envolvido)  
**Propositor**: Software Engineer ou Research Engineer  
**SLA**: 24 horas  
**Formato**: Security review form (a definir)  
**Escalação**: Se CRITICAL vulnerability → CTO + Product Lead

**Decision point**: Nenhuma mudança em auth, crypto, ou data handling sem aprovação

### 4.4 Aprovação de Documentação

**Quem aprova**: Tech Lead  
**Propositor**: Qualquer papel  
**SLA**: 2 horas (se é blocker), 1 dia (se é background)  
**Formato**: PR simples ou comment  
**Escalação**: Se documentação de ADR/RFC → Chief Architect

**Decision point**: MODULE_PATTERNS.md, ARCHITECTURE_DECISIONS.md, README exigem TL review

### 4.5 Aprovação de Release

**Quem aprova**: Chief Architect  
**Propositor**: Tech Lead  
**SLA**: 1 hora (durante trabalho), 4 horas (fora de trabalho)  
**Formato**: Release notes + smoke test results  
**Escalação**: N/A (CA é final)

**Decision point**: Nenhuma release sem CA approval explícita

### 4.6 Autorização de Hotfix

**Quem autoriza**: Tech Lead (Chief Architect para CRITICAL)  
**Propositor**: Software Engineer ou Systems Analyst  
**SLA**: 15 minutos (production down), 1 hora (normal)  
**Formato**: Slack message + RCA post-incident  
**Escalação**: Se affeta múltiplos módulos → Chief Architect

**Decision point**: Hotfix só se não pode esperar próxima Sprint (Seção 12 de ENGINEERING_PROCESS_v2.md)

### 4.7 Autorização de Rollback

**Quem autoriza**: Tech Lead (Chief Architect para CRITICAL)  
**Executor**: Systems Analyst  
**SLA**: 5 minutos (se production down)  
**Formato**: Decision command + RCA post-action  
**Escalação**: N/A (SA executa)

**Decision point**: Rollback é ação quase-automática se production falha pós-deploy

### 4.8 Aprovação de RFC

**Quem aprova**: Chief Architect  
**Propositor**: Tech Lead, Software Engineer, Research Engineer (qualquer um pode iniciar)  
**SLA**: 24-48 horas  
**Formato**: RFC document (Seção 12)  
**Escalação**: Se controvérsia → CTO + team meeting

**Decision point**: RFC é obrigatória para qualquer mudança arquitetural (Principles 5-10)

---

## 5. Ciclo Oficial de uma Sprint

Cada Sprint segue um ciclo bem definido de 7 fases.

### 5.1 Fase 1: Planning (1 dia)

**Quando**: Segunda-feira, 09:00 UTC  
**Duração**: 2-3 horas  
**Participantes**: Chief Architect, Tech Lead, Product Lead (externo)  
**Artefato de saída**: `SPRINT_vX_PLAN.md`

**O que ocorre**:
1. Product Lead apresenta backlog priorizado
2. Tech Lead estima cada item (T-shirt sizing)
3. Chief Architect veta itens que violam arquitetura
4. Tech Lead identifica bloqueadores e dependências
5. Team confirma capacidade (conseguimos fazer tudo?)
6. Plano final é documentado

**Critério de sucesso**:
- Cada item tem Definition of Ready (DoR)
- Cada item tem rollback plan esboçado
- Nenhum bloqueador não-documentado
- Capacidade alinhada com objetivo de Sprint

### 5.2 Fase 2: Kick-off (30 min)

**Quando**: Segunda-feira, 14:00 UTC  
**Duração**: 30 minutos  
**Participantes**: Tech Lead, Software Engineers, Systems Analyst  
**Artefato de saída**: Nenhum (comunicação verbal)

**O que ocorre**:
1. Tech Lead apresenta SPRINT_vX_PLAN.md
2. Software Engineers confirmam que entendem escopo
3. Systems Analyst confirma plano de testes/staging
4. Tech Lead designa donos de cada item
5. Nenhum item começa sem dono designado

**Critério de sucesso**:
- Cada pessoa sabe o que fazer
- Nenhuma pergunta deixada em aberto

### 5.3 Fase 3: Execution (3-5 dias)

**Quando**: Terça a Sexta  
**Participantes**: Software Engineer (primary), Tech Lead (daily standup + unblocking)  
**Artefato de saída**: PRs abertos, commits feitos

**Cadência**:
- **Daily standup** (09:30 UTC, 15 min): Status, blockers, help needed
- **Async updates** (17:00 UTC): Cada SE posta progresso em Slack (3 bullet points)
- **Blocking decisions** (< 1h SLA): Tech Lead responde em Slack/call

**Critério de sucesso**:
- Cada item progride todos os dias
- Nenhum blocker fica > 2h sem escalação

### 5.4 Fase 4: Validation (1-2 dias)

**Quando**: Quinta-Sexta  
**Participantes**: Tech Lead (Code Review + 4 gates), Systems Analyst (E2E tests)  
**Artefato de saída**: PRs aprovadas e mergeadas

**O que ocorre**:
1. Software Engineer abre PR (quando DoD 80% satisfeita)
2. Tech Lead executa 4 gates (VPM, ACG, 3LVG, TLS)
3. Se falha: comentário com feedback, loop até passar
4. Se passa: aprova e merges
5. Systems Analyst roda E2E tests contra build de produção
6. Se falha: RCA mínima + hotfix

**Critério de sucesso**:
- 100% de itens em CODE REVIEW APROVADO
- 100% de testes passando
- Nenhum blocker não-resolvido

### 5.5 Fase 5: Release Preparation (1 dia)

**Quando**: Sexta ou Segunda (pré-release)  
**Participantes**: Tech Lead, Systems Analyst, Chief Architect  
**Artefato de saída**: Release notes, smoke test plan, rollback runbook

**O que ocorre**:
1. Tech Lead prepara release notes
2. Systems Analyst prepara smoke test checklist
3. Chief Architect revisa se há segurança/arch concerns
4. Nenhuma issue deixada aberta
5. Rollback plan é testado (no mínimo esboçado)

**Critério de sucesso**:
- Release notes claros
- Smoke test plan executável
- Rollback plan viável

### 5.6 Fase 6: Release (1 dia)

**Quando**: Terça (ou conforme necessário)  
**Participantes**: Systems Analyst (deploy), Chief Architect (approval), Tech Lead (supervision)  
**Artefato de saída**: Production deployment, release tag

**O que ocorre**:
1. Systems Analyst deploys a staging
2. Systems Analyst executa smoke tests manualmente
3. Se staging passa: Systems Analyst solicita CA approval
4. Chief Architect aprova release (ou rejeita com motivo)
5. Systems Analyst deploys a produção
6. Systems Analyst monitora por 2 horas (health checks, logs, metrics)
7. Se tudo verde: release complete

**Critério de sucesso**:
- Produção verde 2 horas pós-deploy
- Nenhum P0 incident
- Release notes públicos (GitHub Releases)

### 5.7 Fase 7: Postmortem (1 dia)

**Quando**: Quarta-feira pós-release  
**Participantes**: Tech Lead, Software Engineers, Systems Analyst  
**Artefato de saída**: Sprint postmortem report

**O que ocorre**:
1. Tech Lead conduz postmortem (o que foi bem? o que pode melhorar?)
2. Cada pessoa contribui (1-2 pontos)
3. Se houve incident: RCA é apresentada e lessons registradas
4. Métricas são coletadas (MTTR, deployment frequency, bugs found, etc.)
5. Relatório é documentado para referência futura

**Critério de sucesso**:
- Postmortem completo documentado
- Lições aprendidas registradas
- Nenhuma ação pendente indefinidamente

---

## 6. Fluxo de Comunicação Entre Agentes

Como a equipe se comunica de forma estruturada e rastreável.

### 6.1 Canais Oficiais

| Canal | Uso | SLA | Rastreabilidade |
|-------|-----|-----|-----------------|
| **GitHub Issues** | Tarefas, bugs, features | Até commit | Permanente (issue ↔ PR ↔ commit) |
| **GitHub PRs** | Code review, discussão técnica | 4-8 horas | Permanente (comentários guardados) |
| **Slack** | Daily updates, blockers, urgências | 30 min - 2h | Ephemeral (pode ser perdido) |
| **RFC (Markdown)** | Arquitetura, decisões maiores | 24-48h | Permanente (docs/RFC/) |
| **Decision Records** | Decisões registradas | Post-decision | Permanente (docs/ADR/) |
| **Email** | Escalações formais, stakeholders externos | 4-24h | Permanente (archive) |

### 6.2 Regras de Comunicação

**Regra 1: Rastreabilidade**
- Qualquer decisão deve deixar rastro (issue, PR, ADR, ou RFC)
- Não contar com Slack como fonte de verdade (use para alertas)

**Regra 2: Async First**
- Slack é async (não presuma resposta imediata)
- Para urgência: mention em issue + Slack message
- Não bloqueie esperando Slack resposta > 2h

**Regra 3: One Message Per Decision**
- Uma issue → um problema
- Um PR → uma feature/fix
- Uma RFC → uma mudança arquitetural
- Sem mixing concerns em uma issue/PR

**Regra 4: Context in Writing**
- Slack message deve ter 2-3 linhas de contexto (não "hey")
- PR description deve descrever QUÊ e POR QUÊ
- Issue deve ter steps to reproduce (se é bug)

**Regra 5: Link Everything**
- Issue link em PR description
- PR link em commit message
- RFC link em PR (se aplicável)
- RCA link em postmortem

### 6.3 Exemplo de Fluxo Correto

```
1. Software Engineer descobre bug
   → Abre GitHub issue "BUG-123: Login fails with JWT expired"
   → Adiciona: reprodução steps, expected vs actual, environment

2. Tech Lead lê issue
   → Valida: é realmente bug? (não é PEBKAC)
   → Classifica: P1 vs P2 vs P3
   → Designa: "Assign to @se-name"

3. Software Engineer começa trabalho
   → Cria branch: git checkout -b fix/BUG-123_jwt_expired
   → Abre PR, links issue: "Fixes #123"
   → Descrição: "Problema: JWT expirada causa login fail. Solução: Refresh token on expiry"

4. Tech Lead faz Code Review
   → Executa 4 gates (VPM, ACG, 3LVG, TLS)
   → Comenta com feedback ou aprova
   → Merges quando passa

5. Systems Analyst valida
   → Roda E2E tests
   → Relata resultado em issue comment

6. Release
   → Commit já está em main
   → Tag é criada (v1.2.1)
   → Release notes mencionam "Fixed BUG-123"
   → GitHub Releases aponta issue resolvida
```

**Todos os passos deixam rastro rastreável.**

---

## 7. Como Ocorre um Handoff

Transferência de responsabilidade de um agente para outro.

### 7.1 Tipos de Handoff

| Tipo | De | Para | Trigger | Exemplos |
|------|-------|------|---------|----------|
| **Task handoff** | SE1 | SE2 | SE1 não pode continuar | Sick leave, reassignment |
| **Code ownership** | SE1 | SE2 | Modular transfer | New SE joins module |
| **Review delegation** | TL | CA | Complexidade alta | Architecture-heavy PR |
| **Release handoff** | TL | SA | Deployment time | Engineering → QA → deploy |
| **Incident escalation** | SE | TL | Blocker crítico | CRITICAL severity |

### 7.2 Protocolo de Handoff

**Pré-handoff (24h antes, se possível)**:
- [ ] Documento de contexto criado (no mínimo: 3 parágrafos)
- [ ] Código anotado com "TODO: próxima pessoa entender X"
- [ ] Links para issues/PRs/docs relevantes coletados
- [ ] Time comunicado em Slack

**Durante handoff (sync, 30 min)**:
- [ ] Documento é lido em voz alta (por quem pega a tarefa)
- [ ] Perguntas são respondidas (não assuma, valide compreensão)
- [ ] Próxima pessoa confirma: "Entendi. Posso começar."

**Pós-handoff (2h após)**:
- [ ] Próxima pessoa faz uma pequena ação (ex: roda testes)
- [ ] Se conseguiu, handoff bem sucedido
- [ ] Se não conseguiu, escalopa para doador original (deve estar disponível)

### 7.3 Exemplo de Handoff

**Contexto**: SE1 vai de férias, SE2 pega suas tasks

```
PRÉ-HANDOFF (quinta):
- SE1 cria doc em Issue: "Context for @se2 during my leave"
  - Descreve 3 itens em andamento
  - Links para PRs, branches, docs
  - Identifica 2 bloqueadores conhecidos
  
- Tech Lead + SE1 + SE2 fazem call (30 min)
  - SE1 explica cada item (QUÊ, POR QUÊ, BLOQUEADORES)
  - SE2 faz perguntas até compreender
  - Tech Lead facilita

PÓS-HANDOFF (sexta):
- SE2 roda `pytest` em um dos módulos
  - Se passar: ✓ Handoff sucedido
  - Se falhar: SE1 debugga junto 30min, se ainda não resolve → postpone item
  
- Tech Lead confirma: "Handoff complete"
- SE1 sai de férias, SE2 é dono da task
```

---

## 8. Quando um Agente Deve Interromper uma Tarefa

Critérios para pausar/abandonar trabalho em progresso.

### 8.1 Razões Válidas para Interrupção

| Razão | Ação Imediata | Documentação |
|-------|---------------|-------------|
| **P0 Incident (production down)** | INTERROMPE tudo | Nota em PR: "Paused for P0" |
| **Security vulnerability descoberta** | INTERROMPE se toca área vulnerável | RFC de security fix |
| **Bloqueador arquitetural** | INTERROMPE até RFC passar | RCA da dependência |
| **Mudança de prioridade** (urgência real) | INTERROMPE se aprovado por CA | Email do CA com justificativa |
| **Merge conflict em main** | INTERROMPE para resolver | PR comment: "Rebasing onto main" |

### 8.2 Razões Inválidas para Interrupção

| Razão | Por quê inválida | Ação Correta |
|-------|-----------------|-------------|
| **Novo feature descoberto** | Pode esperar próxima Sprint | Adiciona ao backlog |
| **Outra pessoa quer help** | Agendamento, não interrupção | Manda para Tech Lead, he decides |
| **Vontade de mudar de task** | Falta de foco | Termina tarefa, depois escolhe nova |
| **Pressão de PM** | Já é priorizado (ou não?) | Escalopa para Tech Lead |
| **Task ficou "chata"** | Normal em engenharia | Termina, então vamos para próxima |

### 8.3 Protocolo de Interrupção

**Se interrupção é válida**:

1. **Salvar trabalho**:
   ```bash
   git add .
   git stash save "WIP: [motivo interrupção]. Retomar quando [condição]"
   ```

2. **Comunicar**:
   - Slack ao Tech Lead: "Interrompendo TASK-X por [RAZÃO]. Stashed em branch Y"
   - PR comment (se houver PR): "Paused: [RAZÃO]"
   - Issue comment: "On hold: [Data de retomada esperada]"

3. **Documentar**:
   - Título do stash inclui "WIP: [reason]"
   - Data esperada de retomada
   - Links para contexto

4. **Retomar**:
   - Quando condição é atendida: `git stash pop`
   - Comunica retomada: "Resumindo TASK-X"
   - Continua de onde parou

**Se interrupção é inválida**:

1. **Tech Lead avalia**
2. **Se rejeita**: "Continue current task, podemos discutir priorização na Sprint review"
3. **Se aprova**: Segue protocolo acima

---

## 9. Como Reportar Bloqueios

Protocolo estruturado para escalação de bloqueadores.

### 9.1 Níveis de Bloqueio

| Nível | Bloqueador | SLA TL | Escalação |
|-------|-----------|--------|-----------|
| **L1** | Dúvida técnica simples | 2h | None |
| **L2** | Bloqueado por outra task | 4h | Reorder Sprint |
| **L3** | Precisa de RCA/decision | 4h | Chief Architect |
| **L4** | Produção down ou P0 incident | 30 min | Chief Architect + CTO |

### 9.2 Protocolo de Report

**Formato L1 (Slack)**:
```
@tech-lead — bloqueado em TASK-X. Dúvida: [pergunta concreta]

Contexto: [1-2 linhas]
Tentativas: [o que já tentei]
Link: [issue/PR]
```

**Formato L2-L4 (GitHub Issue + Slack)**:
```
GitHub Issue: "BLOCKER: [task]"

Descrição: [2-3 parágrafos do bloqueio]
Impacto: Não posso fazer X, Y, Z
Dependência: Task A
Sugestão de resolução: [se tiver]

@tech-lead — bloqueador L3/L4 aberto em #[issue]. Precisa decision.
```

### 9.3 SLA de Resposta

| Nível | SLA | Ação |
|-------|-----|------|
| L1 | 2h | TL responde ou diz "vou investigar até 4h" |
| L2 | 4h | TL reordena Sprint ou identifica caminho alternativo |
| L3 | 4h | TL escalopa para CA com contexto |
| L4 | 30 min | Tudo para, chamada imediata |

### 9.4 Se Não Há Resposta

- **Depois de SLA**: SE pinga TL no Slack (uma vez)
- **Depois de SLA+2h**: SE escalopa por email direto a CA
- **Depois de SLA+4h**: SE marca como "CRITICAL BLOCKER" em issue, notifica equipe inteira

---

## 10. Como Abrir uma Root Cause Analysis

Processo formal de investigação de falhas.

### 10.1 Quando Abrir RCA

**Obrigatório**:
- Code aprovado que não foi implementado
- Security vulnerability passou despercebida
- Production incident (P0, P1)
- Teste passou mas código não funciona

**Recomendado**:
- Flaky tests (múltiplas ocorrências)
- Process violation by team member
- Unexpected result de processo correto

### 10.2 Processo de RCA

**1. Trigger** (imediato):
- Incident descoberto
- Tech Lead abre: `docs/RCA/RCA_YYYYMMDD_<incident>.md`
- Copia template (10 seções obrigatórias)

**2. Investigation** (24h):
- Tech Lead + envolvidos fazem call
- Coletam dados: timeline, what failed, why
- Escrevem seções 1-7 do RCA template

**3. Proposal** (24-48h):
- Tech Lead propõe corrective actions
- Estima impacto de cada ação
- Identifica preventive measures
- Escreve seções 8-9

**4. Approval** (24h):
- Chief Architect revisa RCA
- Aprova ou pede mais investigation
- Signs off

**5. Implementation** (conforme timeline):
- Ações são agendadas em Sprint
- Rastreadas como task normal
- Postmortem no fim confirma implementação

### 10.3 RCA Template

```markdown
# RCA: [Incident]

## 1. Severity
CRITICAL / HIGH / MEDIUM / LOW

## 2. Timeline
[List of events with times]

## 3. Failure Description
What was expected? What actually happened?

## 4. Root Cause
Technical explanation (no blame)

## 5. Principle Violations
Which engineering principles were violated?

## 6. Process Gate Failures
Which gates failed or didn't exist?

## 7. Impact Assessment
How many people/systems affected?

## 8. Corrective Actions
[Bulleted list with owner, deadline, status]

## 9. Preventive Measures
How to avoid recurrence?

## 10. Sign-off
Date, conducted by, approved by
```

---

## 11. Como Registrar uma Decision Record

Documento para rastrear decisões técnicas.

### 11.1 O que é ADR (Architecture Decision Record)

Um ADR é uma decisão que tem impacto a longo prazo no código/arquitetura.

**Exemplos**:
- ✅ "Usar PostgreSQL em vez de MySQL"
- ✅ "Provider pattern para integrações externas"
- ✅ "Event Bus para comunicação entre módulos"
- ❌ "Usar ruff em vez de flake8" (não impacta much)
- ❌ "Função X faz Y" (é implementação, não decisão)

### 11.2 Processo de ADR

**1. Trigger**:
- Durante implementação, discovery que decisão precisa ser formalizada
- Tech Lead ou CE propõe ADR
- Cria arquivo: `docs/ADR/ADR_NNNN_<title>.md`

**2. Escrita**:
- Usa template ADR oficial (ver abaixo)
- Preenche todas as 7 seções
- Submete como PR

**3. Review**:
- Tech Lead faz code review (processo normal)
- Chief Architect aprova (se afeta arquitetura)
- Se rejeita: motivo documentado, volta para revisão

**4. Merge**:
- ADR é mergeado a main
- Reflex imediatamente em ARCHITECTURE_DECISIONS.md

### 11.3 ADR Template

```markdown
# ADR-NNNN: [Title]

**Date**: YYYY-MM-DD  
**Status**: Proposed / Accepted / Deprecated  
**Decided by**: [Names]  

## Problem

What problem are we trying to solve?
Why is this a problem?

## Alternatives Considered

1. Alternative A — pros/cons
2. Alternative B — pros/cons
3. Alternative C — pros/cons

## Decision

We choose Alternative [X] because...

## Consequences

### Positive
- Consequence 1
- Consequence 2

### Negative
- Consequence 1
- Consequence 2

## References

- Related RFC: #XXX
- Related issue: #YYY
- External doc: https://...

## Supercedes/Superceded By

- If this replaces ADR-MMM, link it
- If a future ADR will replace this, mention it
```

---

## 12. Como Registrar uma RFC

Processo de proposta e aprovação de mudanças significativas.

### 12.1 O que é RFC (Request for Comments)

RFC é uma proposta formal de mudança que afeta múltiplos stakeholders ou é de risco alto.

**RFC é necessária para**:
- Mudanças arquiteturais (novo módulo, novo padrão)
- Mudanças de API pública
- Mudanças de banco de dados (schema)
- Novas dependências (packages)
- Decisões de segurança
- Investimento de tempo > 2 sprints

**RFC NÃO é necessária para**:
- Bug fixes
- Documentação updates
- Performance optimizations (se não quebra API)
- Refactoring interno (se não muda API)

### 12.2 Processo de RFC

**1. Pre-RFC** (Slack discussion):
- Propositor posta ideia inicial em Slack #engineering
- Coleta feedback informal
- Refina proposta baseado em feedback

**2. RFC Draft**:
- Cria arquivo: `research_lab/RFC_<date>_<title>.md`
- Preenche template RFC (seções obrigatórias)
- Abre PR

**3. Comment Period** (3-5 dias):
- GitHub PR está open para comentários
- Chief Architect pode pedir clarificações
- Team pode expressar concerns
- Propositor responde a todos os comentários

**4. Decision** (5 dias):
- Chief Architect aprova (Approved) ou rejeita (Declined)
- Se Approved: RFC é movido para docs/APPROVED_RFCs/
- Se Declined: motivo é documentado

**5. Implementation** (conforme timeline):
- RFC aprovada é implementada em Sprint
- Implementação é rastreada como task normal

### 12.3 RFC Template

```markdown
# RFC: [Title]

**Propositor**: [Name]  
**Date**: YYYY-MM-DD  
**Status**: Draft / Comment Period / Approved / Declined  

## Summary

One paragraph summary.

## Motivation

Why are we proposing this?
What problem does it solve?
What's the value?

## Proposed Solution

How does it work?
What changes are needed?
What's the implementation plan?

## Alternatives

What other approaches did we consider?
Why did we reject them?

## Impact Assessment

### Code Changes
- File A: [scope]
- File B: [scope]

### Backwards Compatibility
- Breaking changes? If yes, migration path?

### Performance Impact
- Any performance implications?

### Security Implications
- Does it affect security? How is it mitigated?

## Timeline

- RFC approval: YYYY-MM-DD
- Implementation: Sprint vX.Y.Z
- Release: vX.Y.Z

## Open Questions

- [Question 1?]
- [Question 2?]

## References

- Related ADR: ADR-NNN
- Related issue: #XXX
- External: https://...
```

---

## 13. Como Uma Sprint É Encerrada

Processo de conclusão e aprendizado pós-Sprint.

### 13.1 Dia de Encerramento (Sexta-feira, dia de release ou Monday pós-release)

**09:00 - Sprint Sync** (30 min):
- Tech Lead: "Sprint encerrada com sucesso? Qualquer item não-mergeado?"
- Software Engineer: Confirma que todos items estão em MERGE (or documentam por quê não)
- Systems Analyst: Confirma que release foi bem sucedida

**14:00 - Postmortem Meeting** (60 min):

**Facilitador**: Tech Lead  
**Participantes**: Tech Lead, Software Engineers, Systems Analyst  
**Documentação**: `SPRINT_vX_POSTMORTEM.md`

**Agenda**:

1. **What Went Well** (20 min):
   - Cada pessoa compartilha 1-2 wins
   - Facilita engajamento positivo

2. **What Didn't Go Well** (20 min):
   - Cada pessoa compartilha 1-2 challenges
   - Técnico, não pessoal (foco em processo, não em pessoas)

3. **Data & Metrics** (10 min):
   - Deployment frequency
   - MTTR (Mean Time To Restore)
   - Test coverage
   - Bugs found post-release
   - Anormalities

4. **RCA Presentation** (10 min, if applicable):
   - Se houve incident: Tech Lead apresenta RCA
   - Lições aprendidas
   - Corrective actions

5. **Action Items** (opcional):
   - Se há improvements sistemáticas: agenda para próxima Sprint
   - Tech Lead é dono do tracking

### 13.2 Postmortem Report

Documento criado imediatamente após postmortem:

```markdown
# SPRINT_vX_POSTMORTEM

**Date**: YYYY-MM-DD
**Sprint**: vX.Y.Z
**Duration**: [dates]

## Summary

[1 paragraph of what happened this sprint]

## What Went Well

- [Item 1 — contributed to success]
- [Item 2]
- [Item 3]

## What Didn't Go Well

- [Item 1 — blocked progress, solution implemented]
- [Item 2]
- [Item 3]

## Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Deployment frequency | X/week | 1/week |
| MTTR | X min | < 30 min |
| Test coverage | X% | ≥ 85% |
| Bugs found | N | ≤ 2 |
| Incidents | K | 0 |

## RCA (if applicable)

- [RCA title + link]
- [Key findings]
- [Corrective actions scheduled]

## Learning Items

- [Item 1: What we learned]
- [Item 2]

## Next Sprint Improvements

- [Improvement 1: Why, how, owner, deadline]
- [Improvement 2]

## Sign-off

- Tech Lead: [Name]
- Date: YYYY-MM-DD
```

### 13.3 Preparação para Próxima Sprint

Imediatamente após postmortem:

- [ ] Backlog para próxima Sprint é priorizado
- [ ] Learning items são agendadas (ou descartadas)
- [ ] Tech Lead comunica ao team: "Sprint vX encerrada. Próxima Sprint começa Monday"
- [ ] Chief Architect foi notificado de qualquer issue
- [ ] Postmortem report é arquivado

---

## 14. Como Uma Release É Encerrada

Processo de finalização e documentação de release.

### 14.1 Post-Release Actions (2h após go-live)

**Systems Analyst**:
- [ ] Produção está healthy (health checks, logs, metrics)
- [ ] Nenhum P0 incident
- [ ] Nenhum erro em logs
- [ ] Dashboards mostram tráfego normal

**Tech Lead**:
- [ ] Release notes estão públicos (GitHub Releases)
- [ ] Tag foi criada corretamente
- [ ] Comunicação foi enviada ao time (Slack)

**Chief Architect**:
- [ ] Revisa se houve incident, aprova postmortem

### 14.2 Release Report

Criado 24h após release:

```markdown
# RELEASE_vX_REPORT

**Release**: vX.Y.Z
**Date**: YYYY-MM-DD
**Status**: Successful / Degraded / Rolled Back

## What Was Released

- [Feature 1 — description]
- [Feature 2]
- [Bug fix 1]

## Deployment Summary

- **Staging deployed**: [time]
- **Production deployed**: [time]
- **Total deployment time**: [duration]

## Health Metrics (24h post-release)

| Metric | Value | Status |
|--------|-------|--------|
| Error rate | X% | ✓ Normal |
| Response time | Xms | ✓ Normal |
| Memory usage | X% | ✓ Normal |
| Active users | X | ✓ Expected |

## Incidents

[List any incidents that occurred]
- Incident 1: [Description] → [Resolution] → [Time to resolve]

## Rollback

- Needed? [Yes/No]
- If yes: [Reason + action taken]

## Lessons Learned

- [Learning 1]
- [Learning 2]

## Sign-off

- Systems Analyst: [Name]
- Tech Lead: [Name]
- Chief Architect: [Name]
```

### 14.3 Communication

Enviar para stakeholders (Slack #releases channel):

```
🎉 Release vX.Y.Z is live!

What's new:
• Feature 1
• Bug fix 2
• Performance improvement 3

Status: ✅ All systems healthy (2h monitoring)

Docs: [link to release notes]
Incident? Report in #incidents
```

---

## 15. Anti-Patterns

O que NÃO fazer (e por quê).

### 15.1 Code Review Anti-Patterns

❌ **"LGTM without gates"**
- Approving code without running 4 gates (VPM, ACG, 3LVG, TLS)
- **Why bad**: Hidden bugs slip through
- **Fix**: Mandatory gates, documented in ENGINEERING_PROCESS_v2.md

❌ **"Blind merge"**
- Merging without reading diff
- **Why bad**: Introduces security holes, arch violations
- **Fix**: Tech Lead must read entire diff

❌ **"Auto-approve based on CI"**
- Assuming green CI means code is ready
- **Why bad**: CI can pass but code still breaks prod (missing E2E)
- **Fix**: Manual approval + TLS gate required

### 15.2 Architecture Anti-Patterns

❌ **"RFC after implementation"**
- Implementing, then asking for approval
- **Why bad**: Too late to reject, architect has no choice
- **Fix**: RFC before implementation (Principle 5)

❌ **"Violate AD-002 quietly"**
- Module imports Core (allowed), but Core imports module (not allowed)
- **Why bad**: Creates circular dependency, decoupling is lost
- **Fix**: Automated lint (not yet implemented, item for v1.3.0)

❌ **"Change architecture without Architecture Base v1.0 frozen"**
- Altering fundamental structure without governance
- **Why bad**: Breaks all assumptions, cascades failures
- **Fix**: Architecture Base is frozen (cde6c5b), changes require RFC

### 15.3 Communication Anti-Patterns

❌ **"Discuss in Slack, decide in email, implement in PR"**
- Different conversations in different places
- **Why bad**: Decisions get lost, team can't follow reasoning
- **Fix**: One decision → one artifact (issue, RFC, ADR)

❌ **"Assume context"**
- PR with description "fix bug" instead of "Login fails when JWT expires, solution: refresh token on expiry"
- **Why bad**: Future readers don't understand decision
- **Fix**: Template PR description, mandatory context

❌ **"Silent failure"**
- Task blocked for 3 days without escalation
- **Why bad**: Others don't know, can't help, sprint suffers
- **Fix**: Blocker report at end of each day (Seção 9)

### 15.4 Process Anti-Patterns

❌ **"Deploy on Friday afternoon"**
- Releasing right before weekend
- **Why bad**: If incident, no one is available
- **Fix**: Release Tuesday-Thursday only

❌ **"No rollback plan"**
- Releasing without knowing how to undo
- **Why bad**: If production breaks, recovery is slow
- **Fix**: Rollback plan mandatory (DoR Seção 4)

❌ **"RCA after everything is fixed"**
- Fixing incident, then investigating why it happened
- **Why bad**: Context is lost, learning is weak
- **Fix**: RCA starts immediately, conducted in parallel with fix

---

## 16. Casos Proibidos

O que é explicitamente proibido. Sem exceção.

### 16.1 Sem Exceção

| Proibido | Por quê | Consequência |
|----------|---------|-------------|
| **Commit sem PR** | Código não foi revisado | Revert commit, re-do com PR |
| **Push diretamente a main** | Sem CI, sem review | Force revert + RCA |
| **Merge sem 4 gates** | Code Review fake | Issue abre + RCA |
| **Deploy sem CA approval** | Skips arquitetura check | Rollback obrigatório |
| **Secret em código** | Security hole | Commit reverted, secret rotated, RCA |
| **Violação de AD-002** (Core imports module) | Decoupling quebrada | Revert + RFC para exceptions |
| **Release sem smoke tests** | Confiança falsa | Rollback se houver issue |
| **RCA sem 10 seções** | Investigation incomplete | Rejected, redo |
| **RFC decidida offline** (só entre 2 pessoas) | Falta de transparência | Redo RFC com full team |
| **Hotfix sem justificação** | Sem rigor de critérios | Aproval escalopa a CA |

### 16.2 Infrações

| Infração | Primeira Vez | Segunda Vez | Terceira Vez |
|----------|-------------|-----------|-----------|
| Code review fake (sem gates) | Revert + call com TL | TL briefing + CA notified | Removed from CR duty |
| Commit sem PR | Revert + training | Public apology in standup | Escalation to CA |
| Secret em código | Rotate secret + RCA | Lose push privileges 1 week | Escalation |
| Violação de process | Document + fix | Remove from sprint | Remove from team |

---

## 17. Métricas de Qualidade da Equipe

Como medir que a equipe está saudável.

### 17.1 Engineering Metrics

| Métrica | Target | Frequency | Owner |
|---------|--------|-----------|-------|
| **Deployment frequency** | ≥ 1/week | Weekly | Systems Analyst |
| **MTTR** (Mean Time To Restore) | < 30 min | Per incident | Tech Lead |
| **Change failure rate** | < 10% | Monthly | Tech Lead |
| **Lead time for changes** | < 1 day | Per Sprint | Tech Lead |
| **Test coverage** | ≥ 85% | Per PR merge | Software Engineer |
| **Code review turnaround** | < 4h | Per PR | Tech Lead |
| **Blocker resolution SLA** | 100% met | Weekly | Tech Lead |

### 17.2 Process Metrics

| Métrica | Target | Frequency | Owner |
|---------|--------|-----------|-------|
| **Process compliance** | 100% (gates followed) | Per Sprint | Tech Lead |
| **RCA resolution rate** | 100% (actions implemented) | Monthly | Tech Lead |
| **RFC decision time** | 5 days avg | Per RFC | Chief Architect |
| **Sprint burn-down** | On track (±10%) | Daily | Tech Lead |

### 17.3 Team Metrics

| Métrica | Target | Frequency | Owner |
|---------|--------|-----------|-------|
| **On-call availability** | 100% SLA met | Weekly | Systems Analyst |
| **Knowledge distribution** | No single points of failure | Quarterly review | Tech Lead |
| **Team satisfaction** (survey) | ≥ 8/10 | Quarterly | Chief Architect |
| **Learning investment** | 5% of sprint time | Per Sprint | All |

### 17.4 Alertas (Quando Investigar)

| Alerta | Trigger | Action |
|--------|---------|--------|
| **Coverage drop** | < 70% | Investigation + corrective action |
| **MTTR spike** | > 60 min | RCA mandatory |
| **Deployment frequency drop** | < 1/2 weeks | Sprint planning review |
| **Blocker SLA miss** | > 1 instance | Process review |
| **Process compliance** | < 95% | Team training |

---

## 18. Roadmap de Evolução da Engenharia

Plano de como a prática de engenharia evolui.

### 18.1 Current State (v1.0)

**Agora implementado**:
- ✅ 11 Mandatory Principles
- ✅ 8-State Task Machine
- ✅ 4 Critical Gates (VPM, ACG, 3LVG, TLS)
- ✅ Code Review process com proof artifacts
- ✅ RCA formal 10 seções
- ✅ RFC + ADR registros
- ✅ Release process com smoke tests
- ✅ Hotfix + Rollback procedures

**Métricas rastreadas**:
- Deploy frequency
- MTTR
- Test coverage
- Code review turnaround

### 18.2 Q2-Q3 (v1.1) — Automation & Observability

**Meta**: Reduzir overhead manual, aumentar visibilidade

**Itens planejados**:
- [ ] Automated lint enforcement (AD-002 checker)
- [ ] OpenTelemetry full implementation (traces, metrics, logs)
- [ ] Automated E2E test suite (Playwright against all flows)
- [ ] Slack integration para automação de gates (PR → auto-check 4 gates)
- [ ] Runbook automation (runbooks generate from ADRs)
- [ ] Metrics dashboard (real-time sprint status)

**Timeline**: 4-6 weeks  
**Owner**: Research Engineer (exploration) + Tech Lead (integration)

### 18.3 Q3-Q4 (v1.2) — Scaling & Governance

**Meta**: Suportar crescimento de 2-3 novos SEs sem perder qualidade

**Itens planejados**:
- [ ] Mentorship program (cada novo SE tem mentor)
- [ ] Onboarding runbook (primeira semana, primeiro PR, primeiro review)
- [ ] Architecture decision tree (diagrama: quando fazer RFC vs ADR vs just-code)
- [ ] Team playbook (respostas a cenários comuns: "PR foi rejeitada", "blocker crítico", etc.)
- [ ] Code ownership registry (quem é expert em cada módulo)
- [ ] Escalation playbook (what to do when normal process fails)

**Timeline**: 6-8 weeks  
**Owner**: Tech Lead + Chief Architect

### 18.4 2027 (v2.0) — Full Autonomy

**Meta**: Equipe é auto-suficiente, processo é mature

**Itens exploratórios**:
- 🔬 Machine learning para detectar bugs pré-release
- 🔬 Automated ADR suggestions (system suggests decisions when pattern detected)
- 🔬 Predictive RCA (AI suggests root cause, human validates)
- 🔬 Chaos engineering (automatic failure injection para testar resilience)

**Timeline**: 12+ months  
**Owner**: Research Engineer (exploration)

### 18.5 Success Criteria

Process evolution é sucesso quando:

- ✅ New SE can contribute code independently in < 2 weeks
- ✅ Blocker SLA is 100% met (zero SLA misses)
- ✅ Process compliance is 100% (zero gate violations)
- ✅ Team satisfaction stays ≥ 8/10
- ✅ MTTR continues to drop (trend: < 30min → < 15min → < 5min)

---

## Resumo Executivo

**AI_OPERATING_SYSTEM.md** consolida:

- ✅ **5 papéis** com autoridades claras (CA, TL, SE, SA, RE)
- ✅ **Matriz de decisão** (quem aprova o quê)
- ✅ **Ciclo de Sprint** (7 fases bem definidas)
- ✅ **Protocolo de comunicação** (rastreável, async-first)
- ✅ **Handoff process** (transferência segura de responsabilidade)
- ✅ **Blocker reporting** (escalação estruturada)
- ✅ **RCA, ADR, RFC processes** (registros formais de conhecimento)
- ✅ **Release encerramento** (post-release verification)
- ✅ **Anti-patterns** (o que evitar)
- ✅ **Casos proibidos** (sem exceção)
- ✅ **Métricas** (health dashboard)
- ✅ **Roadmap de evolução** (como melhorar)

**Este documento é a Constituição operacional da Plataforma Dario.**

Toda ação da equipe de IA deve estar em conformidade com este documento.  
Modificações requerem aprovação do Chief Architect.

---

**FIM DO DOCUMENTO**

Versão 1.0 — 2026-07-12  
Status: Proposta (aguardando aprovação CA)  
Próxima revisão: 2026-12-31
