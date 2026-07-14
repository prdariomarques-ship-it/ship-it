# Dashboard Feature Guide

**Complete guide to all dashboard pages and features**

## Pages Overview

### 🏠 Home Page

**URL:** `/`

The main landing page showing system status at a glance.

**What You See:**

1. **Status Cards** (4 cards across top)
   - Runtime Status: "healthy" or error
   - Version: Runtime version (e.g., "1.0.0")
   - Uptime: How long runtime has been running
   - Active Executions: Number of workflows running now

2. **Storage Status Panel**
   - Storage Valid: YES/NO (data corruption check)
   - Accepting Requests: YES/NO (can accept new workflows)

3. **Information Panel**
   - Runtime Version
   - LTS Period dates
   - Storage Mode
   - Durability guarantee

4. **Getting Started Links**
   - Execute Workflow
   - View Executions
   - Check System Health

**Refresh Rate:** Every 5 seconds (automatic)

**Use This Page:**
- ✅ Daily status check
- ✅ Verify system is "healthy"
- ✅ Check uptime trends
- ✅ Quick navigation to other pages

---

### 📊 Executions Page

**URL:** `/executions`

Monitor all workflow executions in one place.

**Features:**

1. **Search & Filter**
   - Search by execution ID or correlation ID
   - Filter by status: All, Running, Completed, Recovered, Failed

2. **Execution List** (when populated)
   - Shows all executions
   - Real-time status updates
   - Click any execution for full details

3. **Execution Details Modal**
   - Execution ID: Unique identifier
   - Correlation ID: For grouping related runs
   - Workflow Version: YAML version
   - Runtime Version: Which version executed it
   - Status: RUNNING, COMPLETED, RECOVERED, FAILED
   - Started At: Timestamp when started
   - Finished At: Timestamp when finished
   - Duration: Total time in milliseconds
   - Recovery Count: How many times recovered
   - Retry Count: How many times retried
   - Step History: Each step with timing
   - Audit Trail: All events for this execution

4. **Metrics**
   - Total Executions: Count of all executions
   - Running: Currently executing
   - Completed: Finished successfully

**Refresh Rate:** Every 5 seconds (automatic)

**Use This Page:**
- ✅ Monitor workflow progress
- ✅ Check execution details
- ✅ Review step timing breakdown
- ✅ Verify recovery events
- ✅ Search by ID
- ✅ Filter by status

---

### 🔧 Workflows Page

**URL:** `/workflows`

Upload, validate, and execute workflows.

**How to Use:**

1. **Write YAML**
   ```yaml
   name: my-workflow
   workflow_version: "1.0"
   runtime_version: "1.0"
   owner: operator
   timeout: 300
   steps:
     - name: step-1
       type: system
       config:
         description: "First step"
   ```

2. **Dry Run (Optional)**
   - Validates YAML without executing
   - Shows parsing result
   - Verifies all required fields present
   - Returns estimated duration

3. **Execute**
   - Runs workflow against live Runtime
   - Creates execution record
   - Begins step execution
   - Shows result in real-time

**YAML Requirements:**

| Field | Required | Example |
|-------|----------|---------|
| name | Yes | "my-workflow" |
| workflow_version | Yes | "1.0" |
| runtime_version | Yes | "1.0" |
| owner | Yes | "operator" |
| timeout | Yes | 300 (seconds) |
| steps | Yes | Array with ≥1 step |

**Step Configuration:**

```yaml
- name: step-name        # Required: unique name
  type: system           # Required: "system" or "manual"
  config:                # Optional: step config
    description: "..."
    # Other fields as needed
```

**Use This Page:**
- ✅ Test workflows before execution
- ✅ Execute production workflows
- ✅ Validate YAML syntax
- ✅ See dry run estimates

---

### 📋 Audit Page

**URL:** `/audit`

Chronological view of all events and state changes.

**What's Tracked:**

- State Transitions: INITIALIZED → RUNNING → COMPLETED
- Recovery Events: Crash detected, recovery initiated
- Step Completions: Each step start/finish
- Errors: Any failures or exceptions
- Checksum Verification: Data integrity checks

**Search & Filter:**

- Search: Find events by keyword
- Filter: By event type (State, Recovery, Error)

**Information Shown:**

| Column | Content |
|--------|---------|
| Timestamp | When event occurred |
| Event Type | TRANSITION, RECOVERY, ERROR, etc. |
| Details | Specific event information |
| Execution ID | Which execution |
| Affected Component | What changed (step, storage, etc.) |

**Use This Page:**
- ✅ Investigate failures
- ✅ Review recovery history
- ✅ Understand state changes
- ✅ Verify audit trail
- ✅ Compliance/logging

---

### 💾 System Health Page

**URL:** `/system`

Deep dive into storage, persistence, and recovery.

**Health Cards:**

1. **Disk & Persistence**
   - Storage Valid: File-based storage accessible
   - Accepting Requests: Can accept new workflows

2. **Checkpoint & WAL**
   - fsync() Durability: Writes durable to disk
   - Atomic Writes: No partial writes

3. **Memory & Performance**
   - Runtime Available: Responding to requests
   - API Responsive: HTTP endpoints active

4. **Recovery Capability**
   - Crash Safe: Can recover from any crash
   - WAL Replay: Can replay write-ahead log

**Storage Configuration:**

| Setting | Value | Meaning |
|---------|-------|---------|
| Storage Type | File-based | Uses .runtime directory |
| Persistence | JSON + WAL | Format of saved data |
| Durability | fsync() on every write | Survives power loss |
| Checksum | SHA256 | Detects corruption |
| Max Executions | ~100,000 | Before migration needed |
| Current Active | N | Workflows running now |

**Use This Page:**
- ✅ Verify system health
- ✅ Check storage status
- ✅ Confirm durability
- ✅ Monitor recovery capability
- ✅ Ensure no corruption

---

### 🔌 API Page

**URL:** `/api`

Endpoint reference and live testing.

**Available Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Runtime status |
| POST | /workflows | Execute/dry-run workflow |
| GET | /execution/{id} | Get execution details |
| DELETE | /graceful-shutdown | Shutdown with timeout |

**For Each Endpoint:**

- Method: GET, POST, DELETE
- Path: Full URL path
- Description: What it does
- Test Button: Try it out

**Example Request:**

```bash
curl http://localhost:5000/health
```

**Example Response:**

```json
{
  "status": "healthy",
  "runtime_version": "1.0.0",
  "uptime_seconds": 3600,
  "storage_valid": true,
  "accepting_requests": true,
  "active_executions": 0
}
```

**Use This Page:**
- ✅ Reference API endpoints
- ✅ Test API calls
- ✅ Debug integration issues
- ✅ Verify connectivity

---

### 📝 Logs Page

**URL:** `/logs`

Structured logs with filtering and export.

**Features:**

1. **Search**
   - Find events by keyword
   - Search across all fields

2. **Filters**
   - Level: Info, Warning, Error, Debug
   - Source: Runtime, Workflows, Recovery
   - Limit: How many to show

3. **Log Entries**

| Column | Content |
|--------|---------|
| Timestamp | When logged |
| Level | INFO, WARNING, ERROR, DEBUG |
| Source | Component that logged |
| Message | What happened |
| Execution ID | Associated execution (if any) |

4. **Export**
   - Download as CSV
   - Download as JSON
   - Save locally for archiving

**Log Levels:**

- 🔵 **INFO:** Normal operation events
- 🟡 **WARNING:** Potentially problematic
- 🔴 **ERROR:** Something failed
- 🟣 **DEBUG:** Detailed technical info

**Use This Page:**
- ✅ Debug issues
- ✅ Review operation history
- ✅ Export for compliance
- ✅ Archive historical records

---

### ⚙️ Settings Page

**URL:** `/settings`

Configuration and environment information.

**Sections:**

1. **Runtime Configuration**
   - Runtime Version: 1.0.0-LTS
   - Build Date: 2026-07-14
   - Production Certified: Yes
   - Storage Mode: File-based + WAL

2. **Long-Term Support**
   - LTS Period: 2026-07-14 to 2028-01-14
   - Bug Fix SLA: Within 24 hours
   - Security Fix SLA: Within 48 hours
   - Architecture Changes: Not permitted

3. **Environment Variables**
   - RUNTIME_API: Where Runtime API is
   - NODE_ENV: development or production
   - DASHBOARD_VERSION: 1.0.0

4. **Production Checklist**
   - ✓ Runtime certified for production
   - ✓ 18-month LTS active
   - ✓ Durability guaranteed
   - ✓ Crash recovery tested
   - ✓ No external dependencies

**Use This Page:**
- ✅ Verify configuration
- ✅ Check LTS status
- ✅ See version information
- ✅ Confirm production readiness

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + K` | Quick search |
| `Esc` | Close modals |
| `Tab` | Navigate between fields |
| `Enter` | Submit forms |

---

## Visual Indicators

### Status Colors

| Color | Meaning |
|-------|---------|
| 🟢 Green | Healthy, OK, Success |
| 🟡 Yellow | Warning, Caution |
| 🔴 Red | Error, Critical |
| 🔵 Blue | Information |

### Status Indicators

| Icon | Meaning |
|------|---------|
| ✓ | Success, Good |
| ✗ | Failure, Bad |
| ⏳ | Loading, Waiting |
| ℹ | Information |
| ⚠ | Warning |

---

## Responsive Design

### Desktop (1920px+)
- 4 columns for stat cards
- Side-by-side layouts
- Full table views

### Laptop (1366px)
- 3-2 column grids
- Optimized spacing

### Tablet (768px)
- 2 columns
- Stacked layouts
- Touch-friendly buttons

### Mobile (375px)
- 1 column
- Vertical stacking
- Large touch targets
- Swipe-friendly

---

## Refresh Rates

| Page | Refresh | Reason |
|------|---------|--------|
| Home | 5 seconds | Real-time health |
| Executions | 5 seconds | Active monitoring |
| Audit | 30 seconds | Event stream |
| System | 5 seconds | Continuous health check |
| Logs | 30 seconds | New log entries |
| Settings | Manual | Static information |

---

## Tips & Tricks

### Workflow Debugging

1. **Use Dry Run First**
   - Validates without executing
   - Quick feedback on syntax
   - No execution record created

2. **Keep YAML Simple**
   - Small steps are easier to debug
   - Add one step at a time
   - Test each step individually

3. **Check Audit Trail**
   - Every event is logged
   - Shows exact timing
   - Identifies where slowness occurs

### Monitoring Best Practices

1. **Check Home Daily**
   - Verify healthy status
   - Watch uptime trend
   - Check storage valid

2. **Monitor Active Executions**
   - Should be 0 when idle
   - Watch for stuck workflows
   - Review timing for anomalies

3. **Export Logs Weekly**
   - Maintain backup records
   - Identify patterns
   - Prepare for audits

---

## Troubleshooting

### Dashboard won't load

1. Check browser console (F12)
2. Verify Runtime is running
3. Confirm URL in Settings
4. Reload page (Cmd/Ctrl + Shift + R)

### Pages showing "no data yet"

1. Dashboard may be empty on first start
2. Execute a test workflow
3. Data will appear after first execution
4. Check System page for errors

### Slow refresh rates

1. Network latency to Runtime
2. Runtime under heavy load
3. Dashboard browser tab not focused (may throttle)
4. Refresh rates increase back to normal when focused

---

**Master the dashboard to operate the Runtime professionally without terminal access.**
