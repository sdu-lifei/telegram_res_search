#!/usr/bin/env bash
set -euo pipefail

sudo install -m 0644 /tmp/nginx-nip-next-live.conf /etc/nginx/sites-available/telegram-res-search
sudo nginx -t
sudo systemctl reload nginx

if grep -q '^PUBLIC_BASE_URL=' /opt/telegram-res-search/.env; then
    sed -i 's|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://pansou-43-167-14-72.nip.io|' /opt/telegram-res-search/.env
else
    printf '%s\n' 'PUBLIC_BASE_URL=https://pansou-43-167-14-72.nip.io' >> /opt/telegram-res-search/.env
fi
sudo systemctl restart telegram-res-search
sleep 3
curl -fsS http://127.0.0.1:3000/ >/dev/null
curl -fsS http://127.0.0.1:8888/api/health >/dev/null
