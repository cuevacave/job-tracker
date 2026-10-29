#!/bin/bash
cd "$(dirname "$0")" || exit 1
clear
if [ ! -x app/.venv/bin/python ]; then echo "Run Setup first."; read -n1 -r; exit 1; fi
app/.venv/bin/python app/add_job.py
echo
read -n1 -r -p "  Press any key to close..."
