#!/usr/bin/env bash
set -euo pipefail

sudo install -m 0644 /tmp/telegram-res-search.service /etc/systemd/system/telegram-res-search.service
sudo install -m 0644 /tmp/nginx.conf /etc/nginx/sites-available/telegram-res-search
sudo ln -sfn /etc/nginx/sites-available/telegram-res-search /etc/nginx/sites-enabled/telegram-res-search
sudo rm -f /etc/nginx/sites-enabled/default

sed -i 's|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=http://pansou-43-167-14-72.nip.io|' /opt/telegram-res-search/.env

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-res-search nginx
sleep 3
curl -fsS http://127.0.0.1:8888/api/health
