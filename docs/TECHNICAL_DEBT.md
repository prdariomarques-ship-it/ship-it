# Technical Debt — Contact Priority Panel / P0-4 Recommendations

Inventário de dívida técnica identificado nas três rodadas de revisão de
engenharia da feature "Contatos que precisam de atenção" (cockpit `/admin`)
e da correção do bug de renderização de Recommendations (commit `463ff99`,
docs de revisão em `1e2dd67`). Ver também `docs/adr/ADR-0001-contact-priority-panel.md`
para o raciocínio arquitetural por trás dos itens marcados como "aceitos".

**Nota:** a ausência de escopo por usuário em `Contact` (que permitiria a
um segundo usuário real ver/agir sobre os contatos do primeiro) **não**
está listada como item de dívida técnica abaixo. Foi deliberadamente
promovida a restrição arquitetural bloqueante — ver
`docs/adr/ADR-0002-single-operator-constraint.md`. Dívida técnica é algo
que se paga quando conveniente; esta é uma pré-condição que bloqueia uma
funcionalidade inteira (multi-usuário) até ser resolvida.

## Critical

Nenhum item.

## High

### Suíte de testes frontend com falhas intermitentes sob concorrência
- **Descrição:** 7 arquivos de teste (`GoalForm.test.tsx`,
  `CalendarEventForm.test.tsx`, `MemorySearch.test.tsx`, `NoteForm.test.tsx`,
  `AdminWhatsAppPage.test.tsx`, `AdminSettingsPage.test.tsx`,
  `use-toast.test.tsx`) falham de forma intermitente quando a suíte inteira
  roda com concorrência total — confirmado pré-existente via execução do
  checkout limpo (sem nenhuma mudança desta feature) e via reexecução
  isolada (`--no-file-parallelism`), onde todos passam.
- **Impacto no negócio:** baixo diretamente, mas alto indiretamente — reduz
  a confiança em todo resultado de CI futuro, não só desta feature.
- **Impacto de engenharia:** alto — uma quebra real futura pode se esconder
  atrás de "ah, é só a suíte flaky de novo".
- **Esforço estimado:** médio (ajuste de `testTimeout`/`maxForks` no
  `vitest.config`, seguido de validação repetida).
- **Prioridade:** Alta.
- **Quando corrigir:** antes que mais 2-3 ciclos de feature aumentem ainda
  mais a lista de arquivos afetados.

## Medium

### Falta rate limiting no endpoint de execução de recomendação
- **Descrição:** `POST /contacts/{id}/recommendations/{id}/execute` não tem
  rate limiting dedicado, mesmo sendo o único caminho de escrita deste
  módulo e disparando uma ação real via Tool Registry.
- **Impacto no negócio:** baixo hoje (sistema de usuário único).
- **Impacto de engenharia:** médio — vira relevante assim que o sistema
  ganhar mais de um usuário.
- **Esforço estimado:** baixo (reaproveitar `services/rate_limit.py`, já
  usado em `auth/router.py`).
- **Prioridade:** Média.
- **Quando corrigir:** antes de qualquer exposição multi-usuário, ou
  oportunisticamente na próxima mudança no módulo de contatos.

### Falta teste dedicado para `ContactPriorityPanel`/`useContactPriority`
- **Descrição:** o componente e o hook só são exercitados indiretamente
  (a página `/admin` compila e monta com sucesso); não há teste direto do
  estado vazio, do mapeamento de badge por tier, ou do `href` do link.
- **Impacto no negócio:** baixo.
- **Impacto de engenharia:** médio — risco real de regressão silenciosa.
- **Esforço estimado:** baixo (2-3h).
- **Prioridade:** Média.
- **Quando corrigir:** na próxima vez que este painel for tocado por
  qualquer motivo.

### Mapas de label de tier de relacionamento duplicados
- **Descrição:** `TIER_LABEL`/`TIER_TONE` em `ContactPriorityPanel.tsx` e
  `RELATIONSHIP_TIER_LABELS` em `contatos/[id]/page.tsx` repetem as mesmas
  4 strings em português para o mesmo enum `RelationshipTier`, sem fonte
  compartilhada.
- **Impacto no negócio:** baixo (risco cosmético de divergência de texto).
- **Impacto de engenharia:** médio — violação real de DRY.
- **Esforço estimado:** baixo (1-2h).
- **Prioridade:** Média.
- **Quando corrigir:** oportunisticamente, ou assim que um 3º consumidor de
  `RelationshipTier` aparecer.

## Low

- **Números mágicos** (`limit=10` em `useContactPriority`, e os demais
  limits inline em `admin-api.ts`) — convenção já existente no projeto
  inteiro, não uma novidade desta feature. Esforço: baixo, mas fora de
  escopo corrigir isoladamente para só este hook.
- **`primaryReason()` sem memoização** — reordena o array de sinais a cada
  render; irrelevante na escala atual (≤10 itens, poucos sinais cada).
  Esforço: trivial (`useMemo`).
- **Nenhuma telemetria de uso do painel ou de aceitação de recomendações**
  — o princípio "aprender com uso real" do próprio redirecionamento da
  Release 1.5 ainda não gera nenhum dado para este painel especificamente.
  Esforço: médio (decisão de design pequena, não só código).
- **Dois componentes paralelos de execução de ação**
  (`ActionWorkflowControl` para `OperatorInsight`, o fluxo inline de
  `contatos/[id]/page.tsx` para `Recommendation`) — trade-off aceito e
  documentado em ADR-0001, não uma dívida silenciosa. Revisitar somente na
  condição explícita descrita lá (3º shape de ação aparecer).
- **Nenhum suporte a dark mode no shell `(dashboard)`** — pré-existente,
  fora do escopo desta feature; o shell `/admin` é tema único fixo (escuro),
  não um alternador — confirmado, não uma lacuna de implementação.
