#!/usr/bin/env bash
set -euo pipefail

sudo tar -xzf /tmp/pansou-frontend.tgz -C /opt/pansou-frontend
sudo chown -R ubuntu:ubuntu /opt/pansou-frontend
cd /opt/pansou-frontend
/usr/local/bin/npm run build
sudo systemctl restart pansou-frontend
sleep 3
curl -fsS http://127.0.0.1:3000/ >/dev/null
