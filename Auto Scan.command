#!/bin/bash
# Turns the automatic daily scan on or off (macOS launchd). Nothing runs in the background except at the
# scheduled times; turning it off removes the schedule completely.
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/app/.venv/bin/python"
LABEL="com.jobtracker.autoscan"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
clear
echo "=============================================="
echo "  JOB TRACKER: AUTOMATIC DAILY SCAN"
echo "=============================================="
if [ ! -x "$PY" ]; then echo "  Run Setup first."; read -n1 -r -p "  Press any key to close..."; exit 1; fi
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then STATE="ON"; else STATE="OFF"; fi
echo "  Right now it is: $STATE"
echo
echo "  1 = turn ON   (scans every active Watchlist company once a day, starting 6:30 am;"
echo "                 if Excel has the tracker open it tries again every hour until 9:30 pm)"
echo "  2 = turn OFF"
echo "  3 = run a scan now in the background (also checks that macOS lets it open this folder)"
echo "  4 = show the last scan's log"
echo "  5 = wake this Mac at 6:25 am every day (asks for your Mac password; needs power + open lid)"
read -r -p "  Choose: " c
case "$c" in
1)
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "  <key>Label</key><string>$LABEL</string>"
    echo "  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/app/auto_scan.py</string></array>"
    echo "  <key>WorkingDirectory</key><string>$DIR/app</string>"
    echo '  <key>StartCalendarInterval</key><array>'
    echo '    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>'
    for h in 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21; do
      echo "    <dict><key>Hour</key><integer>$h</integer><key>Minute</key><integer>30</integer></dict>"
    done
    echo '  </array>'
    echo "  <key>StandardOutPath</key><string>$HOME/Library/Logs/JobTracker-autoscan.out.log</string>"
    echo "  <key>StandardErrorPath</key><string>$HOME/Library/Logs/JobTracker-autoscan.out.log</string>"
    echo '  <key>ProcessType</key><string>Background</string>'
    echo '</dict></plist>'
  } > "$PLIST"
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null
  if launchctl bootstrap "gui/$(id -u)" "$PLIST"; then
    echo "  ON. The first scan runs at the next half hour from 6:30 am (or when your Mac wakes after a missed time)."
    echo "  Tip: choose 3 now once, to test it. If macOS asks whether Python may access your Desktop or"
    echo "  Documents folder, click Allow."
  else
    echo "  Couldn't turn it on (launchctl refused). Nothing changed."
  fi
  ;;
2)
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "  OFF. No scheduled scans."
  ;;
3)
  echo "  Scanning in the background; a notification appears when it's done (often 5-20 minutes)."
  echo "  Keep the tracker closed in Excel until then."
  if [ "$STATE" = "ON" ]; then
    # start the scheduled job itself, so this also tests that macOS lets it open this folder
    mkdir -p "$HOME/Library/Application Support/JobTracker"
    touch "$HOME/Library/Application Support/JobTracker/run-now"
    launchctl kickstart "gui/$(id -u)/$LABEL"
    echo "  If macOS asks whether Python may access your Desktop or Documents folder, click Allow."
  else
    nohup "$PY" "$DIR/app/auto_scan.py" --now >>"$HOME/Library/Logs/JobTracker-autoscan.out.log" 2>&1 &
  fi
  ;;
4)
  if [ -f "$DIR/app/auto_scan.lock" ]; then
    echo "  A scan is running right now (started $(date -r "$DIR/app/auto_scan.lock" '+%-I:%M %p')). Its results are"
    echo "  added below when it finishes. Below is the log so far:"
    echo
  fi
  if [ -f "$DIR/app/debug/auto_scan.log" ]; then tail -n 25 "$DIR/app/debug/auto_scan.log"; else echo "  No scan has run yet."; fi
  if [ -f "$HOME/Library/Logs/JobTracker-autoscan.log" ]; then echo; echo "  Problems reported:"; tail -n 10 "$HOME/Library/Logs/JobTracker-autoscan.log"; fi
  ;;
5)
  echo "  Your Mac will wake (if plugged in, lid open) at 6:25 every morning. Undo: sudo pmset repeat cancel"
  sudo pmset repeat wakeorpoweron MTWRFSU 06:25:00 && echo "  Done."
  ;;
*) echo "  Nothing changed." ;;
esac
echo
read -n1 -r -p "  Press any key to close..."
