# FlowCore Integration Guide

**Version:** 1.0.0  
**Date:** July 14, 2026  
**Product:** FlowCore Financial Copilot  
**Status:** Ready for Implementation

---

## INTRODUCTION

This guide provides specific technical integration points for building FlowCore on Dario OS. FlowCore is the first product built on the Dario OS platform, serving as both a reference implementation and a revenue-generating financial copilot.

**FlowCore Differentiator:** Automatic financial intelligence without manual data entry. All data ingestion is automated; the AI proactively warns, forecasts, optimizes.

---

## ARCHITECTURE OVERVIEW

```
┌────────────────────────────────────────────────────┐
│           FlowCore Financial Copilot               │
├────────────────────────────────────────────────────┤
│                                                    │
│  Dashboard Layer (Next.js)                         │
│  ├── /flowcore                    Main dashboard   │
│  ├── /flowcore/accounts           Account mgmt     │
│  ├── /flowcore/transactions       Transaction log  │
│  ├── /flowcore/insights           AI insights      │
│  ├── /flowcore/forecasts          Cash flow, tax   │
│  ├── /flowcore/recommendations    Action items     │
│  └── /flowcore/settings           Configuration    │
│                                                    │
│  API Layer (FastAPI Microservice, port 8001)      │
│  ├── /api/flowcore/accounts       CRUD operations │
│  ├── /api/flowcore/transactions   Upload/analyze  │
│  ├── /api/flowcore/forecast       Predictions     │
│  ├── /api/flowcore/insights       AI analysis     │
│  ├── /api/flowcore/optimize       Tax optimization│
│  └── /api/flowcore/recommend      Recommendations │
│                                                    │
│  Data Ingestion Layer (Async Workers)             │
│  ├── Email Parser (Gmail, Outlook)                │
│  ├── Bank Connector (Plaid API)                   │
│  ├── Brokerage Connector (APIs)                   │
│  ├── SMS/WhatsApp Parser                          │
│  └── Document Parser (Tax docs, statements)       │
│                                                    │
│  AI/Analytics Engine (DRT-001 Workflows)          │
│  ├── flowcore:ingest_data         Data processing │
│  ├── flowcore:analyze_expenses    Expense ML      │
│  ├── flowcore:forecast_cash       Cash prediction │
│  ├── flowcore:detect_anomalies    Anomaly detect  │
│  ├── flowcore:optimize_taxes      Tax algorithms  │
│  └── flowcore:generate_insights   AI synthesis    │
│                                                    │
│  Data Layer (PostgreSQL, separate schema)         │
│  ├── flowcore_accounts            Account records │
│  ├── flowcore_transactions        All transactions│
│  ├── flowcore_investments         Portfolio data  │
│  ├── flowcore_taxes               Tax tracking    │
│  ├── flowcore_insights            AI results      │
│  ├── flowcore_recommendations     Action items    │
│  └── flowcore_ingestion_log       Processing log  │
│                                                    │
└────────────────────────────────────────────────────┘
         △ △ △ Consumes Dario OS Services △ △ △
         - Authentication (JWT)
         - Workflow Engine (DRT-001)
         - Data Storage (PostgreSQL)
         - Observability (Logging, Metrics)
```

---

## CORE DATA INGESTION

### Design Principle: Zero Manual Entry

Users never type financial data. Everything is automated.

**Supported Data Sources:**

| Source | Integration | Status | Priority |
|--------|-------------|--------|----------|
| Email (Gmail/Outlook) | OAuth 2.0 | Phase 1 | P0 |
| Bank Accounts (Plaid) | Plaid API | Phase 1 | P0 |
| Credit Cards | Plaid API | Phase 1 | P0 |
| Brokerage Accounts | OAuth + APIs | Phase 1 | P0 |
| Tax Documents | PDF Parser | Phase 1 | P1 |
| Government Services | APIs (IRS, etc.) | Phase 2 | P2 |
| SMS/WhatsApp | SMS Parser | Phase 2 | P2 |

### Implementation Pattern

```python
# api/ingestion/base.py
class DataIngestionWorker:
    """Base class for all data ingestion workers"""
    
    async def authenticate(self):
        """Connect to external data source"""
        pass
    
    async def fetch_data(self) -> List[Dict]:
        """Retrieve raw data from source"""
        pass
    
    async def parse_data(self, raw: List[Dict]) -> List[FinancialRecord]:
        """Normalize to FlowCore schema"""
        pass
    
    async def store_data(self, records: List[FinancialRecord]):
        """Save to PostgreSQL"""
        pass
    
    async def trigger_analysis(self):
        """Queue DRT-001 workflows for AI analysis"""
        pass

# api/ingestion/email_parser.py
class EmailIngestionWorker(DataIngestionWorker):
    """Parse emails for financial information"""
    
    async def authenticate(self):
        # Use Dario OS auth to get user's Gmail token
        user_token = await self.get_user_service_token("gmail")
        self.gmail_client = Gmail(token=user_token)
    
    async def fetch_data(self) -> List[Dict]:
        # Get emails from last 7 days
        messages = await self.gmail_client.search(
            query="label:Financial OR from:bank OR from:broker",
            days=7
        )
        return messages
    
    async def parse_data(self, emails):
        transactions = []
        for email in emails:
            # Extract amounts, dates, payees from email
            parsed = await self.parse_email_body(email)
            if parsed:
                transactions.append(parsed)
        return transactions

# api/ingestion/plaid_worker.py
class PlaidIngestionWorker(DataIngestionWorker):
    """Sync bank and credit card data via Plaid"""
    
    async def authenticate(self):
        # Exchange Plaid Link token for Access token
        self.plaid = PlaidClient(
            client_id=os.getenv("PLAID_CLIENT_ID"),
            secret=os.getenv("PLAID_SECRET")
        )
    
    async def fetch_data(self):
        accounts = await self.plaid.get_accounts()
        transactions = await self.plaid.get_transactions(
            start_date=(today - timedelta(days=90)),
            end_date=today
        )
        return {"accounts": accounts, "transactions": transactions}
    
    async def parse_data(self, data):
        records = []
        for txn in data["transactions"]:
            records.append(FlowCoreTransaction(
                amount=txn["amount"],
                date=txn["date"],
                description=txn["name"],
                category=self.categorize(txn),
                account_id=txn["account_id"]
            ))
        return records
```

### Workflow Integration

```python
# api/integrations/workflow_triggers.py
async def trigger_ingestion_workflow(ingestion_type: str):
    """Queue ingestion task in DRT-001"""
    
    execution = await call_drt(
        workflow_type="flowcore:ingest_data",
        params={
            "ingestion_type": ingestion_type,  # "email", "plaid", etc.
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": current_user.id
        }
    )
    
    return execution  # execution_id for polling

async def poll_ingestion_status(execution_id: str):
    """Check if ingestion workflow is complete"""
    
    status = await get_drt_status(execution_id)
    
    if status["state"] == "completed":
        # Workflow finished, results stored in DB
        insights = await db.query(FlowCoreInsight).filter(
            FlowCoreInsight.execution_id == execution_id
        ).all()
        return insights
    
    return status
```

---

## DATA MODELS

### Core Tables

```python
# api/models/flowcore.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FlowCoreAccount(Base):
    """User's connected financial account"""
    __tablename__ = "flowcore_accounts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    account_name = Column(String)           # e.g., "Chase Checking"
    institution = Column(String)             # e.g., "plaid"
    account_type = Column(String)            # "checking", "savings", "credit", "investment"
    external_id = Column(String, unique=True)  # Plaid account_id
    access_token = Column(String)           # Encrypted
    last_sync = Column(DateTime)
    balance = Column(Float)
    status = Column(String)  # "active", "inactive", "disconnected"
    metadata = Column(JSON)  # Source-specific data

class FlowCoreTransaction(Base):
    """Individual transaction"""
    __tablename__ = "flowcore_transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    account_id = Column(Integer, ForeignKey("flowcore_accounts.id"))
    amount = Column(Float)
    date = Column(DateTime)
    description = Column(String)
    category = Column(String)
    merchant = Column(String)
    status = Column(String)  # "pending", "posted"
    external_id = Column(String, unique=True)
    ingestion_source = Column(String)  # "plaid", "email", "manual"
    created_at = Column(DateTime, default=datetime.utcnow)

class FlowCoreInvestment(Base):
    """Investment holdings"""
    __tablename__ = "flowcore_investments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    account_id = Column(Integer, ForeignKey("flowcore_accounts.id"))
    symbol = Column(String)
    quantity = Column(Float)
    purchase_price = Column(Float)
    current_price = Column(Float)
    cost_basis = Column(Float)
    current_value = Column(Float)
    gain_loss = Column(Float)
    last_updated = Column(DateTime)

class FlowCoreTaxRecord(Base):
    """Tax tracking and documentation"""
    __tablename__ = "flowcore_tax_records"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    tax_year = Column(Integer)
    income_total = Column(Float)
    deductions_total = Column(Float)
    capital_gains = Column(Float)
    estimated_tax_liability = Column(Float)
    documented = Column(Boolean)  # All records documented
    metadata = Column(JSON)

class FlowCoreInsight(Base):
    """AI-generated insights"""
    __tablename__ = "flowcore_insights"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    insight_type = Column(String)  # "opportunity", "warning", "forecast"
    title = Column(String)
    description = Column(String)
    priority = Column(String)  # "high", "medium", "low"
    recommended_action = Column(String)
    financial_impact = Column(Float)  # Potential savings/gain
    created_at = Column(DateTime, default=datetime.utcnow)
    dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime)

class FlowCoreRecommendation(Base):
    """Actionable recommendations"""
    __tablename__ = "flowcore_recommendations"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    recommendation_type = Column(String)  # "tax_saving", "debt_reduction", etc.
    title = Column(String)
    description = Column(String)
    financial_impact = Column(Float)
    complexity = Column(String)  # "simple", "moderate", "complex"
    estimated_time = Column(Integer)  # Minutes to implement
    status = Column(String)  # "new", "in_progress", "completed"
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## API ENDPOINTS

### Accounts

```python
# POST /api/flowcore/accounts/connect
# Request: { "connection_type": "plaid" }
# Response: { "link_token": "...", "session_id": "..." }
# Initiates Plaid Link flow

# GET /api/flowcore/accounts
# Response: [{ "id": 1, "name": "Chase Checking", "balance": 5000, ... }, ...]
# List all connected accounts

# POST /api/flowcore/accounts/{id}/sync
# Triggers immediate sync of account data
# Returns: { "execution_id": "exec_123", "status": "queued" }

# DELETE /api/flowcore/accounts/{id}
# Disconnect account from FlowCore
```

### Transactions

```python
# GET /api/flowcore/transactions
# Query params: start_date, end_date, category, account_id
# Response: [{ "id": 1, "amount": -50, "description": "Coffee", ... }, ...]
# List transactions with filtering

# GET /api/flowcore/transactions/{id}
# Response: { "id": 1, full transaction data }

# POST /api/flowcore/transactions/analyze
# Request: { "data": uploaded CSV/PDF }
# Response: { "execution_id": "exec_123" }
# Analyze uploaded statement
```

### Cash Flow Forecast

```python
# GET /api/flowcore/forecast/cashflow
# Query params: months (default: 12)
# Response:
# {
#   "forecasts": [
#     { "month": "2026-08", "projected_balance": 5500, "confidence": 0.92 },
#     ...
#   ],
#   "factors": ["paycheck on 15th", "subscription on 1st", ...]
# }

# POST /api/flowcore/forecast/scenario
# Request: { "scenario": "lose_job", "months": 6 }
# Response: { "execution_id": "exec_123" }
# Run what-if scenarios
```

### Tax Optimization

```python
# GET /api/flowcore/tax/estimated
# Response:
# {
#   "tax_year": 2026,
#   "estimated_liability": 45000,
#   "breakdown": {
#     "income_tax": 35000,
#     "self_employment_tax": 10000
#   },
#   "opportunities": [
#     {
#       "title": "Max out 401(k)",
#       "savings": 5000,
#       "deadline": "2026-12-31"
#     }
#   ]
# }

# POST /api/flowcore/tax/optimize
# Request: { "filing_status": "single", "dependents": 0 }
# Response: { "execution_id": "exec_123" }
# Generate tax optimization plan
```

### AI Insights

```python
# GET /api/flowcore/insights
# Query params: type (opportunity|warning|forecast), priority, dismissed=false
# Response: [{ "title": "High spending in dining", "impact": 200, ... }, ...]

# GET /api/flowcore/insights/summary
# Response:
# {
#   "monthly_summary": "You spent $3,500 this month, up 15% vs last month",
#   "top_categories": ["Housing", "Food", "Transportation"],
#   "alerts": [
#     { "title": "Unusual charge on credit card", "amount": 500 }
#   ]
# }

# POST /api/flowcore/insights/{id}/dismiss
# Dismiss an insight
```

---

## DASHBOARD PAGES

### 1. Main Dashboard (/flowcore)

**Display:**
- Financial health score (0-100)
- Net worth (total assets - liabilities)
- Monthly spending snapshot
- Key alerts and recommendations
- Quick action buttons

**Components:**
- Dashboard cards
- Mini charts
- Action callouts
- Account balances summary

### 2. Accounts (/flowcore/accounts)

**Display:**
- List of connected accounts
- Account balances
- Last sync time
- Connection status

**Actions:**
- Connect new account (Plaid Link)
- Disconnect account
- Manual sync
- View account transactions

### 3. Transactions (/flowcore/transactions)

**Display:**
- Transaction list with filtering
- Categories with spending trends
- Monthly/yearly summaries
- Export to CSV

**Actions:**
- Filter by date range
- Filter by category
- Tag transactions
- Upload bank statements

### 4. Forecasts (/flowcore/forecasts)

**Display:**
- 12-month cash flow forecast chart
- Projected account balances
- Key upcoming transactions
- Confidence intervals

**Actions:**
- Adjust forecast parameters
- Run scenarios (lose job, big purchase, etc.)
- Generate forecast report

### 5. Taxes (/flowcore/taxes)

**Display:**
- Estimated tax liability
- Tax breakdown by type
- Tax-saving opportunities
- Documents collected status

**Actions:**
- View tax optimization plan
- View collected documents
- Generate tax summary
- Schedule tax planning session

### 6. Insights (/flowcore/insights)

**Display:**
- AI-generated insights and opportunities
- Spending anomalies
- Recommendations with impact
- Historical insights

**Actions:**
- Dismiss insights
- View detailed explanation
- Implement recommendation

### 7. Settings (/flowcore/settings)

**Display:**
- Connected accounts
- Notification preferences
- Data privacy settings
- Export data

**Actions:**
- Adjust alert thresholds
- Change categories
- Download data
- Disconnect accounts

---

## WORKFLOW INTEGRATION (DRT-001)

### Workflow Types

Define in `api/workflows/definitions.py`:

```python
FLOWCORE_WORKFLOWS = {
    "flowcore:ingest_data": {
        "description": "Ingest financial data from multiple sources",
        "params": {
            "ingestion_type": ["email", "plaid", "pdf"],
            "user_id": "int"
        },
        "expected_output": {
            "transactions_imported": "int",
            "accounts_synced": "int"
        }
    },
    
    "flowcore:analyze_expenses": {
        "description": "Analyze spending patterns and categorize",
        "params": {
            "time_period": "string",  # "month", "quarter", "year"
            "user_id": "int"
        },
        "expected_output": {
            "categories": "dict",
            "anomalies": "list"
        }
    },
    
    "flowcore:forecast_cash": {
        "description": "Generate cash flow forecast",
        "params": {
            "months": "int",
            "user_id": "int"
        },
        "expected_output": {
            "forecasts": "list",
            "confidence": "float"
        }
    },
    
    "flowcore:optimize_taxes": {
        "description": "Generate tax optimization recommendations",
        "params": {
            "tax_year": "int",
            "filing_status": "string",
            "user_id": "int"
        },
        "expected_output": {
            "estimated_liability": "float",
            "opportunities": "list"
        }
    }
}
```

### Triggering Workflows

```python
# api/services/flowcore_service.py
async def ingest_financial_data(user_id: int, source: str):
    """Trigger data ingestion workflow"""
    
    execution = await call_drt(
        workflow_type="flowcore:ingest_data",
        params={
            "user_id": user_id,
            "ingestion_type": source,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    # Store execution ID for tracking
    await db.create(WorkflowExecution, {
        "user_id": user_id,
        "workflow_type": "flowcore:ingest_data",
        "execution_id": execution["execution_id"],
        "status": "queued"
    })
    
    return execution

async def get_workflow_results(execution_id: str):
    """Get results after workflow completes"""
    
    status = await get_drt_status(execution_id)
    
    if status["state"] == "completed":
        results = status.get("result", {})
        
        # Insights have been generated by DRT-001
        # Retrieve and display to user
        return {
            "status": "complete",
            "results": results,
            "insights": await get_insights_from_workflow(execution_id)
        }
    
    return {"status": status["state"]}
```

---

## AUTHENTICATION & AUTHORIZATION

### Dario OS Integration

All FlowCore endpoints require JWT token from Dario OS:

```python
# api/middleware/auth.py
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthCredentials = Depends(security)):
    """Verify JWT with Dario OS auth"""
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/auth/verify",
            headers={"Authorization": f"Bearer {credentials.credentials}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = response.json()
        return user

# All endpoints protected
@router.get("/dashboard")
async def get_dashboard(user = Depends(get_current_user)):
    """Get user's dashboard data"""
    return await flowcore_service.get_dashboard(user["id"])
```

### External Service OAuth

For services like Plaid, Gmail:

```python
# api/auth/external_oauth.py
class ExternalOAuthManager:
    """Manage external service credentials"""
    
    async def store_external_token(
        self,
        user_id: int,
        service: str,
        token: str,
        refresh_token: str = None
    ):
        """Encrypt and store external service tokens"""
        
        encrypted = encrypt_token(token)
        
        await db.create(ExternalCredential, {
            "user_id": user_id,
            "service": service,  # "plaid", "gmail", etc.
            "access_token": encrypted,
            "refresh_token": encrypt_token(refresh_token) if refresh_token else None,
            "expires_at": datetime.utcnow() + timedelta(hours=1)
        })
    
    async def get_valid_token(self, user_id: int, service: str):
        """Get valid token, refresh if needed"""
        
        cred = await db.get(ExternalCredential, user_id, service)
        
        if cred and cred.expires_at < datetime.utcnow():
            # Token expired, refresh it
            cred.access_token = await self.refresh_external_token(service, cred)
            await db.update(cred)
        
        return decrypt_token(cred.access_token)
```

---

## DEPLOYMENT

### Environment Variables

```bash
# Database
DATABASE_URL="postgresql://user:password@db:5432/flowcore"

# Dario OS
DARIO_OS_BACKEND="https://api.dariobot.com"
DRT_RUNTIME="https://runtime.dariobot.com"

# External Services
PLAID_CLIENT_ID="..."
PLAID_SECRET="..."
GMAIL_CLIENT_ID="..."
GMAIL_SECRET="..."

# Security
SECRET_KEY="..."
TOKEN_ENCRYPTION_KEY="..."

# Logging
LOG_LEVEL="info"
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY api/ ./api/
COPY alembic/ ./alembic/

# Run migrations
RUN DATABASE_URL="sqlite:///./init.db" alembic upgrade head

# Start service
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Kubernetes Deployment (Production)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flowcore-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: flowcore-api
  template:
    metadata:
      labels:
        app: flowcore-api
    spec:
      containers:
      - name: flowcore-api
        image: flowcore:latest
        ports:
        - containerPort: 8001
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: flowcore-secrets
              key: database-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

## MONITORING & OBSERVABILITY

### Health Endpoints

```python
@router.get("/health")
async def health():
    """Basic health check"""
    return {"status": "ok"}

@router.get("/ready")
async def ready():
    """Readiness check - dependencies available"""
    
    db_ok = await check_database()
    drt_ok = await check_drt_runtime()
    
    if db_ok and drt_ok:
        return {"status": "ready"}
    
    return {"status": "not_ready", "details": {
        "database": db_ok,
        "runtime": drt_ok
    }}, 503
```

### Metrics

```python
from prometheus_client import Counter, Histogram

# Track API calls
api_calls = Counter('flowcore_api_calls_total', 'Total API calls', ['endpoint'])
api_latency = Histogram('flowcore_api_latency_seconds', 'API latency', ['endpoint'])

# Track data ingestion
ingestion_records = Counter('flowcore_ingestion_records', 'Records ingested', ['source'])

# Track workflows
workflows_executed = Counter('flowcore_workflows_executed', 'Workflows executed', ['type'])
workflow_latency = Histogram('flowcore_workflow_latency_seconds', 'Workflow latency', ['type'])
```

---

## TESTING STRATEGY

### Unit Tests

```python
# tests/test_ingestion.py
import pytest
from api.ingestion.plaid_worker import PlaidIngestionWorker

@pytest.mark.asyncio
async def test_plaid_authentication():
    worker = PlaidIngestionWorker()
    await worker.authenticate()
    assert worker.plaid is not None

@pytest.mark.asyncio
async def test_parse_transaction():
    worker = PlaidIngestionWorker()
    raw = {
        "amount": 50,
        "date": "2026-07-14",
        "name": "Coffee Shop"
    }
    parsed = await worker.parse_data([raw])
    assert len(parsed) == 1
    assert parsed[0].amount == 50
```

### Integration Tests

```python
# tests/test_api_integration.py
@pytest.mark.asyncio
async def test_accounts_flow():
    # 1. Connect account via Plaid
    response = await client.post("/api/flowcore/accounts/connect", ...)
    link_token = response.json()["link_token"]
    
    # 2. Simulate Plaid callback
    await simulate_plaid_callback(link_token)
    
    # 3. Verify account is connected
    accounts = await client.get("/api/flowcore/accounts")
    assert len(accounts.json()) > 0
    
    # 4. Verify transactions are synced
    transactions = await client.get("/api/flowcore/transactions")
    assert len(transactions.json()) > 0
```

### E2E Tests

```python
# tests/test_e2e_dashboard.py
# Use Playwright to test full user journey
async def test_user_connects_account_and_sees_forecast():
    # 1. Login
    await page.goto("http://localhost:3000/login")
    await page.fill('[name="email"]', "user@example.com")
    await page.fill('[name="password"]', "password")
    await page.click('button[type="submit"]')
    
    # 2. Navigate to accounts
    await page.goto("http://localhost:3000/flowcore/accounts")
    
    # 3. Connect account
    await page.click("text=Connect Account")
    # (Plaid Link modal appears and completes)
    
    # 4. Navigate to forecasts
    await page.goto("http://localhost:3000/flowcore/forecasts")
    
    # 5. Verify forecast chart exists and has data
    assert await page.locator("canvas").count() > 0
```

---

## LAUNCH CHECKLIST

- [ ] All endpoints implemented and tested
- [ ] Dashboard pages created and responsive
- [ ] Authentication integrated with Dario OS
- [ ] Plaid integration complete and tested
- [ ] Email parser working for financial documents
- [ ] Tax workflows generating insights
- [ ] Forecast generation accurate
- [ ] Recommendations appearing in dashboard
- [ ] Database migrations applied
- [ ] Docker image built and tested
- [ ] Environment variables documented
- [ ] Monitoring and alerting configured
- [ ] Documentation complete
- [ ] Security review passed
- [ ] Load testing complete (100+ concurrent users)
- [ ] Production deployment tested
- [ ] Runbook for operations team
- [ ] Support and escalation procedures documented

---

## SUCCESS METRICS

**User Engagement:**
- 80%+ users connect at least one account within first week
- Daily active users
- Feature adoption rates

**Product Quality:**
- < 1% error rate on ingestion
- < 100ms API latency (p95)
- 99.9% uptime

**Business Impact:**
- Tax savings realized per user (tracked annually)
- Time saved per user (hours/year)
- Net Promoter Score (NPS) > 50

---

**FlowCore Integration Guide v1.0.0**  
**Last Updated:** July 14, 2026
