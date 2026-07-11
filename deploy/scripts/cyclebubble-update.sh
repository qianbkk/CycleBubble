#!/bin/bash
# CycleBubble auto-update script - called by webhook on push events
# Pulls latest code, installs deps, refreshes frontend, restarts backend.
set +e

APP_DIR="/var/www/app"
WEB_ROOT="/var/www/frontend"
SERVICE_NAME="cyclebubble-api"
BRANCH="${1:-master}"
LOG="/var/log/app/auto-update.log"

log() {
    echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

cd "$APP_DIR" || { log "FAIL: cd $APP_DIR"; exit 1; }

log "=========================================="
log "Auto-update triggered, branch=$BRANCH"
log "=========================================="

# 1. Pull latest
log "[1/5] git fetch + reset to origin/$BRANCH"
git fetch origin "$BRANCH" --prune 2>&1 | tail -3 | tee -a "$LOG"
git reset --hard "origin/$BRANCH" 2>&1 | tee -a "$LOG"
NEW_COMMIT=$(git rev-parse --short HEAD)
log "now at commit: $NEW_COMMIT"

# 2. (api.js BASE 自部署同源 由 PR #12 已在代码里默认，无需 patch)

# 3. Install/update Python deps
log "[3/5] pip install -r requirements.txt"
source venv/bin/activate
pip install -r requirements.txt --quiet 2>&1 | tail -3 | tee -a "$LOG"

# 4. Refresh frontend files
log "[4/5] copy frontend to nginx root"
cp -f index.html styles.css script.js api.js "$WEB_ROOT/"
chown -R www:www "$WEB_ROOT"
# 目录必须有 755（x 权限）才能被 nginx worker 进入，文件 644
chmod 755 "$WEB_ROOT"
find "$WEB_ROOT" -type f -exec chmod 644 {} +

# 5. Restart backend
log "[5/5] restart $SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "✓ $SERVICE_NAME is active"
    curl -s http://127.0.0.1:8000/api/health | tee -a "$LOG"
    echo "" | tee -a "$LOG"
else
    log "✗ $SERVICE_NAME failed to start"
    systemctl status "$SERVICE_NAME" --no-pager | tail -20 | tee -a "$LOG"
    exit 1
fi

# Reload nginx (in case any config touched)
nginx -s reload 2>&1 | tee -a "$LOG"

log "Auto-update complete."
log "=========================================="