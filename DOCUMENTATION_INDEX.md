# Documentation Index — Dario Platform & Core

**Consolidation Date**: Phase 0, 2026-07-11  
**Status**: Authoritative sources established; deprecated documents marked

This index identifies the current authoritative source for each major architectural and operational area.

## Primary Architecture Documents (Authoritative)

These are the single source of truth for platform and core architecture:

| Document | Purpose | Status |
|---|---|---|
| **ARCHITECTURE_FINAL.md** | Consolidated platform architecture, vision, topology, dependency rules, communication channels, module definitions, provider governance, data strategy, observability, production engineering | ✅ Authoritative (Phase 0) |
| **MODULE_CATALOG.md** | Per-module specification: objectives, responsibilities, boundaries, dependencies, events, APIs, data ownership | ✅ Authoritative (Phase 0) |
| **ARCHITECTURE_DECISIONS.md** | Nine architectural decisions (DEC-1 through DEC-9) with rationale, trade-offs, and implications | ✅ Authoritative (Phase 0) |
| **AI_GOVERNANCE.md** | Formal roles of AI contributors (ChatGPT vision/approval, Claude Code tech lead, Qwen Coder implementation, GLM research), approval gates, scope boundaries | ✅ Authoritative (Phase 0) |
| **ARCHITECTURE_MIGRATION_PLAN.md** | Phased migration from Dario OS v1.2.0 to consolidated Dario Platform (7 sequential phases: Fase 0–7) | ✅ Authoritative (Phase 0) |
| **docs/architecture.md** | Core (Dario OS) architecture — unchanged; remains authoritative for Core only | ✅ Authoritative (Core, pre-platform) |

## Core Operational Documents (Authoritative)

| Document | Purpose | Status |
|---|---|---|
| **CONTRIBUTING.md** | Development conventions and processes (agents, tools, providers, testing, CI/CD) | ✅ Authoritative |
| **docs/governance/ENGINEERING_GUIDE.md** | Platform-level engineering practices extending CONTRIBUTING.md | ✅ Authoritative |
| **docs/roadmap/ROADMAP_24_MONTHS.md** | 24-month platform evolution roadmap (8 trimesters, module sequencing) | ✅ Authoritative |
| **ROADMAP_v2.md** | Core (Dario OS) roadmap v1.2.1 → v2.0.0 | ✅ Authoritative (Core only) |
| **PROJECT_STATUS.md** | Current production status, 555+ test suite, known issues | ✅ Authoritative |
| **TECHNICAL_DEBT.md** | Documented technical debt inventory and priorities | ✅ Authoritative |
| **KNOWN_LIMITATIONS.md** | Formal limitations catalog with context | ✅ Authoritative |
| **VERSION_HISTORY.md** | Version-by-version changelog with architectural notes | ✅ Authoritative |
| **CHANGELOG.md** | Latest release notes and changes | ✅ Authoritative |

## Deprecated Documents (Historical Record — Do Not Reference)

These documents are kept in the repository as historical record but **are no longer authoritative**. New references should use the authoritative sources above.

| Document | Superseded By | Reason |
|---|---|---|
| **PLATFORM_ARCHITECTURE.md** | ARCHITECTURE_FINAL.md, MODULE_CATALOG.md | Original draft before consolidation and resolution of issues identified in ARCHITECTURE_REVIEW.md |
| **docs/modulos/MODULE_CATALOG.md** | MODULE_CATALOG.md (root) | Pre-consolidation version; content updated and moved to root |
| **docs/architecture/MASTER_CONTEXT.md** | ARCHITECTURE_FINAL.md | Context consolidated into single authoritative document |
| **docs/architecture/ARCHITECT_DECISIONS.md** | ARCHITECTURE_DECISIONS.md (root) | Pre-consolidation version with 7 decisions; expanded to 9 in root version |

**Note**: All deprecated documents have a deprecation notice at the top with references to authoritative replacements.

## Historical Documents (For Reference Only)

| Document | Purpose |
|---|---|
| **ARCHITECTURE_REVIEW.md** | Critical review of initial architecture draft; identifies 6 major issues (PF-FRACO-1 through PF-FRACO-6) and 6 risks (RISCO-1 through RISCO-6) |
| **SPRINT_v1.2.1_PREPARATION_REPORT.md** | Phase preparation for current sprint |
| **SPRINT_v1.2.1_PLAN.md** | Sprint plan and task breakdown |
| **SPRINT_v1.2.1_BACKLOG.md** | Sprint backlog items |
| **docs/fase*.md** | Phase reports from prior development cycles |

## Core Component Documentation

| Component | Document |
|---|---|
| Agents | docs/AGENTS.md |
| Tools | docs/TOOLS.md |
| Memory Manager | docs/MEMORY.md |
| Event Bus | (see ARCHITECTURE_FINAL.md, "How modules communicate") |
| Job Queue | (see ARCHITECTURE_FINAL.md, "How modules communicate") |
| Providers | docs/architecture.md + CONTRIBUTING.md |
| Calendar Integration | docs/CALENDAR.md |
| Email Integration | docs/EMAIL.md |
| Google Workspace Integration | docs/DRIVE.md, docs/CONTACTS.md |
| WhatsApp Integration | docs/architecture.md, backend/providers/whatsapp/README.md |
| Workflows | docs/WORKFLOWS.md |
| API | docs/api.md |
| Dashboard | (see PROJECT_STATUS.md) |

## How to Navigate This Project

**Starting from scratch?** Read in this order:
1. ARCHITECTURE_FINAL.md (vision, topology, principles)
2. MODULE_CATALOG.md (module specifications)
3. ARCHITECTURE_MIGRATION_PLAN.md (implementation phases)
4. docs/governance/ENGINEERING_GUIDE.md (practices)
5. CONTRIBUTING.md (conventions)

**Looking for a decision?** Check:
1. ARCHITECTURE_DECISIONS.md (DEC-1 through DEC-9)
2. ARCHITECTURE_REVIEW.md (issues that led to decisions)

**Setting up or deploying?** See:
1. docs/governance/ENGINEERING_GUIDE.md (practices)
2. CONTRIBUTING.md (conventions)
3. docs/roadmap/ROADMAP_24_MONTHS.md (current phase context)

**Implementing a module?** Start with:
1. MODULE_CATALOG.md (module spec)
2. ARCHITECTURE_FINAL.md (communication channels, dependency rules)
3. CONTRIBUTING.md (conventions to follow)
4. docs/governance/ENGINEERING_GUIDE.md (platform practices)

---

**Last Updated**: 2026-07-11 (Phase 0 consolidation)  
**Maintained By**: Claude Code (Chief Software Architect)  
**Approved By**: (Awaiting approval of Phase 0)
