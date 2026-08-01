#!/usr/bin/env bash
set -euo pipefail

install -m 0644 /tmp/main.py /opt/telegram-res-search/main.py
install -m 0644 /tmp/catalog.py /opt/telegram-res-search/pansou_py/api/catalog.py
install -m 0755 /tmp/import_public_indexes.py /opt/telegram-res-search/scripts/import_public_indexes.py
sudo systemctl restart telegram-res-search
sleep 3
curl -fsS http://127.0.0.1:8888/api/catalog?limit=1 >/dev/null
