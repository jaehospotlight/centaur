#!/bin/bash
set -euo pipefail

# Deploy ai_v2 to dev-aibot
# Usage: ./scripts/deploy-dev-aibot.sh

HOST="ubuntu@dev-aibot"
REMOTE_DIR="~/github/tempoxyz/ai_v2"
DB_URL="postgresql://tempo:tempo_prod@localhost:5432/ai_v2"

echo "=== Deploying ai_v2 to dev-aibot ==="

# 1. Sync code
echo "Syncing code..."
ssh $HOST "mkdir -p $REMOTE_DIR"
ssh $HOST "cd $REMOTE_DIR && git pull 2>/dev/null || (cd ~/github/tempoxyz && gh repo clone tempoxyz/ai_v2 -- --depth=1)"

# 2. Install dependencies
echo "Installing dependencies..."
ssh $HOST "cd $REMOTE_DIR && uv sync"

# 3. Run migrations
echo "Running migrations..."
ssh $HOST "cd $REMOTE_DIR && DATABASE_URL=$DB_URL uv run alembic -c migrations/alembic.ini upgrade head"

# 4. Set up systemd services
echo "Setting up systemd services..."
ssh $HOST "sudo tee /etc/systemd/system/ai-v2-api.service > /dev/null" <<SERVICE
[Unit]
Description=AI v2 API Server
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REMOTE_DIR
Environment=DATABASE_URL=$DB_URL
EnvironmentFile=$REMOTE_DIR/.env
ExecStart=$(which uv) run uvicorn ai_v2_api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

ssh $HOST "sudo tee /etc/systemd/system/ai-v2-sync.service > /dev/null" <<SERVICE
[Unit]
Description=AI v2 ETL Sync
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REMOTE_DIR
Environment=DATABASE_URL=$DB_URL
EnvironmentFile=$REMOTE_DIR/.env
ExecStart=$(which uv) run python -m ai_v2_dataplane.cli sync --continuous
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE

ssh $HOST "sudo tee /etc/systemd/system/ai-v2-repo-sync.timer > /dev/null" <<TIMER
[Unit]
Description=AI v2 Repo Sync Timer

[Timer]
OnCalendar=*-*-* */6:00:00
Persistent=true

[Install]
WantedBy=timers.target
TIMER

ssh $HOST "sudo tee /etc/systemd/system/ai-v2-repo-sync.service > /dev/null" <<SERVICE
[Unit]
Description=AI v2 Repo Sync
After=network.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=$REMOTE_DIR
ExecStart=$REMOTE_DIR/sandbox/scripts/update-repos.sh

[Install]
WantedBy=multi-user.target
SERVICE

ssh $HOST "sudo systemctl daemon-reload"
ssh $HOST "sudo systemctl enable ai-v2-api ai-v2-sync ai-v2-repo-sync.timer"
ssh $HOST "sudo systemctl restart ai-v2-api ai-v2-sync"
ssh $HOST "sudo systemctl start ai-v2-repo-sync.timer"

echo "=== Deployment complete ==="
echo "API: http://dev-aibot:8000"
echo "Health: http://dev-aibot:8000/health"
