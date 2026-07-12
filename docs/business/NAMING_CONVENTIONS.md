# Business Module — Naming Conventions v1.0

**Status**: APPROVED
**Applies to**: All Business module database objects
**Consistency with**: Core naming patterns (existing infrastructure)

---

## Table Naming

### Rule 1: Plural, Lowercase

- ✅ `clients` — stores multiple client records
- ✅ `deals` — stores multiple deal records
- ✅ `followups` — stores multiple followup records
- ✅ `projects` — stores multiple projects
- ✅ `kpis` — stores multiple KPI records

**Rationale**: Standard SQL convention, matches Core infrastructure (users, agents, tools, etc.)

### Rule 2: No Prefix

- ✅ `clients` (not `business_clients`)
- ✅ `deals` (not `biz_deals`)

**Rationale**: Module boundary enforced by filesystem (`docs/business/`, `backend/business/`), not by table prefix. Database is single Postgres instance; schema isolation via ownership.

---

## Column Naming

### Rule 1: Lowercase, Underscores

- ✅ `created_at` (not `createdAt`, `created_time`, `createTime`)
- ✅ `client_id` (not `clientId`, `client_ID`)
- ✅ `expected_close_date` (not `expectedCloseDate`, `close_date`)

**Rationale**: Python/SQL standard, matches Core patterns

### Rule 2: Explicit Semantics

Use descriptive names that clarify intent:
- ✅ `scheduled_at` — when something is scheduled
- ✅ `completed_at` — when something was completed
- ✅ `expected_close_date` — expected close (not just `close_date` which could be ambiguous)
- ✅ `metric_value` (not just `value` which is generic)

---

## Primary Key Naming

### Rule: Always `id` (BIGINT, auto-increment)

- ✅ `clients.id`
- ✅ `deals.id`
- ✅ `followups.id`
- ✅ `projects.id`
- ✅ `kpis.id`

**Type**: BIGINT (signed 64-bit integer)
**Generation**: PostgreSQL `BIGSERIAL` or Alembic `sa.BIGINT` with `autoincrement=True`
**Rationale**: Matches Core infrastructure; scalable; matches ORM defaults

---

## Foreign Key Naming

### Rule: `<referenced_table>_id`

| Column | Meaning | Example |
|--------|---------|---------|
| `client_id` | References `clients.id` | In `deals`, `followups`, `kpis` tables |
| `deal_id` | References `deals.id` | In `followups`, `projects`, `kpis` tables |

**NOT**:
- ❌ `clientId` (use `client_id`)
- ❌ `fk_clients` (use `client_id`)
- ❌ `deals_fk` (use `deal_id`)

**Rationale**: Unambiguous, matches Core patterns (user_id, agent_id, tool_id)

---

## Unique Constraint Naming

### Rule: `<table>_<column>_unique`

Example: `clients_email_unique`

**Applied in Schema**:
```
clients.email — UNIQUE constraint named clients_email_unique
```

**NOT**:
- ❌ `ux_clients_email`
- ❌ `clients_email_key`
- ❌ No explicit name (rely on auto-generated)

**Rationale**: Explicit names are audit-friendly and survive schema migrations

---

## Index Naming

### Rule: `<table>_<column>_<type>_idx`

| Index | Table | Column | Type | Purpose |
|-------|-------|--------|------|---------|
| `clients_created_at_idx` | clients | created_at | Range | Date range queries |
| `deals_client_id_idx` | deals | client_id | FK | List deals per client |
| `deals_status_idx` | deals | status | Filter | Status-based queries |
| `followups_scheduled_at_idx` | followups | scheduled_at | Range | Job queue scheduling |
| `kpis_client_id_idx` | kpis | client_id | FK | List KPIs per client |

**NOT**:
- ❌ `idx_clients_created_at` (prefix before table name)
- ❌ `ix_created_at` (too generic)
- ❌ `deals_client_fk_idx` (say column, not constraint)

**Rationale**: Consistent ordering (table → column → type), clear purpose

---

## Type Naming & Defaults

### String Columns

| Column | Type | Max Length | Nullable | Default | Example |
|--------|------|------------|----------|---------|---------|
| `name` | VARCHAR | 255 | NOT NULL | (none) | "Acme Corp" |
| `email` | VARCHAR | 255 | NOT NULL | (none) | "contact@acme.com" |
| `phone` | VARCHAR | 20 | NULL | NULL | "+55 11 98765-4321" |
| `status` | VARCHAR | 50 | NULL | NULL | "open" |
| `period` | VARCHAR | 50 | NULL | NULL | "Q3 2026" |
| `notes` | TEXT | unlimited | NULL | NULL | Long text fields |

### Numeric Columns

| Column | Type | Precision | Nullable | Default | Example |
|--------|------|-----------|----------|---------|---------|
| `id` | BIGINT | N/A | NOT NULL | AUTOINCREMENT | 1, 2, 3, ... |
| `value` | NUMERIC | (12,2) | NULL | NULL | 1500.50 (USD) |
| `budget` | NUMERIC | (12,2) | NULL | NULL | 5000.00 |
| `spent` | NUMERIC | (12,2) | NULL | 0 | 2345.67 |
| `metric_value` | NUMERIC | (12,4) | NULL | NULL | 75.2500 (percentage) |

### Timestamp Columns

| Column | Type | Nullable | Default | Meaning |
|--------|------|----------|---------|---------|
| `created_at` | TIMESTAMP | NOT NULL | NOW() | Record creation time |
| `updated_at` | TIMESTAMP | NOT NULL | NOW() | Last modification time |
| `completed_at` | TIMESTAMP | NULL | NULL | When action was completed (optional) |
| `scheduled_at` | TIMESTAMP | NOT NULL | (none) | When event is scheduled (required for scheduling) |
| `expected_close_date` | DATE | NULL | NULL | Expected close (date only, no time) |
| `deleted_at` | TIMESTAMP | NULL | NULL | Soft delete marker (NULL = active) |

### JSON Columns

| Column | Type | Nullable | Example | Purpose |
|--------|------|----------|---------|---------|
| `address` | JSONB | NULL | `{street: "123 Main St", city: "São Paulo", state: "SP", country: "BR", zip: "01234-567"}` | Flexible address storage |

**Rationale**: JSONB allows indexing, querying, and type validation while remaining flexible for expansion

---

## Special Column Patterns

### Soft Delete Pattern

**Column**: `deleted_at`
**Type**: TIMESTAMP
**Nullable**: YES
**Default**: NULL
**Semantics**: 
- NULL = record is active (not deleted)
- TIMESTAMP value = record is soft-deleted (not shown in queries by default)

**Usage**:
```sql
-- Active records only
SELECT * FROM clients WHERE deleted_at IS NULL;

-- All records including deleted
SELECT * FROM clients;

-- Soft delete (don't actually delete)
UPDATE clients SET deleted_at = NOW() WHERE id = 1;

-- Restore deleted record
UPDATE clients SET deleted_at = NULL WHERE id = 1;
```

### Audit Timestamps

**Columns**: `created_at`, `updated_at`
**Type**: TIMESTAMP
**Defaults**: Both default to NOW()
**Semantics**:
- `created_at` = never changes (immutable)
- `updated_at` = updated on every row modification (via database trigger or application logic)

---

## Reserved Words & Avoidance

**Avoid these PostgreSQL reserved keywords**:
- ❌ `order`, `group`, `select`, `where`, `from`, `join` (use as suffixes/prefixes if needed: `sort_order`, `group_id`)
- ❌ `user` (use `client` or `account` instead; `user` is Core-owned)
- ❌ `event` (reserved in some contexts; use `event_record` if needed)

**OK to use** (not reserved in PostgreSQL, but be explicit):
- ✅ `status`
- ✅ `value`
- ✅ `notes`
- ✅ `name`

---

## Summary Table

| What | Rule | Example |
|------|------|---------|
| **Table** | lowercase, plural | `clients`, `deals` |
| **Column** | lowercase_underscore | `created_at`, `client_id` |
| **PK** | `id` (BIGINT) | `id` |
| **FK** | `<table>_id` | `client_id`, `deal_id` |
| **Index** | `<table>_<col>_<type>_idx` | `deals_client_id_idx` |
| **Unique** | `<table>_<col>_unique` | `clients_email_unique` |
| **Soft Delete** | `deleted_at` (TIMESTAMP, NULL) | `deleted_at` |
| **Audit** | `created_at`, `updated_at` (TIMESTAMP) | Both columns on all tables |

---

## Version

**Naming Conventions Version**: 1.0
**Created**: 2026-07-12
**Applies to**: Business Module Schema v1.0
**Consistency**: Follows Core infrastructure patterns
