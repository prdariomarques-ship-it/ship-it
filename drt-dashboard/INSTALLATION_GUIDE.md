# DRT Runtime Dashboard - Installation Guide

**Complete installation and deployment instructions**

## System Requirements

### Minimum

- OS: Linux, macOS, or Windows (WSL2)
- Node.js: 18.0 or later
- npm: 9.0 or later
- Disk Space: 500MB for dashboard + node_modules
- Runtime API: Must be accessible on network

### Recommended

- Node.js: 20.0 LTS or later
- npm: 10.0 or later
- Disk Space: 2GB+ (allows future updates)
- Network: Direct access to Runtime (no proxy issues)

---

## Installation Steps

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd drt-dashboard
```

### Step 2: Install Dependencies

```bash
npm install
```

**What's installed:**
- Next.js 14.2 framework
- React 18.3 UI library
- Tailwind CSS styling
- TypeScript compiler
- Lucide icons
- Framer Motion animations
- React Query (commented out, polling used instead)

**Time:** ~2-3 minutes on good internet

### Step 3: Configure Runtime URL

Create `.env.local` file (optional if Runtime is localhost:5000):

```bash
echo "NEXT_PUBLIC_RUNTIME_API=http://localhost:5000" > .env.local
```

**Change URL if:**
- Runtime runs on different host
- Runtime on different port
- Running in container/VM setup

### Step 4: Build for Production

```bash
npm run build
```

**Output:**
- `.next/` directory created
- ~1-2 minutes to build
- Shows build summary and size report

### Step 5: Start Dashboard

#### Development (with hot reload)

```bash
npm run dev
```

Opens on http://localhost:3000 automatically

#### Production (optimized)

```bash
npm start
```

Runs production-optimized build

---

## Verification

After starting, verify installation:

1. **Open Dashboard:** http://localhost:3000
2. **Check Home Page:**
   - Page loads without errors
   - Sidebar shows all menu items
   - Header shows "Connecting to Runtime..."
3. **Check Settings Page:**
   - Runtime Version displays
   - Environment shows Runtime API URL
4. **Verify Health Connection:**
   - Home page shows "Runtime Status: healthy" (after 5s)
   - Green indicator pulses

If any step fails, see [Troubleshooting](#troubleshooting).

---

## Deployment

### Docker Deployment

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY .next .next
COPY public public

ENV NEXT_PUBLIC_RUNTIME_API=http://runtime:5000
ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "start"]
```

Build and run:

```bash
docker build -t drt-dashboard:latest .
docker run -p 3000:3000 -e NEXT_PUBLIC_RUNTIME_API=http://host.docker.internal:5000 drt-dashboard:latest
```

### Systemd Service (Linux)

Create `/etc/systemd/system/drt-dashboard.service`:

```ini
[Unit]
Description=DRT Runtime Dashboard
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/drt-dashboard
Environment="NEXT_PUBLIC_RUNTIME_API=http://localhost:5000"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable drt-dashboard
sudo systemctl start drt-dashboard
sudo systemctl status drt-dashboard
```

### Nginx Reverse Proxy

```nginx
upstream drt_dashboard {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name drt.example.com;

    location / {
        proxy_pass http://drt_dashboard;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Apache Reverse Proxy

```apache
ProxyPreserveHost On
ProxyPass / http://127.0.0.1:3000/
ProxyPassReverse / http://127.0.0.1:3000/
```

---

## Troubleshooting

### npm install fails

```bash
# Clear cache and retry
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### Build fails with TypeScript errors

```bash
# Verify TypeScript version
npm ls typescript

# Rebuild from scratch
npm run build -- --force
```

### Dashboard won't connect to Runtime

1. **Verify Runtime is running:**
   ```bash
   curl http://localhost:5000/health
   ```
   Should return: `{"status": "healthy", ...}`

2. **Check URL in dashboard:**
   - Go to Settings page
   - See Runtime API URL
   - Should match your Runtime URL

3. **If different machine:**
   - Update `.env.local`:
     ```bash
     NEXT_PUBLIC_RUNTIME_API=http://runtime-host:5000
     ```
   - Rebuild: `npm run build`
   - Restart: `npm start`

4. **If firewall blocks:**
   - Allow port 5000 on Runtime machine
   - Allow port 3000 on Dashboard machine

### Port already in use

**Port 3000:**
```bash
# Find process using port 3000
lsof -i :3000

# Kill if needed
kill -9 <PID>

# Or use different port
PORT=3001 npm start
```

**Port 5000 (Runtime):**
```bash
lsof -i :5000
kill -9 <PID>
python src/runtime_api.py  # Restart Runtime
```

### Memory issues during build

```bash
# Increase Node.js memory limit
NODE_OPTIONS=--max-old-space-size=2048 npm run build
```

### CSS/styling not loading

```bash
# Rebuild Tailwind CSS
npm run build -- --no-cache
```

### Old files interfering

```bash
# Complete clean rebuild
rm -rf .next node_modules package-lock.json
npm install
npm run build
npm start
```

---

## Production Checklist

Before deploying to production:

- [ ] Node.js version 18+ confirmed
- [ ] `npm install` completed successfully
- [ ] `npm run build` completes without errors
- [ ] `.env.local` configured with correct Runtime API URL
- [ ] Runtime is accessible from Dashboard machine
- [ ] Dashboard opens in browser
- [ ] Home page shows "healthy" status
- [ ] Can execute test workflow
- [ ] Logs are being recorded
- [ ] Firewall allows traffic between systems
- [ ] Backup of configuration completed

---

## Uninstallation

To completely remove dashboard:

```bash
# Stop any running processes
pkill -f "npm start"
pkill -f "npm run dev"

# Remove dashboard directory
rm -rf /opt/drt-dashboard

# If using systemd
sudo systemctl disable drt-dashboard
sudo rm /etc/systemd/system/drt-dashboard.service
sudo systemctl daemon-reload
```

---

## Version & Support

- **Dashboard Version:** 1.0.0
- **Runtime Compatibility:** 1.0.0-LTS
- **Node.js Support:** 18.0+
- **LTS Period:** 2026-07-14 to 2028-01-14

For issues not covered here, see [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md).

---

**Installation complete!** Proceed to [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md) for daily operations.
