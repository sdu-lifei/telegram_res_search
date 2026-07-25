#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq goaccess
sudo install -m 0755 /tmp/traffic-report.sh /usr/local/bin/pansou-traffic-report
sudo install -m 0644 /tmp/pansou-traffic-report.service /etc/systemd/system/pansou-traffic-report.service
sudo install -m 0644 /tmp/pansou-traffic-report.timer /etc/systemd/system/pansou-traffic-report.timer
sudo systemctl daemon-reload
sudo systemctl enable --now pansou-traffic-report.timer
sudo systemctl start pansou-traffic-report.service
