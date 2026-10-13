#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/launchd/com.leo.x-following-audit-daily-enrich.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.leo.x-following-audit-daily-enrich.plist"

mkdir -p "$ROOT/data/following_audit/logs"
chmod +x "$ROOT/scripts/daily_recent_enrich.py"

sed "s#__HOME__#$HOME#g" "$PLIST_SRC" > "$PLIST_DST"
launchctl bootout "gui/$(id -u)/com.leo.x-following-audit-daily-enrich" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.leo.x-following-audit-daily-enrich" 2>/dev/null || true

echo "Installed: $PLIST_DST"
echo "Schedule: daily 10:30 + 21:30 (25/run, 50/day cap)"
echo "Manual run: python3 $ROOT/scripts/daily_recent_enrich.py"
echo "Status: launchctl print gui/$(id -u)/com.leo.x-following-audit-daily-enrich"
