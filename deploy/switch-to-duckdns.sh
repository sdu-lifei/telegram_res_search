#!/usr/bin/env bash
set -euo pipefail

sudo install -m 0644 /tmp/nginx-duckdns.conf /etc/nginx/sites-available/panss-duckdns
sudo ln -sfn /etc/nginx/sites-available/panss-duckdns /etc/nginx/sites-enabled/panss-duckdns
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d panss.duckdns.org --non-interactive --agree-tos --register-unsafely-without-email --redirect

sed -i 's|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://panss.duckdns.org|' /opt/telegram-res-search/.env
sudo systemctl restart telegram-res-search
sleep 3
curl -fsS http://127.0.0.1:8888/api/health
