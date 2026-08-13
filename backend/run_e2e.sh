#!/usr/bin/env bash
# Sandbox E2E: run ship-it backend pointing at the local FlowCore (port 8090)
set -e
cd /home/ubuntu/ship-it/backend
export DATABASE_URL=postgresql+asyncpg://dario:dario@localhost:5432/darioos
export FLOWCORE_BASE_URL=http://127.0.0.1:8090

python3 - <<'EOF'
from alembic.config import Config
from alembic import command
import os
cfg = Config('alembic.ini')
cfg.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
command.upgrade(cfg, 'head')
print('MIGRATIONS OK')
EOF

nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 9100 > /tmp/shipit_backend.log 2>&1 &
sleep 8
tail -2 /tmp/shipit_backend.log
echo "=== MERCADO HEALTH ==="
curl -s --max-time 20 http://127.0.0.1:9100/api/mercado/health
echo
for ep in scores events regime; do
  echo "=== MERCADO $ep ==="
  curl -s --max-time 30 http://127.0.0.1:9100/api/mercado/$ep | head -c 250
  echo
done
