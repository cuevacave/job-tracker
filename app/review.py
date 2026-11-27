"""Review screen: a local web page for deciding on New Matches, 5 jobs at a time.

Started by Review Jobs.command. Runs only on this Mac (http://127.0.0.1); nothing goes online except the job
links you click yourself. Every decision is written right away to app/decisions.csv (your history: what you added
or skipped, when, and why) and queued for the workbook; the queue is applied whenever the tracker isn't open in
Excel (with Save, Done, or when the window closes). Add uses the same step as Check Jobs > a; Skip is the tracker's
Dismiss; Interesting dismisses the job too and puts it on the Interesting tab, with its posting text saved in
app/saved_postings.
"""
from __future__ import annotations

import builtins
import csv
import datetime as dt
import html
import io
import json
import re
import signal
import sys
import threading
import time
import webbrowser
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

import common  # noqa: E402
import sheets  # noqa: E402
from apply import ApplyRules, years_number  # noqa: E402

DECISIONS = APP / "decisions.csv"
SAVED = APP / "saved_postings"
PENDING = APP / "review_pending.json"
PAGE = 5
DEC_COLS = ["Date", "Time", "Decision", "Reason", "Company", "Title", "Location", "Tier", "Years", "Fit", "Apply Group",
            "Pay", "Posted", "Link", "Key", "Row"]
SETTING_KEYS = {"apply_referral": "Apply: referral companies", "apply_top": "Apply: top companies",
                "apply_fit_min": "Apply: fit threshold", "review_watch_outs": "Review: watch-out words",
                "review_skip_reasons": "Review: skip reasons",
                "review_interest_reasons": "Review: interesting reasons"}
FACETS = ("tier", "prio", "grp", "yrs", "age", "role", "pay")
LATER = set()            # row keys put off during this session (shown last)
LOCK = threading.Lock()  # one change at a time
_VIEW = {"mtime": None}


# ------------------------------------------------------------------ files
def excel_open() -> bool:
    return common.excel_lock_path().exists()


def load_pending() -> dict:
    try:
        p = json.loads(PENDING.read_text())
    except (OSError, ValueError):
        p = {}
    p.setdefault("decisions", [])
    p.setdefault("settings", {})
    return p


def save_pending(p: dict):
    PENDING.write_text(json.dumps(p, indent=1, default=str))


def _plain(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return v


def log_decision(action: str, reason: str, row: dict):
    new = not DECISIONS.exists()
    now = dt.datetime.now()
    with open(DECISIONS, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(DEC_COLS)
        w.writerow([now.date().isoformat(), now.strftime("%H:%M"), action, reason or "", row.get("company"),
                    row.get("title"), row.get("location"), row.get("loc_tier"), row.get("years"), row.get("fit"),
                    row.get("apply_group"), row.get("pay"), _plain(row.get("posted")), row.get("link"), row.get("key"),
                    json.dumps({k: _plain(v) for k, v in row.items()}, default=str)])


def read_decisions() -> list:
    try:
        with open(DECISIONS, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


# ------------------------------------------------------------------ what's on New Matches
def view():
    """Settings, apply rules and New Matches rows, re-read whenever the workbook changes."""
    mt = common.WB_PATH.stat().st_mtime
    if _VIEW.get("mtime") != mt:
        import openpyxl
        wb = openpyxl.load_workbook(common.WB_PATH)
        s = common.read_settings(wb)
        _VIEW.update(mtime=mt, s=s, wl=sheets.read_watchlist(wb), rows=sheets.read_new_matches(wb))
    s = dict(_VIEW["s"])
    s.update(load_pending()["settings"])  # edits not in the workbook yet
    return s, ApplyRules(s, _VIEW["wl"]), _VIEW["rows"]


def _cache():
    import watcher
    return watcher._load_desc_cache()


def _norm_title(t):
    return re.sub(r"\W+", " ", str(t or "").lower()).strip()


def _days_ago(d):
    d = d if isinstance(d, dt.date) else None
    if isinstance(d, dt.datetime):
        d = d.date()
    return (dt.date.today() - d).days if d else None


def _watch_hits(text: str, words: list) -> list:
    out = []
    for w in words:
        if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", text, re.I):
            out.append(w)
    return out


def card_attrs(g: list) -> dict:
    """What the filters look at, for one card (its best row; Tier = its best location)."""
    first = g[0]
    tiers = [r.get("loc_tier") for r in g if isinstance(r.get("loc_tier"), (int, float))]
    y = first.get("years")
    y = years_number(y) if not isinstance(y, (int, float)) else y
    posted = common.to_date(first.get("posted"))
    if isinstance(posted, str):
        try:
            posted = dt.date.fromisoformat(posted[:10])
        except ValueError:
            posted = None
    ago = _days_ago(posted)
    pr = first.get("co_priority")
    try:
        pr = str(int(float(pr)))
    except (TypeError, ValueError):
        pr = "-"
    return {"tier": str(int(min(tiers))) if tiers else "u", "prio": pr, "grp": first.get("apply_group") or "Other",
            "yrs": "none" if y is None else ("0-2" if y <= 2 else "3+"),
            "age": "none" if ago is None else ("7" if ago <= 7 else "14" if ago <= 14 else "old"),
            "role": first.get("role_type") or "Other", "pay": "listed" if first.get("pay") else "none"}


def _matches(a: dict, f: dict, skip=None) -> bool:
    for k in FACETS:
        if k != skip and f.get(k) and a[k] not in f[k]:
            return False
    return True


def apply_filters(groups: list, f: dict):
    """(cards that pass, counts per filter value). Each count assumes your other filters, like a shop's filters do."""
    f = f or {}
    q = str(f.get("q") or "").strip().lower()
    if q:
        groups = [g for g in groups if q in f"{g[0].get('company')} {g[0].get('title')} "
                                           f"{' '.join(str(r.get('location')) for r in g)}".lower()]
    attrs = [card_attrs(g) for g in groups]
    counts = {k: {} for k in FACETS}
    for a in attrs:
        for k in FACETS:
            if _matches(a, f, skip=k):
                counts[k][a[k]] = counts[k].get(a[k], 0) + 1
    keep = [g for g, a in zip(groups, attrs) if _matches(a, f)]
    return keep, counts


def cards(show: str, f: dict = None):
    """Jobs grouped into cards (same company and title in several places = one card), in the apply order, with your
    filters applied. Returns (settings, cards, filter counts)."""
    import watcher
    s, rules, rows = view()
    pend = {d["key"]: d["action"] for d in load_pending()["decisions"]}
    cache = _cache()
    if show in ("skipped", "interesting"):
        want = "Skip" if show == "skipped" else "Interesting"
        latest = {}
        for d in read_decisions():
            if d["Decision"] != "Later":
                latest[d["Key"]] = d
        live = {r.get("key"): r for r in rows}
        rows = []
        for k, d in latest.items():
            if d["Decision"] != want or pend.get(k) == "Restore":
                continue
            r = live.get(k)
            if r is None:
                try:
                    r = json.loads(d.get("Row") or "{}")
                except ValueError:
                    continue
            r = dict(r)
            r["_reason"] = d.get("Reason")
            r["_when"] = d.get("Date")
            rows.append(r)
    else:
        want_grey = show == "greyed"
        rows = [r for r in rows if not str(r.get("action") or "").strip() and r.get("key") not in pend
                and bool(r.get("filtered")) == want_grey and r.get("title")]
    for r in rows:
        if r.get("fit") in (None, ""):
            desc = (cache.get(r.get("link")) or {}).get("t")
            r["fit"] = watcher.fit_of(r.get("title"), desc, s) if desc else None
        if r.get("years") in (None, ""):
            y = years_number(r.get("requirements"))
            r["years"] = int(y) if y is not None else None
        r["apply_group"] = rules.group(r.get("company"), r.get("link"))
    groups = {}
    for r in rows:
        groups.setdefault((str(r.get("company")).lower(), _norm_title(r.get("title"))), []).append(r)
    out = []
    for g in groups.values():
        g.sort(key=rules.row_key)
        later = all(r.get("key") in LATER for r in g)
        out.append((later, rules.row_key(g[0]), g))
    out.sort(key=lambda x: (x[0], x[1]))
    keep, counts = apply_filters([g for _, _, g in out], f)
    return s, keep, counts


def card_json(g: list, s: dict) -> dict:
    import scoring
    cache = _cache()
    first = g[0]
    desc = (cache.get(first.get("link")) or {}).get("t") or ""
    words = [w.strip() for w in str(s.get("review_watch_outs") or "").split(",") if w.strip()]
    notes = ""
    if desc:
        try:
            notes = scoring.fit({"title": first.get("title"), "description": desc}, s, None)[1]
        except Exception:
            notes = ""
    posted = common.to_date(first.get("posted"))
    if isinstance(posted, str):
        try:
            posted = dt.date.fromisoformat(posted[:10])
        except ValueError:
            posted = None
    return {
        "company": first.get("company"), "title": first.get("title"), "group": first.get("apply_group"),
        "years": first.get("years"), "fit": first.get("fit"), "fit_notes": notes, "pay": first.get("pay"),
        "requirements": first.get("requirements"), "filtered": first.get("filtered"),
        "posted": posted.isoformat() if isinstance(posted, dt.date) else None, "ago": _days_ago(posted),
        "track": first.get("track"), "role": first.get("role_type"),
        "watch": _watch_hits(f"{first.get('title')}\n{desc}", words),
        "flags": (["no relocation help"] if _watch_hits(desc, [w.strip() for w in str(s.get("review_no_relo") or "")
                                                              .split(",") if w.strip()]) else []),
        "description": desc, "reason": first.get("_reason"), "when": first.get("_when"),
        "tier": card_attrs(g)["tier"], "prio": first.get("co_priority"),
        "rows": [{"key": r.get("key"), "location": r.get("location"), "area": r.get("area"), "tier": r.get("loc_tier"),
                  "link": r.get("link"), "pay": r.get("pay"), "years": r.get("years")} for r in g],
    }


# ------------------------------------------------------------------ decisions
def decide(body: dict) -> dict:
    keys = body.get("keys") or []
    add = set(body.get("add") or keys)
    action, reason = body.get("action"), str(body.get("reason") or "")
    _, _, rows = view()
    by = {r.get("key"): r for r in rows}
    with LOCK:
        p = load_pending()
        for k in keys:
            r = dict(by.get(k) or {"key": k})
            if action == "later":
                LATER.add(k)
                log_decision("Later", reason, r)
                continue
            if action == "add":
                a, why = ("Add", reason) if k in add else ("Skip", "same job, other location")
            elif action == "skip":
                a, why = "Skip", reason
            elif action == "interesting":
                a, why = "Interesting", reason
            elif action == "restore":
                a, why = "Restore", reason
                if r.get("company") is None:
                    for d in reversed(read_decisions()):
                        if d["Key"] == k and d.get("Row"):
                            r = json.loads(d["Row"])
                            break
            else:
                continue
            LATER.discard(k)
            log_decision(a, why, r)
            p["decisions"] = [d for d in p["decisions"] if d["key"] != k]
            p["decisions"].append({"key": k, "action": a, "reason": why,
                                   "row": {kk: _plain(v) for kk, v in r.items()}})
        save_pending(p)
    return status()


def save_settings(body: dict) -> dict:
    with LOCK:
        p = load_pending()
        for k in SETTING_KEYS:
            if k in body:
                p["settings"][k] = body[k]
        save_pending(p)
    return status()


def apply_now() -> dict:
    """Write the queued decisions and setting changes into the workbook (and add the jobs marked Add)."""
    with LOCK:
        p = load_pending()
        if not p["decisions"] and not p["settings"]:
            return {**status(), "message": ""}
        if excel_open():
            return {**status(), "message": "The tracker is open in Excel. Save and close it there (Cmd+S, Cmd+W), "
                                           "then press Save to workbook."}
        import watcher
        buf = io.StringIO()
        def no_questions(*a, **k):
            raise EOFError  # nobody is at the Terminal to answer
        builtins.input = no_questions
        added = 0
        try:
            with redirect_stdout(buf):
                tr = common.Tracker()
                tr.ensure_settings_rows()
                if p["settings"]:
                    for row in tr.wb["Settings"].iter_rows(min_row=1, max_col=2):
                        for k, label in SETTING_KEYS.items():
                            if row[0].value == label and k in p["settings"]:
                                row[1].value = p["settings"][k]
                    tr.s = common.read_settings(tr.wb)
                    if hasattr(tr, "_apply"):
                        del tr._apply
                rows = sheets.read_new_matches(tr.wb)
                by = {r.get("key"): r for r in rows}
                for d in p["decisions"]:
                    r = by.get(d["key"])
                    if d["action"] == "Restore":
                        if r is None:
                            r = {k: v for k, v in d["row"].items() if k in sheets.NM_KEYS}
                            for k in ("found", "posted"):
                                if r.get(k):
                                    try:
                                        r[k] = dt.datetime.fromisoformat(str(r[k])[:10])
                                    except ValueError:
                                        r[k] = None
                            r["found"] = dt.datetime.combine(dt.date.today(), dt.time())
                            rows.append(r)
                            by[d["key"]] = r
                        r["action"] = None
                    elif r is not None:
                        r["action"] = "Add" if d["action"] == "Add" else "Dismiss"
                watcher.fill_columns(tr, rows)
                rows.sort(key=watcher.nm_order)
                sheets.write_new_matches(tr.wb, rows, n_new=0)
                restored = {str(d["row"].get("link") or "") for d in p["decisions"] if d["action"] == "Restore"}
                sheets.remove_interesting(tr.wb, restored - {""})
                keep = [interesting_item(d, by.get(d["key"])) for d in p["decisions"] if d["action"] == "Interesting"]
                if keep:
                    sheets.add_interesting(tr.wb, keep)
                if any(d["action"] == "Add" for d in p["decisions"]):
                    added = watcher.add_marked(tr)
                tr.save()
            save_pending({"decisions": [], "settings": {}})
            _VIEW["mtime"] = None
            out = buf.getvalue()
            unread = len(re.findall(r"couldn't read", out))
            msg = "Saved to the workbook." + (f" Added {added} job(s) to To Apply." if added else "")
            if keep:
                msg += f" {len(keep)} job(s) put on the Interesting tab."
            if unread:
                msg += f" {unread} posting(s) couldn't be read (left marked Add on New Matches; probably taken down)."
            return {**status(), "message": msg, "log": out[-3000:]}
        except Exception as e:
            return {**status(), "message": f"Couldn't save ({type(e).__name__}: {e}). Your decisions are kept; "
                                           f"try Save again.", "log": buf.getvalue()[-3000:]}


def _safe(s: str, n=60) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-")[:n] or "job"


def interesting_item(d: dict, live: dict | None) -> dict:
    """A row for the Interesting tab, with the posting's full text saved to app/saved_postings (postings get taken
    down; the text stays)."""
    r = dict(d.get("row") or {})
    if live:
        r.update({k: v for k, v in live.items() if v not in (None, "")})
    r["why"] = d.get("reason") or ""
    desc = (_cache().get(r.get("link")) or {}).get("t") if r.get("link") else None
    if desc:
        SAVED.mkdir(exist_ok=True)
        f = SAVED / f"{dt.date.today().isoformat()}_{_safe(r.get('company'), 30)}_{_safe(r.get('title'))}.txt"
        head = [f"{r.get('company')} - {r.get('title')}", f"Location: {r.get('location') or ''}",
                f"Link: {r.get('link') or ''}", f"Saved: {dt.date.today().isoformat()}"
                + (f" (why: {r['why']})" if r["why"] else ""), "", ""]
        try:
            f.write_text("\n".join(head) + desc, encoding="utf-8")
            r["file"] = f"app/saved_postings/{f.name}"
        except OSError:
            pass
    return r


def status() -> dict:
    p = load_pending()
    return {"pending": len(p["decisions"]) + (1 if p["settings"] else 0), "excel": excel_open(),
            "adds": sum(1 for d in p["decisions"] if d["action"] == "Add")}


# ------------------------------------------------------------------ web
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        data = body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._send(PAGE_HTML, "text/html")
            if u.path == "/api/cards":
                f = {k: set(x for x in q[k].split(",") if x) for k in FACETS if q.get(k)}
                f["q"] = q.get("q", "")
                s, all_cards, counts = cards(q.get("show", "review"), f)
                page = max(0, int(q.get("page", 0)))
                part = all_cards[page * PAGE:(page + 1) * PAGE]
                return self._send({**status(), "total": len(all_cards), "page": page, "counts": counts,
                                   "cards": [card_json(g, s) for g in part]})
            if u.path == "/api/settings":
                s, _, _ = view()
                reasons = [x.strip() for x in str(s.get("review_skip_reasons") or "").split(",") if x.strip()][:9]
                ints = [x.strip() for x in str(s.get("review_interest_reasons") or "").split(",") if x.strip()][:9]
                return self._send({k: s.get(k) for k in SETTING_KEYS} | {"reasons": reasons, "ints": ints})
            if u.path == "/api/status":
                return self._send(status())
        except Exception as e:
            return self._send({"error": f"{type(e).__name__}: {e}"}, code=500)
        self._send({"error": "not found"}, code=404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/decide":
                return self._send(decide(body))
            if self.path == "/api/settings":
                return self._send(save_settings(body))
            if self.path == "/api/apply":
                return self._send(apply_now())
            if self.path == "/api/quit":
                res = apply_now()
                self._send(res)
                if not load_pending()["decisions"]:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        except Exception as e:
            return self._send({"error": f"{type(e).__name__}: {e}"}, code=500)
        self._send({"error": "not found"}, code=404)


PAGE_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Review jobs</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1f2328;--mut:#5b6472;--line:#dfe3e8;--acc:#0b63ce;--ok:#1a7f37;--no:#b42318;--warn:#b54708;--warnbg:#fff4e5;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a20;--fg:#e6e9ee;--mut:#9aa3af;--line:#2a2f38;--acc:#4c9aff;--ok:#3fb950;--no:#f85149;--warn:#f0a35e;--warnbg:#2b2113;--chip:#232833}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0 8px 0 0}.tabs button{border:0;background:none;color:var(--mut);font:inherit;padding:6px 10px;border-radius:6px;cursor:pointer}
.tabs button.on{background:var(--chip);color:var(--fg);font-weight:600}.sp{flex:1}
.pend{font-size:13px;color:var(--mut)}.pend b{color:var(--fg)}button.act{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:6px 12px;font:inherit;cursor:pointer}
button.act:hover{border-color:var(--acc)}main{max-width:980px;margin:0 auto;padding:16px 20px 80px}
.msg{margin:0 0 12px;padding:10px 14px;border-radius:8px;background:var(--chip);font-size:14px;display:none}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 14px;outline:none}
.card.focus{border-color:var(--acc);box-shadow:0 0 0 2px color-mix(in srgb,var(--acc) 25%,transparent)}
.card.done{opacity:.45}.top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.co{font-weight:600}.ti{font-size:16px;font-weight:600}
.g{font-size:12px;padding:1px 8px;border-radius:999px;background:var(--chip);color:var(--mut)}.g.Referral{background:#e7f6ec;color:#1a7f37}.g.Top{background:#e8f0fe;color:#0b57d0}
@media (prefers-color-scheme:dark){.g.Referral{background:#16341f;color:#56d364}.g.Top{background:#14243f;color:#79b0ff}}
.facts{display:flex;gap:14px;flex-wrap:wrap;color:var(--mut);font-size:13.5px;margin:6px 0}.facts b{color:var(--fg);font-weight:600}
.watch{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.w{font-size:12px;background:var(--warnbg);color:var(--warn);border-radius:999px;padding:1px 9px;font-weight:600}
.w.f{background:var(--chip);color:var(--fg);border:1px solid var(--line)}.locs{margin:6px 0;font-size:14px}.locs label{display:block;padding:2px 0}.req,.notes{font-size:13.5px;color:var(--mut);margin:4px 0}
.grey{font-size:13px;color:var(--no)}details{margin:8px 0 2px}summary{cursor:pointer;color:var(--acc);font-size:14px}
.desc{white-space:pre-wrap;font-size:14px;max-height:420px;overflow:auto;border-top:1px solid var(--line);margin-top:6px;padding-top:8px}
.desc mark{background:var(--warnbg);color:var(--warn);font-weight:600}
.btns{display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap}.btns button{font:inherit;border-radius:7px;padding:6px 14px;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.btns .add{border-color:var(--ok);color:var(--ok)}.btns .skip{border-color:var(--no);color:var(--no)}.btns kbd{font-size:11px;color:var(--mut);margin-left:4px}
.reasons{display:none;gap:6px;flex-wrap:wrap}.reasons button{font-size:13px;padding:3px 10px}.reasons.on{display:flex}
.nav{display:flex;gap:10px;align-items:center;justify-content:center;margin:18px 0;color:var(--mut)}
.help{font-size:12.5px;color:var(--mut);text-align:center}.set label{display:block;font-weight:600;margin:14px 0 4px}.set textarea,.set input{width:100%;font:inherit;padding:8px;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--fg)}
.set .hint{font-size:13px;color:var(--mut)}a{color:var(--acc)}
#cover{position:fixed;inset:0;background:color-mix(in srgb,var(--bg) 80%,transparent);display:none;align-items:center;justify-content:center;z-index:20;text-align:center}#cover.on{display:flex}#cover div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 28px;max-width:460px}
#fbox{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;margin:0 0 14px}#fbox summary{color:var(--fg);font-size:14px}#fbox summary span{color:var(--mut);font-weight:400}
.frow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:7px 0}.frow b{font-size:12.5px;color:var(--mut);width:70px;font-weight:600}
.fc{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:999px;padding:2px 10px;cursor:pointer}.fc span{color:var(--mut);font-size:12px;margin-left:3px}
.fc.on{background:var(--acc);border-color:var(--acc);color:#fff}.fc.on span{color:#e8f0fe}.fc.zero{opacity:.45}
#fq{font:inherit;font-size:13px;padding:3px 9px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);width:220px}
.nudge{margin:0 0 12px;padding:10px 14px;border-radius:8px;background:var(--warnbg);color:var(--warn);font-size:14px}.nudge button{margin-left:8px}
.btns .int{border-color:#7a5af8;color:#7a5af8}
.reasons input{font:inherit;font-size:13px;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);display:none}.reasons.other input{display:inline-block}
</style></head><body>
<header><h1>Review jobs</h1>
<div class="tabs"><button data-t="review" class="on">To review</button><button data-t="greyed">Greyed</button><button data-t="skipped">Skipped</button><button data-t="interesting">Interesting</button><button data-t="settings">Settings</button></div>
<div class="sp"></div><span class="pend" id="pend"></span><button class="act" id="save">Save to workbook</button><button class="act" id="quit">Done: save and close</button></header>
<div id="cover"><div><b id="covt">Saving to the workbook...</b><p id="covp"></p></div></div>
<main><div class="msg" id="msg"></div><div id="filters"></div><div id="nudge"></div><div id="list"></div><div class="nav" id="nav"></div>
<p class="help">Keys: <b>A</b> add · <b>S</b> skip (then a number for the reason, <b>O</b> to type your own, Enter for none) · <b>I</b> interesting, for a side project (reasons the same way) · <b>L</b> later · <b>J/K</b> next/previous job · <b>E</b> description · <b>N/P</b> next/previous 5 · <b>F</b> filters<br>Your decisions are recorded as you go and written to the workbook when you press <b>Save</b> or <b>Done</b> (or close the Terminal window).</p></main>
<script>
let tab="review",page=0,data=null,focus=0,reasons=[],ints=[];
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const store={get(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
let filt=store.get("jt_filters",{tier:["1","2","u"]}),fopen=store.get("jt_fopen",true),fq="";
const FL={tier:["Tier",["1","2","u","3","4"],{u:"? (unclear)"}],prio:["Priority",null,{"-":"not on Watchlist"}],grp:["Group",["Referral","Top","Other"],{}],
yrs:["Years",["0-2","3+","none"],{none:"not stated"}],age:["Posted",["7","14","old","none"],{"7":"this week","14":"last 2 weeks",old:"older",none:"no date"}],role:["Role",null,{}],pay:["Pay",["listed","none"],{none:"not listed"}]};
const filtered=()=>tab==="review"||tab==="greyed";
async function api(p,b){const r=await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{});return r.json()}
function msg(t){const m=$("#msg");m.textContent=t||"";m.style.display=t?"block":"none"}
function pend(st){$("#pend").innerHTML=st.pending?`<b>${st.pending}</b> decision(s) recorded, not in the workbook yet`+(st.excel?" · close the tracker in Excel before saving":""):(st.excel?"Tracker is open in Excel":"Everything is saved");$("#save").disabled=!st.pending}
function cover(on,t,p){$("#cover").classList.toggle("on",on);if(t)$("#covt").textContent=t;$("#covp").textContent=p||""}
async function save(quit){const st=await api("/api/status");if(st.excel){msg("The tracker is open in Excel. Save and close it there (Cmd+S, Cmd+W), then press Save again.");return false}
cover(true,quit?"Saving and closing...":"Saving to the workbook...",st.adds?`Adding ${st.adds} job(s) to To Apply: about ${Math.max(5,st.adds*6)} seconds.`:"A few seconds.");
const r=await api(quit?"/api/quit":"/api/apply",{});cover(false);if(quit&&!r.pending){document.body.innerHTML=`<main><h2>Saved. You can close this tab.</h2><p>${esc(r.message||"")}</p></main>`;return true}msg(r.message);return true}
function mark(text,words){let t=esc(text);for(const w of words){const re=new RegExp("(?<![\\w])("+w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")(?![\\w])","gi");t=t.replace(re,"<mark>$1</mark>")}return t}
function query(){let q=`show=${tab}&page=${page}`;if(filtered()){for(const k in FL)if(filt[k]&&filt[k].length)q+=`&${k}=${encodeURIComponent(filt[k].join(","))}`;if(fq)q+=`&q=${encodeURIComponent(fq)}`}return q}
async function load(){msg("");if(tab==="settings"){$("#filters").innerHTML="";$("#nudge").innerHTML="";return settings()}data=await api(`/api/cards?${query()}`);if(data.error){msg(data.error);return}pend(data);renderFilters();render()}
function label(k,v){const m=FL[k][2];return m[v]??(k==="prio"?"P"+v:v)}
function summary(){const on=Object.keys(FL).filter(k=>filt[k]&&filt[k].length).map(k=>FL[k][0]+" "+filt[k].map(v=>label(k,v)).join(", "));if(fq)on.push(`"${fq}"`);return on.length?on.join(" · "):"showing everything"}
function renderFilters(){const F=$("#filters");if(!filtered()){F.innerHTML="";$("#nudge").innerHTML="";return}const c=data.counts||{};
const rows=Object.keys(FL).map(k=>{let vals=FL[k][1];const have=c[k]||{};if(!vals){vals=Object.keys(have).sort((a,b)=>k==="prio"?(a==="-")-(b==="-")||a-b:(have[b]-have[a]));}
const sel=filt[k]||[];vals=vals.filter(v=>have[v]||sel.includes(v));if(!vals.length)return"";
return `<div class="frow"><b>${FL[k][0]}</b>${vals.map(v=>`<button class="fc${sel.includes(v)?" on":""}${have[v]?"":" zero"}" data-f="${k}" data-v="${esc(v)}">${esc(label(k,v))}<span>(${have[v]||0})</span></button>`).join("")}</div>`}).join("");
F.innerHTML=`<details id="fbox" ${fopen?"open":""}><summary>Filters <span>· ${esc(summary())}</span></summary>${rows}<div class="frow"><b>Search</b><input id="fq" placeholder="company, title or place" value="${esc(fq)}"><button class="fc" id="fclear">Show everything</button><button class="fc" id="fdef">Default (Tier 1-2)</button></div><div class="hint" style="font-size:12.5px;color:var(--mut)">Tap to show only those; tap again to undo. No chip picked in a row = all of them. Numbers = jobs you'd see with your other filters.</div></details>`;
$("#fbox").ontoggle=()=>{fopen=$("#fbox").open;store.set("jt_fopen",fopen)};
F.querySelectorAll(".fc[data-f]").forEach(b=>b.onclick=()=>{const k=b.dataset.f,v=b.dataset.v;const s=new Set(filt[k]||[]);s.has(v)?s.delete(v):s.add(v);filt[k]=[...s];refilter()});
$("#fclear").onclick=()=>{filt={};fq="";refilter()};$("#fdef").onclick=()=>{filt={tier:["1","2","u"]};fq="";refilter()};
let tmr;$("#fq").oninput=e=>{clearTimeout(tmr);tmr=setTimeout(()=>{fq=e.target.value.trim();page=0;focus=0;load().then(()=>{const i=$("#fq");if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length)}})},350)};
const N=$("#nudge");N.innerHTML="";if(tab==="review"&&filt.tier&&filt.tier.length&&data.total<=5){const more=Object.entries(c.tier||{}).filter(([v,n])=>n&&!filt.tier.includes(v));
if(more.length){N.innerHTML=`<div class="nudge">${data.total?`Only ${data.total} job(s) left`:"Nothing left"} in Tier ${filt.tier.map(v=>label("tier",v)).join(", ")}. ${more.map(([v,n])=>`Tier ${esc(label("tier",v))} has ${n}`).join(", ")}.<button class="act" id="more">Include them</button></div>`;
$("#more").onclick=()=>{filt.tier=[...new Set([...filt.tier,...more.map(x=>x[0])])];refilter()}}}}
function refilter(){store.set("jt_filters",filt);page=0;focus=0;load()}
function rbox(kind,list){return `<span class="reasons" data-kind="${kind}">${list.map((r,j)=>`<button data-r="${esc(r)}">${j+1} ${esc(r)}</button>`).join("")}<button data-o="1">O other...</button><input placeholder="type a reason, Enter"><button data-r="">no reason</button></span>`}
function render(){const L=$("#list");if(!data.cards.length){L.innerHTML=`<p class="help">${tab==="review"?(data.total===0&&filtered()?"Nothing left to review with these filters. New jobs arrive with the next scan.":"Nothing left to review."):"Nothing here."}</p>`;$("#nav").innerHTML="";return}
L.innerHTML=data.cards.map((c,i)=>{const multi=c.rows.length>1;const locs=c.rows.map((r,j)=>multi?`<label><input type="checkbox" data-k="${esc(r.key)}" ${j===0?"checked":""}> ${esc(r.location)} · Tier ${esc(r.tier??"?")}${r.pay&&r.pay!==c.pay?" · "+esc(r.pay):""} · <a href="${esc(r.link)}" target="_blank">open</a></label>`:`${esc(r.location)} · Tier ${esc(r.tier??"?")} · <a href="${esc(r.link)}" target="_blank">open posting</a>`).join("");
const act=(tab==="skipped"||tab==="interesting")?`<button class="add" data-a="restore">Bring back</button>`:`<button class="add" data-a="add">Add<kbd>A</kbd></button><button class="skip" data-a="skip">Skip<kbd>S</kbd></button><button class="int" data-a="interesting">Interesting<kbd>I</kbd></button><button data-a="later">Later<kbd>L</kbd></button>${rbox("skip",reasons)}${rbox("interesting",ints)}`;
return `<div class="card" tabindex="0" data-i="${i}"><div class="top"><span class="co">${esc(c.company)}</span><span class="g ${esc(c.group)}">${esc(c.group)}</span>${c.role?`<span class="g">${esc(c.role)}</span>`:""}${c.prio?`<span class="g">P${esc(c.prio)}</span>`:""}</div>
<div class="ti">${esc(c.title)}</div><div class="facts"><span>Years <b>${c.years??"not stated"}</b></span><span>Fit <b>${c.fit??"?"}</b>/10</span><span>Pay <b>${esc(c.pay||"not listed")}</b></span><span>Posted <b>${c.posted?esc(c.posted)+" ("+c.ago+"d ago)":"?"}</b></span>${multi?`<span><b>${c.rows.length}</b> locations</span>`:""}</div>
${c.watch.length||c.flags.length?`<div class="watch">${c.flags.map(w=>`<span class="w f">${esc(w)}</span>`).join("")}${c.watch.map(w=>`<span class="w">${esc(w)}</span>`).join("")}</div>`:""}
<div class="locs">${locs}</div>${c.requirements?`<div class="req">Requirements: ${esc(c.requirements)}</div>`:""}${c.filtered?`<div class="grey">Greyed: ${esc(c.filtered)}</div>`:""}${c.reason!=null&&(tab==="skipped"||tab==="interesting")?`<div class="grey">${tab==="skipped"?"Skipped":"Saved"} ${esc(c.when)}${c.reason?": "+esc(c.reason):""}</div>`:""}
${c.fit_notes?`<div class="notes">Fit: ${esc(c.fit_notes)}</div>`:""}<details><summary>Description</summary><div class="desc">${c.description?mark(c.description,c.watch):"Not saved. Use the link above."}</div></details>
<div class="btns">${act}</div></div>`}).join("");
const pages=Math.ceil(data.total/5);$("#nav").innerHTML=`<button class="act" id="prev" ${page?"":"disabled"}>Previous 5 (P)</button><span>${page*5+1}-${Math.min(data.total,page*5+5)} of ${data.total} ${tab==="review"?"left to review":"jobs"}</span><button class="act" id="next" ${page+1<pages?"":"disabled"}>Next 5 (N)</button>`;
$("#prev").onclick=()=>{page--;load()};$("#next").onclick=()=>{page++;load()};
document.querySelectorAll(".card").forEach(el=>{el.onclick=e=>{setFocus(+el.dataset.i,false);const b=e.target.closest("button");if(!b)return;if(b.dataset.a)act(+el.dataset.i,b.dataset.a);if(b.dataset.o)other(+el.dataset.i);if(b.dataset.r!==undefined)choose(+el.dataset.i,b.closest(".reasons").dataset.kind,b.dataset.r)};
el.querySelectorAll(".reasons input").forEach(inp=>inp.onkeydown=e=>{e.stopPropagation();const kind=inp.closest(".reasons").dataset.kind;if(e.key==="Enter")choose(+el.dataset.i,kind,inp.value.trim());if(e.key==="Escape"){inp.closest(".reasons").classList.remove("other")}})});setFocus(Math.min(focus,data.cards.length-1),false)}
function setFocus(i,scroll=true){focus=Math.max(0,i);document.querySelectorAll(".card").forEach(c=>c.classList.toggle("focus",+c.dataset.i===focus));const el=document.querySelector(`.card[data-i="${focus}"]`);if(el&&scroll)el.scrollIntoView({block:"nearest",behavior:"smooth"})}
function keysOf(i,picked){const el=document.querySelector(`.card[data-i="${i}"]`),c=data.cards[i];if(picked&&c.rows.length>1)return[...el.querySelectorAll("input:checked")].map(x=>x.dataset.k);return c.rows.map(r=>r.key)}
async function act(i,a){const el=document.querySelector(`.card[data-i="${i}"]`);if(!el||el.classList.contains("done"))return;
if(a==="skip"||a==="interesting"){el.querySelectorAll(".reasons").forEach(r=>r.classList.toggle("on",r.dataset.kind===a));el.dataset.asking=a;return}
const all=keysOf(i,false);let st;if(a==="add"){const pick=keysOf(i,true);if(!pick.length){msg("Tick at least one location to add.");return}st=await api("/api/decide",{action:"add",keys:all,add:pick})}
else st=await api("/api/decide",{action:a,keys:all});done(el,st)}
function other(i){const el=document.querySelector(`.card[data-i="${i}"]`);const box=el.querySelector(`.reasons[data-kind="${el.dataset.asking||"skip"}"]`);box.classList.add("other");box.querySelector("input").focus()}
async function choose(i,kind,r){const el=document.querySelector(`.card[data-i="${i}"]`);delete el.dataset.asking;const st=await api("/api/decide",{action:kind,keys:keysOf(i,false),reason:r});done(el,st)}
async function done(el,st){el.classList.add("done");pend(st);const left=[...document.querySelectorAll(".card")].filter(c=>!c.classList.contains("done"));
if(left.length){setFocus(+left[0].dataset.i);return}focus=0;await load();window.scrollTo({top:0,behavior:"smooth"})}
async function settings(){const s=await api("/api/settings");$("#nav").innerHTML="";$("#list").innerHTML=`<div class="card set">
<label>Referral companies</label><textarea id="s_ref" rows="2">${esc(s.apply_referral||"")}</textarea>
<label>Top companies</label><textarea id="s_top" rows="4">${esc(s.apply_top||"")}</textarea><div class="hint">Comma-separated. Moving a company between groups = cutting it from one box and pasting it in the other. Every other company is Other.</div>
<label>Fit threshold</label><input id="s_fit" value="${esc(s.apply_fit_min??5)}"><div class="hint">Jobs whose Fit is below this go to the bottom of their group (never hidden).</div>
<label>Watch-out words</label><textarea id="s_watch" rows="3">${esc(s.review_watch_outs||"")}</textarea><div class="hint">Highlighted on each job (never hidden).</div>
<label>Skip reasons</label><textarea id="s_reasons" rows="2">${esc(s.review_skip_reasons||"")}</textarea><div class="hint">Offered when you skip (keys 1-9). "Other" always lets you type one.</div>
<label>Interesting reasons</label><textarea id="s_ints" rows="2">${esc(s.review_interest_reasons||"")}</textarea><div class="hint">Offered when you mark a job Interesting (key I, then 1-9).</div>
<div class="btns"><button class="add" id="s_save">Save settings</button></div></div>`;
$("#s_save").onclick=async()=>{const st=await api("/api/settings",{apply_referral:$("#s_ref").value,apply_top:$("#s_top").value,apply_fit_min:$("#s_fit").value,review_watch_outs:$("#s_watch").value,review_skip_reasons:$("#s_reasons").value,review_interest_reasons:$("#s_ints").value});pend(st);const s2=await api("/api/settings");reasons=s2.reasons||[];ints=s2.ints||[];msg("Settings recorded; they go into the workbook with your next Save.")}}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("on",x===b));tab=b.dataset.t;page=0;focus=0;load()});
$("#save").onclick=async()=>{if(await save(false)){const t=$("#msg").textContent;await load();msg(t)}};$("#quit").onclick=()=>save(true);
document.addEventListener("keydown",e=>{if(!data||!data.cards||tab==="settings"||e.metaKey||e.ctrlKey||e.target.matches("input,textarea"))return;const k=e.key.toLowerCase();const el=document.querySelector(`.card[data-i="${focus}"]`);
if(el&&el.dataset.asking){const kind=el.dataset.asking,list=kind==="skip"?reasons:ints;if(/^[1-9]$/.test(k)&&list[+k-1]){choose(focus,kind,list[+k-1]);e.preventDefault()}else if(k==="o"){other(focus);e.preventDefault()}else if(k==="enter"){choose(focus,kind,"");e.preventDefault()}else if(k==="escape"){delete el.dataset.asking;el.querySelectorAll(".reasons").forEach(r=>r.classList.remove("on"))}return}
if(k==="a")act(focus,"add");else if(k==="s")act(focus,"skip");else if(k==="i")act(focus,"interesting");else if(k==="l")act(focus,"later");else if(k==="j")setFocus(Math.min(focus+1,data.cards.length-1));else if(k==="k")setFocus(focus-1);
else if(k==="f"&&$("#fbox")){const d=$("#fbox");d.open=!d.open}
else if(k==="e"&&el){const d=el.querySelector("details:not(#fbox)");d.open=!d.open}else if(k==="n"&&$("#next")&&!$("#next").disabled){page++;focus=0;load()}else if(k==="p"&&page){page--;focus=0;load()}});
setInterval(async()=>{const st=await api("/api/status");if(data)pend(st)},15000);
api("/api/settings").then(s=>{reasons=s.reasons||[];ints=s.ints||[];load()});
</script></body></html>"""


def main():
    port = 8765
    for p in range(8765, 8785):
        try:
            srv = HTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    else:
        sys.exit("No free local port for the review screen.")
    url = f"http://127.0.0.1:{port}/"
    print(f"  Review screen: {url}")
    print("  It opened in your browser. Keep this window open while you review; close it (or press Ctrl+C) when done.")
    if load_pending()["decisions"] and not excel_open():
        print("  Saving decisions left from last time...")
        print("  " + apply_now().get("message", ""))
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    def stop(*_):
        raise KeyboardInterrupt  # closing the Terminal window or Ctrl+C: save, then quit
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    p = load_pending()
    if p["decisions"] or p["settings"]:
        if excel_open():
            say(f"\n  {len(p['decisions'])} decision(s) are kept in app/review_pending.json; they go into the workbook "
                f"the next time you open the Review screen with Excel closed.")
        else:
            say("\n  Saving your decisions to the workbook...")
            say("  " + apply_now().get("message", ""))
    say("  Review screen closed.")


def say(text: str):
    """Print, but never fail when the Terminal window is already gone."""
    try:
        print(text, flush=True)
    except OSError:
        pass


if __name__ == "__main__":
    main()
