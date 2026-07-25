#!/usr/bin/env bash
set -euo pipefail

# Usage: bash deploy/publish-to-vps.sh ubuntu@43.167.14.72
# The target account must have passwordless SSH and sudo access. The script
# deliberately preserves the server's .env (credentials and API settings).
TARGET="${1:?usage: bash deploy/publish-to-vps.sh user@host}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_ARCHIVE="$(mktemp -t pansou-api-deploy.XXXXXX.tgz)"
FRONTEND_ARCHIVE="$(mktemp -t pansou-frontend-deploy.XXXXXX.tgz)"

trap 'rm -f "$API_ARCHIVE" "$FRONTEND_ARCHIVE"' EXIT
tar -C "$ROOT" \
  --exclude='.git' --exclude='.venv' --exclude='frontend-clone/node_modules' \
  --exclude='frontend-clone' --exclude='logs' --exclude='cache' \
  --exclude='*.db' --exclude='.DS_Store' --exclude='.env' \
  -czf "$API_ARCHIVE" .
tar -C "$ROOT/frontend-clone" --exclude='node_modules' --exclude='.next' -czf "$FRONTEND_ARCHIVE" .

scp "$API_ARCHIVE" "$TARGET:/tmp/pansou-api-deploy.tgz"
scp "$FRONTEND_ARCHIVE" "$TARGET:/tmp/pansou-frontend-deploy.tgz"
scp "$ROOT/deploy/nginx-dpdns-next-live.conf" "$ROOT/deploy/nginx-dpdns-bootstrap.conf" "$ROOT/deploy/switch-to-dpdns.sh" \
  "$ROOT/deploy/traffic-report.sh" "$ROOT/deploy/install-traffic-report.sh" \
  "$ROOT/deploy/pansou-traffic-report.service" "$ROOT/deploy/pansou-traffic-report.timer" "$TARGET:/tmp/"

ssh "$TARGET" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo tar -xzf /tmp/pansou-api-deploy.tgz -C /opt/telegram-res-search
sudo chown -R ubuntu:ubuntu /opt/telegram-res-search
sudo tar -xzf /tmp/pansou-frontend-deploy.tgz -C /opt/pansou-frontend
sudo chown -R ubuntu:ubuntu /opt/pansou-frontend
bash /tmp/switch-to-dpdns.sh
bash /tmp/install-traffic-report.sh
REMOTE
