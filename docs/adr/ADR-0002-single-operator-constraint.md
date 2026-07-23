# ADR-0002: Release 1.x suporta exclusivamente um único operador

**Status:** Aceito
**Data:** 2026-07-23
**Origem:** Red-team engineering audit da Contact Priority Panel / P0-4
Recommendations (Release 1.5).

## Contexto

O red-team audit da feature de Contact Priority identificou o seguinte,
com precisão que passes de revisão anteriores haviam descrito como "por
design" sem tratá-lo como um gate real:

`Contact` (`backend/models/contact.py`) não tem coluna de dono
(`user_id`) — é um único endereço de contatos compartilhado. Isso é
correto **somente** enquanto existir exatamente um usuário real do
sistema. `Notes`/`Tasks`/`Calendar` já são escopados por `user_id`, mas
`Contact` em si, e por consequência todo o Contact Workspace/Intelligence/
Recommendations (P0-2/P0-3/P0-4) construído sobre ele, **não são**.

O sistema já tem um modelo de `UserRole` e um endpoint `/admin/users`
(criação de usuários) — ou seja, nada impede tecnicamente que um segundo
usuário real seja criado hoje. Se isso acontecer sem esta constraint ser
respeitada primeiro, o segundo usuário veria e poderia agir sobre
**todos** os contatos, tarefas vinculadas a contatos, recomendações e
sinais de relacionamento do primeiro usuário — não é uma dívida técnica
silenciosa, é uma exposição real de privacidade entre usuários.

## Decisão

**Release 1.x (esta e as seguintes até que esta ADR seja explicitamente
revisada) suporta exclusivamente um único operador.**

Isso é tratado como uma **restrição arquitetural documentada**, não como
item de `docs/TECHNICAL_DEBT.md` — dívida técnica é algo que se paga
oportunisticamente; esta é uma pré-condição que **bloqueia** uma
funcionalidade inteira (multi-usuário) até ser resolvida deliberadamente.

Concretamente:

1. Nenhuma criação de um segundo usuário real com acesso a Contacts deve
   acontecer antes de um redesenho explícito do modelo de propriedade de
   `Contact`.
2. `backend/models/contact.py` carrega um comentário apontando para esta
   ADR, no ponto exato da ausência da coluna de dono.
3. `docs/TECHNICAL_DEBT.md` referencia esta ADR em vez de listar "Contacts
   não são owner-scoped" como um item de dívida entre outros.

## Alternativas consideradas

### A. Tratar como dívida técnica comum, priorizar oportunisticamente
**Rejeitada.** Dívida técnica comum assume que o sistema continua correto
enquanto não for pago — aqui, o sistema deixa de ser correto (privacidade
quebrada) no exato momento em que um segundo usuário é criado. Tratar como
dívida comum sub-representa o risco.

### B. Redesenhar `Contact` para ser owner-scoped agora, preventivamente
**Rejeitada por agora.** Não há um segundo usuário real hoje, e o redirecionamento
estratégico da Release 1.5 é explicitamente contra trabalho especulativo
("Desenvolvimento Guiado por Uso" — não implementar antes de existir uso
real). Redesenhar a propriedade de Contact é um projeto de escopo
significativo (schema, migração, toda query que hoje assume "todos os
contatos" precisaria decidir come/se filtrar por usuário) — não deve ser
feito sem uma necessidade real de multi-usuário confirmada.

### C. Bloquear a criação de um segundo usuário no código (enforcement técnico)
**Não implementada nesta rodada** (fora de escopo desta ADR, que é
documentação, não implementação, conforme instrução explícita do
hardening). Vale considerar como um enforcement real (ex.: um check em
`POST /admin/users` que impede criar um segundo usuário enquanto Contact
não for owner-scoped) — ver "Evolução futura".

## Trade-offs

| Decisão | Ganho | Custo aceito |
|---|---|---|
| Documentar como constraint, não como dívida | Sinaliza corretamente a severidade (bloqueante, não oportunístico) | Nenhum enforcement técnico ainda — depende de processo/disciplina humana |
| Não redesenhar `Contact` agora | Evita trabalho especulativo antes de necessidade real | Redesenho futuro será um projeto real, não um ajuste incremental |

## Consequências

- Qualquer decisão de criar um segundo usuário real precisa primeiro
  revisitar explicitamente esta ADR — ela é o gate.
- `models/contact.py`, `docs/TECHNICAL_DEBT.md` e esta ADR formam uma
  cadeia de referência cruzada que qualquer engenheiro futuro encontra ao
  tocar em qualquer um dos três pontos.

## Evolução futura

Esta ADR deve ser revisitada, com uma proposta técnica real de redesenho
de propriedade de `Contact` (coluna `user_id`, migração, e uma decisão
explícita sobre se contatos passam a ser por-usuário ou se um modelo de
"contatos compartilhados com permissão explícita" faz mais sentido para o
caso de uso real), no momento em que:

- Uma necessidade real e concreta de suportar um segundo usuário surgir
  (não especulação).
- Alguém propuser criar uma segunda conta de usuário no sistema por
  qualquer motivo — isso deve disparar a revisão desta ADR antes de a
  conta ser criada, não depois.

Até lá, esta constraint permanece em vigor.
