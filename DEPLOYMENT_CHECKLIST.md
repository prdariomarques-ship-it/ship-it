# DARIO OS v1.0.0-LTS — PRODUCTION DEPLOYMENT CHECKLIST

## PRE-DEPLOYMENT VALIDATION (DO NOT SKIP)

### Code Quality Gates
- [ ] All tests passing: `npm test` (frontend), `pytest` (backend)
- [ ] No linting errors: `npm run lint` (frontend), `ruff check` (backend)
- [ ] TypeScript clean: No type errors in build
- [ ] Build successful: `npm run build` completes without warnings
- [ ] Git status clean: All changes committed

### Security Pre-Checks
- [ ] Review `.env.example` for all required variables
- [ ] Generate strong JWT_SECRET: `openssl rand -hex 32`
- [ ] Generate strong WEBHOOK_SECRET: `openssl rand -hex 32`
- [ ] Verify no hardcoded credentials in codebase
- [ ] Confirm OAuth credentials obtained (if using Google integrations)
- [ ] Whitelist production IPs in firewall
- [ ] Enable HTTPS/TLS in Caddy configuration

### Infrastructure Setup

#### Database Preparation
- [ ] PostgreSQL 16+ installed and running
- [ ] Create database: `createdb darioos`
- [ ] Create database user with restricted permissions
- [ ] Verify connection string format: `postgresql+asyncpg://user:pass@host:5432/darioos`
- [ ] Enable SSL connections (production requirement)
- [ ] Configure automated backups (daily minimum)
- [ ] Set up point-in-time recovery

#### Redis Setup (Optional but Recommended)
- [ ] Redis 7+ installed and running
- [ ] Configure password protection
- [ ] Enable persistence (RDB or AOF)
- [ ] Set up replication (if high availability required)
- [ ] Configure eviction policy: `allkeys-lru`

#### Qdrant Setup (Optional for Semantic Search)
- [ ] Qdrant 1.0+ running (Docker recommended)
- [ ] Create collection: `darioos_memory`
- [ ] Configure vector size matching embeddings model
- [ ] Enable persistence volumes
- [ ] Set up backup strategy

#### External Services
- [ ] LLM Provider account and API key obtained
  - [ ] OpenAI account with API key (default)
  - [ ] OR Anthropic API key
  - [ ] OR other provider configured
- [ ] WhatsApp provider account configured
  - [ ] OpenWA API key (if using OpenWA)
  - [ ] OR Evolution/Baileys/Official provider credentials
- [ ] Embedding provider account (if different from LLM)
- [ ] n8n instance configured (if using workflows)

---

## DEPLOYMENT EXECUTION

### Pre-Deployment Steps

1. **Environment Setup**
   ```bash
   cd /path/to/darioos
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Verify Configuration**
   ```bash
   # Backend
   cd backend
   DATABASE_URL="postgresql+asyncpg://..." python -c "from utils.config import get_settings; s = get_settings(); print(f'Environment: {s.environment}'); print(f'App: {s.app_name} v{s.app_version}')"
   
   # Check critical settings
   # - environment=production
   # - jwt_secret (>= 32 chars)
   # - webhook_secret (>= 32 chars)
   # - otel_enabled=true (recommended)
   ```

3. **Database Migration**
   ```bash
   cd backend
   alembic upgrade head
   # Verify: SELECT * FROM alembic_version;
   ```

4. **Health Checks Before Deployment**
   ```bash
   # Backend health
   curl -s http://localhost:8000/health | jq .
   
   # Frontend build
   cd frontend && npm run build
   
   # DRT Runtime
   cd drt-001 && python src/runtime_api.py &
   curl -s http://localhost:5000/health | jq .
   ```

### Docker Deployment

1. **Build Images**
   ```bash
   docker-compose -f docker/docker-compose.yml build
   ```

2. **Start Services**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

3. **Verify Service Status**
   ```bash
   docker-compose ps
   # All services should show "Up"
   
   # Check logs
   docker-compose logs -f backend
   docker-compose logs -f frontend
   ```

4. **Initial Data Setup**
   ```bash
   # Create admin user (if applicable)
   docker-compose exec backend python -m admin.setup
   
   # Verify database
   docker-compose exec postgres psql -U dario -d darioos -c "SELECT COUNT(*) FROM users;"
   ```

---

## POST-DEPLOYMENT VALIDATION

### Service Health Checks (Critical)
- [ ] Backend API responding on port 8000
  ```bash
  curl -s http://localhost:8000/health | jq .status
  # Expected: "healthy"
  ```

- [ ] Frontend accessible on port 3000 (or Caddy proxy)
  ```bash
  curl -s http://localhost/
  # Expected: HTML page loads
  ```

- [ ] DRT Runtime responding on port 5000
  ```bash
  curl -s http://localhost:5000/health | jq .status
  # Expected: "healthy"
  ```

- [ ] Database connectivity verified
  ```bash
  docker-compose exec backend python -c "from database import get_async_session; print('Database connected')"
  ```

- [ ] Redis connectivity (if configured)
  ```bash
  redis-cli -u redis://localhost:6379 ping
  # Expected: PONG
  ```

### Functional Testing (Critical)

1. **Authentication Flow**
   - [ ] Login works with valid credentials
   - [ ] JWT token generated and valid
   - [ ] Token refresh endpoint functional
   - [ ] Logout clears session

2. **Dashboard Access**
   - [ ] Admin can access dashboard
   - [ ] All 32 pages load without errors
   - [ ] Data displays correctly
   - [ ] Charts render properly

3. **Workflow Execution** (DRT Runtime)
   - [ ] Dry run workflow works
   - [ ] Execute workflow works
   - [ ] Execution tracked in audit
   - [ ] Recovery works if interrupted

4. **API Integration**
   - [ ] Admin endpoints authenticated
   - [ ] Rate limiting active
   - [ ] Error responses formatted
   - [ ] CORS headers present

### Monitoring & Observability

- [ ] Prometheus scraping backend metrics
  ```bash
  curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets'
  ```

- [ ] Grafana dashboards accessible
  - [ ] System Health dashboard
  - [ ] Performance dashboard
  - [ ] Security dashboard

- [ ] Jaeger tracing operational
  - [ ] Backend traces appearing in Jaeger UI
  - [ ] Trace propagation working across services

- [ ] AlertManager configured
  - [ ] Test alert: `amtool alert add test critical`
  - [ ] Notification channels working (Slack, email, etc.)

### Security Post-Deployment

- [ ] HTTPS/TLS enforced (redirect 80→443)
- [ ] Security headers present
  ```bash
  curl -I http://localhost:8000/health | grep -E "X-|Strict-Transport"
  ```

- [ ] Rate limiting working
  ```bash
  # Generate 30 requests rapidly
  for i in {1..30}; do curl -s http://localhost:8000/health; done
  # Should see HTTP 429 after threshold
  ```

- [ ] CORS properly configured
  ```bash
  curl -I -H "Origin: http://untrusted.com" http://localhost:8000/
  # Should NOT have Access-Control-Allow-Origin for untrusted domain
  ```

### Performance Validation

- [ ] Frontend page load time < 3 seconds
- [ ] API response time < 200ms (p95)
- [ ] Database queries < 100ms (p95)
- [ ] Memory usage stable (not growing)
- [ ] CPU utilization reasonable (< 70% idle)

---

## ROLLBACK PROCEDURES

### If Deployment Fails

1. **Immediate Rollback**
   ```bash
   # Stop all services
   docker-compose down
   
   # Restore previous database state
   # (via backup/snapshot)
   
   # Restart with previous version
   docker-compose up -d
   ```

2. **Database Rollback**
   ```bash
   # Rollback migration
   cd backend
   alembic downgrade -1
   
   # Or restore from backup
   pg_restore -d darioos /path/to/backup.sql
   ```

3. **Communication**
   - [ ] Notify users of rollback
   - [ ] Post status update on status page
   - [ ] Document issue in incident log

---

## OPERATIONAL PROCEDURES

### Daily Operations

**Monitoring Routine**
- [ ] Check dashboard health status
- [ ] Verify no critical alerts in AlertManager
- [ ] Review logs for errors: `docker-compose logs --since 1h | grep ERROR`
- [ ] Monitor disk usage (PostgreSQL, Qdrant)
- [ ] Check rate limiting effectiveness

**Backup Verification**
- [ ] Automated backup completed successfully
- [ ] Backup retention policy enforced
- [ ] Test restore procedure weekly

### Weekly Maintenance

- [ ] Review slow query log (PostgreSQL)
- [ ] Check for security updates
- [ ] Verify backup integrity
- [ ] Test disaster recovery procedures
- [ ] Review error logs for patterns

### Monthly Tasks

- [ ] Security audit of access logs
- [ ] Dependency vulnerability scan
- [ ] Load testing (if high traffic)
- [ ] Disaster recovery drill
- [ ] Documentation review and updates

---

## TROUBLESHOOTING GUIDE

### Backend Not Starting

**Symptom:** `Error: Address already in use (8000)`
```bash
# Kill process on port 8000
lsof -i :8000 | tail -1 | awk '{print $2}' | xargs kill -9
docker-compose restart backend
```

**Symptom:** Database connection failure
```bash
# Verify connection string in .env
# Test connection:
psql "postgresql://user:pass@localhost:5432/darioos"
# If fails, check:
# 1. Database exists: createdb darioos
# 2. User has permissions: GRANT ALL ON darioos TO user;
# 3. Network connectivity: ping database_host
```

### Frontend Not Loading

**Symptom:** 404 on pages
```bash
# Rebuild frontend
npm run build
docker-compose restart frontend

# Check logs
docker-compose logs frontend
```

**Symptom:** Blank page, console errors
```bash
# Check NEXT_PUBLIC_API_URL pointing to backend
# Verify backend is running and accessible
curl http://localhost:8000/health
```

### DRT Runtime Issues

**Symptom:** `Connection refused on port 5000`
```bash
# Check if running
ps aux | grep runtime_api.py

# Start manually
cd drt-001 && python src/runtime_api.py &

# Check port
lsof -i :5000
```

**Symptom:** Workflow execution fails
```bash
# Check persistence directory
ls -la drt-001/.runtime/

# Check execution files
ls -la drt-001/.runtime/executions/

# Verify checksums
# (Manual recovery if corrupted)
```

---

## CAPACITY PLANNING

### Resource Estimates

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| Backend (1 instance) | 2 cores | 2 GB | 10 GB |
| Frontend | 1 core | 512 MB | 5 GB |
| PostgreSQL | 4 cores | 4 GB | 100 GB* |
| Redis | 1 core | 1 GB | 20 GB |
| Qdrant | 2 cores | 2 GB | 50 GB* |
| Prometheus | 1 core | 1 GB | 20 GB* |
| Grafana | 1 core | 512 MB | 5 GB |

*Grows with data volume; adjust based on usage

### Scaling Strategy

**Horizontal Scaling:**
- Backend: Run multiple instances behind load balancer (stateless)
- Frontend: CDN distribution (static assets)
- Database: Read replicas for reporting
- Redis: Sentinel for HA
- Qdrant: Clustering for large vector stores

**Vertical Scaling:**
- Increase machine resources if bottleneck identified
- Monitor metrics in Grafana for specific constraints

---

## SUPPORT & ESCALATION

### Logging Issues

All service logs available:
```bash
# Backend logs
docker-compose logs -f backend --since 1h

# Frontend logs (build-time)
docker-compose logs -f frontend

# All services
docker-compose logs -f --all
```

### Getting Help

1. Check FINAL_RELEASE_AUDIT.md for known limitations
2. Review error logs in docker-compose output
3. Check database for data integrity
4. Verify all environment variables set correctly
5. Test individual services in isolation

---

## SIGN-OFF

**Deployment Date:** _______________  
**Deployed By:** _______________  
**Environment:** ☐ Staging ☐ Production  
**Status:** ☐ Successful ☐ Rollback Required

**Post-Deployment Validation Completed:** _______________  
**Monitoring Dashboards Verified:** _______________  
**Stakeholder Approval:** _______________

---

*This checklist ensures safe, repeatable deployments of Dario OS v1.0.0-LTS to production environments.*
