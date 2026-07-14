# Dario OS API Reference

**Version:** 1.0.0  
**Date:** July 14, 2026  
**Base URL:** http://localhost:8000/api (development)  
**Status:** Stable

---

## OVERVIEW

The Dario OS API is a REST API built with FastAPI. All endpoints require authentication via JWT token except `/api/auth/login` and `/health`.

### Authentication

All endpoints (except login) require a JWT token in the `Authorization` header:

```bash
curl http://localhost:8000/api/endpoint \
  -H "Authorization: Bearer eyJ0eXAi..."
```

### Response Format

All responses are JSON. Error responses include a `detail` field:

```json
{
  "detail": "Error message"
}
```

### Rate Limiting

Default: 120 requests per 60 seconds per user.

Response headers include:
- `RateLimit-Limit`: Maximum requests
- `RateLimit-Remaining`: Requests left
- `RateLimit-Reset`: Unix timestamp when limit resets

---

## AUTHENTICATION ENDPOINTS

### POST /api/auth/login

Login and receive access/refresh tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure-password"
}
```

**Response:** 200 OK
```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "9uZw...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user_id": 1,
  "email": "user@example.com",
  "role": "admin"
}
```

**Errors:**
- 400 Bad Request: Missing email or password
- 401 Unauthorized: Invalid credentials
- 429 Too Many Requests: Too many failed login attempts

---

### POST /api/auth/refresh

Refresh access token using refresh token.

**Request:**
```json
{
  "refresh_token": "9uZw..."
}
```

**Response:** 200 OK
```json
{
  "access_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### GET /api/auth/me

Get current user profile.

**Headers:**
```
Authorization: Bearer eyJ0eXAi...
```

**Response:** 200 OK
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "User Name",
  "role": "admin",
  "created_at": "2026-07-14T12:00:00Z"
}
```

---

### POST /api/auth/logout

Logout and invalidate tokens.

**Headers:**
```
Authorization: Bearer eyJ0eXAi...
```

**Response:** 204 No Content

---

## DASHBOARD ENDPOINTS

### GET /api/dashboard/summary

Get dashboard summary data (requires auth).

**Query Params:**
- `time_range` (optional): "day", "week", "month" (default: "month")

**Response:** 200 OK
```json
{
  "user_id": 1,
  "total_tasks": 42,
  "completed_tasks": 35,
  "upcoming_events": 5,
  "messages_unread": 3,
  "summary": "You have 5 upcoming events and 3 unread messages."
}
```

---

### GET /api/messages

Get user messages.

**Query Params:**
- `limit` (optional): Max results (default: 50, max: 500)
- `offset` (optional): Pagination offset (default: 0)
- `status` (optional): "unread", "read", "archived"

**Response:** 200 OK
```json
{
  "total": 127,
  "limit": 50,
  "offset": 0,
  "messages": [
    {
      "id": 1,
      "sender": "John Doe",
      "subject": "Meeting tomorrow",
      "body": "Let's discuss the project...",
      "status": "unread",
      "created_at": "2026-07-14T11:30:00Z"
    }
  ]
}
```

---

### GET /api/calendar

Get calendar events.

**Query Params:**
- `start_date` (required): ISO 8601 date
- `end_date` (required): ISO 8601 date
- `limit` (optional): Max results (default: 100)

**Response:** 200 OK
```json
{
  "events": [
    {
      "id": 1,
      "title": "Team Meeting",
      "start": "2026-07-15T14:00:00Z",
      "end": "2026-07-15T15:00:00Z",
      "location": "Conference Room A",
      "attendees": ["john@example.com", "jane@example.com"]
    }
  ]
}
```

---

### POST /api/calendar

Create calendar event.

**Request:**
```json
{
  "title": "Project Review",
  "start": "2026-07-16T10:00:00Z",
  "end": "2026-07-16T11:00:00Z",
  "location": "Room 101",
  "description": "Quarterly project review"
}
```

**Response:** 201 Created
```json
{
  "id": 42,
  "title": "Project Review",
  "start": "2026-07-16T10:00:00Z",
  "end": "2026-07-16T11:00:00Z",
  "location": "Room 101",
  "created_at": "2026-07-14T12:00:00Z"
}
```

---

### GET /api/tasks

Get user tasks.

**Query Params:**
- `status` (optional): "open", "completed", "archived"
- `priority` (optional): "high", "medium", "low"
- `limit` (optional): Max results (default: 50)

**Response:** 200 OK
```json
{
  "tasks": [
    {
      "id": 1,
      "title": "Complete report",
      "description": "Q2 financial report",
      "status": "open",
      "priority": "high",
      "due_date": "2026-07-15T17:00:00Z",
      "assigned_to": "john@example.com"
    }
  ]
}
```

---

### POST /api/tasks

Create task.

**Request:**
```json
{
  "title": "Review code",
  "description": "Review PR #123",
  "priority": "medium",
  "due_date": "2026-07-18T17:00:00Z"
}
```

**Response:** 201 Created
```json
{
  "id": 99,
  "title": "Review code",
  "description": "Review PR #123",
  "status": "open",
  "priority": "medium",
  "due_date": "2026-07-18T17:00:00Z",
  "created_at": "2026-07-14T12:00:00Z"
}
```

---

### PUT /api/tasks/{id}

Update task.

**Request:**
```json
{
  "status": "completed",
  "priority": "high"
}
```

**Response:** 200 OK
```json
{
  "id": 99,
  "title": "Review code",
  "status": "completed",
  "updated_at": "2026-07-14T12:30:00Z"
}
```

---

### DELETE /api/tasks/{id}

Delete task.

**Response:** 204 No Content

---

## WORKFLOW ENDPOINTS

### POST /api/workflows/execute

Execute a workflow (async).

**Request:**
```json
{
  "workflow_type": "tax_optimize",
  "params": {
    "income": 150000,
    "deductions": 45000,
    "filing_status": "single"
  }
}
```

**Response:** 202 Accepted
```json
{
  "execution_id": "exec_12345",
  "workflow_type": "tax_optimize",
  "status": "queued",
  "created_at": "2026-07-14T12:00:00Z"
}
```

---

### GET /api/workflows/status/{execution_id}

Get workflow execution status.

**Response:** 200 OK
```json
{
  "execution_id": "exec_12345",
  "workflow_type": "tax_optimize",
  "status": "completed",
  "result": {
    "estimated_tax": 45000,
    "optimizations": [
      {
        "title": "Max out 401(k)",
        "savings": 5000
      }
    ]
  },
  "started_at": "2026-07-14T12:00:00Z",
  "completed_at": "2026-07-14T12:05:00Z",
  "duration_ms": 300000
}
```

**Statuses:**
- `queued`: Waiting to execute
- `running`: Currently executing
- `completed`: Finished successfully
- `failed`: Execution failed
- `cancelled`: Execution cancelled

---

## OBSERVABILITY ENDPOINTS

### GET /health

Health check (no auth required).

**Response:** 200 OK
```json
{
  "status": "ok",
  "app": "Dario OS",
  "version": "0.2.1"
}
```

---

### GET /metrics

Prometheus metrics (no auth required).

**Response:** 200 OK
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/tasks",method="GET",status="200"} 1234
...
```

---

## ADMIN ENDPOINTS

### GET /api/admin/users

List all users (requires admin role).

**Query Params:**
- `limit` (optional): Max results
- `offset` (optional): Pagination offset

**Response:** 200 OK
```json
{
  "users": [
    {
      "id": 1,
      "email": "admin@example.com",
      "name": "Admin User",
      "role": "admin",
      "created_at": "2026-07-14T12:00:00Z"
    }
  ]
}
```

---

### GET /api/admin/logs

Get system logs (requires admin role).

**Query Params:**
- `level` (optional): "debug", "info", "warning", "error"
- `limit` (optional): Max results

**Response:** 200 OK
```json
{
  "logs": [
    {
      "timestamp": "2026-07-14T12:00:00Z",
      "level": "INFO",
      "message": "User logged in",
      "user_id": 1
    }
  ]
}
```

---

## ERROR CODES

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | Request successful |
| 201 | Created | Resource created |
| 204 | No Content | Successful deletion |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Missing/invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource already exists |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Internal server error |

---

## PAGINATION

Endpoints that return lists support pagination:

**Request:**
```
GET /api/tasks?limit=25&offset=50
```

**Response:**
```json
{
  "total": 150,
  "limit": 25,
  "offset": 50,
  "items": [...]
}
```

---

## FILTERING

Endpoints support filtering via query parameters:

```
GET /api/tasks?status=open&priority=high
```

Filter operators:
- Exact match: `field=value`
- Range: `field_min=10&field_max=100`
- Substring: `field__contains=text`
- Date range: `created_at_min=2026-07-01&created_at_max=2026-07-31`

---

## SORTING

Sort results with `sort` parameter:

```
GET /api/tasks?sort=-priority,+created_at
```

Format: `sort=[+|-]field,[+|-]field`
- `+` prefix: ascending (default)
- `-` prefix: descending

---

## WEBHOOK EVENTS

The platform can send webhooks for events:

```
POST https://your-app.com/webhooks/event
Content-Type: application/json
X-Webhook-Signature: sha256=...

{
  "event": "task.completed",
  "timestamp": "2026-07-14T12:00:00Z",
  "data": {
    "id": 99,
    "title": "Review code"
  }
}
```

Events:
- `task.created`
- `task.completed`
- `message.received`
- `event.scheduled`
- `workflow.completed`

---

## SDKs & CLIENTS

### Python

```python
from dario_os_client import DarioOS

client = DarioOS(
    base_url="http://localhost:8000",
    email="user@example.com",
    password="password"
)

# Get tasks
tasks = client.tasks.list(status="open")

# Create task
new_task = client.tasks.create(
    title="New task",
    priority="high"
)

# Execute workflow
result = client.workflows.execute(
    workflow_type="tax_optimize",
    params={...}
)
```

### TypeScript/JavaScript

```typescript
import { DarioOS } from 'dario-os-sdk';

const client = new DarioOS({
  baseUrl: 'http://localhost:8000',
  email: 'user@example.com',
  password: 'password'
});

// Get tasks
const tasks = await client.tasks.list({ status: 'open' });

// Create task
const newTask = await client.tasks.create({
  title: 'New task',
  priority: 'high'
});

// Execute workflow
const result = await client.workflows.execute({
  workflowType: 'tax_optimize',
  params: {...}
});
```

---

## COMMON PATTERNS

### Handling Errors

```python
try:
    response = await client.tasks.create(title="Task")
except HTTPException as e:
    if e.status_code == 400:
        print("Validation error:", e.detail)
    elif e.status_code == 401:
        print("Authentication failed")
except Exception as e:
    print("Network error:", str(e))
```

### Retrying Requests

```python
import asyncio

async def retry_request(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff
```

### Batch Operations

```python
# Create multiple tasks
tasks = [
    {"title": "Task 1", "priority": "high"},
    {"title": "Task 2", "priority": "medium"},
]

for task_data in tasks:
    task = await client.tasks.create(**task_data)
```

---

## PERFORMANCE TIPS

1. **Use pagination** for large datasets
2. **Cache responses** when appropriate
3. **Use selective fields** if API supports it
4. **Batch multiple operations** when possible
5. **Implement exponential backoff** for retries

---

**API Reference v1.0.0**  
**Last Updated:** July 14, 2026  
**OpenAPI Documentation:** http://localhost:8000/docs
