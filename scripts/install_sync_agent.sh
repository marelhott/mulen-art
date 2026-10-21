#!/bin/bash
# Installs (or reinstalls) a macOS LaunchAgent that keeps scripts/sync_images.py running (checks every 15 s).
# Remove it with:  launchctl bootout gui/$(id -u)/cz.mulen.art.sync && rm ~/Library/LaunchAgents/cz.mulen.art.sync.plist
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="cz.mulen.art.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/mulen-art-sync.log"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$ROOT/.venv/bin/python</string><string>-W</string><string>ignore</string><string>$ROOT/scripts/sync_images.py</string><string>--watch</string><string>--interval</string><string>15</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL (checks every 15 seconds). Log: $LOG"
