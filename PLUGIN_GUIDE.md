# Plugin Development Guide for Dario OS

**Version:** 1.0.0  
**Date:** July 14, 2026  
**Audience:** Plugin Developers

---

## INTRODUCTION

This guide explains how to build plugins that extend the Dario OS dashboard and backend without modifying core platform code.

**Key Difference from Modules:**
- **Modules** (like FlowCore) are complete products with API services and data models
- **Plugins** are lightweight extensions that integrate with existing services

---

## PLUGIN TYPES

### 1. Dashboard Plugins

Extend the UI with new pages, components, or integrations.

**Example:** A weather widget, crypto ticker, or news feed.

### 2. API Plugins

Add new endpoints to the backend without modifying core routes.

**Example:** A calculator API, translation service, or email sender.

### 3. Workflow Plugins

Define custom workflow types for automation.

**Example:** SMS notification workflow, PDF generator, or report scheduler.

### 4. Integration Plugins

Connect external services to Dario OS.

**Example:** Slack integration, Gmail integration, or webhook receiver.

---

## PLUGIN ARCHITECTURE

Plugins follow this structure:

```
your-plugin/
├── manifest.json           # Plugin metadata
├── dashboard/              # Dashboard components (optional)
│   ├── page.tsx
│   └── components/
├── api/                    # Backend endpoints (optional)
│   ├── plugin_router.py
│   └── services/
├── workflows/              # Workflow definitions (optional)
│   └── definitions.json
└── README.md
```

---

## STEP 1: CREATE PLUGIN MANIFEST

Create `manifest.json`:

```json
{
  "name": "your-plugin",
  "version": "1.0.0",
  "title": "Your Plugin Title",
  "description": "What this plugin does",
  "author": "Your Name",
  "license": "MIT",
  
  "capabilities": {
    "dashboard": true,
    "api": true,
    "workflows": false
  },
  
  "permissions": [
    "read:dashboard",
    "write:api",
    "read:database"
  ],
  
  "dependencies": [
    "dario-os>=1.0.0"
  ],
  
  "entrypoints": {
    "dashboard": "dashboard/page.tsx",
    "api": "api/plugin_router.py"
  }
}
```

---

## STEP 2: CREATE DASHBOARD PLUGIN

### 2.1 Plugin Page Component

Create `dashboard/page.tsx`:

```typescript
'use client';

import { useState, useEffect } from 'react';

export default function YourPluginPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const response = await fetch('/api/your-plugin/data', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
        
        if (!response.ok) throw new Error('Failed to load');
        
        const result = await response.json();
        setData(result);
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-4">Your Plugin</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data && Object.entries(data).map(([key, value]) => (
          <div key={key} className="border p-4 rounded">
            <h2 className="font-bold">{key}</h2>
            <p>{JSON.stringify(value)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 2.2 Register with Dashboard

Add to `/frontend/app/yourplugin/page.tsx`:

```typescript
export { default } from '/your-plugin-path/dashboard/page';
```

Navigation is automatic if the folder exists.

---

## STEP 3: CREATE API PLUGIN

### 3.1 Plugin Router

Create `api/plugin_router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.auth import verify_token

router = APIRouter(prefix="/api/your-plugin", tags=["your-plugin"])

@router.get("/data")
async def get_plugin_data(
    user = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """Get plugin data for authenticated user"""
    
    # Your logic here
    return {
        "user_id": user["id"],
        "data": "your plugin data"
    }

@router.post("/action")
async def perform_action(
    payload: dict,
    user = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """Perform an action"""
    
    # Validate payload
    if not payload.get("action"):
        raise HTTPException(status_code=400, detail="Missing action")
    
    # Execute action
    result = await execute_plugin_action(payload["action"], user["id"], db)
    
    return {"result": result}
```

### 3.2 Register Plugin Routes

In `backend/main.py`:

```python
from your_plugin.api.plugin_router import router as your_plugin_router

# Include plugin router
app.include_router(
    your_plugin_router,
    prefix="/api",
    tags=["plugins"]
)
```

---

## STEP 4: CREATE WORKFLOW PLUGIN

### 4.1 Define Workflow Types

Create `workflows/definitions.json`:

```json
{
  "workflows": {
    "your-plugin:send-notification": {
      "description": "Send a notification via plugin",
      "params": {
        "message": "string",
        "channel": "string"
      }
    },
    "your-plugin:process-data": {
      "description": "Process data with plugin logic",
      "params": {
        "data": "object",
        "options": "object"
      }
    }
  }
}
```

### 4.2 Implement Workflow Handler

Create `workflows/handlers.py`:

```python
async def send_notification(params: dict, user_id: int):
    """Handle send-notification workflow"""
    
    message = params.get("message")
    channel = params.get("channel")
    
    # Send notification
    result = await send_via_channel(message, channel, user_id)
    
    return {
        "status": "sent",
        "notification_id": result["id"]
    }

async def process_data(params: dict, user_id: int):
    """Handle process-data workflow"""
    
    data = params.get("data")
    options = params.get("options")
    
    # Process data
    result = await process_plugin_data(data, options, user_id)
    
    return {
        "status": "processed",
        "result": result
    }
```

---

## STEP 5: CREATE INTEGRATION PLUGIN

### 5.1 External Service Integration

Create `api/integrations.py`:

```python
import httpx
import os

class ExternalServiceClient:
    """Client for external service integration"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("EXTERNAL_API_KEY")
        self.base_url = "https://api.example.com"
    
    async def authenticate(self):
        """Authenticate with external service"""
        pass
    
    async def send_request(self, endpoint: str, data: dict = None):
        """Send request to external service"""
        
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = await client.post(
                f"{self.base_url}/{endpoint}",
                json=data,
                headers=headers
            )
            
            return response.json()

# Initialize client
external_client = ExternalServiceClient()
```

### 5.2 Webhook Handler

Create `api/webhooks.py`:

```python
from fastapi import APIRouter, Request
import hmac
import hashlib

router = APIRouter(prefix="/api/webhooks/your-plugin")

@router.post("/handle")
async def handle_webhook(request: Request):
    """Handle incoming webhook from external service"""
    
    # Verify webhook signature
    signature = request.headers.get("X-Webhook-Signature")
    body = await request.body()
    
    expected_signature = hmac.new(
        os.getenv("WEBHOOK_SECRET").encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Process webhook
    data = await request.json()
    
    # Update database, trigger workflows, etc.
    await process_webhook_data(data)
    
    return {"status": "received"}
```

---

## STEP 6: PLUGIN CONFIGURATION

### 6.1 Environment Variables

Create `.env.example`:

```bash
# Plugin Configuration
PLUGIN_ENABLED=true
PLUGIN_DEBUG=false

# External Service
EXTERNAL_API_KEY=your-api-key
EXTERNAL_API_SECRET=your-secret
WEBHOOK_SECRET=your-webhook-secret

# Database
PLUGIN_DB_SCHEMA=your_plugin
```

### 6.2 Requirements

Create `requirements.txt`:

```
fastapi==0.104.1
httpx==0.25.2
pydantic==2.5.0
```

---

## STEP 7: PLUGIN INSTALLATION

### 7.1 Install Locally

```bash
# Copy plugin to plugins directory
cp -r your-plugin /home/user/ship-it/plugins/

# Install dependencies
cd /home/user/ship-it/plugins/your-plugin
pip install -r requirements.txt

# Restart backend
pkill -f "uvicorn main:app"
python -m uvicorn main:app --port 8000
```

### 7.2 Enable Plugin

Update `backend/settings.py`:

```python
ENABLED_PLUGINS = [
    "your-plugin",
    "other-plugins"
]
```

---

## STEP 8: PLUGIN PERMISSIONS

### System Permissions

Plugins declare what they need:

```json
{
  "permissions": [
    "read:dashboard",        // Read dashboard state
    "write:dashboard",       // Modify dashboard UI
    "read:database",         // Query database
    "write:database",        // Create/update records
    "read:auth",            // Access auth info
    "execute:workflows"     // Trigger workflows
  ]
}
```

Platform enforces sandboxing:
- Plugins cannot modify core files
- Plugins cannot access other plugins' data
- Plugins cannot escalate privileges
- API calls are rate-limited per plugin

---

## STEP 9: TESTING PLUGINS

### Unit Tests

Create `tests/test_plugin.py`:

```python
import pytest
from fastapi.testclient import TestClient
from your_plugin.api.plugin_router import router

client = TestClient(app)

@pytest.mark.asyncio
async def test_plugin_endpoint():
    response = client.get(
        "/api/your-plugin/data",
        headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_plugin_workflow():
    response = client.post(
        "/api/workflows/execute",
        json={
            "workflow_type": "your-plugin:send-notification",
            "params": {"message": "test", "channel": "email"}
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
```

---

## PLUGIN BEST PRACTICES

### 1. Error Handling

```python
try:
    result = await perform_action(data)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.error(f"Plugin error: {e}")
    raise HTTPException(status_code=500, detail="Internal error")
```

### 2. Logging

```python
from utils.logging import get_logger

logger = get_logger(__name__)

logger.info(f"Plugin action executed: {action}")
logger.warning(f"Plugin rate limit approaching")
logger.error(f"Plugin failed: {error}")
```

### 3. Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
async def get_cached_data(key: str):
    # This result is cached
    return await fetch_from_api(key)
```

### 4. Rate Limiting

```python
from services.rate_limit import rate_limiter

@rate_limiter.limit("100/minute")
@router.get("/data")
async def get_data():
    pass
```

---

## PLUGIN TROUBLESHOOTING

| Issue | Cause | Solution |
|-------|-------|----------|
| Import error | Plugin path wrong | Check manifest entrypoint |
| 401 on API calls | No auth token | Get token before calling |
| Slow performance | N+1 queries | Batch database queries |
| Memory leak | Event listeners not cleared | Clean up on unmount |

---

## PLUGIN EXAMPLES

### 1. Weather Widget

```typescript
export default function WeatherWidget() {
  const [weather, setWeather] = useState(null);
  
  useEffect(() => {
    fetch('/api/weather/current')
      .then(r => r.json())
      .then(setWeather);
  }, []);
  
  return (
    <div className="p-4 bg-blue-50 rounded">
      <h3>Weather</h3>
      <p>{weather?.temp}°C - {weather?.condition}</p>
    </div>
  );
}
```

### 2. Calculator API

```python
@router.post("/calculate")
async def calculate(expression: str):
    """Calculate math expression"""
    try:
        result = eval(expression)  # Use safer eval or sympy
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 3. Email Workflow

```python
async def send_email(params: dict, user_id: int):
    """Send email via plugin workflow"""
    
    email_client = SMTPClient()
    
    await email_client.send(
        to=params["recipient"],
        subject=params["subject"],
        body=params["body"]
    )
    
    return {"status": "sent"}
```

---

## PLUGIN DISTRIBUTION

### Package Plugin

```bash
# Create distribution
tar czf your-plugin-1.0.0.tar.gz your-plugin/

# Sign package
gpg --detach-sign your-plugin-1.0.0.tar.gz
```

### Publish

1. Create GitHub release with tarball
2. List in plugin registry
3. Share installation instructions

---

## SUPPORT

For questions:
1. Check MODULE_DEVELOPMENT_GUIDE.md for core concepts
2. Review existing plugin examples
3. Read plugin troubleshooting section
4. File issue in plugin repository

---

**Plugin Development Guide v1.0.0**  
**Last Updated:** July 14, 2026
