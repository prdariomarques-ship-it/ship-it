# Business Module — Expand-Contract Migration Strategy

**Status**: APPROVED
**Version**: 1.0
**Pattern**: Expand-Contract (two-phase migration pattern)
**Reference**: ARCHITECTURE_FINAL.md DEC-5

---

## Executive Summary

All new columns in Business Module v1.0 are created as **NULLABLE** in the initial deployment (expand phase). In v1.1, after backfill and validation in production, columns will transition to **NOT NULL** (contract phase). This ensures:

- ✅ Zero-downtime deployment
- ✅ Reversibility (rollback = no data loss)
- ✅ Production validation before locking schema
- ✅ Gradual enforcement of constraints

---

## Phase 1: Expand (v1.0 — Current)

### Deployment Strategy

All new tables and columns are created with:
- **Nullable columns**: `NOT NULL` only on absolutely required fields
- **Defaults**: Sensible defaults provided for some fields (timestamps, booleans)
- **No constraints**: Business logic validation deferred to application layer initially

### Tables Created (v1.0)

| Table | Phase 1 State | Notes |
|-------|---------------|-------|
| `clients` | New table, all columns nullable except `id`, `name`, `email` | Essential fields only NOT NULL |
| `deals` | New table, all columns nullable except `id`, `client_id` | FK required, everything else optional |
| `followups` | New table, all columns nullable except `id`, `deal_id`, `scheduled_at` | Requires deal and schedule time |
| `projects` | New table, all columns nullable except `id`, `deal_id` | Deal association required |
| `kpis` | New table, all columns nullable except `id`, one of `client_id` or `deal_id` | At least one association required (app layer) |

### Migration Implementation (MIG-001 through MIG-005)

```python
# Example: MIGration for clients table (MIG-001)

def upgrade():
    op.create_table(
        'clients',
        sa.Column('id', sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column('name', sa.VARCHAR(length=255), nullable=False),  # Required
        sa.Column('email', sa.VARCHAR(length=255), nullable=False),  # Required
        sa.Column('phone', sa.VARCHAR(length=20), nullable=True),    # Optional
        sa.Column('address', sa.JSON(), nullable=True),               # Optional
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True),      # Soft delete
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='clients_email_unique'),
    )
    op.create_index('clients_email_unique', 'clients', ['email'], unique=True)
    op.create_index('clients_created_at_idx', 'clients', ['created_at'])

def downgrade():
    op.drop_table('clients')
```

### Validation in v1.0

- ✅ Tables exist and are accessible
- ✅ Columns can be NULL (no data loss risk)
- ✅ Application logic enforces NOT NULL where required (via Pydantic validation)
- ✅ Rollback is safe: `DROP TABLE` reverses everything

---

## Phase 2: Contract (v1.1 — Future)

### Deployment Strategy

After v1.0 has been in production for sufficient time (1-2 sprints), transition columns from NULLABLE to NOT NULL:

1. Backfill any NULL values with appropriate defaults
2. Validation: Ensure all rows satisfy new NOT NULL constraint
3. Migration: Add NOT NULL constraints
4. Lock schema: Columns now enforced NOT NULL

### Backfill Strategy

For each column transitioning from NULL to NOT NULL:

| Column | Current NULL Behavior | Backfill Strategy | Example |
|--------|-------|---|---|
| `clients.phone` | NULL allowed | Keep as-is OR provide default | NULL → "" (empty string) |
| `clients.address` | NULL allowed | Keep as-is OR provide default | NULL → {} (empty JSON) |
| `deals.value` | NULL allowed | Backfill with 0 or average | NULL → 0.00 |
| `deals.status` | NULL allowed | Backfill with default status | NULL → "open" |
| `projects.budget` | NULL allowed | Backfill with 0 | NULL → 0.00 |
| `projects.spent` | NULL allowed (but defaults 0) | No backfill needed | Already defaults 0 |

### v1.1 Migration Example

```python
# Backfill phase (before adding NOT NULL)
def upgrade():
    # Backfill NULL values
    op.execute("UPDATE clients SET phone = '' WHERE phone IS NULL")
    op.execute("UPDATE deals SET status = 'open' WHERE status IS NULL")
    op.execute("UPDATE deals SET value = 0 WHERE value IS NULL")
    
    # Add NOT NULL constraints
    op.alter_column('clients', 'phone', nullable=False, server_default='')
    op.alter_column('deals', 'status', nullable=False, server_default='open')
    op.alter_column('deals', 'value', nullable=False, server_default=0)

def downgrade():
    # Revert to nullable
    op.alter_column('clients', 'phone', nullable=True, server_default=None)
    op.alter_column('deals', 'status', nullable=True, server_default=None)
    op.alter_column('deals', 'value', nullable=True, server_default=None)
```

### Validation in v1.1

- ✅ All rows satisfy new NOT NULL constraint
- ✅ Application layer can rely on column presence (no null checks)
- ✅ Rollback (if needed): revert to nullable + restore NULLs from backup
- ✅ Performance: NOT NULL columns are slightly faster in queries

---

## Columns: Phase 1 (v1.0) vs Phase 2 (v1.1)

### `clients` Table

| Column | v1.0 (Expand) | v1.1 (Contract) | Backfill Strategy |
|--------|---|---|---|
| `id` | NOT NULL (PK) | NOT NULL (PK) | No change |
| `name` | NOT NULL | NOT NULL | No change |
| `email` | NOT NULL | NOT NULL | No change |
| `phone` | NULL | NULL | Keep NULL (optional) |
| `address` | NULL | NULL | Keep NULL (optional) |
| `created_at` | NOT NULL | NOT NULL | No change |
| `updated_at` | NOT NULL | NOT NULL | No change |
| `deleted_at` | NULL | NULL | No change (soft delete flag) |

### `deals` Table

| Column | v1.0 (Expand) | v1.1 (Contract) | Backfill Strategy |
|--------|---|---|---|
| `id` | NOT NULL (PK) | NOT NULL (PK) | No change |
| `client_id` | NOT NULL (FK) | NOT NULL (FK) | No change |
| `title` | NOT NULL | NOT NULL | No change (required on insert) |
| `value` | NULL | NOT NULL | Backfill: 0.00 |
| `status` | NULL | NOT NULL | Backfill: "open" |
| `expected_close_date` | NULL | NULL | Keep NULL (optional) |
| `created_at` | NOT NULL | NOT NULL | No change |
| `updated_at` | NOT NULL | NOT NULL | No change |
| `deleted_at` | NULL | NULL | No change |

### `followups` Table

| Column | v1.0 (Expand) | v1.1 (Contract) | Backfill Strategy |
|--------|---|---|---|
| `id` | NOT NULL (PK) | NOT NULL (PK) | No change |
| `deal_id` | NOT NULL (FK) | NOT NULL (FK) | No change |
| `scheduled_at` | NOT NULL | NOT NULL | No change (required on insert) |
| `completed_at` | NULL | NULL | Keep NULL (optional, set only on completion) |
| `notes` | NULL | NULL | Keep NULL (optional) |
| `created_at` | NOT NULL | NOT NULL | No change |
| `updated_at` | NOT NULL | NOT NULL | No change |
| `deleted_at` | NULL | NULL | No change |

### `projects` Table

| Column | v1.0 (Expand) | v1.1 (Contract) | Backfill Strategy |
|--------|---|---|---|
| `id` | NOT NULL (PK) | NOT NULL (PK) | No change |
| `deal_id` | NOT NULL (FK) | NOT NULL (FK) | No change |
| `name` | NOT NULL | NOT NULL | No change |
| `status` | NULL | NOT NULL | Backfill: "planning" |
| `budget` | NULL | NOT NULL | Backfill: 0.00 |
| `spent` | NULL (default 0) | NOT NULL | No backfill needed (already has default) |
| `created_at` | NOT NULL | NOT NULL | No change |
| `updated_at` | NOT NULL | NOT NULL | No change |
| `deleted_at` | NULL | NULL | No change |

### `kpis` Table

| Column | v1.0 (Expand) | v1.1 (Contract) | Backfill Strategy |
|--------|---|---|---|
| `id` | NOT NULL (PK) | NOT NULL (PK) | No change |
| `client_id` | NULL (optional FK) | NULL (optional FK) | No change (either client_id or deal_id, app enforces) |
| `deal_id` | NULL (optional FK) | NULL (optional FK) | No change (either client_id or deal_id, app enforces) |
| `metric_name` | NOT NULL | NOT NULL | No change |
| `metric_value` | NULL | NULL | Keep NULL (optional numeric data) |
| `period` | NULL | NULL | Keep NULL (optional) |
| `created_at` | NOT NULL | NOT NULL | No change |
| `updated_at` | NOT NULL | NOT NULL | No change |
| `deleted_at` | NULL | NULL | No change |

---

## Rollback Strategy

### v1.0 Rollback

**If Phase 1 (expand) fails**:
```bash
# Individual migration rollback
alembic downgrade -1  # Rolls back MIG-005 (or whichever is latest)

# Multiple rollbacks
alembic downgrade -5  # Rolls back last 5 migrations
```

**Effect**: Tables are dropped, data is gone (by design — v1.0 is initial deployment)

### v1.1 Rollback (Planned)

**If Phase 2 (contract) fails**:
```bash
# Revert to nullable
alembic downgrade -1  # Rolls back the NOT NULL migration

# Effect**: Columns revert to NULLABLE, existing NOT NULL rows remain valid
# Data is preserved
```

---

## Application Layer Validation (v1.0)

Since columns are NULLABLE at database level, application layer must enforce business rules:

### Pydantic Schemas (v1.0)

```python
# Create schema — enforce requirements at API boundary
class ClientCreate(BaseModel):
    name: str  # Required (not Optional)
    email: EmailStr  # Required, validated
    phone: Optional[str] = None  # Optional
    address: Optional[dict] = None  # Optional

class DealCreate(BaseModel):
    client_id: int  # Required (FK to existing client)
    title: str  # Required
    value: Optional[Decimal] = None  # Optional (will be nullable in DB)
    status: Optional[str] = None  # Optional (app could provide default "open")
    expected_close_date: Optional[date] = None  # Optional
```

### Validation Layer

```python
# Example: Business logic before INSERT
def create_deal(client_id: int, title: str, value: Optional[Decimal] = None):
    # Validate client exists
    if not client_exists(client_id):
        raise ValueError(f"Client {client_id} not found")
    
    # Validate business rules
    if value is not None and value < 0:
        raise ValueError("Deal value cannot be negative")
    
    # Provide sensible defaults for v1.0
    status = status or "open"  # Default to open if not provided
    
    # INSERT into database
    return db.insert(Deal(
        client_id=client_id,
        title=title,
        value=value,
        status=status,
    ))
```

---

## Testing Strategy

### v1.0 Tests (Expand Phase)

1. **Schema Tests**: Verify tables exist, columns have correct types
   ```python
   def test_clients_table_exists():
       # Query information_schema to verify structure
   ```

2. **Null Tests**: Verify nullable columns accept NULL
   ```python
   def test_deals_value_can_be_null():
       deal = Deal(client_id=1, title="Test", value=None)
       db.session.add(deal)
       db.session.commit()  # Should succeed
   ```

3. **FK Tests**: Verify foreign key constraints
   ```python
   def test_deal_requires_valid_client():
       # Should fail if client_id doesn't exist
   ```

4. **API Tests**: Verify endpoints reject invalid data per Pydantic schema
   ```python
   def test_create_deal_missing_title():
       response = POST /api/business/deals with body: {client_id: 1}
       assert response.status_code == 400  # Pydantic validation error
   ```

### v1.1 Tests (Contract Phase)

1. **Backfill Tests**: Verify backfill query correct, no data loss
2. **Not-Null Tests**: Verify NOT NULL constraint prevents NULL inserts
3. **Migration Rollback Tests**: Verify downgrade reverts to nullable

---

## Timeline

| Phase | Sprint | Action | Duration |
|-------|--------|--------|----------|
| **Expand** | Sprint 6 | Create tables (MIG-001...005), all nullable except critical fields | 1 week |
| **Production v1.0** | Sprint 6+ | Deploy, validate data, monitor | 1-2 sprints |
| **Backfill Plan** | Sprint 7-8 | Plan v1.1 backfill (QA, testing) | Planning only |
| **Contract** | Sprint 8+ (TBD) | Execute backfill + add NOT NULL constraints | 1 week |
| **Production v1.1** | Sprint 8+ (TBD) | Lock schema, deploy | Ongoing |

---

## Risk Mitigation

| Risk | Mitigation | v1.0 Impact |
|------|-----------|---|
| Rollback complexity | Expand-contract is fully reversible | LOW — simple `DROP TABLE` |
| Missed backfill | Test backfill logic before v1.1 deployment | MEDIUM — caught in v1.1 testing |
| Data loss | Regular backups maintained | LOW — backup exists |
| Schema confusion | This document is source of truth | LOW — documented clearly |

---

## References

- **ARCHITECTURE_FINAL.md** — DEC-5 (Expand-Contract Migration Pattern)
- **SCHEMA_v1.0.md** — Column details and constraints
- **NAMING_CONVENTIONS.md** — Naming rules for migration code

---

## Version

**Expand-Contract Strategy**: 1.0
**Created**: 2026-07-12
**Applies to**: Business Module Schema v1.0
**Next Review**: Sprint 7-8 (before v1.1 planning)
