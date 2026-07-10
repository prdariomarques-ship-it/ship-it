# Migration Fix Report — PostgreSQL ENUM Creation

**Data**: 2026-07-10
**Bug reportado**: `sqlalchemy.exc.ProgrammingError` / `asyncpg.exceptions.UndefinedObjectError: type "messagedeliverystatus" does not exist` ao rodar `ALTER TABLE messages ADD COLUMN delivery_status messagedeliverystatus`.
**Status**: Corrigido, testado e validado. Commit `14b5bca`.

## Causa raiz

O `CREATE TYPE` de um ENUM do PostgreSQL não é emitido por toda operação DDL do
Alembic/SQLAlchemy — só quando o `Enum`/`postgresql.ENUM` está anexado a um objeto
`Table` **completo** (com colunas) no momento em que o DDL roda. SQLAlchemy usa um
listener de evento ligado à `Table` (`before_create`/`after_drop`) para emitir
`CREATE TYPE`/`DROP TYPE` antes/depois do `CREATE TABLE`/`DROP TABLE` correspondente.

- `op.create_table('jobs', ..., sa.Column('status', sa.Enum(..., name='jobstatus')), ...)`
  passa a definição completa da coluna → o listener dispara e `CREATE TYPE jobstatus`
  é emitido antes do `CREATE TABLE jobs`. É assim que os seis enums da migration
  inicial (`jobstatus`, `userrole`, `messagedirection`, `messagemediatype`,
  `taskstatus`, `taskpriority`) sempre funcionaram.

- `op.add_column('messages', sa.Column('delivery_status', sa.Enum(..., name='messagedeliverystatus')))`
  (migration `d3e16cbf2688`, saída padrão do `alembic revision --autogenerate`) é um
  `ALTER TABLE ADD COLUMN` isolado — não passa por `Table.create()`, então o listener
  que criaria o tipo automaticamente nunca é acionado. O `ALTER TABLE` tenta usar
  `messagedeliverystatus` como se já existisse e falha, porque o `CREATE TYPE`
  correspondente nunca foi emitido.

O model ORM (`models/message.py::MessageDeliveryStatus`) estava correto — o nome do
tipo que ele gera (`Enum(MessageDeliveryStatus)` → `messagedeliverystatus`, minúsculo
do nome da classe) bate exatamente com o nome usado na migration. O defeito era
inteiramente da migration, não do model.

### Bug relacionado, mesma causa raiz, encontrado durante a validação de roundtrip

Ao validar downgrade → upgrade completos, apareceu um segundo bug real na direção
oposta: `790826c45a84_initial_schema.py::downgrade()` chama `op.drop_table('jobs')`
apenas com o nome da tabela, sem colunas — o mesmo listener (que depende do `Enum`
estar anexado a um `Table` com colunas) também não dispara aqui, então nenhum
`DROP TYPE` era emitido. Um `alembic downgrade base` completo removia todas as
tabelas mas deixava os seis tipos ENUM da migration inicial órfãos no banco; a
tentativa seguinte de `alembic upgrade head` falhava com
`asyncpg.exceptions.DuplicateObjectError: type "jobstatus" already exists`. Corrigido
junto por ser a mesma causa raiz e por ser exigido pela validação de roundtrip
completo.

## Solução adotada

Padrão oficial do cookbook do Alembic para ENUMs no PostgreSQL
(https://alembic.sqlalchemy.org/en/latest/cookbook.html#postgresql-enum-types):
gerenciar o ciclo de vida do tipo explicitamente, fora do controle implícito do
SQLAlchemy.

1. `postgresql.ENUM(..., name='messagedeliverystatus', create_type=False)` —
   `create_type=False` desliga qualquer tentativa implícita do SQLAlchemy de
   criar/dropar o tipo por conta própria quando a coluna é manipulada; o ciclo de
   vida do tipo passa a ser 100% explícito no código da migration.
2. `upgrade()`: `_delivery_status_enum.create(op.get_bind(), checkfirst=True)` **antes**
   de qualquer `op.add_column` que use o tipo — `CREATE TYPE` roda garantidamente
   antes do `ALTER TABLE`. `checkfirst=True` torna a criação idempotente: se o tipo
   já existir (banco que rodou uma versão anterior/parcial desta migration), o
   `CREATE TYPE` vira no-op em vez de erro `DuplicateObjectError`.
3. `downgrade()`: dropa a coluna primeiro (`op.drop_column`) e só then remove o tipo
   (`_delivery_status_enum.drop(op.get_bind(), checkfirst=True)`) — nesta ordem
   porque o Postgres recusa `DROP TYPE` enquanto uma coluna ainda o referencia.
   `checkfirst=True` também torna essa remoção idempotente.
4. Mesmo padrão aplicado a `790826c45a84_initial_schema.py::downgrade()`: depois de
   todas as tabelas serem removidas (portanto nenhuma coluna mais referencia os seis
   tipos), cada um é dropado explicitamente com `checkfirst=True`.

```python
_delivery_status_enum = postgresql.ENUM(
    'SENT', 'DELIVERED', 'READ', 'FAILED', name='messagedeliverystatus', create_type=False
)

def upgrade() -> None:
    _delivery_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('messages', sa.Column('provider_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('messages', sa.Column('delivery_status', _delivery_status_enum, nullable=True))

def downgrade() -> None:
    op.drop_column('messages', 'delivery_status')
    op.drop_column('messages', 'provider_timestamp')
    _delivery_status_enum.drop(op.get_bind(), checkfirst=True)
```

`upgrade()` de `790826c45a84` não foi alterado — a criação dos seis enums via
`op.create_table(...)` já era correta. Nenhuma outra migration (`abb2a2bf950e`,
`8d535824ec8f`, `61c82eeb3be5`, `0e6459491047`) cria ou depende de ENUM.

## Por que a solução é correta

- **Não depende de comportamento implícito do SQLAlchemy**: `create_type=False` +
  `.create()`/`.drop()` explícitos removem qualquer ambiguidade sobre quando o tipo é
  criado ou removido — o ciclo de vida do tipo é uma linha de código visível na
  migration, não um efeito colateral de qual `op.*` foi chamado.
- **Idempotente por construção**: `checkfirst=True` consulta o catálogo do Postgres
  (`pg_type`) antes de agir, então rodar a mesma migration mais de uma vez, ou contra
  um banco que já tenha o tipo por uma tentativa anterior (inclusive uma tentativa
  falha do bug original, que pode ter deixado o tipo criado manualmente por alguém
  investigando), nunca produz `DuplicateObjectError`/`UndefinedObjectError`.
  Verificado nas 5 validações abaixo.
- **Ordem de operações correta em ambas as direções**: `CREATE TYPE` sempre antes do
  `ALTER TABLE ADD COLUMN` que o usa; `DROP TYPE` sempre depois do
  `DROP COLUMN`/`DROP TABLE` que o referenciava — nunca há uma janela em que o tipo é
  referenciado antes de existir ou removido enquanto ainda está em uso.
- **Downgrade remove o tipo somente quando seguro**: cada tipo (`messagedeliverystatus`
  e os seis da migration inicial) é usado por exatamente uma coluna em todo o
  schema — confirmado por busca no repositório inteiro antes da correção. Nenhum
  outro tipo é compartilhado entre migrations, então dropá-lo no downgrade da
  migration que o criou nunca quebra uma migration diferente. Se um tipo fosse
  compartilhado, `DROP TYPE` falharia com erro de dependência do próprio Postgres
  (não removeria silenciosamente algo em uso) — a abordagem é segura mesmo nesse
  caso hipotético, só deixaria de ser idempotente sem investigação adicional, o que
  não se aplica a este schema.
- **Não é workaround**: é o padrão oficialmente documentado pelo projeto Alembic para
  este cenário exato (ENUM + operação de coluna fora de `create_table`), não uma
  solução ad-hoc.

## Compatibilidade com bancos existentes

- **Instalações novas** (banco vazio): `alembic upgrade head` antes falhava sempre ao
  chegar em `d3e16cbf2688`. Agora completa a cadeia inteira sem erro.
- **Instalações já existentes, paradas antes de `d3e16cbf2688`** (por terem batido
  neste mesmo bug antes): continuam a migração normalmente a partir de onde estavam.
- **Instalações que já tenham `messagedeliverystatus` criado manualmente** (por
  alguém contornando o bug antes desta correção): `checkfirst=True` detecta o tipo
  existente e pula a criação — sem erro, sem duplicação.
- **Nenhuma alteração de schema além do defeito em si**: a coluna `delivery_status`
  continua com o mesmo nome, tipo lógico e valores (`SENT`, `DELIVERED`, `READ`,
  `FAILED`); nenhum model SQLAlchemy, API ou teste existente foi alterado.
- **Downgrade completo até a base**: agora limpa os seis tipos ENUM da migration
  inicial além do `messagedeliverystatus`, sem deixar tipos órfãos que quebrem uma
  reexecução futura do upgrade.

## Arquivos alterados

- `backend/alembic/versions/d3e16cbf2688_message_provider_timestamp_and_delivery_.py`
- `backend/alembic/versions/790826c45a84_initial_schema.py`

Nenhum model, nenhuma API, nenhum teste foi alterado. Nenhuma migration foi apagada,
renumerada ou teve `revision`/`down_revision` alterado. Nenhum schema de banco foi
editado manualmente.

## Resultado das validações

Executado com PostgreSQL 16 real e local (não SQLite, não mock), para exercitar o
comportamento real de DDL do Postgres:

| Validação | Resultado |
|---|---|
| Banco vazio → `alembic upgrade head` | ✅ completa a cadeia inteira (790826c45a84 → 0e6459491047) |
| `alembic downgrade base` a partir de head | ✅ remove todas as tabelas e todos os 7 tipos ENUM (6 da inicial + `messagedeliverystatus`), sem tipos órfãos (`\dT+` retorna 0 linhas) |
| `alembic upgrade head` novamente após downgrade completo (roundtrip) | ✅ completa sem `DuplicateObjectError` |
| Banco parcialmente migrado (parado em `abb2a2bf950e`) → `alembic upgrade head` | ✅ continua e completa normalmente a partir do ponto parcial |
| `alembic current` ao final | ✅ `0e6459491047 (head)` |
| `pytest` (suíte completa) | ✅ 479 passed, 0 falhas, 0 regressões |
| `ruff check .` | ✅ All checks passed |
| `docker compose config` | ✅ válido (exit 0) |
| mypy | Não configurado no projeto (limitação preexistente, documentada em `ROADMAP_v1.1.md` P3-2 e `PRODUCTION_APPROVAL.md`) — fora do escopo desta correção |

Todas as validações passaram — commit já realizado (`14b5bca`), conforme a condição
"só commitar se todas as validações forem aprovadas".
