#!/bin/bash
cd "$(dirname "$0")" || exit 1
clear
if [ ! -x app/.venv/bin/python ]; then echo "Run Setup first."; read -n1 -r; exit 1; fi
app/.venv/bin/python app/check_email.py
echo
read -r -p "  Open the tracker now? (y/n) " ans
[ "$ans" = "y" ] && open Job_Tracker.xlsx
