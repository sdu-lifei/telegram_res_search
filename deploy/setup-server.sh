#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx

sudo mkdir -p /opt/telegram-res-search
sudo tar -xzf /tmp/telegram-res-search-deploy.tgz -C /opt/telegram-res-search
sudo chown -R ubuntu:ubuntu /opt/telegram-res-search

cd /opt/telegram-res-search
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

bash /tmp/install.sh
