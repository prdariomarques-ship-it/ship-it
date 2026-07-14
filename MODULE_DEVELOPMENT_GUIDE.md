# Module Development Guide for Dario OS

**Version:** 1.0.0  
**Date:** July 14, 2026  
**Audience:** Module Developers

---

## INTRODUCTION

This guide provides step-by-step instructions for developing modules (products) on Dario OS. A module is a domain-specific application that solves a real user problem by consuming Dario OS platform services.

**Key Concept:** Your module doesn't modify Dario OS. Your module consumes Dario OS services.

---

## PREREQUISITES

Before starting module development, ensure you have:

1. **Local Dario OS Setup**
   - Backend running on port 8000
   - DRT-001 Runtime running on port 5000
   - Frontend Dashboard running on port 3000
   - PostgreSQL or SQLite database configured
   - Alembic for schema migrations

2. **Required Skills**
   - Python (for API service)
   - TypeScript/React (for dashboard UI)
   - SQL (for data models)
   - REST API design

3. **Development Tools**
   - Git
   - Docker (recommended)
   - Python 3.9+
   - Node.js 18+

---

## MODULE ARCHITECTURE

Every module follows this structure:

```
your-module/
├── api/                      # FastAPI microservice
│   ├── main.py              # Entry point
│   ├── endpoints/           # Your API routes
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   └── services/            # Business logic
├── dashboard/               # React/Next.js pages
│   ├── page.tsx            # Main page
│   └── components/         # Shared UI components
├── migrations/              # Alembic schema migrations
├── tests/                   # Unit & integration tests
├── docker/                  # Docker configuration
│   ├── Dockerfile          # Container image
│   └── compose.yml         # Container orchestration (dev)
├── docs/                    # Module documentation
│   ├── API.md              # API documentation
│   ├── ARCHITECTURE.md     # Module architecture
│   └── DEPLOYMENT.md       # Deployment guide
└── README.md               # Project overview
```

---

## STEP 1: CREATE MODULE REPOSITORY

**Task:** Initialize your module as a standalone Git repository.

```bash
# Create repository
mkdir your-module
cd your-module
git init

# Create Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Create directory structure
mkdir -p api/endpoints api/models api/schemas api/services
mkdir -p dashboard/components
mkdir -p migrations tests docker docs

# Create core files
touch api/__init__.py
touch api/main.py
touch api/models.py
touch api/schemas.py
touch README.md
touch requirements.txt
touch .env.example
```

---

## STEP 2: SET UP PYTHON BACKEND

### 2.1 Install Dependencies

Create `requirements.txt`:

```
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
alembic==1.13.1
pydantic==2.5.0
python-dotenv==1.0.0
httpx==0.25.2
```

Install:
```bash
pip install -r requirements.txt
```

### 2.2 Create Main API Service

Create `api/main.py`:

```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

app = FastAPI(
    title="Your Module API",
    version="1.0.0"
)

# CORS for dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./dev.db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Import routers
# from api.endpoints import your_routes
# app.include_router(your_routes.router, prefix="/api/yourmodule")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 2.3 Define Data Models

Create `api/models.py`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class YourModel(Base):
    __tablename__ = "yourmodule_table"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    name = Column(String, index=True)
    value = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 2.4 Create API Schemas

Create `api/schemas.py`:

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class YourModelCreate(BaseModel):
    name: str
    value: float

class YourModelResponse(BaseModel):
    id: int
    user_id: int
    name: str
    value: float
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
```

### 2.5 Create API Endpoints

Create `api/endpoints/your_routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from api.main import get_db
from api.models import YourModel
from api.schemas import YourModelCreate, YourModelResponse

router = APIRouter()

@router.post("/create", response_model=YourModelResponse)
async def create_item(
    item: YourModelCreate,
    db: AsyncSession = Depends(get_db)
):
    db_item = YourModel(**item.dict())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/{item_id}", response_model=YourModelResponse)
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db)
):
    item = await db.get(YourModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
```

---

## STEP 3: SET UP DATABASE MIGRATIONS

### 3.1 Initialize Alembic

```bash
alembic init alembic
```

### 3.2 Configure Alembic

Edit `alembic/env.py` to point to your database:

```python
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
from api.models import Base

config = context.config
sqlalchemy_url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
config.set_main_option("sqlalchemy.url", sqlalchemy_url)
target_metadata = Base.metadata

# ... rest of configuration
```

### 3.3 Create Initial Migration

```bash
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## STEP 4: INTEGRATE WITH DARIO OS AUTHENTICATION

### 4.1 Add JWT Verification

Create `api/auth.py`:

```python
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredentials
import httpx
import os

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthCredentials = Depends(security)):
    """Verify JWT token with Dario OS auth service"""
    token = credentials.credentials
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid token")
            
            user_data = response.json()
            return user_data
        except Exception as e:
            raise HTTPException(status_code=401, detail="Auth verification failed")
```

### 4.2 Protect Endpoints

```python
from api.auth import verify_token

@router.get("/protected")
async def protected_route(user = Depends(verify_token)):
    return {"message": f"Hello {user['email']}"}
```

---

## STEP 5: ADD DASHBOARD PAGES

### 5.1 Create Route Group

In `/home/user/ship-it/frontend/app/yourmodule/`:

```bash
mkdir -p /home/user/ship-it/frontend/app/yourmodule
cd /home/user/ship-it/frontend/app/yourmodule
touch page.tsx layout.tsx
mkdir components
```

### 5.2 Create Main Page

Create `/home/user/ship-it/frontend/app/yourmodule/page.tsx`:

```typescript
'use client';

import { useEffect, useState } from 'react';

export default function YourModulePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch('http://localhost:8001/api/items', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
        
        if (!response.ok) throw new Error('Failed to fetch');
        
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold">Your Module</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
```

### 5.3 Use Shared Components

```typescript
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export default function YourModulePage() {
  return (
    <div className="space-y-4">
      <Card>
        <h2>My Feature</h2>
        <Button>Click me</Button>
      </Card>
    </div>
  );
}
```

---

## STEP 6: INTEGRATE WITH WORKFLOWS (DRT-001)

### 6.1 Define Workflow

```python
# api/workflows.py
WORKFLOW_DEFINITIONS = {
    "yourmodule:process_data": {
        "description": "Process data with AI",
        "params": {
            "data_id": "int",
            "options": "dict"
        }
    }
}
```

### 6.2 Execute Workflow

```python
import httpx

async def trigger_workflow(data_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:5000/workflows/execute",
            json={
                "workflow_type": "yourmodule:process_data",
                "params": {"data_id": data_id}
            }
        )
        return response.json()
```

### 6.3 Poll Workflow Status

```python
async def get_workflow_status(execution_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:5000/workflows/status/{execution_id}"
        )
        return response.json()
```

---

## STEP 7: WRITE TESTS

### 7.1 Unit Tests

Create `tests/test_endpoints.py`:

```python
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_create_item():
    response = client.post("/api/items", json={"name": "test", "value": 100})
    assert response.status_code == 200
```

### 7.2 Run Tests

```bash
pytest tests/
```

---

## STEP 8: CONTAINERIZE MODULE

### 8.1 Create Dockerfile

Create `docker/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY api/ ./api/
COPY alembic/ ./alembic/

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 8.2 Create Docker Compose (Dev)

Create `docker/compose.yml`:

```yaml
version: '3.9'

services:
  yourmodule-api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: "sqlite+aiosqlite:///./dev.db"
    volumes:
      - ../api:/app/api
```

### 8.3 Run Locally

```bash
docker compose -f docker/compose.yml up
```

---

## STEP 9: DOCUMENTATION

### 9.1 API Documentation

Create `docs/API.md`:

```markdown
# API Reference

## Endpoints

### Create Item
POST /api/items

**Request:**
```json
{
  "name": "string",
  "value": 100
}
```

**Response:** 200 OK
```json
{
  "id": 1,
  "name": "string",
  "value": 100,
  "created_at": "2026-07-14T12:00:00Z"
}
```

### Get Item
GET /api/items/{id}

**Response:** 200 OK
```json
{
  "id": 1,
  "name": "string",
  "value": 100,
  "created_at": "2026-07-14T12:00:00Z"
}
```
```

### 9.2 Architecture Document

Create `docs/ARCHITECTURE.md`:

Document your module's design, data flow, key components.

### 9.3 Deployment Guide

Create `docs/DEPLOYMENT.md`:

Document production deployment steps, environment variables, scaling strategy.

---

## STEP 10: DEPLOY MODULE

### 10.1 Update Environment

Create `.env`:

```
DATABASE_URL=postgresql://user:password@db:5432/yourmodule
DARIO_OS_BACKEND=http://localhost:8000
DRT_RUNTIME=http://localhost:5000
LOG_LEVEL=info
```

### 10.2 Run Migrations

```bash
DATABASE_URL="postgresql://..." alembic upgrade head
```

### 10.3 Start Service

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

### 10.4 Verify in Dashboard

Visit `http://localhost:3000/yourmodule` to see your dashboard pages.

---

## CHECKLIST

- [ ] Repository initialized with Git
- [ ] Python environment created
- [ ] FastAPI backend implemented
- [ ] Database models defined
- [ ] Alembic migrations configured
- [ ] JWT authentication integrated
- [ ] Dashboard pages created
- [ ] Tests written and passing
- [ ] Docker image built
- [ ] Documentation complete
- [ ] Local testing successful
- [ ] Environment variables documented
- [ ] Ready for deployment

---

## COMMON PATTERNS

### Calling Other Services

```python
async def call_dario_service(endpoint: str, token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000{endpoint}",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()
```

### Error Handling

```python
from fastapi import HTTPException

@router.get("/items/{item_id}")
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item
```

### Async Database Operations

```python
from sqlalchemy import select

async def get_user_items(user_id: int, db: AsyncSession):
    result = await db.execute(
        select(Item).where(Item.user_id == user_id)
    )
    return result.scalars().all()
```

---

## TROUBLESHOOTING

**Q: Dashboard pages not appearing in navigation**
A: Ensure route group folder name matches module name exactly. Add page.tsx with React component.

**Q: API endpoint returns 401 Unauthorized**
A: Verify JWT token is valid and not expired. Check Dario OS auth service is running.

**Q: Database migrations fail**
A: Ensure DATABASE_URL is set correctly and database is accessible. Run `alembic current` to check version.

**Q: CORS errors when calling API from dashboard**
A: Verify CORS middleware is configured with correct allowed origins in your FastAPI app.

---

## SUPPORT

For questions:
1. Read PLATFORM_SDK.md for platform concepts
2. Review existing modules in /modules
3. Check Dario OS API documentation
4. File issue in repository

**Dario OS Support:** CTO or Principal Engineer

---

**Guide Version:** 1.0.0  
**Last Updated:** July 14, 2026
