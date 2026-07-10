# Migration Fix Report — PostgreSQL ENUM Creation

**Data**: 2026-07-10
**Bug reportado**: `sqlalchemy.exc.ProgrammingError` / `asyncpg.exceptions.UndefinedObjectError: type "messagedeliverystatus" does not exist` ao rodar `ALTER TABLE messages ADD COLUMN delivery_status messagedeliverystatus`.
**Status**: Corrigido, testado e validado.

## Causa raiz

O tipo ENUM do PostgreSQL não é criado automaticamente por toda operação DDL do
Alembic/SQLAlchemy — só quando o `Enum`/`postgresql.ENUM` está anexado a um objeto
`Table` completo (com colunas) no momento em que o DDL é emitido. SQLAlchemy usa um
listener de evento (`before_create`/`after_drop` no `Table`) para emitir
`CREATE TYPE`/`DROP TYPE` antes/depois do `CREATE TABLE`/`DROP TABLE` correspondente.

- `op.create_table('jobs', ..., sa.Column('status', sa.Enum(..., name='jobstatus')), ...)`
  passa a definição completa da coluna — o listener dispara e `CREATE TYPE jobstatus`
  é emitido antes do `CREATE TABLE jobs`. Isso já funcionava corretamente para todos
  os enums da migration inicial (`jobstatus`, `userrole`, `messagedirection`,
  `messagemediatype`, `taskstatus`, `taskpriority`).

- `op.add_column('messages', sa.Column('delivery_status', sa.Enum(..., name='messagedeliverystatus')))`
  (migration `d3e16cbf2688`) é um `ALTER TABLE ADD COLUMN` — não passa por
  `Table.create()`, então o listener que criaria o tipo automaticamente nunca é
  acionado. O `ALTER TABLE` tenta usar `messagedeliverystatus` como se já existisse,
  e falha porque o `CREATE TYPE` correspondente nunca foi emitido.

Este é o autogenerate padrão do Alembic (`op.add_column` com `sa.Enum(...)` inline) —
um problema conhecido e documentado do Alembic com PostgreSQL, não um erro de digitação
ou de nomeação: `messagedeliverystatus` bate exatamente com o nome que
`Enum(MessageDeliveryStatus)` gera em `models/message.py` (nome padrão = classe em
minúsculas), então o modelo ORM está correto — só a migration que faltava criar o
tipo explicitamente.

### Bug relacionado encontrado durante a validação de roundtrip

Ao validar downgrade → upgrade completos (exigido pela tarefa), foi descoberto um
segundo bug real, mesma causa raiz, direção oposta: `790826c45a84_initial_schema.py::downgrade()`
chama `op.drop_table('jobs')` apenas com o nome da tabela, sem colunas — então o
listener de `DROP TYPE` (que depende do `Enum` estar anexado ao `Table`) também nunca
dispara aqui. Resultado: um `alembic downgrade base` completo dropava todas as
tabelas, mas deixava os seis tipos ENUM da migration inicial órfãos no banco. Uma
tentativa seguinte de `alembic upgrade head` falhava com
`asyncpg.exceptions.DuplicateObjectError: type "jobstatus" already exists`, quebrando
o roundtrip completo (reprodução e correção documentadas abaixo, junto com o bug
principal, já que fazem parte da mesma cadeia de causa e a tarefa exige "roundtrip
completo" funcionando antes do commit).

## Por que o ENUM não existia

Resumo direto: porque o ponto de criação do tipo (`CREATE TYPE`) depende de o
SQLAlchemy "ver" o `Enum` como parte da definição completa de uma `Table` no momento
do DDL. `op.add_column` isoladamente nunca fornece esse contexto — é preciso criar o
tipo explicitamente antes do `ALTER TABLE`.

## Solução implementada

Padrão recomendado pelo próprio Alembic para este caso (documentado em
"Working with sqlalchemy.types.Enum" — https://alembic.sqlalchemy.org/en/latest/cookbook.html#postgresql-enum-types):
usar `postgresql.ENUM(..., create_type=False)` na definição da coluna, e chamar
`.create(bind, checkfirst=True)`/`.drop(bind, checkfirst=True)` explicitamente no
`upgrade()`/`downgrade()`. `create_type=False` impede que o SQLAlchemy tente também
criar o tipo implicitamente ao lado da tentativa explícita (evitando um `CREATE TYPE`
duplicado); `checkfirst=True` torna a criação/remoção idempotente para bancos que já
tenham o tipo de uma execução parcial anterior.

### `d3e16cbf2688_message_provider_timestamp_and_delivery_.py` (bug principal)

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

### `790826c45a84_initial_schema.py` (bug relacionado — limpeza de tipos no downgrade)

`upgrade()` não foi alterado — a criação dos seis enums via `op.create_table(...)` já
funcionava corretamente. `downgrade()` ganhou uma limpeza explícita dos seis tipos,
depois de todas as tabelas serem removidas:

```python
bind = op.get_bind()
for enum_name in _ENUM_NAMES:  # jobstatus, userrole, messagedirection, messagemediatype, taskstatus, taskpriority
    postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
```

Nenhuma outra migration (`abb2a2bf950e`, `8d535824ec8f`, `61c82eeb3be5`,
`0e6459491047`) cria ou depende de ENUM — não precisaram de alteração.

## Arquivos alterados

- `backend/alembic/versions/d3e16cbf2688_message_provider_timestamp_and_delivery_.py`
- `backend/alembic/versions/790826c45a84_initial_schema.py`

Nenhum model SQLAlchemy foi alterado (`models/message.py` já estava correto — o nome
do tipo gerado pelo ORM já batia com o nome usado na migration). Nenhum schema de
banco foi editado manualmente; nenhuma migration foi apagada, renumerada ou teve seu
`revision`/`down_revision` alterado.

## Impacto

- **Instalações novas** (banco vazio): `alembic upgrade head` antes falhava sempre ao
  chegar em `d3e16cbf2688`. Agora completa a cadeia inteira sem erro.
- **Instalações já existentes parcialmente migradas** (ex.: pararam em
  `abb2a2bf950e` ou anterior, por terem batido nesse mesmo bug antes): continuam a
  migração normalmente a partir de onde estavam — testado.
- **Instalações que já aplicaram `d3e16cbf2688` manualmente/por workaround**: não
  afetadas — `checkfirst=True` faz a criação do tipo ser um no-op se ele já existir.
- **Downgrade completo até a base**: agora limpa os seis tipos ENUM da migration
  inicial, além do `messagedeliverystatus`, sem deixar tipos órfãos.

## Compatibilidade

- Nenhuma alteração de schema além da correção do defeito em si — a coluna
  `delivery_status` continua com o mesmo nome, tipo lógico e valores possíveis
  (`SENT`, `DELIVERED`, `READ`, `FAILED`).
- Nenhuma alteração de API, comportamento de aplicação, ou model ORM.
- Idempotente: seguro rodar `alembic upgrade head` repetidamente ou a partir de
  qualquer ponto da cadeia.

## Resultado dos testes

Executado com um banco PostgreSQL 16 real local (não SQLite, não mock) para validar
o comportamento real de DDL do Postgres:

| Cenário | Resultado |
|---|---|
| Banco vazio → `alembic upgrade head` | ✅ completa a cadeia inteira (790826c45a84 → 0e6459491047) |
| Banco parcialmente migrado (parado em `abb2a2bf950e`) → `alembic upgrade head` | ✅ continua e completa normalmente |
| `alembic downgrade base` a partir de head | ✅ remove todas as tabelas e todos os 7 tipos ENUM (6 da inicial + `messagedeliverystatus`), sem tipos órfãos |
| `alembic upgrade head` novamente após downgrade completo (roundtrip) | ✅ completa sem "type already exists" |
| Downgrade/upgrade isolado em torno de `d3e16cbf2688` (um passo de cada vez) | ✅ tipo criado/removido corretamente em cada direção |
| `pytest` (suíte completa) | ✅ 479 passed, 93% cobertura — sem regressão |
| `ruff check .` | ✅ All checks passed |
| `mypy` | Não configurado no projeto (limitação preexistente e já documentada em `ROADMAP_v1.1.md` P3-2, `PRODUCTION_APPROVAL.md`) — fora do escopo desta correção |
| Frontend `next build` (type check + build) | ✅ compila, gera as 14 rotas estáticas |
| `docker compose config` | ✅ válido |

## Confirmação de que novas instalações não quebram mais

Confirmado por reprodução direta: banco PostgreSQL 16 vazio, `alembic upgrade head`
do zero, chain completa `790826c45a84 → abb2a2bf950e → d3e16cbf2688 → 8d535824ec8f →
61c82eeb3be5 → 0e6459491047`, sem qualquer erro. O tipo `messagedeliverystatus` é
criado explicitamente antes do `ALTER TABLE`, exatamente como os demais tipos
`jobstatus`/`userrole`/`messagedirection`/`messagemediatype`/`taskstatus`/`taskpriority`
já eram (implicitamente, via `create_table`) — a cadeia de migrations agora é
simétrica e reversível em qualquer ponto.
