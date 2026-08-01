#!/usr/bin/env bash
set -euo pipefail

NODE_VERSION="24.18.0"
NODE_SHA="55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742"
NODE_ARCHIVE="node-v${NODE_VERSION}-linux-x64.tar.xz"

if ! command -v node >/dev/null || [[ "$(node --version)" != "v${NODE_VERSION}" ]]; then
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE}"
    echo "${NODE_SHA}  ${NODE_ARCHIVE}" | sha256sum -c -
    sudo mkdir -p "/opt/node-v${NODE_VERSION}"
    sudo tar -xJf "${NODE_ARCHIVE}" -C "/opt/node-v${NODE_VERSION}" --strip-components=1
    sudo ln -sfn "/opt/node-v${NODE_VERSION}/bin/node" /usr/local/bin/node
    sudo ln -sfn "/opt/node-v${NODE_VERSION}/bin/npm" /usr/local/bin/npm
    sudo ln -sfn "/opt/node-v${NODE_VERSION}/bin/npx" /usr/local/bin/npx
fi

if ! swapon --show | grep -q .; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

sudo mkdir -p /opt/pansou-frontend
sudo tar -xzf /tmp/pansou-frontend.tgz -C /opt/pansou-frontend
sudo chown -R ubuntu:ubuntu /opt/pansou-frontend
cd /opt/pansou-frontend
/usr/local/bin/npm ci
/usr/local/bin/npm run build

sudo install -m 0644 /tmp/pansou-frontend.service /etc/systemd/system/pansou-frontend.service
sudo install -m 0644 /tmp/nginx-next-live.conf /etc/nginx/sites-available/panss-duckdns
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now pansou-frontend
sudo systemctl restart pansou-frontend
sudo systemctl reload nginx
