#!/bin/bash
# One-time setup for Job Tracker. Safe to run again any time (to add an email account or the AI model).
cd "$(dirname "$0")" || exit 1
clear
echo "=============================================="
echo "  JOB TRACKER SETUP"
echo "=============================================="

# Let the double-click launchers run (macOS blocks downloaded scripts by default).
xattr -dr com.apple.quarantine . 2>/dev/null
chmod +x ./*.command 2>/dev/null

# 1. Python ------------------------------------------------------------
if ! /usr/bin/python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1 \
   && ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1; then
  echo
  echo "  Python isn't installed yet. A macOS window will offer to install"
  echo "  'command line developer tools'. Click Install, wait for it to finish,"
  echo "  then double-click Setup again."
  xcode-select --install 2>/dev/null
  read -n1 -r -p "  Press any key to close..."
  exit 0
fi
PY=python3
command -v python3 >/dev/null || PY=/usr/bin/python3

echo
echo "  [1/3] Installing the tracker's Python libraries (one time, ~1 minute)..."
if [ ! -x app/.venv/bin/python ]; then
  $PY -m venv app/.venv || { echo "  Couldn't create the Python environment."; read -n1 -r; exit 1; }
fi
app/.venv/bin/python -m pip install -q --upgrade pip >/dev/null 2>&1
app/.venv/bin/python -m pip install -q -r app/requirements.txt || { echo "  Library install failed. Check your internet and run Setup again."; read -n1 -r; exit 1; }
app/.venv/bin/python -m pip install -q zipcodes >/dev/null 2>&1   # free US place data for distances (optional)
app/.venv/bin/python app/geo.py --build
echo "  Done."

# 2. Gmail ---------------------------------------------------------------
echo
echo "  [2/3] Gmail accounts"
app/.venv/bin/python app/setup_accounts.py

# 3. Free local AI (optional) -------------------------------------------
echo
echo "  [3/3] Free local AI helper (optional, recommended)"
OLLAMA=""
if command -v ollama >/dev/null 2>&1; then OLLAMA="ollama";
elif [ -x /Applications/Ollama.app/Contents/Resources/ollama ]; then OLLAMA="/Applications/Ollama.app/Contents/Resources/ollama"; fi

MODEL=$(app/.venv/bin/python -c "
import sys; sys.path.insert(0,'app')
import openpyxl, common
print(common.read_settings(openpyxl.load_workbook(common.WB_PATH)).get('ai_model') or 'qwen3:4b')" 2>/dev/null)
MODEL=${MODEL:-qwen3:4b}

if [ -z "$OLLAMA" ]; then
  echo "  Ollama isn't installed. It's free and runs entirely on your Mac."
  echo "  To add it: download from https://ollama.com/download , drag it to Applications,"
  echo "  open it once, then double-click Setup again. (Everything works without it, just less accurately.)"
  read -r -p "  Open the download page now? (y/n) " ans
  [ "$ans" = "y" ] && open "https://ollama.com/download"
else
  # start Ollama's background service without opening the app window
  STARTED=""
  if ! curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    "$OLLAMA" serve >/dev/null 2>&1 &
    STARTED=$!
    for i in $(seq 1 40); do curl -s -m 1 http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 0.25; done
  fi
  if "$OLLAMA" list 2>/dev/null | grep -q "^${MODEL}"; then
    echo "  AI model $MODEL is ready."
  else
    echo "  Downloading AI model $MODEL (about 2.5 GB, one time)..."
    "$OLLAMA" pull "$MODEL" && echo "  AI model ready."
  fi
  [ -n "$STARTED" ] && kill "$STARTED" 2>/dev/null
fi

echo
app/.venv/bin/python app/selfcheck.py
echo
echo "=============================================="
echo "  All set. Use 'Add Job' and 'Check Email'."
echo "  Fill in the yellow cells on the Settings tab of Job_Tracker.xlsx."
echo "=============================================="
read -n1 -r -p "  Press any key to close..."
