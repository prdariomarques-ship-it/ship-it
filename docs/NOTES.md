# Notes — arquitetura e prontidão para IA futura

## Por que um router dedicado, não o CRUD genérico

Notas nasceram sobre `create_crud_router` (`api/crud.py`), a mesma factory
genérica usada por `contacts`, `tasks`, `church`, `store`. Reescritas como um
módulo dedicado (`notes/router.py` + `repositories/note.py`) porque os
requisitos reais — busca por texto (título/conteúdo/tags), ordenação
fixadas-primeiro, filtro de arquivadas — não existem na factory genérica, e
adicioná-los lá afetaria todo recurso que a usa (contacts, tasks, church,
store), não só notas. `list()`/`count()`/`get()`/`update()`/`delete()` do
`SQLAlchemyRepository` genérico continuam reaproveitados sem mudança — só a
busca é específica de `NoteRepository`.

## Campos

| Campo | Propósito |
|---|---|
| `title`, `content`, `tags` | Como já existiam antes desta reescrita. |
| `pinned` | Ordena a nota no topo da lista — organização, não estado de ciclo de vida. |
| `archived` | Exclui do filtro padrão sem apagar — memória de longo prazo não deveria acumular ruído na visão do dia a dia, mas também não deveria ser perdida. Não existe convenção de soft-delete no projeto (checado: nenhum model usa `deleted_at`/`is_deleted`), então isto é deliberadamente uma flag de organização própria de Notes, não um substituto de exclusão. |
| `contact_id` (nullable, `ON DELETE SET NULL`) | Reservado, não usado por nenhum endpoint hoje — existe só para que "vincular esta nota a um contato/conversa" seja uma mudança de camada de aplicação no futuro, não uma migration nova. |

`created_by`: não existe como campo separado — `user_id` já cumpre esse papel
(dono do registro), seguindo a mesma convenção de `Goal`, `Task`, `Contact`.
Duplicar como `created_by` seria um campo redundante, não uma funcionalidade
nova.

## Busca

`GET /notes?q=...` filtra em Python (não em SQL) por três motivos:
1. `tags` é uma lista JSON — não existe consulta portável entre SQLite (usado
   nos testes) e Postgres (produção) para "algum elemento contém esta
   substring, sem diferenciar maiúsculas/minúsculas".
2. O volume de notas por usuário, num sistema pessoal de um único operador,
   não justifica otimização prematura.
3. Mantém o contrato do endpoint (`GET /notes?q=...`) estável — é exatamente
   o ponto de extensão para busca semântica futura (abaixo).

## Prontidão para IA futura (arquitetura preparada, nada implementado)

Sem embeddings implementados agora, deliberadamente. O que já existe no
projeto e permite evoluir sem migration nova:

- **Recuperar notas**: já possível via `GET /notes`/`GET /notes/{id}`, sem
  mudança nenhuma.
- **Resumir notas**: um agente pode buscar via API e resumir — não exige
  nada na camada de dados.
- **Busca semântica**: `MemoryManager.remember(db, content, source=...)`
  (`memory/manager.py`) já é usado hoje para outros domínios (ex.:
  `GoalService._remember_completion`, `source="goal"`). Estender esse mesmo
  padrão para notas (`source="note"`) no momento de criar/editar uma nota
  seria a extensão natural — sem tocar no schema de `notes`, e sem mudar o
  contrato de `GET /notes?q=...` (que continuaria funcionando como busca
  textual determinística; uma versão semântica poderia ser uma opção
  adicional do mesmo endpoint, não um substituto).
- **Vincular notas a conversas**: `contact_id` (nullable, já na tabela) é
  exatamente essa preparação — nenhuma migration necessária quando essa
  funcionalidade for implementada de verdade.

Nenhum destes é implementado nesta release — apenas confirmado que a
arquitetura atual não bloqueia nenhum deles.
