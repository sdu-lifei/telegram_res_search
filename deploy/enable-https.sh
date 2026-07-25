#!/usr/bin/env bash
set -euo pipefail

sed -i 's|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://pansou-43-167-14-72.nip.io|' /opt/telegram-res-search/.env
sudo systemctl restart telegram-res-search
sleep 3
curl -fsS http://127.0.0.1:8888/api/health
