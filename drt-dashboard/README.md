# DRT Runtime Dashboard

**Operational dashboard for DRT Runtime v1.0.0-LTS**

Professional, dark-mode dashboard for operating the DRT (Deterministic Resilient Transactions) Runtime. No terminal required.

## Features

- 🚀 **Runtime Status** - Real-time health, version, uptime, and metrics
- 📊 **Execution Management** - Monitor running, completed, recovered, and failed executions
- 🔧 **Workflow Management** - Upload YAML, dry run, and execute workflows
- 📋 **Audit Trail** - Complete chronological view of state transitions and recovery events
- 💾 **System Health** - Disk, persistence, checkpoint, and WAL status
- 🔌 **API Browser** - Integrated endpoint reference and live testing
- 📝 **Structured Logs** - Execution logs, recovery logs, and error tracking
- ⚙️ **Settings** - Configuration, environment, and LTS policy information

## Installation

### Prerequisites

- Node.js 18+ and npm/yarn
- DRT Runtime running on the same machine or accessible network

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd drt-dashboard

# Install dependencies
npm install

# Start development server (port 3000)
npm run dev

# For production
npm run build
npm start
```

**Dashboard URL:** http://localhost:3000

**Runtime API URL (default):** http://localhost:5000

### Environment Configuration

Create `.env.local` if Runtime is on a different URL:

```bash
NEXT_PUBLIC_RUNTIME_API=http://runtime-server:5000
```

## Architecture

- **Technology:** Next.js 14.2 + React 18.3 + TypeScript
- **Styling:** Tailwind CSS with custom dark theme
- **Communication:** Direct HTTP to Runtime API (no authentication)
- **Storage:** No local persistence (stateless)
- **Build:** SWC compiler, tree-shaking, code splitting

## Pages

| Page | Route | Purpose |
|------|-------|---------|
| Home | / | System overview and status dashboard |
| Executions | /executions | View all workflow executions |
| Workflows | /workflows | Upload, validate, and execute workflows |
| Audit | /audit | Chronological audit trail and events |
| System Health | /system | Storage, persistence, and recovery status |
| API | /api | Endpoint browser and live testing |
| Logs | /logs | Structured logs with filtering |
| Settings | /settings | Configuration and LTS information |

## Operator Experience

The dashboard enables complete Runtime operation without terminal:

1. **Open Dashboard** → System status immediately visible
2. **Upload Workflow** → Paste YAML in Workflow editor
3. **Dry Run** → Validate workflow before execution
4. **Execute** → Run workflow with full tracking
5. **Monitor** → Watch real-time execution progress
6. **Audit** → Review all state transitions and recovery events
7. **Inspect Health** → Check disk, persistence, WAL status
8. **Debug** → Access structured logs and error details

## Production Readiness

- ✅ Dark mode (WCAG AAA contrast)
- ✅ Responsive design (mobile to 4K)
- ✅ Keyboard navigation
- ✅ TypeScript strict mode
- ✅ ESLint compliance
- ✅ No external CDN dependencies
- ✅ Optimized bundle (~200KB gzipped)
- ✅ Graceful error handling
- ✅ Real-time polling architecture

## Configuration

### Runtime API Connection

The dashboard connects to the DRT Runtime via HTTP. Ensure the Runtime is:

1. **Started:** `python src/runtime_api.py`
2. **Accessible:** On configured URL (default: localhost:5000)
3. **Healthy:** Check /health endpoint returns status=healthy

### Development vs Production

```bash
# Development (with hot reload)
npm run dev

# Production (optimized build)
npm run build
npm start
```

## Documentation

- **[OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md)** - Complete operator manual
- **[INSTALLATION_GUIDE.md](./INSTALLATION_GUIDE.md)** - Installation and deployment
- **[DASHBOARD_GUIDE.md](./DASHBOARD_GUIDE.md)** - Feature-by-feature guide
- **[LTS_POLICY.md](./LTS_POLICY.md)** - Long-Term Support policy and guarantees

## Support & Troubleshooting

### Dashboard won't start

```bash
npm install          # Reinstall dependencies
npm run build        # Rebuild
npm start            # Start production build
```

### Can't connect to Runtime

1. Check Runtime is running: `curl http://localhost:5000/health`
2. Verify URL in settings: http://localhost:3000/settings
3. Check firewall allows localhost:5000

### Workflow upload fails

1. Verify YAML syntax is valid
2. Check workflow_version and runtime_version fields
3. Ensure at least one step is defined
4. Review error message in dashboard

## Version

**Dashboard:** 1.0.0  
**Runtime:** 1.0.0-LTS  
**Compatibility:** Runtime 1.0.x  
**LTS Period:** 2026-07-14 to 2028-01-14

## License

Internal use only. DRT Program - Long-Term Support.

---

**For production operation, see [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md)**
