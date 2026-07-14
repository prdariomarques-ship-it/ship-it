# DRT Runtime - Operator Guide

**Complete operational manual for the DRT Runtime Dashboard**

## Table of Contents

1. [Getting Started](#getting-started)
2. [Daily Operations](#daily-operations)
3. [Workflow Execution](#workflow-execution)
4. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
5. [Recovery Procedures](#recovery-procedures)
6. [Maintenance](#maintenance)

---

## Getting Started

### First-Time Setup

1. **Install Dashboard**
   ```bash
   cd drt-dashboard
   npm install
   ```

2. **Start Runtime**
   ```bash
   cd drt-001/src
   python runtime_api.py
   ```

3. **Start Dashboard**
   ```bash
   cd drt-dashboard
   npm run dev
   ```

4. **Access Dashboard**
   - Open http://localhost:3000 in browser
   - You should see "Runtime Status: healthy"

### Verify Installation

1. Go to **Home** page
2. Check:
   - ✅ Runtime Status shows "healthy" (green indicator)
   - ✅ Version displays "1.0.0"
   - ✅ Uptime is > 0s
   - ✅ Storage Valid is "OK"
   - ✅ Accepting Requests is "OK"

If any check fails, see [Troubleshooting](#troubleshooting).

---

## Daily Operations

### Checking System Status

**Every Morning:**

1. Open Dashboard → Home page
2. Verify:
   - ✅ Runtime Status: healthy
   - ✅ Storage Valid: OK
   - ✅ Accepting Requests: OK
   - ✅ Memory usage reasonable

**If issues found:** Contact system administrator

### Monitoring Executions

1. Go to **Executions** page
2. View:
   - Running workflows (real-time update every 5s)
   - Recently completed workflows
   - Any failed or recovered workflows

3. Click any execution to see:
   - Execution ID
   - Correlation ID
   - All step details
   - Complete audit trail

### Checking Logs

1. Go to **Logs** page
2. Filter by:
   - Level: Info, Warning, Error, Debug
   - Source: Runtime, Workflows, Recovery
   - Search: Keyword or execution ID

3. Export logs if needed:
   - Button: Download as CSV/JSON

---

## Workflow Execution

### Uploading a Workflow

1. Go to **Workflows** page
2. Enter YAML in text area:

```yaml
name: example-workflow
workflow_version: "1.0"
runtime_version: "1.0"
owner: operator
timeout: 300
steps:
  - name: step-1
    type: system
    config:
      description: "First step"
  - name: step-2
    type: manual
    config:
      description: "Requires approval"
```

### Dry Run (Validation)

1. Click **Dry Run** button
2. Dashboard will:
   - Parse YAML
   - Validate all fields
   - Check timeout and steps
   - Show validation result

3. If successful: Shows step sequence and estimated duration
4. If failed: Shows specific error message

### Execute Workflow

1. Click **Execute** button
2. Runtime will:
   - Create execution record
   - Begin step execution
   - Track duration
   - Record all events

3. Execution immediately appears in **Executions** page
4. Status updates real-time (refreshes every 5s)

### Monitoring Execution

1. Go to **Executions** page
2. Find your execution in the list
3. Watch:
   - Current step
   - Duration (updates in real-time)
   - Status changes

4. Click execution for full details:
   - Complete step history
   - Timing breakdown
   - Audit trail
   - Recovery count (if any)

---

## Monitoring & Troubleshooting

### Health Check

Go to **System Health** page to see:

- **Storage Valid:** File-based persistence is accessible
- **Checkpoint:** WAL checkpoint file is valid
- **Recovery Capability:** Runtime can recover from crash
- **API Responsive:** HTTP API is responding
- **Disk Space:** Not full (critical!)

### Performance Metrics

Go to **Home** page:

- **Active Executions:** Should be 0-1 (single-threaded)
- **Uptime:** Should increase steadily
- **Storage Valid:** Should always be "OK"

### Common Issues

#### "Connection Error: Failed to load health"

**Cause:** Runtime not started or URL wrong

**Fix:**
1. Start Runtime: `python src/runtime_api.py`
2. Verify URL in Settings (default: localhost:5000)
3. Reload dashboard

#### "Workflow execution failed: Checksum mismatch"

**Cause:** File corruption detected

**Fix:**
1. Check system disk space (must be > 1GB available)
2. Check file permissions on .runtime directory
3. See [Recovery Procedures](#recovery-procedures)

#### "Runtime timeout exceeded"

**Cause:** Workflow took longer than timeout value

**Fix:**
1. Check timeout value in YAML (in seconds)
2. Increase timeout if needed
3. Execute again

#### "Storage validation error"

**Cause:** Corrupted execution file detected

**Fix:**
1. Runtime automatically detected corruption (see Logs)
2. Check .runtime directory for corrupted files
3. May require manual cleanup (contact admin)

---

## Recovery Procedures

### Normal Recovery

If Runtime crashes and restarts:

1. **Automatic:** Runtime loads all executions from disk
2. **Verify:** Go to Home page, check Status is "healthy"
3. **Check Audit:** Go to Audit page, look for "RECOVERED" events
4. **Inspect:** Click recovered execution to see full state

### Manual Recovery

If execution is stuck:

1. **Access API:** Go to API page
2. **Get Execution:** Use GET /execution/{id} endpoint
3. **Check State:** See if status is "RUNNING", "RECOVERED", or other
4. **Review Audit:** Look at audit trail for last state change

### Corrupted File Recovery

If you see "Checksum mismatch" error:

1. **Identify File:** Error will show execution ID
2. **Stop Runtime:** Kill runtime_api.py process
3. **Backup:** Copy .runtime directory to backup location
4. **Remove:** Delete corrupted execution file (only that one)
5. **Restart:** Start Runtime again
6. **Verify:** Check Home page → Storage Valid should be OK

---

## Maintenance

### Daily Maintenance (5 min)

- [ ] Check Home page - all systems green
- [ ] Review Logs for any warnings or errors
- [ ] Check disk space (in Settings)

### Weekly Maintenance (15 min)

- [ ] Review all completed executions (Executions page)
- [ ] Check for any patterns in failures (Logs page)
- [ ] Verify Storage Valid still OK (System page)
- [ ] Export logs for record-keeping (Logs page)

### Monthly Maintenance (30 min)

- [ ] Full system backup (.runtime directory)
- [ ] Clean up old execution records (> 30 days old)
- [ ] Review audit trail for anomalies
- [ ] Test recovery procedure (if safe)
- [ ] Verify LTS policy still in effect (Settings page)

### Log Retention

- Keep logs for minimum 90 days
- Export and archive monthly
- Delete after 1 year retention period
- Always backup before deletion

### Disk Space Management

**Recommended Levels:**

| Level | Action | Urgency |
|-------|--------|---------|
| < 100MB | Stop accepting new workflows | Critical |
| < 500MB | Archive old logs | High |
| > 1GB | Normal operation | Ok |
| > 5GB | Available for growth | Excellent |

**Free up space:**

1. Export and delete old logs (Logs page)
2. Archive completed executions (Executions page)
3. Clean .runtime directory (only old files!)

---

## Key Operational Policies

### Durability Guarantee

- **fsync():** Every write to disk is durable (survives power loss)
- **Checksums:** All data integrity verified on load
- **WAL:** Write-ahead log prevents partial writes
- **Atomic:** File operations use temp+rename for safety

### Concurrency Model

- **Single-threaded:** Only one workflow runs at a time
- **Throughput:** ~1-2 workflows/second
- **Idempotency:** Duplicate requests return same execution
- **No race conditions:** Correlation ID prevents duplicates

### Timeout Enforcement

- **Default:** 300 seconds (5 minutes)
- **Per-workflow:** Set in YAML `timeout` field
- **Checked:** Before and after each step
- **Exceeded:** Workflow marked FAILED

### Long-Term Support (LTS)

- **Period:** 2026-07-14 to 2028-01-14 (18 months)
- **Bug fixes:** Within 24 hours
- **Security fixes:** Within 48 hours
- **No new features:** v1.0 frozen, use v1.1 for new features

---

## Emergency Procedures

### Runtime Won't Start

1. Check Python version: `python --version` (must be 3.7+)
2. Check dependencies: `pip install -r requirements.txt`
3. Check port 5000 not in use: `lsof -i :5000`
4. Check .runtime directory exists and readable
5. Check file permissions: `chmod 755 .runtime`

### Mass Execution Failure

1. Check disk space: Dashboard Settings page
2. Check storage valid: Dashboard System page
3. Review recent logs: Dashboard Logs page
4. If corrupted: See Corrupted File Recovery

### Dashboard Won't Load

1. Check Node.js running: `npm run dev`
2. Check http://localhost:3000 is accessible
3. Check port 3000 not in use: `lsof -i :3000`
4. Check .env.local has correct RUNTIME_API URL
5. Restart: `npm install && npm run dev`

---

## Support Contacts

For issues not covered in this guide:

- **Installation Issues:** See INSTALLATION_GUIDE.md
- **Feature Questions:** See DASHBOARD_GUIDE.md
- **Policy Questions:** See LTS_POLICY.md
- **Emergency:** System admin or on-call engineer

---

**Version:** 1.0.0  
**Last Updated:** 2026-07-14  
**LTS Status:** Active (ends 2028-01-14)

**For production operation, always have this guide accessible.**
