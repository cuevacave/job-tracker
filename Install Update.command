#!/bin/bash
# Installs a Job Tracker update. Copies new program files only - never touches your tracker,
# Gmail accounts, saved postings or the AI model. Old program files are backed up first.
UPD="$(cd "$(dirname "$0")" && pwd)"
clear
echo "=============================================="
echo "  JOB TRACKER: INSTALL UPDATE"
echo "=============================================="

# Where the new files are: an update folder ("files" inside), or a full new copy of Job Tracker
# (e.g. downloaded from GitHub). Only program files are copied, never a tracker, logins or postings.
if [ -d "$UPD/files" ]; then
  SRC="$UPD/files"
elif [ -f "$UPD/app/watcher.py" ]; then
  SRC="$UPD"
else
  echo "  This doesn't look like a Job Tracker update. Nothing changed."
  read -n1 -r -p "  Press any key to close..."; exit 1
fi

# Find the Job Tracker folder: the folder this update sits in, or ask.
TARGET="$(dirname "$UPD")"
if [ ! -f "$TARGET/Job_Tracker.xlsx" ] || [ ! -d "$TARGET/app" ]; then
  echo "  Drag your Job Tracker folder into this window, then press Enter:"
  read -r TARGET
  TARGET="${TARGET%/}"; TARGET="${TARGET%\'}"; TARGET="${TARGET#\'}"; TARGET="${TARGET//\\ / }"
fi
if [ ! -f "$TARGET/Job_Tracker.xlsx" ] || [ ! -d "$TARGET/app" ]; then
  echo "  That doesn't look like the Job Tracker folder (no Job_Tracker.xlsx + app folder). Nothing changed."
  read -n1 -r -p "  Press any key to close..."; exit 1
fi
if [ "$(cd "$TARGET" && pwd -P)" = "$(cd "$UPD" && pwd -P)" ]; then
  echo "  That's this same folder - it's already up to date. Run Install Update from the NEW download,"
  echo "  and drag your existing Job Tracker folder in when asked."
  read -n1 -r -p "  Press any key to close..."; exit 0
fi
echo "  Updating: $TARGET"

# 1. back up the current program files
STAMP=$(date +%Y%m%d-%H%M%S)
BK="$TARGET/app/backups/code-$STAMP"
mkdir -p "$BK"
cp "$TARGET"/app/*.py "$TARGET"/app/*.txt "$BK"/ 2>/dev/null
cp "$TARGET"/*.command "$TARGET"/*.txt "$TARGET"/*.md "$BK"/ 2>/dev/null
echo "  [1/4] Old program files backed up to app/backups/code-$STAMP"

# 2. copy the new program files (only these - nothing else is touched)
cp "$SRC"/app/*.py "$SRC"/app/requirements.txt "$TARGET/app/"
for f in "$SRC"/*.command "$SRC"/*.md "$SRC"/README.html "$SRC"/"READ ME FIRST.txt" "$SRC"/LICENSE "$SRC"/.gitignore; do
  [ -f "$f" ] && cp "$f" "$TARGET/"
done
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
chmod +x "$TARGET"/*.command 2>/dev/null
echo "  [2/4] New program files installed."

# 3. libraries (skips anything already installed)
PY="$TARGET/app/.venv/bin/python"
if [ -x "$PY" ]; then
  "$PY" -m pip install -q -r "$TARGET/app/requirements.txt" >/dev/null 2>&1
  "$PY" -m pip install -q zipcodes >/dev/null 2>&1
  echo "  [3/4] Libraries checked."
  # 4. data + quick checks; also applies any new tracker layout right away
  "$PY" "$TARGET/app/geo.py" --build
  "$PY" "$TARGET/app/upgrade.py"
  chflags nohidden "$TARGET/Job_Tracker.xlsx" 2>/dev/null
  "$PY" "$TARGET/app/selfcheck.py"
  echo "  [4/4] Done."
else
  echo "  [3/4] Setup hasn't been run in this folder yet - run Setup next."
fi
echo
chflags nohidden "$TARGET/Job_Tracker.xlsx" 2>/dev/null
echo "  Update installed. You can delete the update folder now."
read -n1 -r -p "  Press any key to close..."
