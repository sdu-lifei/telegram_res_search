#!/usr/bin/env bash
set -euo pipefail

DOMAIN="panss.dpdns.org"
APP_DIR="/opt/telegram-res-search"

# The DNS A record must already resolve to this VPS before Certbot runs.
# Install a port-80-only vhost first: the live TLS vhost cannot be parsed until
# the new certificate exists.
sudo install -m 0644 /tmp/nginx-dpdns-bootstrap.conf /etc/nginx/sites-available/panss-dpdns
sudo ln -sfn /etc/nginx/sites-available/panss-dpdns /etc/nginx/sites-enabled/panss-dpdns
sudo nginx -t
sudo systemctl reload nginx

sudo certbot certonly --webroot -w /var/www/html -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email
sudo install -m 0644 /tmp/nginx-dpdns-next-live.conf /etc/nginx/sites-available/panss-dpdns
sudo rm -f /etc/nginx/sites-enabled/panss-duckdns
sudo nginx -t
sudo systemctl reload nginx
if grep -q '^PUBLIC_BASE_URL=' "$APP_DIR/.env"; then
    sudo sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" "$APP_DIR/.env"
else
    printf 'PUBLIC_BASE_URL=https://%s\n' "$DOMAIN" | sudo tee -a "$APP_DIR/.env" >/dev/null
fi
sudo systemctl restart telegram-res-search telegram-res-harvester pansou-frontend
curl -fsSI --max-time 20 "https://$DOMAIN/"
curl -fsSI --max-time 20 "https://$DOMAIN/static/index.html?kw=test" | grep -Eqi "^location: (https://$DOMAIN)?/search\\?kw=test"
