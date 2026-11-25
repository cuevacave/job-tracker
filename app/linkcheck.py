"""Are your saved jobs still open?

check_open(link) -> "open" | "closed" | "unknown". Only clear signs count as closed (page not found, "no longer
available", a job board's own feed saying the job is gone). A timeout or an odd page is "unknown" and never counts.

expire_closed(tr) marks a job Expired only after two "closed" answers on different days. Applied jobs are never
touched. Undecided New Matches rows whose posting closed are removed (and stay remembered, so never shown again).
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from common import load_state, norm_url, save_state, to_date, today

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
CHECK_EVERY_DAYS = 7
APP_SITES = ("eightfold", "oraclecloud", "jobs.apple.com", "google.com", "careers.qualcomm", "jobs.northropgrumman",
             "careers.appliedmaterials", "jhuapl")
CLOSED_TEXT = re.compile(
    r"no longer (?:available|accepting applications|open|active|posted)|this (?:job|position|posting|requisition) "
    r"(?:has (?:expired|been filled|been closed|closed)|is (?:closed|no longer)|was removed)|job (?:posting )?(?:has )?expired|"
    r"position has been filled|job (?:you are|you're) looking for (?:is no longer|can(?:no|')t be found|was not found)|"
    r"(?:job|page) not found|requisition is no longer|posting has (?:closed|expired)|not accepting applications|"
    # pages that stay up but say the job is gone
    r"(?:job|position|posting|requisition|page) (?:you(?: are| were|'re|’re) looking for )?(?:does(?:n't| not)|no longer) exists?|"
    r"(?:job|position|posting) is (?:now )?unavailable|"
    r"(?:could not|couldn't|can ?not|can't|unable to) find (?:the|this|that) (?:job|position|posting|page)|"
    r"(?:job|position|posting) has been removed|"
    r"this (?:job|position|role) is (?:closed|filled)|applications? (?:are|is|have) (?:now )?closed",
    re.I)


def _get(url, **kw):
    return requests.get(url, headers=UA, timeout=20, allow_redirects=True, **kw)


def _api_check(link):
    """Job boards with a simple per-job feed: a missing job answers 404. Returns a verdict or None (not one of these)."""
    u = urlparse(link)
    host, parts = u.netloc.lower(), [p for p in u.path.split("/") if p]
    if "greenhouse.io" in host and "jobs" in parts:
        board = parts[0] if parts[0] != "embed" else None
        jid = parts[parts.index("jobs") + 1] if len(parts) > parts.index("jobs") + 1 else None
        if board and jid and jid.isdigit():
            r = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}")
            return "closed" if r.status_code == 404 else ("open" if r.status_code == 200 else "unknown")
    if host == "jobs.lever.co" and len(parts) >= 2:
        r = _get(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}")
        return "closed" if r.status_code == 404 else ("open" if r.status_code == 200 else "unknown")
    if "myworkdayjobs.com" in host or "myworkdaysite.com" in host:
        import watcher
        sysname, p = watcher.detect(link)
        if sysname == "Workday" and p:
            path = u.path
            m = re.search(r"(/job/.+)$", path)
            if m:
                r = requests.get(f"https://{p['host']}/wday/cxs/{p['tenant']}/{p['site']}{m.group(1)}",
                                 headers={**UA, "Accept": "application/json"}, timeout=20)
                if r.status_code in (404, 410):
                    return "closed"
                if r.status_code == 403 and '"S22"' in r.text:
                    return "closed"  # Workday's answer for a requisition that's no longer posted ("permission denied")
                if r.status_code == 200:
                    try:
                        info = (r.json() or {}).get("jobPostingInfo") or {}
                    except ValueError:
                        return "unknown"
                    return "open" if info.get("title") else "unknown"
                return "unknown"
    return None


def check_open(link) -> str:
    if not link or not str(link).startswith("http"):
        return "unknown"
    try:
        v = _api_check(link)
        if v:
            return v
        r = _get(link)
        if r.status_code in (404, 410):
            return "closed"
        if r.status_code != 200:
            return "unknown"
        host = urlparse(link).netloc.lower()
        text = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", r.text or "")
        text = re.sub(r"<[^>]+>", " ", text)
        if any(h in host for h in APP_SITES):
            # pages built by code (Apple, Google, Eightfold, Oracle...): the address keeps working after a job is
            # taken down, so ask the site's own job reader whether the posting still has a title and description
            try:
                import extract
                d = extract.extract(link, None)
                if d.get("title") and len(d.get("description") or "") >= 200:
                    return "open"
            except Exception:
                pass
            return "closed" if CLOSED_TEXT.search(text[:200000]) else "unknown"
        if CLOSED_TEXT.search(text[:200000]):
            return "closed"
        # sent back to a search or home page: the job's own id is gone from the address
        ids = re.findall(r"\d{4,}", urlparse(link).path + "?" + urlparse(link).query)
        if ids and not any(i in r.url for i in ids) and re.search(r"search|jobs/?$|careers/?$|error", r.url, re.I):
            return "closed"
        return "open"
    except requests.RequestException:
        return "unknown"


def check_many(links: list) -> dict:
    """Several sites at once, one at a time per site."""
    by_host = {}
    for l in links:
        by_host.setdefault(urlparse(l).netloc.lower(), []).append(l)

    def work(item):
        out = {}
        for i, l in enumerate(item[1]):
            out[l] = check_open(l)
            if i < len(item[1]) - 1:
                time.sleep(1.0 if "eightfold" in item[0] else 0.4)
        return out

    res = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for part in ex.map(work, by_host.items()):
            res.update(part)
    return res


def due() -> bool:
    last = load_state().get("link_check")
    try:
        return (today() - __import__("datetime").date.fromisoformat(last)).days >= CHECK_EVERY_DAYS
    except Exception:
        return True


def expire_closed(tr, verbose=True) -> dict:
    """Check saved (not applied) jobs and undecided New Matches rows. Returns counts."""
    import sheets
    try:
        import watcher
        watcher.register_eightfold_domains(sheets.read_watchlist(tr.wb))
    except Exception:
        pass
    st = load_state()
    pending = st.setdefault("closing", {})  # link -> date of the first "closed" answer
    jobs = [j for j in tr.jobs if j.get("status") == "Saved" and j.get("applied") != "Yes" and j.get("link")]
    nm = [r for r in sheets.read_new_matches(tr.wb)]
    nm_open = [r for r in nm if not str(r.get("action") or "").strip() and isinstance(r.get("link"), str)]
    links = sorted({str(j["link"]) for j in jobs} | {r["link"] for r in nm_open})
    if verbose:
        print(f"\n  Checking whether {len(links)} saved job posting{'s are' if len(links) != 1 else ' is'} still open...",
              end="", flush=True)
    t0 = time.time()
    res = check_many(links)
    expired, first, dropped = [], 0, 0
    gone = set()
    for link, v in res.items():
        key = norm_url(link)
        if v == "closed":
            when = pending.get(key)
            if when and when < today().isoformat():
                gone.add(link)
                pending.pop(key, None)
            elif not when:
                pending[key] = today().isoformat()
                first += 1
        elif v == "open":
            pending.pop(key, None)  # back up, or a false alarm
    for j in jobs:
        if str(j["link"]) in gone:
            j["status"] = "Expired"
            j["last_update"] = today()
            j["next_action"] = None
            j["notes"] = (str(j.get("notes") or "") + f" [Expired {today():%m/%d/%y}: posting closed]").strip()
            expired.append(j)
    # a deadline alone never closes a job (many stay open until filled); it only adds a reminder
    late = 0
    for j in jobs:
        if str(j["link"]) in gone:
            continue
        dl = to_date(j.get("deadline"))
        if not dl or dl >= today():
            continue
        na = str(j.get("next_action") or "")
        if na and not na.startswith("Past deadline"):
            continue  # your own next step stays
        v = res.get(str(j["link"]))
        if v == "closed":
            msg = f"Past deadline ({dl:%m/%d}) and the posting looks closed - confirming next check"
        elif v == "open":
            msg = f"Past deadline ({dl:%m/%d}) but the posting is still up - apply soon or skip"
        else:
            msg = f"Past deadline ({dl:%m/%d}) - open the link to see if it's still taking applications"
        if na != msg:
            j["next_action"] = msg
            late += 1
    keep = [r for r in nm if r.get("link") not in gone or str(r.get("action") or "").strip()]
    dropped = len(nm) - len(keep)
    if dropped:
        sheets.write_new_matches(tr.wb, keep, n_new=0)
    st["link_check"] = today().isoformat()
    save_state(st)
    if verbose:
        unknown = sum(1 for v in res.values() if v == "unknown")
        print(f" done ({time.time() - t0:.0f}s)")
        print(f"  {len(expired)} saved job(s) expired, {dropped} New Matches row(s) removed; {first} more look closed "
              f"and will be confirmed next check; {unknown} couldn't be checked (left alone).")
        for j in expired:
            print(f"    expired: {str(j.get('company'))[:20]:20} {str(j.get('title'))[:50]}")
        if late:
            print(f"  {late} saved job(s) are past their posted deadline: see Next Action (they stay until the posting "
                  f"itself closes).")
    return {"expired": len(expired), "dropped": dropped, "pending": first, "late": late}
