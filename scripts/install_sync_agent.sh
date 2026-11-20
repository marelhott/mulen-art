#!/bin/bash
# Installs (or reinstalls) a macOS LaunchAgent that keeps scripts/sync_images.py running (checks every 15 s).
# Remove it with:  launchctl bootout gui/$(id -u)/cz.mulen.art.sync && rm ~/Library/LaunchAgents/cz.mulen.art.sync.plist
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="cz.mulen.art.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/mulen-art-sync.log"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "Missing $PYTHON - create the virtualenv first (python3 -m venv .venv && .venv/bin/pip install -r app_runtime/requirements.txt)." >&2
  exit 1
fi
# Paths go into XML: escape the characters that would break it (a folder name may contain & or <).
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
# Keep the log from growing without bound: keep the previous one as .1 once it passes 5 MB.
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then mv -f "$LOG" "$LOG.1"; fi
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$(xml "$PYTHON")</string><string>-W</string><string>ignore</string><string>$(xml "$ROOT/scripts/sync_images.py")</string><string>--watch</string><string>--interval</string><string>15</string>
  </array>
  <key>WorkingDirectory</key><string>$(xml "$ROOT")</string>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOG")</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL (checks every 15 seconds). Log: $LOG"
