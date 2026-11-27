#!/bin/bash
# Opens My Job Board in your browser (a page served from this Mac only). Close this window when you're done.
cd "$(dirname "$0")" || exit 1
clear
if [ ! -x app/.venv/bin/python ]; then echo "Run Setup first."; read -n1 -r; exit 1; fi
echo "=============================================="
echo "  JOB TRACKER: MY JOB BOARD"
echo "=============================================="
app/.venv/bin/python app/review.py
