# Performance Review — Contact Priority Panel / P0-4 Recommendations

## Rendering
Render de lista trivial, no máximo 10 itens (`limit=10` em
`useContactPriority`). Nenhum cálculo caro por item além de uma ordenação
pequena de sinais (ver "Memoização" abaixo).

## React re-renders
Controlados inteiramente pelo ciclo de poll/cache do react-query — nenhum
estado local extra introduzido que cause re-render fora desse ciclo.

## Memoização
`ContactPriorityPanel.primaryReason()` reordena o array de sinais a cada
render. Irrelevante na escala atual (≤10 itens × poucos sinais cada);
candidato a `useMemo` apenas se o volume de dados crescer de forma
mensurável.

## Hooks
`useContactPriority` é um wrapper fino e correto de react-query — sem
lógica de efeito customizada, nada para usar incorretamente.

## Cálculos caros
Nenhum. A ordenação em `primaryReason()` é O(n log n) sobre, no máximo, uma
dúzia de sinais.

## Requisições de rede
Um GET novo por ciclo de poll (30s) — mesma cadência de todo widget irmão
do cockpit. Sem risco de tempestade de requisições.

## Polling
30s (`NORMAL_INTERVAL_MS`), idêntico a todo outro hook em `admin-api.ts`.
Nenhum nível de polling novo introduzido.

## Cache
O cache próprio do react-query é suficiente nesta escala; nenhuma camada de
cache adicional necessária.

## Queries de banco
Zero queries novas — `last_interaction_at` já estava carregado no objeto
`Contact` ORM. `/contacts/priority` continua sendo exatamente 2 queries
agregadas, independente do tamanho da agenda de contatos (verdade antes
desta mudança também).

## Índices
`ix_tasks_contact_id` e `ix_calendar_contact_id` já existem (confirmado via
migração `2cc4e7d820a6`). Nenhum padrão de query novo que precisasse de
índice novo foi introduzido.

## Tamanho de payload
+1 campo timestamp ISO × até 10 itens — desprezível.

## Bundle size
Um componente novo (~2KB) e um hook novo (~10 linhas) — desprezível frente
ao bundle já existente do admin.

## Code splitting
`/admin` já é seu próprio chunk de rota (padrão do Next.js App Router) —
nenhuma mudança necessária.

## Lazy loading
Não aplicável no tamanho atual; o painel não é candidato a `next/dynamic`
dado seu peso trivial.

## Hidratação
Nenhum estado sensível a SSR (nenhum `Date.now()`/`Math.random()` em tempo
de render no componente novo) — seguro sob hidratação.

## Oportunidades de streaming
Não aplicável — já é um painel react-query client-side dentro de uma
página já inteiramente client-rendered (`"use client"` no topo de
`app/admin/page.tsx`).

## Oportunidades de Server Components
A página `/admin` inteira já é `"use client"` (necessário para
react-query + framer-motion + gráficos interativos) — converter um único
painel para Server Component exigiria reestruturar todo o modelo de
busca de dados da página. Fora de escopo para esta feature.

## Client Components
Uso correto — dado genuinamente interativo, com polling.

## Estimativa de escalabilidade atual
Confortável para um sistema pessoal de usuário único em qualquer tamanho
realista de agenda de contatos.

## Provável primeiro gargalo
`contact_priority_candidate_ceiling` sendo aproximado por uma agenda de
contatos genuinamente grande — nesse ponto, a abordagem de "rankear todo o
conjunto candidato em Python" precisaria virar paginação real em
`/contacts/priority`.

## Plano de escalabilidade
Não urgente; revisitar somente se/quando o uso real se aproximar do teto.
