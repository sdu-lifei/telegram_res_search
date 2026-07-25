#!/usr/bin/env bash
set -euo pipefail

# Generates a privacy-preserving 24-hour traffic summary from Nginx access logs.
# IPs are only used transiently for deduplication and never written to the report.
LOG_FILE="${1:-/var/log/nginx/access.log}"
OUT_FILE="${2:-/var/www/pansou-traffic/index.html}"
LOG_FILES=("$LOG_FILE")
[[ -f "$LOG_FILE.1" ]] && LOG_FILES+=("$LOG_FILE.1")

command -v goaccess >/dev/null || { echo "goaccess is not installed" >&2; exit 1; }
sudo install -d -m 0755 "$(dirname "$OUT_FILE")"
sudo goaccess "${LOG_FILES[@]}" --log-format=COMBINED --date-format='%d/%b/%Y' --time-format='%T' \
  --date-spec=24h --ignore-crawlers --ignore-panel=REQUESTS_STATIC --output="$OUT_FILE" --html-report-title='盘搜近 24 小时真人流量'
sudo chown -R www-data:www-data "$(dirname "$OUT_FILE")"
