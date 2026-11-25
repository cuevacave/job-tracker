"""Automatic daily scan, started by macOS (launchd). Turn it on or off with Auto Scan.command.

Once a day it scans every active Watchlist company, quietly, then shows a Mac notification with what it found.
The schedule calls it at 6:30 am and then every hour until 9:30 pm; after one successful run a day the later
calls do nothing. It never touches the workbook while Excel has it open: it just tries again an hour later.
Output goes to app/debug/auto_scan.log (and ~/Library/Logs/JobTracker-autoscan.log if the folder can't be read).

    app/.venv/bin/python app/auto_scan.py          scheduled run (skips if today's scan is done)
    app/.venv/bin/python app/auto_scan.py --now    run a scan now, even if one ran today
"""
from __future__ import annotations

import builtins
import datetime as dt
import io
import json
import os
import subprocess
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
STATE = APP / "auto_scan.json"
LOCK = APP / "auto_scan.lock"
LOG = APP / "debug" / "auto_scan.log"
FALLBACK_LOG = Path.home() / "Library" / "Logs" / "JobTracker-autoscan.log"
KEEP_LINES = 3000


def notify(msg: str, title: str = "Job Tracker"):
    msg, title = msg.replace('"', "'"), title.replace('"', "'")
    try:
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                       timeout=10, capture_output=True)
    except Exception:
        pass


def log(text: str, path: Path = LOG):
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[{stamp}] {l}" if l.strip() else l for l in text.rstrip().splitlines()]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        path.write_text("\n".join((old + lines)[-KEEP_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        if path != FALLBACK_LOG:
            log(text, FALLBACK_LOG)


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save(st: dict):
    STATE.write_text(json.dumps(st, indent=1))


def excel_open() -> bool:
    return any(ROOT.glob("~$Job_Tracker*.xlsx"))


def lock_held() -> bool:
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)  # still running?
        return True
    except (OSError, ValueError):
        return False


def online() -> bool:
    import requests
    for url in ("https://www.apple.com", "https://www.google.com"):
        try:
            requests.head(url, timeout=8)
            return True
        except requests.RequestException:
            continue
    return False


def main():
    flag = Path.home() / "Library" / "Application Support" / "JobTracker" / "run-now"  # set by Auto Scan.command
    now = "--now" in sys.argv or flag.exists()
    if flag.exists():
        try:
            flag.unlink()
        except OSError:
            pass
    today = dt.date.today().isoformat()
    try:
        st = load()
        ROOT.joinpath("Job_Tracker.xlsx").stat()
    except PermissionError:
        log("macOS didn't let the scheduled scan open the Job Tracker folder. Allow Python in System Settings > "
            "Privacy & Security > Files and Folders (or Full Disk Access).", FALLBACK_LOG)
        notify("The automatic scan can't open your Job Tracker folder. Open Auto Scan.command for the fix.")
        return
    if st.get("last_done") == today and not now:
        return  # today's scan is done
    if lock_held():
        return  # a scan is still running
    if excel_open():
        if st.get("excel_warned") != today:
            log("The tracker is open in Excel; skipped. Trying again in an hour.")
            notify("Close the tracker in Excel so the daily scan can run (it tries again every hour).")
            st["excel_warned"] = today
            save(st)
        return

    if not online():
        log("No internet connection (the Mac may have just woken up); trying again in an hour.")
        return

    LOCK.write_text(str(os.getpid()))
    t0 = time.time()
    buf = io.StringIO()
    try:
        builtins.input = lambda *a, **k: ""  # never wait for an answer nobody is there to give
        sys.path.insert(0, str(APP))
        with redirect_stdout(buf), redirect_stderr(buf):
            import common
            import linkcheck
            import watcher
            tr = common.Tracker()
            shown = watcher.run(tr)
            if linkcheck.due():
                try:
                    linkcheck.expire_closed(tr)
                except Exception as e:
                    print(f"  (Skipped the open-posting check: {type(e).__name__})")
            tr.save()
        found = [r for r in shown if not r.get("filtered")]
        best = [r for r in found if r.get("loc_tier") in (1, 2)]
        mins = (time.time() - t0) / 60
        log(f"Scan finished in {mins:.0f} min: {len(found)} new match(es), {len(best)} in Tier 1-2, "
            f"{len(shown) - len(found)} greyed.\n" + buf.getvalue())
        st.update({"last_done": today, "last_found": len(found), "last_minutes": round(mins, 1)})
        save(st)
        if found:
            top = ", ".join(f"{r['company']}" for r in (best or found)[:3])
            notify(f"{len(found)} new match(es), {len(best)} in Tier 1-2: {top}... See New Matches.",
                   "Job Tracker: new jobs")
        else:
            notify("Daily scan done: no new matching jobs today.")
    except Exception:
        log("The scan stopped with an error:\n" + buf.getvalue() + "\n" + traceback.format_exc())
        notify("The daily scan hit an error. Details: app/debug/auto_scan.log")
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
