# Business Module — Schema v1.0

## Entity-Relationship Diagram

```
┌─────────────────────┐
│     clients         │
├─────────────────────┤
│ id (PK)             │
│ name                │
│ email (UNIQUE)      │
│ phone               │
│ address (JSON)      │
│ created_at          │
│ updated_at          │
│ deleted_at          │
└──────────┬──────────┘
           │
           │ 1:N
           │
    ┌──────┴──────────────────┐
    │                         │
    v                         v
┌──────────────────┐  ┌──────────────────┐
│     deals        │  │  kpis            │
├──────────────────┤  ├──────────────────┤
│ id (PK)          │  │ id (PK)          │
│ client_id (FK)   │  │ client_id (FK*)  │
│ title            │  │ deal_id (FK*)    │
│ value            │  │ metric_name      │
│ status           │  │ metric_value     │
│ expected_close   │  │ period           │
│ created_at       │  │ created_at       │
│ updated_at       │  │ updated_at       │
│ deleted_at       │  │ deleted_at       │
└────────┬─────────┘  └──────────────────┘
         │
    ┌────┴────────────────┐
    │                     │
    v                     v
┌──────────────────┐  ┌──────────────────┐
│  followups       │  │  projects        │
├──────────────────┤  ├──────────────────┤
│ id (PK)          │  │ id (PK)          │
│ deal_id (FK)     │  │ deal_id (FK)     │
│ scheduled_at     │  │ name             │
│ completed_at     │  │ status           │
│ notes            │  │ budget           │
│ created_at       │  │ spent            │
│ updated_at       │  │ created_at       │
│ deleted_at       │  │ updated_at       │
└──────────────────┘  │ deleted_at       │
                      └──────────────────┘

Legend:
(PK) = Primary Key
(FK) = Foreign Key
(FK*) = Optional Foreign Key (can be NULL)
(UNIQUE) = Unique constraint
```

## Data Dictionary

### Table: `clients`

| Column | Type | Constraints | Index | Purpose |
|--------|------|-------------|-------|---------|
| `id` | BIGINT | PRIMARY KEY, NOT NULL | ✅ clients_pkey | Unique client identifier (auto-increment) |
| `name` | VARCHAR(255) | NOT NULL | ❌ | Client business name |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | ✅ clients_email_unique | Client contact email |
| `phone` | VARCHAR(20) | NULL | ❌ | Client phone number |
| `address` | JSONB | NULL | ❌ | Full address object {street, city, state, country, zip} |
| `created_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ✅ clients_created_at_idx | Record creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Last update timestamp |
| `deleted_at` | TIMESTAMP | NULL | ❌ | Soft delete marker (NULL = active) |

**Relationships**:
- 1:N with `deals` (one client has many deals)
- 1:N with `kpis` (one client can have many KPIs)

**Soft Delete**: Queries must filter `WHERE deleted_at IS NULL`

---

### Table: `deals`

| Column | Type | Constraints | Index | Purpose |
|--------|------|-------------|-------|---------|
| `id` | BIGINT | PRIMARY KEY, NOT NULL | ✅ deals_pkey | Unique deal identifier |
| `client_id` | BIGINT | FOREIGN KEY, NOT NULL | ✅ deals_client_id_idx | Reference to `clients.id` |
| `title` | VARCHAR(255) | NOT NULL | ❌ | Deal/opportunity title |
| `value` | NUMERIC(12,2) | NULL | ❌ | Deal value in currency (e.g., USD) |
| `status` | VARCHAR(50) | NULL | ✅ deals_status_idx | Status: "open", "closed_won", "closed_lost" |
| `expected_close_date` | DATE | NULL | ✅ deals_expected_close_idx | Expected close date for forecasting |
| `created_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ✅ deals_created_at_idx | Record creation |
| `updated_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Last update |
| `deleted_at` | TIMESTAMP | NULL | ❌ | Soft delete marker |

**Relationships**:
- N:1 with `clients` (many deals belong to one client)
- 1:N with `followups` (one deal has many followups)
- 1:N with `projects` (one deal has many projects)
- 1:N with `kpis` (one deal can have many KPIs)

**Foreign Key Constraint**: `deals.client_id` → `clients.id` (ON DELETE CASCADE not applied, require explicit management)

---

### Table: `followups`

| Column | Type | Constraints | Index | Purpose |
|--------|------|-------------|-------|---------|
| `id` | BIGINT | PRIMARY KEY, NOT NULL | ✅ followups_pkey | Unique followup identifier |
| `deal_id` | BIGINT | FOREIGN KEY, NOT NULL | ✅ followups_deal_id_idx | Reference to `deals.id` |
| `scheduled_at` | TIMESTAMP | NOT NULL | ✅ followups_scheduled_at_idx | When followup is scheduled (for jobs) |
| `completed_at` | TIMESTAMP | NULL | ❌ | When followup was actually completed |
| `notes` | TEXT | NULL | ❌ | Internal notes about followup |
| `created_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Record creation |
| `updated_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Last update |
| `deleted_at` | TIMESTAMP | NULL | ❌ | Soft delete marker |

**Relationships**:
- N:1 with `deals` (many followups belong to one deal)

**Job Queue Integration**: `scheduled_at` used by job queue for async task scheduling

---

### Table: `projects`

| Column | Type | Constraints | Index | Purpose |
|--------|------|-------------|-------|---------|
| `id` | BIGINT | PRIMARY KEY, NOT NULL | ✅ projects_pkey | Unique project identifier |
| `deal_id` | BIGINT | FOREIGN KEY, NOT NULL | ✅ projects_deal_id_idx | Reference to `deals.id` |
| `name` | VARCHAR(255) | NOT NULL | ❌ | Project name/title |
| `status` | VARCHAR(50) | NULL | ❌ | Status: "planning", "active", "completed", "on_hold" |
| `budget` | NUMERIC(12,2) | NULL | ❌ | Project budget allocation |
| `spent` | NUMERIC(12,2) | DEFAULT 0, NULL | ❌ | Amount spent so far (spent ≤ budget constraint) |
| `created_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Record creation |
| `updated_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Last update |
| `deleted_at` | TIMESTAMP | NULL | ❌ | Soft delete marker |

**Relationships**:
- N:1 with `deals` (many projects belong to one deal)

**Business Validation**: Application layer must enforce `spent ≤ budget`

---

### Table: `kpis`

| Column | Type | Constraints | Index | Purpose |
|--------|------|-------------|-------|---------|
| `id` | BIGINT | PRIMARY KEY, NOT NULL | ✅ kpis_pkey | Unique KPI record identifier |
| `client_id` | BIGINT | FOREIGN KEY, NULL | ✅ kpis_client_id_idx | Reference to `clients.id` (optional) |
| `deal_id` | BIGINT | FOREIGN KEY, NULL | ✅ kpis_deal_id_idx | Reference to `deals.id` (optional) |
| `metric_name` | VARCHAR(255) | NOT NULL | ❌ | KPI metric name (e.g., "revenue", "close_rate") |
| `metric_value` | NUMERIC(12,4) | NULL | ❌ | Metric numeric value |
| `period` | VARCHAR(50) | NULL | ❌ | Period label (e.g., "Q3 2026", "2026", "YTD") |
| `created_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Record creation |
| `updated_at` | TIMESTAMP | DEFAULT NOW(), NOT NULL | ❌ | Last update |
| `deleted_at` | TIMESTAMP | NULL | ❌ | Soft delete marker |

**Relationships**:
- N:1 with `clients` (many KPIs can reference one client, optional)
- N:1 with `deals` (many KPIs can reference one deal, optional)

**Business Validation**: Application layer must ensure `client_id IS NOT NULL OR deal_id IS NOT NULL` (at least one must be set)

---

## Index Summary

**Primary Keys**:
- clients_pkey
- deals_pkey
- followups_pkey
- projects_pkey
- kpis_pkey

**Unique Constraints**:
- clients_email_unique

**Performance Indexes** (for common queries):
- clients_created_at_idx → Range queries on creation date
- clients_email_unique → Email lookups (also unique constraint)
- deals_client_id_idx → List deals by client
- deals_status_idx → Filter by status
- deals_expected_close_idx → Forecasting queries
- deals_created_at_idx → Range queries
- followups_deal_id_idx → List followups by deal
- followups_scheduled_at_idx → Job queue scheduling queries
- projects_deal_id_idx → List projects by deal
- kpis_client_id_idx → List KPIs by client
- kpis_deal_id_idx → List KPIs by deal

---

## Naming Convention Summary

See `docs/business/NAMING_CONVENTIONS.md` for detailed rules.

**Quick Reference**:
- Table names: lowercase, plural (clients, deals, followups, projects, kpis)
- Column names: lowercase, underscores (created_at, client_id, expected_close_date)
- Primary keys: `id` (BIGINT, auto-increment)
- Foreign keys: `<table>_id` pattern (client_id, deal_id)
- Indexes: `<table>_<column>_<type>_idx` (deals_client_id_idx, clients_email_unique)
- Soft delete: `deleted_at` column (TIMESTAMP, NULL = active)
- Timestamps: `created_at`, `updated_at` (both TIMESTAMP, default NOW())

---

## Expand-Contract Strategy

See `docs/business/EXPAND_CONTRACT_STRATEGY.md` for implementation phases.

**Phase 1 (v1.0)**: All new columns NULLABLE (expand phase)
**Phase 2 (v1.1)**: Backfill with defaults, transition to NOT NULL (contract phase)

---

## Version

**Schema Version**: 1.0.0
**Created**: 2026-07-12
**Status**: APPROVED
**Next Review**: After Phase 1 implementation (MIG-001 through MIG-005)
