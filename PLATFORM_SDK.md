# Dario OS Platform SDK

**Version:** v1.0.0-LTS  
**Date:** July 14, 2026  
**Status:** Stable & Frozen

---

## OVERVIEW

Dario OS is a personal operating system platform. It provides a stable foundation for building domain-specific applications (called "modules" or "products") that solve real user problems.

This SDK describes how to build applications on top of Dario OS **without modifying its core**.

---

## CORE PRINCIPLES

### 1. Dario OS is a Platform, Not a Product

**Wrong:** "Dario OS is a personal assistant."  
**Right:** "Dario OS is the foundation. FlowCore is the financial copilot built on it."

Dario OS provides:
- User authentication & authorization
- API gateway & request routing
- Workflow execution engine (DRT-001)
- Dashboard & UI framework
- Data persistence layer
- Logging & observability

Products built on Dario OS provide:
- Domain-specific intelligence (AI)
- User-facing features
- Business logic
- Value to users

### 2. No Core Modification

**Dario OS core is frozen.**

Your module cannot:
- Modify backend code in `/backend/main.py`
- Modify the runtime in `/drt-001`
- Modify the dashboard framework in `/frontend/app/(dashboard)`
- Change database schema directly (use migrations)

Your module can:
- Add new API endpoints (as microservices)
- Add new dashboard pages (in route groups)
- Add new workflow types
- Store data in separate tables/databases

### 3. Consume, Don't Replicate

Dario OS provides services. Use them instead of building your own.

```
❌ Bad:  Your module implements its own authentication
✅ Good: Your module uses Dario OS auth via JWT tokens

❌ Bad:  Your module has its own database
✅ Good: Your module stores data in Dario OS PostgreSQL (separate schema)

❌ Bad:  Your module implements its own workflow engine
✅ Good: Your module defines workflows, Dario OS (DRT-001) executes them
```

### 4. Independent Deployability

Each module must be deployable independently.

```
✅ You can deploy FlowCore without touching Dario OS
✅ You can update Dario OS without redeploying FlowCore
✅ You can scale each independently
✅ You can fail independently (module down ≠ platform down)
```

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                    Dario OS Platform (FROZEN)               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Dashboard Framework                      │  │
│  │         (Next.js, React, TailwindCSS)                │  │
│  │  • Layout & Navigation (read-only)                   │  │
│  │  • Component Library (shared UI elements)            │  │
│  │  • Authentication UI                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           API Gateway (FastAPI Backend)              │  │
│  │  • Auth endpoints (/api/auth/*)                      │  │
│  │  • Health & metrics (/health, /metrics)             │  │
│  │  • Rate limiting & CORS                              │  │
│  │  • Request routing & validation                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        Workflow Execution Engine (DRT-001)           │  │
│  │  • Accepts workflow definitions                      │  │
│  │  • Executes async tasks                              │  │
│  │  • Manages state & persistence                       │  │
│  │  • Provides recovery & monitoring                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Data Persistence Layer                        │  │
│  │  • PostgreSQL (or SQLite in dev)                     │  │
│  │  • Alembic migrations                                │  │
│  │  • Connection pooling                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Observability & Logging                    │  │
│  │  • Prometheus metrics                                │  │
│  │  • Structured JSON logging                           │  │
│  │  • Request tracing (correlation IDs)                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          △ △ △
            Consume These Services Below
                          △ △ △

┌─────────────────────────────────────────────────────────────┐
│                 FlowCore Module (EXAMPLE)                    │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         FlowCore Dashboard Pages                     │  │
│  │  • Financial Copilot UI                              │  │
│  │  • Tax Planning page                                 │  │
│  │  • Investment Dashboard                              │  │
│  │  (Mounted in Dario OS dashboard)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      FlowCore API Microservice                        │  │
│  │  • POST /api/flowcore/tax-optimize                   │  │
│  │  • GET /api/flowcore/portfolio                       │  │
│  │  • POST /api/flowcore/invest-recommendation          │  │
│  │  (Separate service, calls Dario OS API Gateway)      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      FlowCore Domain Logic (AI/Algorithms)            │  │
│  │  • Tax optimization engine                            │  │
│  │  • Portfolio analysis                                 │  │
│  │  • Investment recommendations                         │  │
│  │  • Financial forecasting                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        FlowCore Data (Separate Schema)                │  │
│  │  • Transactions table                                 │  │
│  │  • Portfolio table                                    │  │
│  │  • Tax records table                                  │  │
│  │  (In Dario OS PostgreSQL, flowcore_* prefix)         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │     FlowCore Workflows                                │  │
│  │  • tax_optimize workflow                              │  │
│  │  • portfolio_rebalance workflow                       │  │
│  │  • (Execute via Dario OS DRT-001)                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## AVAILABLE SERVICES

### Authentication & Authorization

**Endpoint:** `POST /api/auth/login`

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "secure-password"
  }'

# Response
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "9uZw...",
  "token_type": "bearer",
  "user_id": 1,
  "role": "admin"
}
```

**Use in Requests:**
```bash
curl http://localhost:8000/api/yourmodule/endpoint \
  -H "Authorization: Bearer eyJ0eXAi..."
```

---

### Workflow Execution (DRT-001)

**Execute an async workflow:**

```bash
# Define workflow
curl -X POST http://localhost:8000/api/workflows/execute \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "tax_optimize",
    "params": {
      "income": 150000,
      "deductions": 45000,
      "filing_status": "single"
    }
  }'

# Response
{
  "execution_id": "exec_12345",
  "status": "queued",
  "created_at": "2026-07-14T12:00:00Z"
}

# Poll for completion
curl http://localhost:8000/api/workflows/status/exec_12345 \
  -H "Authorization: Bearer TOKEN"
```

**Supported Workflow Types:**
- Your module defines custom types
- Dario OS handles queuing & execution
- DRT-001 provides recovery & monitoring

---

### Dashboard Integration

**Add pages to Dario OS dashboard:**

```
/frontend/app/flowcore/  (new route group)
├── page.tsx              (main page)
├── tax-planning/
│   └── page.tsx
├── investments/
│   └── page.tsx
└── layout.tsx            (optional: custom layout)
```

Pages are automatically:
- Added to navigation menu
- Protected by authentication
- Styled with Tailwind CSS & shadcn/ui
- Responsive on mobile

---

### Data Persistence

**Use Dario OS PostgreSQL:**

```python
# Backend microservice code
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Create your own tables (separate schema)
Base = declarative_base()

class Transaction(Base):
    __tablename__ = "flowcore_transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, foreign_key="user.id")
    amount = Column(Float)
    category = Column(String)

# Connect to Dario OS database
engine = create_engine(os.getenv("DATABASE_URL"))
Base.metadata.create_all(engine)

# Use Alembic for migrations
# alembic init flowcore_migrations
# alembic revision --autogenerate -m "Add transactions table"
```

---

## MODULE DEVELOPMENT CHECKLIST

### Before Starting

- [ ] Module name decided (e.g., "FlowCore")
- [ ] Problem statement clear
- [ ] Users identified
- [ ] Success metrics defined

### API Development

- [ ] New endpoints defined (not modifying Dario OS)
- [ ] Authentication integrated
- [ ] Request validation implemented
- [ ] Error handling complete
- [ ] Logging & tracing added

### Dashboard

- [ ] Pages created in `/frontend/app/modulename/`
- [ ] Components use shadcn/ui
- [ ] Styling consistent with Dario OS
- [ ] Mobile responsive
- [ ] Dark mode support

### Data

- [ ] Database schema designed (separate tables)
- [ ] Alembic migrations created
- [ ] Data model documented
- [ ] Backup/recovery tested

### Workflows

- [ ] Workflow types defined
- [ ] Integration with DRT-001 tested
- [ ] Error recovery handled
- [ ] Monitoring & alerting set up

### Testing

- [ ] Unit tests written (80%+ coverage)
- [ ] Integration tests with Dario OS
- [ ] E2E tests in dashboard
- [ ] Load testing completed
- [ ] Security review passed

### Documentation

- [ ] README.md written
- [ ] API documentation complete
- [ ] Deployment guide created
- [ ] Troubleshooting guide written

### Deployment

- [ ] Docker image created
- [ ] Environment variables documented
- [ ] Scaling strategy defined
- [ ] Monitoring configured

---

## EXAMPLE: FlowCore Financial Copilot

### 1. API Endpoints

```
POST   /api/flowcore/tax-optimize     # Calculate tax optimization
GET    /api/flowcore/portfolio        # Get portfolio status
POST   /api/flowcore/recommend-invest # Get investment recommendations
POST   /api/flowcore/forecast-cash    # Forecast cash flow
GET    /api/flowcore/metrics          # Get financial health metrics
```

### 2. Dashboard Pages

```
/flowcore                              # Main dashboard
/flowcore/tax-planning                 # Tax optimization UI
/flowcore/investments                  # Investment management
/flowcore/cash-flow                    # Cash flow forecasting
```

### 3. Database Tables

```
flowcore_accounts              # Bank/investment accounts
flowcore_transactions          # Financial transactions
flowcore_tax_records          # Tax information
flowcore_investments          # Investment portfolio
flowcore_recommendations      # AI recommendations
```

### 4. Workflows

```
flowcore:optimize_taxes       # Run tax optimization
flowcore:rebalance_portfolio  # Rebalance investments
flowcore:forecast_cash_flow   # Generate cash flow forecast
```

---

## GETTING STARTED

1. **Fork or create a module repository**
   ```bash
   mkdir flowcore
   cd flowcore
   ```

2. **Create API service (Python FastAPI or other)**
   ```bash
   pip install fastapi uvicorn sqlalchemy
   ```

3. **Add dashboard pages**
   ```bash
   mkdir /home/user/ship-it/frontend/app/flowcore
   # Create page.tsx files
   ```

4. **Add database migrations**
   ```bash
   alembic init alembic
   # Create migration for your tables
   ```

5. **Integrate with Dario OS**
   - Use auth endpoints for login
   - Call DRT-001 for workflows
   - Use dashboard framework for UI
   - Store data in shared PostgreSQL

6. **Test thoroughly**
   - Unit tests
   - Integration tests
   - E2E tests in dashboard

7. **Deploy**
   - Follow DEPLOYMENT_CHECKLIST.md
   - Configure environment variables
   - Set up monitoring

---

## SUPPORT & GOVERNANCE

**Dario OS Platform Owner:** Principal Engineer  
**FlowCore Product Owner:** Financial Product Manager  
**Decision Authority:** CTO

**For questions:**
1. Check `docs/` folder
2. Read `DEPLOYMENT_CHECKLIST.md`
3. Review existing modules
4. Escalate to CTO if needed

---

**SDK Version:** 1.0.0  
**Last Updated:** July 14, 2026  
**Status:** Stable
