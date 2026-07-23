# ADR-0001: Contact Priority Panel — visualização no cockpit sem duplicar execução

**Status:** Aceito
**Data:** 2026-07-23
**Release:** 1.5 (Redirecionamento estratégico — "User Usable")

## Contexto

O redirecionamento estratégico da Release 1.5
(`REDIRECIONAMENTO_RELEASE_1_5.md`) mudou a prioridade de "Feature Complete"
para "User Usable": toda funcionalidade pronta deve aparecer imediatamente
no Dashboard, reaproveitando o máximo possível de infraestrutura existente.

Duas peças já existiam, prontas, mas invisíveis:

1. **Contact Intelligence (P0-3)**: `GET /contacts/priority` já rankeava
   contatos por `priority_score` de forma determinística
   (`backend/contacts/intelligence.py`), mas só era consumido dentro de
   `/contatos/[id]` — nada no cockpit `/admin` (o dashboard operacional já
   maduro, ver `DASHBOARD_MVP.md`) sinalizava "quem precisa de atenção
   entre todos os contatos".
2. **Recommendations (P0-4)**: `backend/contacts/recommendations.py`
   (motor puro, determinístico) e o endpoint de execução
   (`POST /contacts/{id}/recommendations/{id}/execute`) estavam completos e
   testados, mas `frontend/app/(dashboard)/contatos/[id]/page.tsx`
   renderizava `{recommendations.map((_, index) => <li key={index} />)}` —
   um item vazio por recomendação. O usuário nunca via o conteúdo.

Era necessário decidir: (a) como expor o ranking de prioridade no cockpit
sem duplicar lógica, e (b) se o mecanismo de execução de ação já existente
no cockpit (`ActionWorkflowControl`, usado pelo AI Operator Center) deveria
ser estendido para cobrir `Recommendation` também.

## Decisão

1. **Adicionar um card "Contatos que precisam de atenção" em `/admin`**,
   implementado como uma camada de visualização pura sobre
   `GET /contacts/priority` — nenhuma lógica de scoring no frontend.
2. **Cada item do painel faz link-through para `/contatos/{id}`** em vez de
   duplicar detalhe ou ação no próprio card do cockpit.
3. **`Recommendation` NÃO foi integrado a `ActionWorkflowControl`.** A
   execução de recomendações continua exclusiva de `/contatos/[id]`, através
   do fluxo próprio já existente (correção do bug de renderização, não um
   componente novo de execução).
4. **Polling a cada 30s** (`NORMAL_INTERVAL_MS`), igual a todo outro widget
   da seção "Operação" do cockpit.
5. **Tipos duplicados manualmente** entre `admin-types.ts` (novo
   `ContactPriorityItem`/`RelationshipTier`/`RelationshipSignal`) e os tipos
   já existentes, equivalentes mas não compartilhados, dentro de
   `contatos/[id]/page.tsx`.
6. **Composição sobre abstração**: nenhuma interface nova, nenhum tipo
   genérico de "ação executável" foi introduzido para unificar
   `OperatorInsight` e `Recommendation`.

## Alternativas consideradas

### A. Adaptar `Recommendation` para o shape `OperatorInsight`
Permitiria reusar `ActionWorkflowControl` (incluindo o painel de preview de
ação, os estados de confirmação, etc.) diretamente no card do cockpit.
**Rejeitada**: `planAction`/`planAlternatives` (`lib/actions.ts`) resolvem
um `actionKind` fechado (`approve_goal`, `retry_job`, `complete_task`,
`reschedule_task`, `create_followup_task`, `schedule_time`,
`open_related_item`) — nenhum mapeia para "execute esta recomendação
através do Tool Registry, revalidando a partir de dados vivos", que é o
contrato real do endpoint de execução de Recommendation. Forçar o encaixe
exigiria ou (a) um `actionKind` novo com uma ramificação de execução
paralela dentro do mesmo componente, aumentando o acoplamento sem reduzir
duplicação de fato, ou (b) enfraquecer a garantia de revalidação que o
endpoint já oferece.

### B. Criar um componente de execução genérico (`ActionControl<T>`)
Generalizar `ActionWorkflowControl` para aceitar qualquer shape de ação via
um adapter/mapper injetado. **Rejeitada por agora**: hoje existem apenas
dois shapes de ação executável no sistema inteiro
(`OperatorInsight`, `Recommendation`). Generalizar uma interface para dois
casos concretos é abstração prematura — o custo de manter uma interface
genérica correta para dois consumidores tende a ser maior que o de manter
dois componentes simples e específicos. Ver "Condições que justificariam
revisar esta decisão" abaixo.

### C. Duplicar o card do cockpit com execução inline
Mostrar a recomendação completa (incluindo botão "Executar") diretamente
no card "Contatos que precisam de atenção", sem exigir clique-through.
**Rejeitada por agora**: exigiria replicar o estado de confirmação, o
tratamento de erro e o preview de ação que `contatos/[id]/page.tsx` já
implementa corretamente. O clique-through é mais barato e mantém uma única
fonte de verdade para a ação. Reavaliar se o uso real mostrar que o
clique-through atrapalha o fluxo de trabalho diário.

### D. Unificar os tipos duplicados num pacote compartilhado agora
Extrair `RelationshipTier`/`RelationshipSignal`/etc. para um único lugar
importado por ambas as páginas. **Adiada**: são hoje só dois consumidores,
o projeto não tem geração automática de tipos a partir do backend (todo
tipo em `admin-types.ts` já é espelhado à mão, por convenção documentada no
topo do próprio arquivo) e a duplicação atual é puramente estrutural (mesmo
shape, comentado como espelhando o mesmo endpoint) — não é duplicação de
lógica.

## Trade-offs

| Decisão | Ganho | Custo aceito |
|---|---|---|
| Link-through em vez de execução inline | Zero duplicação de fluxo de confirmação/erro | Um clique a mais para agir a partir do cockpit |
| Não estender `ActionWorkflowControl` | Sem acoplamento entre dois domínios de ação distintos | Dois componentes de "executar ação" no código em vez de um |
| Polling de 30s (não dedicado) | Consistência com todo o resto do cockpit, zero configuração nova | Sinal de prioridade pode ficar até 30s desatualizado |
| Tipos duplicados manualmente | Sem introduzir infraestrutura de compartilhamento para 2 usos | Risco de desalinhamento se um dos dois lados mudar sem o outro |

## Consequências

- O cockpit `/admin` ganha visibilidade sobre contatos em risco sem
  nenhuma query nova, nenhum endpoint novo, e sem tocar em
  `contacts/intelligence.py` (a lógica de scoring permanece
  exclusivamente backend, conforme o limite arquitetural já estabelecido
  em `CONTACT_INTELLIGENCE_ARCHITECTURE.md`).
- Existem agora dois componentes de "executar uma ação" no frontend
  (`ActionWorkflowControl` para `OperatorInsight`, o fluxo inline de
  `contatos/[id]/page.tsx` para `Recommendation`). Isso é aceito como
  duplicação limitada e intencional, não como dívida técnica silenciosa —
  está registrado aqui e no backlog de refactor.
- Qualquer novo tipo de ação executável que apareça no futuro deve, no
  mínimo, ser comparado contra esses dois shapes antes de crescer um
  terceiro padrão paralelo.

## Evolução futura

Esta decisão deve ser revisitada, não é definitiva. Reavaliar quando:

- Aparecer um **terceiro tipo de ação executável** com formato de
  confirmação semelhante — nesse ponto, três implementações paralelas
  passam a justificar uma abstração real (regra prática: duas
  implementações concretas primeiro, abstração depois, nunca o contrário).
- O uso real mostrar que o **clique-through incomoda** no fluxo diário —
  nesse caso, a Alternativa C (execução inline) deve ser reconsiderada
  especificamente para o card do cockpit, mantendo `contatos/[id]` como
  fallback completo.
- Os tipos duplicados **divergirem** de fato (um lado ganhar um campo que o
  outro não tem) — sinal de que a duplicação deixou de ser só estrutural.
  Nota de uma revisão posterior: os mapas de **label** de
  `RelationshipTier` (`TIER_LABEL` neste painel, `RELATIONSHIP_TIER_LABELS`
  em `contatos/[id]/page.tsx`) já duplicam as mesmas 4 strings hoje — isso
  é dívida de baixo esforço para extrair (ver `docs/TECHNICAL_DEBT.md`),
  não precisa esperar um 3º consumidor para valer a pena resolver, ao
  contrário dos tipos de dado propriamente ditos.
- O volume de contatos ultrapassar o que `contact_priority_candidate_ceiling`
  suporta confortavelmente — nesse ponto vale revisitar tanto o polling
  quanto as duas queries agregadas por trás de `/contacts/priority`.
