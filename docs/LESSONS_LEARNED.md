# Lições Aprendidas — Contact Priority Panel / P0-4 Recommendations (Release 1.5)

Registro para quem entrar no projeto depois: o que funcionou, o que travou,
o que descobrimos e o que deveria virar padrão. Escrito logo após a
implementação do painel "Contatos que precisam de atenção" e da correção do
bug de renderização das Recommendations (commit `463ff99`).

## O que funcionou bem

- **Seguir o padrão existente em vez de inventar um novo.** `ContactPriorityPanel`
  copiou a forma exata de `GoalsPanel`/`TasksPanel` (mesmo layout de card,
  mesmo uso de `EmptyState`, mesmo `Badge`) e `useContactPriority` copiou a
  forma exata de todo hook em `admin-api.ts` (react-query + `refetchInterval`).
  Zero decisão de design nova precisou ser tomada — só reconhecer o padrão e
  segui-lo. Isso tornou a revisão de código trivial: qualquer um que já
  conhece uma dessas duas famílias reconhece a outra instantaneamente.
- **Reaproveitar helpers de formatação já existentes.** `formatRelativeTime`
  já existia em `lib/format.ts` e já produzia exatamente "Nd atrás" — a
  forma que "dias desde a última interação" precisava. Não escrevemos
  nenhuma lógica de data nova.
- **Separar "consumir dados" de "decidir o que fazer com eles".** O painel
  nunca decide prioridade, nunca calcula sinais — só renderiza o que o
  backend já decidiu (`contacts/intelligence.py`). Esse limite, definido
  antes na arquitetura do P0-3/P0-4, tornou a implementação do painel
  praticamente sem ambiguidade: não havia decisão de "onde fica essa regra"
  para tomar.
- **Baseline comparável antes de acusar regressão.** Rodar a mesma bateria
  de testes contra o checkout limpo (sem nenhuma mudança) antes de assumir
  que uma falha era culpa da implementação evitou perseguir um fantasma.

## O que atrasou o desenvolvimento

- **Isolamento em worktree perde `node_modules` (e qualquer coisa
  gitignored).** `git worktree add` não copia arquivos não versionados. A
  primeira tentativa (symlink para o `node_modules` do checkout principal)
  funcionou para `tsc`/`eslint`/`vitest`, mas quebrou o build de produção —
  o Turbopack tem uma verificação própria de sandboxing de filesystem que
  rejeita um symlink apontando para fora da árvore do projeto
  (`Symlink [project]/node_modules is invalid, it points out of the
  filesystem root`). A correção foi trocar o symlink por uma cópia real via
  `cp -al` (hardlink, mesmo filesystem, sem custo extra de disco).
- **Redirecionar output de comando para um caminho que não existe falha
  silenciosamente feio.** Ao rodar `tsc`/`eslint`/`vitest` em background
  redirecionando para um arquivo de log, um erro de caminho (diretório
  inexistente) faz o shell reportar `TSC_EXIT: 1` — indistinguível, à
  primeira vista, de uma falha real da ferramenta. A causa raiz só apareceu
  ao ler o conteúdo real do log (a mensagem "No such file or directory" do
  próprio bash), não o código de saída do wrapper.
- **Trabalho não commitado em duas frentes independentes no mesmo working
  tree.** O P0-3/P0-4 (relevante) e uma mudança de Drive provider (não
  relacionada) estavam misturados nos arquivos modificados/untracked. Isso
  não bloqueou o trabalho, mas exigiu atenção deliberada no `git add` para
  não commitar as duas frentes juntas.

## Descobertas inesperadas

- **~90% do "Dashboard MVP" pedido em `REDIRECIONAMENTO_RELEASE_1_5.md` já
  existia, ao vivo, em `/admin`.** Foi construído numa iniciativa anterior
  (`DASHBOARD_MVP.md`) e nunca desativado — só não estava sendo tratado como
  "o" dashboard oficial. O maior risco do ciclo não era "falta backend", era
  reconstruir algo que já existe por falta de descoberta.
- **O bug de Recommendations era pior que "não implementado".** O
  `contatos/[id]/page.tsx` já buscava `recommendations` da API e renderizava
  `<li key={index} />` — um item vazio por recomendação. Do ponto de vista
  do usuário, isso é indistinguível de "quebrado", não de "faltando".
  `unknown[]` no lugar de um tipo real escondeu isso do TypeScript.
- **`ActionWorkflowControl` não é reutilizável como está.** Está fortemente
  acoplado ao shape `OperatorInsight` (via `planAction`/`planAlternatives`
  em `lib/actions.ts`), que só conhece os `actionKind` do Operator Center.
  Adaptar `Recommendation` para esse componente exigiria ou um adapter não
  trivial ou duplicar o componente — decidimos não fazer isso agora (ver
  ADR-0001).

## Fontes de dívida técnica

- **Labels de tier de relacionamento duplicados.** `ContactPriorityPanel.tsx`
  define seu próprio `TIER_LABEL`/`TIER_TONE`; `contatos/[id]/page.tsx` já
  tinha `RELATIONSHIP_TIER_LABELS` com as mesmas 4 strings. Nenhuma fonte
  compartilhada. Achado só na terceira rodada de revisão — mostra que vale
  a pena, da próxima vez, perguntar explicitamente "esse enum já tem um
  mapa de label em algum lugar?" antes de escrever um novo, não só depois.
- Suite de testes frontend com falhas intermitentes sob concorrência total
  (`GoalForm`, `CalendarEventForm`, `MemorySearch`, `NoteForm`,
  `AdminWhatsAppPage`, `AdminSettingsPage`, `use-toast`) — confirmado
  pré-existente via baseline no checkout limpo, não introduzido por este
  trabalho, mas nunca endereçado antes.
- Tipos duplicados manualmente (`RelationshipTier`/`RelationshipSignal`
  existem tanto em `admin-types.ts` quanto inline em `contatos/[id]/page.tsx`)
  — decisão deliberada de não introduzir um pacote de tipos compartilhado
  para dois usos (ver ADR-0001).
- `ActionWorkflowControl` continua servindo só a um shape (`OperatorInsight`)
  — se um terceiro tipo de ação parecida com essa aparecer, vale revisitar
  uma abstração real.

## O que deveria virar padrão do projeto

- **Todo novo widget do cockpit `/admin` segue exatamente o padrão:**
  1 hook em `admin-api.ts` (react-query + `refetchInterval` de
  `LIVE_INTERVAL_MS`/`NORMAL_INTERVAL_MS`), 1 tipo em `admin-types.ts` com o
  comentário explícito de qual arquivo backend ele espelha, 1 componente em
  `components/admin/` no estilo `EmptyState`/`Badge`/card, e o card
  encaixado na seção "Operação" de `app/admin/page.tsx`.
- **Nenhum widget de visualização deve decidir lógica de negócio.** Se uma
  pergunta tipo "isso é urgente?" aparecer no componente de UI, a resposta
  já deveria ter vindo pronta do backend.
- **Rodar o baseline (checkout limpo) antes de reportar qualquer falha de
  teste como regressão** — isso deveria ser rotina, não uma investigação
  ad-hoc, dado o quanto essa suíte já é conhecida como sensível a
  concorrência de CPU.

## Padrões que vale reaproveitar

- O par hook (`admin-api.ts`) + tipo espelhado (`admin-types.ts`) + painel
  (`components/admin/*Panel.tsx`) é o "molde" correto para qualquer nova
  informação que precise aparecer no cockpit.
- Link-through em vez de duplicar UI de execução: quando dois lugares
  precisam mostrar/agir sobre a mesma entidade, prefira linkar para a página
  que já é a fonte única de verdade em vez de replicar o fluxo de ação.

## Erros a evitar

- Não redirecionar output de comando de longa duração para um caminho sem
  verificar antes que o diretório existe — o erro de shell some dentro do
  código de saída do wrapper.
- Não presumir que um symlink resolve tudo em ambientes isolados (worktree);
  ferramentas com sandboxing de filesystem (Turbopack) podem rejeitá-lo
  mesmo quando outras ferramentas (tsc, eslint, vitest) o aceitam sem
  reclamar.
- Não reescrever cópia de UI "só porque parece redundante" sem antes checar
  se o texto exato é usado por uma asserção de teste existente — a primeira
  tentativa deste trabalho trocou "ainda" por "no momento" no estado vazio
  de Recommendations sem necessidade, quebrando um teste já existente.

## Observações sobre testes

- A suíte inteira falha de forma diferente a cada execução sob concorrência
  total (arquivos diferentes, subtestes diferentes) — sintoma clássico de
  timeout sensível a CPU, não de teste realmente quebrado. Rodar os
  arquivos suspeitos sozinhos (`--no-file-parallelism`) é o jeito correto de
  diferenciar "flaky" de "quebrado de verdade".
- O teste novo do fluxo de execução de recomendação precisou de um texto de
  explicação distinto do já usado no fixture de sinais de relacionamento —
  reaproveitar o mesmo texto em dois lugares do mesmo fixture quebra
  queries `getByText` (que exigem unicidade) mesmo quando o comportamento
  da aplicação está correto.

## Observações de performance

- O endpoint `/contacts/priority` já era de 2 queries agregadas (não uma
  por contato) antes deste trabalho — adicionar `last_interaction_at` não
  mudou esse número (o campo já vinha carregado no objeto `Contact`).
- O painel do cockpit usa o mesmo intervalo de polling (30s) de todo outro
  widget da seção "Operação" — não há necessidade de um intervalo dedicado
  para esta informação.

## Observações de segurança

- Nenhuma superfície nova: o endpoint reaproveitado já era autenticado e
  não expunha nada de sensível; o único campo novo (`last_interaction_at`)
  já estava implicitamente disponível via `/contacts/{id}/workspace`.
- Nem `/contacts/priority` nem o endpoint de execução de recomendação têm
  rate limiting dedicado — isso já era verdade antes deste trabalho, não é
  uma regressão, mas vale registrar como pendência (ver ADR-0001 e o
  backlog de refactor).

## Sobre tema visual (descoberta confirmada, não assumida)

`/admin` é um tema único fixo (escuro) — `frontend/styles/admin.css` só
define uma paleta `.admin-theme`, sem variante `.dark`/light nem alternador.
O painel novo está corretamente consistente com isso porque usa os mesmos
tokens semânticos de todo componente irmão. Já o shell `(dashboard)` (onde
a correção de Recommendations vive) não tem nenhum sistema de tema —
confirmado em `frontend/styles/globals.css`, nenhuma regra de dark mode
existe ali. Vale confirmar isso via grep antes de assumir "provavelmente
já suporta dark mode" em qualquer PR futuro que toque em UI — a suposição
errada nos dois sentidos (assumir que suporta quando não suporta, ou
vice-versa) é fácil de fazer sem checar.

## Melhorias futuras

- Adaptar (ou criar um análogo dedicado a) `ActionWorkflowControl` para
  `Recommendation`, se o clique-through para o Contact Workspace se mostrar
  incômodo no uso real.
- Investigar e estabilizar a suíte de testes flaky (ver backlog de
  refactor) — hoje reduz a confiança do sinal de CI a cada execução.
- Avaliar rate limiting no endpoint de execução de recomendação, já que ele
  dispara uma ferramenta real (Tool Registry) a partir de uma ação do
  usuário.
