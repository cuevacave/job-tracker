"""Applies a new tracker layout right away (adds new columns/tabs/settings, keeps all your data)."""
import sys

from common import WB_PATH, Tracker

if __name__ == "__main__":
    if not WB_PATH.exists():
        sys.exit(0)
    try:
        tr = Tracker()
        counts = tr.save()
        print(f"  Tracker updated: To Apply {counts['To Apply']}, Applied {counts['Applied']}, Closed {counts['Closed']}.")
    except Exception as e:
        print(f"  (tracker will update on your next Add Job / Check Email run: {e})")
