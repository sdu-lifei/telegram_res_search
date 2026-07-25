#!/usr/bin/env bash
set -euo pipefail

sudo install -m 0644 /tmp/telegram-res-harvester.service /etc/systemd/system/telegram-res-harvester.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-res-harvester
sleep 3
sudo systemctl --no-pager --full status telegram-res-harvester
