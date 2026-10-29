"""Check Jobs: scans the companies on your Watchlist tab for NEW postings that match you.

How it works
  1. Each Watchlist row has a careers link. The watcher works out which hiring system the company uses
     (Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Eightfold, SuccessFactors, Phenom, iCIMS, Oracle, Paylocity, BambooHR, Rippling, Breezy, plus Apple, Google and Arup). If the link is a plain company page,
     it looks inside that page for a link to one of those systems.
  2. It reads the company's job list from that system's public job feed (the same data their careers
     site shows), searching for your watch keywords where the system supports search.
  3. It keeps postings that: have a watch keyword in the title, have none of your skip words, are in a
     location you'd consider (Home / your Areas / your Region / Remote), and are new since the last run.
  4. New ones go on the New Matches tab (newest first). At the end you can type numbers to add some to
     the tracker right away (the normal Add Job flow), or mark them Add / Dismiss in Excel for later.
No AI is used here, so a run is quick. Full scoring happens when you add a job.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import requests
from requests import ConnectionError as NetError, HTTPError, Timeout

import geo
from common import APP_DIR, Tracker, num, split_list, today, to_date
from scoring import _kw_rx, is_senior_title, keyword_score, title_has

STATE_PATH = APP_DIR / "watch_state.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/129.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
WORKDAY_PAGES = 3      # x 20 results per search term
SEARCH_TERMS_MAX = 12  # search terms used on systems that support search


def get(url, **kw):
    return requests.get(url, headers=H, timeout=25, **kw)


def hget(url, **kw):
    """A careers web page (HTML), asked for the way a browser asks."""
    return requests.get(url, headers={**H, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                        timeout=30, **kw)


# ------------------------------------------------------------------ dates
def _ts(v):
    try:
        v = float(v)
        return dt.date.fromtimestamp(v / 1000 if v > 1e11 else v)
    except (TypeError, ValueError):
        return None


def _iso(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def workday_posted(s):
    s = str(s or "").lower()
    if "today" in s:
        return today()
    if "yesterday" in s:
        return today() - dt.timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*days?", s)
    return today() - dt.timedelta(days=int(m.group(1))) if m else None


# ------------------------------------------------------------------ which system?
def detect(url: str):
    """Return (system, params) from a careers/job-board link, or (None, {})."""
    u = urlparse(url.strip())
    host, q = u.netloc.lower(), parse_qs(u.query)
    parts = [p for p in u.path.split("/") if p]
    if "myworkdayjobs.com" in host:
        site = [p for p in parts if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p) and p not in ("job", "jobs")]
        if site:
            return "Workday", {"host": u.netloc, "tenant": host.split(".")[0], "site": site[0]}
    if "greenhouse.io" in host:
        board = (q.get("for") or [None])[0] or (parts[0] if parts and parts[0] not in ("embed", "v1") else None)
        if board:
            return "Greenhouse", {"board": board}
    if "lever.co" in host and parts:
        return "Lever", {"company": parts[0], "eu": ".eu." in host}
    if "ashbyhq.com" in host and parts:
        return "Ashby", {"org": parts[0]}
    if "smartrecruiters.com" in host and parts:
        return "SmartRecruiters", {"company": parts[0]}
    if "eightfold.ai" in host:
        return "Eightfold", {"host": u.netloc, "domain": (q.get("domain") or [host.split(".")[0] + ".com"])[0]}
    if "myworkdaysite.com" in host and "recruiting" in parts:
        i = parts.index("recruiting")  # wd5.myworkdaysite.com/recruiting/<company>/<site>/...
        if len(parts) > i + 2:
            return "Workday", {"host": u.netloc, "tenant": parts[i + 1], "site": parts[i + 2], "mws": True}
    if host == "jobs.arup.com":
        # a list page (e.g. /page/americas-region-3, /latest-jobs) is read as given; anything else -> the Americas list
        # a list page is read as given (a saved search /jobs/search/123 is best: it has every result);
        # anything else -> the full latest-jobs list
        path = re.sub(r"/page\d+/?$", "", u.path.rstrip("/"))
        listing = path if re.match(r"/(jobs/search/\d+|page/|latest-jobs|landing-?pages)", path) else "/latest-jobs"
        return "Arup", {"path": listing}
    if host.endswith(".bamboohr.com"):
        return "BambooHR", {"sub": host.split(".")[0]}
    if host.endswith(".breezy.hr") and host.split(".")[0] not in ("www", "app", "help"):
        return "Breezy", {"sub": host.split(".")[0]}
    if host == "ats.rippling.com" and parts:
        return "Rippling", {"slug": parts[0]}
    if "paylocity.com" in host:
        m = re.search(r"/jobs/all/([0-9a-f-]{36})", u.path, re.I)
        if m:
            return "Paylocity", {"guid": m.group(1).lower()}
    if host.endswith(".icims.com"):
        return "iCIMS", {"host": u.netloc}
    m = re.search(r"(/(?:hcmUI/CandidateExperience/)?[a-z]{2}(?:-[A-Za-z]{2})?/sites)/(CX_\w+)", u.path)
    if m:
        return "Oracle", {"host": u.netloc, "site": m.group(2), "ui": m.group(1)}
    if host.endswith("jobs.apple.com"):
        return "Apple", {}
    if host in ("careers.google.com", "www.google.com", "google.com") and (host.startswith("careers") or "careers" in u.path):
        return "Google", {}
    return None, {}


EMBED = [
    (r"https?://[\w.-]+\.myworkdayjobs\.com/[^\s\"'<>\\]+", None),
    (r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=|v1/boards/)?([\w-]+)", "Greenhouse"),
    (r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)", "Lever"),
    (r"jobs\.ashbyhq\.com/([\w.%-]+)", "Ashby"),
    (r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", "SmartRecruiters"),
]


def discover(url: str):
    """A plain company careers page: find the hiring system it uses. Returns (system, params, note)."""
    u = urlparse(url)
    try:
        r = hget(url, allow_redirects=True)
        html = r.text or ""
    except Exception as e:
        return None, {}, f"couldn't open the page ({type(e).__name__})"
    sysname, params = detect(r.url or url)  # redirected straight to a job board?
    if sysname:
        return sysname, params, ""
    for rx, kind in EMBED:
        m = re.search(rx, html, re.I)
        if not m:
            continue
        if kind is None:
            sysname, params = detect(m.group(0))
        else:
            name = m.group(1)
            if name.lower() in ("embed", "v1", "jobs", "js"):
                continue
            key = {"Greenhouse": "board", "Lever": "company", "SmartRecruiters": "company", "Ashby": "org"}[kind]
            sysname, params = kind, {key: name}
        if sysname:
            return sysname, params, ""
    found = page_system(u, html)
    if found:
        return found[0], found[1], ""
    if "career4.successfactors.com" in u.netloc or "careers?company=" in url:
        return None, {}, ("this is SuccessFactors' old-style portal; look for the company's newer careers site "
                          "(open a job there, click Apply, and use that page's link)")
    # Eightfold career sites live on the company's own domain: probe their job feed
    domain = (parse_qs(u.query).get("domain") or [".".join(u.netloc.lower().split(".")[-2:])])[0]
    for params in ({"domain": domain, "num": 1}, {"domain": domain, "start": 0, "num": 1, "query": ""}):
        try:
            r = requests.get(f"https://{u.netloc}/api/apply/v2/jobs", params=params,
                             headers={**H, "Accept": "application/json"}, timeout=15)
            data = r.json() if r.status_code == 200 else {}
            if isinstance(data, dict) and ("positions" in data or "count" in data):
                return "Eightfold", {"host": u.netloc, "domain": domain}, ""
        except Exception:
            pass
    if re.search(r"eightfold", html, re.I) or re.search(r"/careers/job/\d+", url):
        return "Eightfold", {"host": u.netloc, "domain": domain}, ""
    return None, {}, "couldn't tell which hiring system this careers page uses"


def _sf_prefix(path):
    """jobs.teradyne.com/Teradyne/job/... -> '/Teradyne' (a SuccessFactors site with a brand folder)."""
    parts = [p for p in path.split("/") if p]
    for i, p in enumerate(parts):
        if p.lower() in ("job", "search", "go", "content", "viewalljobs"):
            return "".join("/" + x for x in parts[:i])
    return ""


def _phenom_loc(path):
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and re.fullmatch(r"[a-z]{2,6}", parts[0]) and re.fullmatch(r"[a-z]{2}(?:[_-][a-z]{2})?", parts[1]):
        return f"/{parts[0]}/{parts[1]}"
    if parts and re.fullmatch(r"[a-z]{2}(?:[_-][a-z]{2})?", parts[0]):
        return f"/{parts[0]}"
    return ""


def page_system(u, html):
    """Hiring systems recognized from a page's own code (company-branded career sites)."""
    m = re.search(r"/Recruiting/Jobs/All/([0-9a-fA-F-]{36})", html)
    if m:
        return "Paylocity", {"guid": m.group(1).lower()}
    if re.search(r"phApp\.ddo|phenompeople", html):
        return "Phenom", {"host": u.netloc, "loc": _phenom_loc(u.path)}
    if re.search(r"rmkcdn\.successfactors|jobTitle-link|careersite[_-]?sf|j2w\.|successfactors\.com/careers", html, re.I) \
            and "career4.successfactors.com" not in u.netloc:
        return "SuccessFactors", {"host": u.netloc, "prefix": _sf_prefix(u.path)}
    m = re.search(r"(/(?:hcmUI/CandidateExperience/)?[a-z]{2}(?:-[A-Za-z]{2})?/sites)/(CX_\w+)", html) \
        or re.search(r"siteNumber[\"'=:\s]+(CX_\w+)", html)
    if m:
        site = m.group(m.lastindex)
        ui = m.group(1) if m.lastindex == 2 else "/hcmUI/CandidateExperience/en/sites"
        return "Oracle", {"host": u.netloc, "site": site, "ui": ui}
    m = re.search(r"https?://([\w-]+\.icims\.com)", html)
    if m and not m.group(1).startswith(("www.", "cdn")):
        return "iCIMS", {"host": m.group(1)}
    m = re.search(r"https?://([\w-]+)\.bamboohr\.com", html)
    if m and m.group(1) not in ("www", "static", "resources"):
        return "BambooHR", {"sub": m.group(1)}
    m = re.search(r"ats\.rippling\.com/([\w-]+)", html)
    if m:
        return "Rippling", {"slug": m.group(1)}
    m = re.search(r"https?://([\w-]+)\.breezy\.hr", html)
    if m and m.group(1) not in ("www", "app", "help", "assets"):
        return "Breezy", {"sub": m.group(1)}
    return None


# ------------------------------------------------------------------ job feeds
def _p(id_, title, loc, link, posted, extra=None):
    d = {"id": str(id_), "title": (title or "").strip(), "location": (loc or "").strip(), "link": link, "posted": posted}
    d.update(extra or {})
    return d


class NotJobData(Exception):
    """The site answered with a web page (maintenance, sign-in or a block) instead of job data."""


def wd_post(p, url, body):
    """One Workday job-list request, asked for the way their own careers page asks. One retry."""
    site_url = (f"https://{p['host']}/recruiting/{p['tenant']}/{p['site']}" if p.get("mws")
                else f"https://{p['host']}/{p['site']}")
    hdr = {**H, "Accept": "application/json", "Content-Type": "application/json",
           "Origin": f"https://{p['host']}", "Referer": site_url}
    r = None
    for attempt in range(2):
        r = requests.post(url, json=body, headers=hdr, timeout=30)
        if r.status_code in (429, 503) and attempt == 0:
            time.sleep(6)
            continue
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            if attempt == 0:
                time.sleep(4)
    _save_debug("workday", r.text if r is not None else "")
    raise NotJobData("Workday sent a web page instead of job data")


def fetch_workday(p, terms):
    base = f"https://{p['host']}/wday/cxs/{p['tenant']}/{p['site']}"
    out, failed = {}, 0
    try:  # how many postings the whole board has (decides "small company" on a first scan)
        BOARD_SIZE["Workday"] = int(wd_post(p, f"{base}/jobs", {"appliedFacets": {}, "limit": 1, "offset": 0,
                                                                 "searchText": ""}).get("total") or 0) or None
    except NotJobData:
        raise
    except Exception:
        pass
    for term in terms or [""]:
        try:
            for page in range(WORKDAY_PAGES):
                data = wd_post(p, f"{base}/jobs", {"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": term})
                posts = data.get("jobPostings") or []
                for j in posts:
                    path = j.get("externalPath") or ""
                    if not path or path in out:
                        continue
                    link = (f"https://{p['host']}/recruiting/{p['tenant']}/{p['site']}{path}" if p.get("mws")
                            else f"https://{p['host']}/{p['site']}{path}")
                    out[path] = _p(path, j.get("title"), j.get("locationsText"), link,
                                   workday_posted(j.get("postedOn")), {"_wd_detail": f"{base}{path}"})
                if len(posts) < 20:
                    break
        except NotJobData:
            if not out:
                raise  # nothing read at all: report it
            failed += 1
            break  # keep what was read
    if failed:
        FETCH_NOTE["Workday"] = "(Workday stopped answering partway; some keyword searches skipped)"
    return list(out.values())


def workday_location(job):
    """'3 Locations' or an unclear place -> the real list from the posting's detail feed, with the country added
    when it isn't the US (e.g. 'Caesarea' -> 'Caesarea, Israel'). Only fetched for postings that match your titles."""
    try:
        r = requests.get(job["_wd_detail"], headers={**H, "Accept": "application/json"}, timeout=25)
        info = r.json().get("jobPostingInfo") or {}
        locs = [l for l in [info.get("location")] + list(info.get("additionalLocations") or []) if l]
        country = str((info.get("country") or {}).get("descriptor") or "")
        text = "; ".join(locs) or job["location"]
        if country and not re.search(r"united states|^usa?$", country, re.I) and country.lower() not in text.lower():
            text = f"{text}, {country}"
        return text
    except Exception:
        return job["location"]


def unclear_place(loc: str) -> bool:
    """A location the map can't place (e.g. 'Caesarea' or 'IL - Kfar Saba'): worth a closer look."""
    loc = str(loc or "").strip()
    if not loc or re.search(r"\bremote\b", loc, re.I) or geo.is_foreign("", loc):
        return False
    return not geo.locate(loc)


def fetch_greenhouse(p, terms):
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{p['board']}/jobs")
    r.raise_for_status()
    return [_p(j.get("id"), j.get("title"), (j.get("location") or {}).get("name"), j.get("absolute_url"),
               _iso(j.get("first_published") or j.get("updated_at"))) for j in r.json().get("jobs") or []]


def fetch_lever(p, terms):
    api = "api.eu.lever.co" if p.get("eu") else "api.lever.co"
    r = get(f"https://{api}/v0/postings/{p['company']}", params={"mode": "json"})
    r.raise_for_status()
    out = []
    for j in r.json() or []:
        cat = j.get("categories") or {}
        loc = cat.get("location") or ", ".join(cat.get("allLocations") or [])
        if str(j.get("workplaceType") or "").lower() == "remote":
            loc = (loc + " (Remote)").strip()
        out.append(_p(j.get("id"), j.get("text"), loc, j.get("hostedUrl"), _ts(j.get("createdAt"))))
    return out


def fetch_ashby(p, terms):
    r = get(f"https://api.ashbyhq.com/posting-api/job-board/{p['org']}")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs") or []:
        loc = j.get("location") or ""
        if j.get("isRemote") or str(j.get("workplaceType") or "").lower() == "remote":
            loc = (loc + " (Remote)").strip()
        out.append(_p(j.get("id"), j.get("title"), loc, j.get("jobUrl"), _iso(j.get("publishedAt"))))
    return out


US_ONLY = True  # set from Settings each run: False when you include "Outside US"


def fetch_smartrecruiters(p, terms):
    """Searches by your keywords (and US only) so big companies like AECOM aren't cut off at the first 1,000 postings."""
    out = {}

    def read(q, max_rows):
        offset = 0
        while offset < max_rows:
            params = {"limit": 100, "offset": offset}
            if q:
                params["q"] = q
            if US_ONLY:
                params["country"] = "us"
            r = get(f"https://api.smartrecruiters.com/v1/companies/{p['company']}/postings", params=params)
            r.raise_for_status()
            data = r.json()
            rows = data.get("content") or []
            for j in rows:
                loc = j.get("location") or {}
                text = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
                country = str(loc.get("country") or "")
                if country and country.lower() not in ("us", "usa"):
                    text = f"{text}, {country.upper()}"
                if loc.get("remote"):
                    text = (text + " (Remote)").strip()
                jid = str(j.get("id"))
                out[jid] = _p(jid, j.get("name"), text, f"https://jobs.smartrecruiters.com/{p['company']}/{jid}",
                              _iso(j.get("releasedDate") or ""))
            offset += 100
            if not rows or offset >= int(data.get("totalFound") or 0):
                break

    read("", 300)  # the newest postings of every kind
    for t in [t for t in terms if t]:
        read(t, 300)
        time.sleep(0.2)
    return list(out.values())


def fetch_eightfold(p, terms):
    out = {}
    for term in terms or [""]:
        r = requests.get(f"https://{p['host']}/api/apply/v2/jobs", headers=H, timeout=25,
                         params={"domain": p["domain"], "start": 0, "num": 100, "query": term})
        r.raise_for_status()
        data = r.json()
        if not term and data.get("count"):
            BOARD_SIZE["Eightfold"] = int(data["count"])
        for j in data.get("positions") or []:
            jid = str(j.get("id"))
            if jid in out:
                continue
            locs = j.get("locations") or ([j["location"]] if j.get("location") else [])
            out[jid] = _p(jid, j.get("name"), "; ".join(str(l).replace(", United States", "") for l in locs[:3]),
                          j.get("canonicalPositionUrl") or f"https://{p['host']}/careers/job/{jid}", _ts(j.get("t_create")))
    return list(out.values())


# ------------------------------------------------------------------ Apple / Google (their own search pages)
# Both sites put the search results inside the page itself. We read that data; if the layout ever changes,
# the page is saved to app/debug/ so it can be sent to Claude for a fix.
SITE_PAGES = 3        # x ~20 results per search term
DEBUG_DIR = APP_DIR / "debug"


WINDOW_DAYS = 14      # set from Settings at the start of a run
FETCH_NOTE = {}       # system -> note about a partial read
BOARD_SIZE = {}       # system -> total postings on the company's board, when the site says
_SESS = None


def site_get(url, params):
    """Apple/Google search page: a browser-style session, a generous wait and one retry."""
    global _SESS
    if _SESS is None:
        _SESS = requests.Session()
        _SESS.headers.update({**H, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    last = None
    for attempt in range(2):
        try:
            r = _SESS.get(url, params=params, timeout=(10, 45))
            if r.status_code in (429, 503) and attempt == 0:
                time.sleep(8)
                continue
            r.raise_for_status()
            return r
        except (Timeout, NetError) as e:
            last = e
            time.sleep(5)
    raise last or Timeout()


def _search_site(sysname, url, qkey, base_params, parser, terms):
    """Search each keyword (newest first), stopping a keyword once its results are older than your window.
    A keyword that times out is skipped; if two in a row fail, stop and keep what was read."""
    out, failed, streak = {}, [], 0
    for term in terms or [""]:
        try:
            for page in range(1, SITE_PAGES + 1):
                r = site_get(url, {**base_params, qkey: term, "page": page})
                posts = parser(r.text)
                if not posts and page == 1 and not out:
                    _save_debug(sysname.lower(), r.text)
                new = [j for j in posts if j["id"] not in out]
                out.update({j["id"]: j for j in new})
                dated = [j["posted"] for j in posts if j.get("posted")]
                if len(posts) < 15 or not new or (dated and (today() - min(dated)).days > WINDOW_DAYS):
                    break
                time.sleep(0.6)
            streak = 0
        except HTTPError:
            raise
        except Exception:
            failed.append(term or "(all)")
            streak += 1
            if streak >= 2:
                break
        time.sleep(0.6)
    if failed and not out:
        raise Timeout(f"{sysname} didn't answer")
    if failed:
        FETCH_NOTE[sysname] = f"(slow site: skipped {len(failed)} keyword search{'es' if len(failed) > 1 else ''})"
    return list(out.values())


def _save_debug(name, html):
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        (DEBUG_DIR / f"{DEBUG_TAG or name}.html").write_text(html)
    except Exception:
        pass


def _json_blobs(html):
    """JSON data embedded in a page: JSON.parse("...") strings and plain <script> JSON."""
    out = []
    for m in re.finditer(r'JSON\.parse\(\s*("(?:[^"\\]|\\.)*")\s*\)', html):
        try:
            out.append(json.loads(json.loads(m.group(1))))
        except Exception:
            pass
    for m in re.finditer(r"<script[^>]*>\s*(\{.*?\}|\[.*?\])\s*</script>", html, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except Exception:
            pass
    return out


def _walk(o):
    yield o
    if isinstance(o, dict):
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _text(h):
    import html as _html
    h = re.sub(r"<[^>]+>", " ", h or "")
    return re.sub(r"\s+", " ", _html.unescape(h)).strip()


def _slug_title(slug):
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip().title()


def _date_any(v):
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{10,13}", v)):
        return _ts(v)
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    if not v:
        return None
    d = _iso(v)
    if d:
        return d
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y"):
        try:
            return dt.datetime.strptime(v[:20].strip(" ,"), fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?\s+ago", v, re.I)
    if m:
        n = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2).lower()]
        return today() - dt.timedelta(days=n)
    if re.search(r"\btoday\b|just posted|hours? ago", v, re.I):
        return today()
    if re.search(r"\byesterday\b", v, re.I):
        return today() - dt.timedelta(days=1)
    m = re.search(r"[A-Z][a-z]{2,8} \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4}", v)
    return _date_any(m.group(0)) if m and m.group(0) != v else None


def parse_apple(html):
    jobs = {}
    for blob in _json_blobs(html):
        for o in _walk(blob):
            if isinstance(o, dict) and o.get("postingTitle") and (o.get("positionId") or o.get("id")):
                pid = str(o.get("positionId") or o.get("id"))
                locs = o.get("locations") or []
                names = [", ".join(x for x in ((l.get("city") or l.get("name")), l.get("stateProvince") or l.get("state")) if x)
                         for l in locs if isinstance(l, dict)]
                if locs and isinstance(locs[0], dict) and str(locs[0].get("countryName") or "").lower() \
                        not in ("", "united states", "united states of america", "usa"):
                    names = [f"{n}, {locs[0].get('countryName')}" for n in names if n]
                slug = o.get("transformedPostingTitle") or re.sub(r"[^a-z0-9]+", "-", o["postingTitle"].lower()).strip("-")
                loc = "; ".join(n for n in names if n)
                if o.get("homeOffice") or re.search(r"remote|home office", loc, re.I):
                    loc = (loc + " (Remote)").strip()
                jobs[pid] = _p(pid, o["postingTitle"], loc, f"https://jobs.apple.com/en-us/details/{pid}/{slug}",
                               _date_any(o.get("postDateInGMT") or o.get("postingDate")))
    if jobs:
        return list(jobs.values())
    # fallback: read the result links in the page
    for m in re.finditer(r'href="(?:https://jobs\.apple\.com)?(/[a-z]{2}-[a-z]{2}/details/([\w-]+)/([\w-]+))[^"]*"[^>]*>(.*?)</a>(.{0,1500})',
                         html, re.S):
        path, pid, slug, label, after = m.groups()
        if pid in jobs:
            continue
        title = _text(label) or _slug_title(slug)
        tail = _text(after)
        dm = re.search(r"[A-Z][a-z]{2} \d{1,2}, \d{4}", tail)
        lm = re.search(r"Location\s*:?\s*([A-Z][\w .'-]+(?:, [\w .'-]+)?)", tail)
        jobs[pid] = _p(pid, title, lm.group(1) if lm else "", f"https://jobs.apple.com{path}",
                       _date_any(dm.group(0)) if dm else None)
    return list(jobs.values())


def fetch_apple(p, terms):
    BOARD_SIZE["Apple"] = 10**5
    return _search_site("Apple", "https://jobs.apple.com/en-us/search", "search",
                        {"sort": "newest", "location": "united-states-USA"}, parse_apple, terms)


_GLOC = re.compile(r"^[A-Z][\w .'-]+, (?:[A-Z]{2}, )?(?:USA|[A-Z][a-z]+(?: [A-Z][a-z]+)*)$")


def _google_from_array(a):
    """One job from Google's embedded data: [id, title, apply url, ..., locations..., [seconds, nanos] ...]."""
    if not (isinstance(a, list) and len(a) > 3 and isinstance(a[0], str) and re.fullmatch(r"\d{12,22}", a[0])
            and isinstance(a[1], str) and 3 < len(a[1]) < 160):
        return None
    locs, posted = [], None
    for o in _walk(a[2:]):
        if isinstance(o, str) and _GLOC.match(o) and o not in locs and len(o) < 60:
            locs.append(o)
        elif isinstance(o, list) and len(o) == 2 and all(isinstance(x, int) for x in o) and 1.4e9 < o[0] < 2.2e9:
            posted = posted or _ts(o[0])
    slug = re.sub(r"[^a-z0-9]+", "-", a[1].lower()).strip("-")
    return _p(a[0], a[1], "; ".join(l.replace(", USA", "") for l in locs[:4]),
              f"https://www.google.com/about/careers/applications/jobs/results/{a[0]}-{slug}", posted)


def parse_google(html):
    jobs = {}
    for m in re.finditer(r"AF_initDataCallback\((\{.*?\})\);?\s*</script>", html, re.S):
        dm = re.search(r"data:(\[.*\])\s*,\s*sideChannel", m.group(1), re.S) or re.search(r"data:(\[.*\])", m.group(1), re.S)
        if not dm:
            continue
        try:
            data = json.loads(dm.group(1))
        except Exception:
            continue
        for o in _walk(data):
            j = _google_from_array(o)
            if j and j["id"] not in jobs:
                jobs[j["id"]] = j
    if jobs:
        return list(jobs.values())
    # fallback: the result links in the page
    for m in re.finditer(r'href="(?:\./|/about/careers/applications/|https://www\.google\.com/about/careers/applications/)?'
                         r'jobs/results/(\d{12,22})-([\w-]+)[^"]*"', html):
        jid, slug = m.groups()
        if jid in jobs:
            continue
        before = html[max(0, m.start() - 3000):m.start()]
        hs = re.findall(r"<h3[^>]*>(.*?)</h3>", before, re.S)
        title = _text(hs[-1]) if hs else _slug_title(slug)
        locs = [x for x in (_text(t) for t in re.findall(r"<span[^>]*>([^<]{4,60})</span>", before[-1500:])) if _GLOC.match(x)]
        jobs[jid] = _p(jid, title, "; ".join(l.replace(", USA", "") for l in dict.fromkeys(locs)),
                       f"https://www.google.com/about/careers/applications/jobs/results/{jid}-{slug}", None)
    return list(jobs.values())


def fetch_google(p, terms):
    BOARD_SIZE["Google"] = 10**5
    return _search_site("Google", "https://www.google.com/about/careers/applications/jobs/results/", "q",
                        {"location": "United States", "sort_by": "date"}, parse_google, terms)


# ------------------------------------------------------------------ more hiring systems
# These read the same public job lists the company's careers site shows. Each scan starts with one unfiltered
# page (the newest postings): if even that reads 0 jobs, the page is saved to app/debug/ for Claude.
def _json_after(html, marker_rx):
    """The JSON value right after a marker like 'phApp.ddo = '."""
    m = re.search(marker_rx, html or "")
    if not m:
        return None
    i = m.end()
    while i < len(html) and html[i] not in "{[":
        i += 1
    try:
        return json.JSONDecoder().raw_decode(html[i:])[0]
    except ValueError:
        return None


def _clean_loc(loc):
    """'Lakewood, CO, US, 80215' -> 'Lakewood, CO';  'US-MA-Boston' -> 'Boston, MA'."""
    loc = re.sub(r"\s+", " ", str(loc or "")).strip()
    m = re.fullmatch(r"(?:US|USA)-([A-Z]{2})-(.+)", loc)
    if m:
        return f"{m.group(2).strip()}, {m.group(1)}"
    parts = [x.strip() for x in loc.split(",") if x.strip()]
    keep = [x for x in parts if not re.fullmatch(r"\d{5}(-\d{4})?|US|USA|United States( of America)?", x, re.I)]
    return ", ".join(keep[:3]) if keep else loc


def _paged(sysname, terms, fetch_page, per_page, max_pages=4):
    """Shared paging loop for keyword-search sites (newest first where the site allows)."""
    out = {}
    for n, term in enumerate([""] + [t for t in terms if t]):
        for page in range(max_pages if term else 1):
            html, posts = fetch_page(term, page)
            if n == 0 and page == 0 and not posts:
                _save_debug(sysname.lower(), html)
                return []
            new = [j for j in posts if j["id"] not in out]
            out.update({j["id"]: j for j in new})
            dated = [j["posted"] for j in posts if j.get("posted")]
            if len(posts) < per_page * 0.8 or not new or (dated and (today() - min(dated)).days > WINDOW_DAYS):
                break
            time.sleep(0.3)
    return list(out.values())


def parse_successfactors(html, p):
    base = f"https://{p['host']}"
    m = re.search(r"Results?\s+(?:<[^>]+>\s*)*\d+\s*(?:<[^>]+>\s*)*[–-]\s*(?:<[^>]+>\s*)*\d+\s*(?:<[^>]+>\s*)*of\s*(?:<[^>]+>\s*)*([\d,]+)", html)
    if m:
        BOARD_SIZE.setdefault("SuccessFactors", int(m.group(1).replace(",", "")))
    jobs = {}
    rows = re.findall(r'<tr[^>]*class="[^"]*data-row[^"]*"[^>]*>(.*?)</tr>', html, re.S)
    chunks = rows or [html]
    for chunk in chunks:
        for m in re.finditer(r'<a[^>]+href="([^"]*/job/[^"]*?/(\d{5,})/?)"[^>]*>(.*?)</a>', chunk, re.S):
            href, jid, label = m.groups()
            title = _text(label)
            if not title or jid in jobs or len(title) > 150:
                continue
            tail = chunk[m.end():] if rows else chunk[m.end():m.end() + 2500]
            lm = re.search(r'class="[^"]*jobLocation[^"]*"[^>]*>(.*?)</span>', tail, re.S)
            dm = re.search(r'class="[^"]*jobDate[^"]*"[^>]*>(.*?)</span>', tail, re.S)
            jobs[jid] = _p(jid, title, _clean_loc(_text(lm.group(1))) if lm else "",
                           href if href.startswith("http") else base + href, _date_any(_text(dm.group(1))) if dm else None)
    return list(jobs.values())


def fetch_successfactors(p, terms):
    base = f"https://{p['host']}{p.get('prefix') or ''}"

    def page(term, n):
        r = hget(f"{base}/search/", params={"q": term, "sortColumn": "referencedate", "sortDirection": "desc",
                                           "startrow": n * 25})
        r.raise_for_status()
        return r.text, parse_successfactors(r.text, p)
    return _paged("SuccessFactors", terms, page, 25, max_pages=20)


def parse_phenom(html, p):
    data = _json_after(html, r"phApp\.ddo\s*=\s*")
    m = re.search(r'"totalHits"\s*:\s*(\d+)', html)
    if m:  # the first request of a scan is unfiltered, so the first count seen is the board size
        BOARD_SIZE.setdefault("Phenom", int(m.group(1)))
    jobs = {}
    for o in _walk(data or {}):
        if not (isinstance(o, dict) and isinstance(o.get("title"), str) and (o.get("jobId") or o.get("jobSeqNo"))
                and any(k in o for k in ("city", "location", "cityState", "cityStateCountry", "multi_location", "applyUrl"))):
            continue
        jid = str(o.get("jobId") or o.get("jobSeqNo"))
        if jid in jobs:
            continue
        loc = o.get("location") or o.get("cityStateCountry") or ", ".join(
            str(x) for x in (o.get("city"), o.get("state")) if x)
        if isinstance(loc, list):
            loc = "; ".join(str(x) for x in loc[:3])
        country = str(o.get("country") or "")
        if country and country.lower() not in ("united states", "united states of america", "usa", "us") \
                and country.lower() not in str(loc).lower():
            loc = f"{loc}, {country}"
        slug = re.sub(r"[^A-Za-z0-9]+", "-", o["title"]).strip("-")
        jobs[jid] = _p(jid, o["title"], _clean_loc(loc), f"https://{p['host']}{p.get('loc') or ''}/job/{jid}/{slug}",
                       _date_any(o.get("postedDate") or o.get("dateCreated") or o.get("postedOn")))
    return list(jobs.values())


def fetch_phenom(p, terms):
    def page(term, n):
        r = hget(f"https://{p['host']}{p.get('loc') or ''}/search-results",
                params={"keywords": term, "from": n * 10, "s": 1})
        r.raise_for_status()
        return r.text, parse_phenom(r.text, p)
    return _paged("Phenom", terms, page, 10, max_pages=5)


def parse_icims(html, p):
    jobs = {}
    for m in re.finditer(r'href="((?:https?://[^"/]+)?/jobs/(\d+)/([^/"?]+)/job)[^"]*"', html):
        href, jid, slug = m.groups()
        if jid in jobs:
            continue
        seg = html[m.start():m.start() + 3000]
        tm = re.search(r"<h[23][^>]*>(.*?)</h[23]>", seg, re.S)
        title = _text(tm.group(1)) if tm else _slug_title(requests.utils.unquote(slug))
        txt = _text(seg)
        lm = re.search(r"\b(?:US|USA)-([A-Z]{2})-([A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,2})", txt) \
            or re.search(r"Location\s*:?\s*([A-Z][\w .'-]+, [A-Z]{2})\b", txt)
        loc = (f"{lm.group(2)}, {lm.group(1)}" if lm and lm.lastindex == 2 else lm.group(1)) if lm else ""
        loc = re.sub(r"\s+(?:Posted|Category|ID|Type|Job|Date|Overview|Department)\b.*?(?=,|$)", "", loc)
        dm = re.search(r"Posted Date\s*:?\s*([^|]{4,24}?)(?:\s{2}|$|Category|Location|ID)", txt) \
            or re.search(r"\d{1,2}/\d{1,2}/\d{4}", txt)
        posted = _date_any(dm.group(1) if dm and dm.lastindex else (dm.group(0) if dm else ""))
        link = href if href.startswith("http") else f"https://{p['host']}{href}"
        jobs[jid] = _p(jid, title, loc, link, posted)
    return list(jobs.values())


def fetch_icims(p, terms):
    def page(term, n):
        r = hget(f"https://{p['host']}/jobs/search", params={"ss": 1, "searchKeyword": term, "in_iframe": 1, "pr": n})
        r.raise_for_status()
        return r.text, parse_icims(r.text, p)
    return _paged("iCIMS", terms, page, 15, max_pages=3)


def fetch_oracle(p, terms):
    host, site = p["host"], p["site"]
    ui = p.get("ui") or "/hcmUI/CandidateExperience/en/sites"

    def page(term, n):
        finder = f"findReqs;siteNumber={site},limit=25,offset={n * 25},sortBy=POSTING_DATES_DESC"
        if term:
            finder += f',keyword="{term}"'
        r = get(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                params={"onlyData": "true", "expand": "requisitionList.secondaryLocations", "finder": finder})
        r.raise_for_status()
        items = (r.json() or {}).get("items") or []
        reqs = (items[0].get("requisitionList") if items else None) or []
        if not term and items and items[0].get("TotalJobsCount"):
            BOARD_SIZE.setdefault("Oracle", int(items[0]["TotalJobsCount"]))
        posts = []
        for j in reqs:
            locs = [j.get("PrimaryLocation")] + [x.get("Name") for x in (j.get("secondaryLocations") or [])]
            posts.append(_p(j.get("Id"), j.get("Title"), "; ".join(_clean_loc(l) for l in locs[:3] if l),
                            f"https://{host}{ui}/{site}/job/{j.get('Id')}", _date_any(j.get("PostedDate"))))
        return r.text, posts
    return _paged("Oracle", terms, page, 25, max_pages=20)


def fetch_bamboohr(p, terms):
    r = get(f"https://{p['sub']}.bamboohr.com/careers/list")
    r.raise_for_status()
    out = []
    for j in (r.json() or {}).get("result") or []:
        loc = j.get("location") or j.get("atsLocation") or {}
        text = ", ".join(str(x) for x in (loc.get("city"), loc.get("state")) if x) if isinstance(loc, dict) else str(loc)
        if j.get("isRemote") or "remote" in str(j.get("locationType") or "").lower():
            text = (text + " (Remote)").strip()
        out.append(_p(j.get("id"), j.get("jobOpeningName"), text, f"https://{p['sub']}.bamboohr.com/careers/{j.get('id')}",
                      _date_any(j.get("datePosted"))))
    return out


def fetch_rippling(p, terms):
    slug, data = p["slug"], None
    try:
        r = get(f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs")
        if r.ok:
            data = r.json()
    except Exception:
        data = None
    if not data:
        r = hget(f"https://ats.rippling.com/{slug}/jobs")
        r.raise_for_status()
        data = _json_after(r.text, r'<script id="__NEXT_DATA__"[^>]*>')
        if not data:
            _save_debug("rippling", r.text)
    jobs = {}
    for o in _walk(data or {}):
        if not isinstance(o, dict):
            continue
        jid = o.get("uuid") or (o.get("id") if ("workLocation" in o or "locations" in o) else None)
        title = o.get("name") or o.get("title")
        if not jid or not isinstance(title, str) or str(jid) in jobs:
            continue
        wl = o.get("workLocation") or {}
        loc = wl.get("label") if isinstance(wl, dict) else str(wl or "")
        if not loc and isinstance(o.get("locations"), list):
            loc = "; ".join(str(x.get("name") if isinstance(x, dict) else x) for x in o["locations"][:3])
        link = o.get("url") if str(o.get("url") or "").startswith("http") else f"https://ats.rippling.com/{slug}/jobs/{jid}"
        jobs[str(jid)] = _p(jid, title, _clean_loc(loc), link, _date_any(o.get("createdOn") or o.get("postedDate")))
    return list(jobs.values())


ARUP_JOB = re.compile(r'href="((?:https://jobs\.arup\.com)?/jobs/([^"/?#]+)-(\d+))"[^>]*>(.*?)</a>', re.S)
ARUP_LOC = re.compile(r"([A-ZÀ-Ý][^,<>]{0,40}(?:,\s*[^,<>]{1,40}){1,2})")
ARUP_END = re.compile(r"\s*\(?\s*and\s+(\d+)\s+additional\s+locations?\s*\)?|\s+(?:Total\s+Views|Views|Apply|Save|Posted|Share)\b|\s{2}|\s*\d")
ARUP_CITY = {"new york": "New York, NY", "washington": "Washington, DC"}  # 'City, United States' names that are also states


ARUP_ROW = re.compile(r'id="job_list_(\d+)"(.*?)(?=id="job_list_\d+"|$)', re.S)


def arup_location(raw):
    """'Madrid, -, Spain' / 'New York, New York, United States and 2 additional locations' -> a place we can map."""
    text = re.sub(r"\s+", " ", _text(raw)).strip()
    m = re.search(r"\s*\(?\s*and\s+(\d+)\s+additional\s+locations?\s*\)?\s*$", text, re.I)
    more = m.group(1) if m else None
    if m:
        text = text[:m.start()]
    parts = [x.strip() for x in text.split(",") if x.strip() and x.strip() != "-"]
    loc = _clean_loc(", ".join(parts))
    return ARUP_CITY.get(loc.lower(), loc) + (f" (+{more} more)" if more else "")


def parse_arup(html):
    """Arup's list: one block per job (id="job_list_<id>") with the link and a 'location' field."""
    jobs = {}
    for jid, block in ARUP_ROW.findall(html):
        lm = re.search(r'<a[^>]+href="([^"]*/jobs/[^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not lm:
            continue
        title = _text(lm.group(2))
        loc = re.search(r'class="location"[^>]*>(.*?)</span>', block, re.S)
        href = lm.group(1)
        jobs[jid] = _p(jid, title, arup_location(loc.group(1)) if loc else "",
                       href if href.startswith("http") else "https://jobs.arup.com" + href, None)
    return list(jobs.values()) or parse_arup_text(html)


def parse_arup_text(html):
    """Fallback for other page layouts: one entry per job link; each job's location is read only from the text between its link and the next
    job's link, in either 'City, State, Country' or 'City, Country' form."""
    jobs = {}
    found = [m for m in ARUP_JOB.finditer(html)]
    for i, m in enumerate(found):
        href, slug, jid, label = m.groups()
        if jid in jobs:
            continue
        title = _text(label) or _slug_title(requests.utils.unquote(slug))
        if not title or len(title) > 160:
            continue
        nxt = next((f.start() for f in found[i + 1:] if f.group(3) != jid), len(html))
        seg = _text(html[m.end():min(nxt, m.end() + 3000)])
        loc, more = "", None
        lm = ARUP_LOC.search(seg)
        if lm:
            text = lm.group(1)
            e = ARUP_END.search(seg[lm.start():])
            if e and e.start() < len(text):
                text = seg[lm.start():lm.start() + e.start()]
            e2 = re.search(r"\(?\s*and\s+(\d+)\s+additional\s+locations?", seg[lm.start():lm.start() + len(text) + 60], re.I)
            more = e2.group(1) if e2 else None
            text = re.sub(r"\s+New$", "", text.strip())  # a 'New' badge right after the place
            parts = [x.strip() for x in text.split(",") if x.strip() and x.strip() != "-"]
            loc = _clean_loc(", ".join(parts))
            loc = ARUP_CITY.get(loc.lower(), loc) + (f" (+{more} more)" if more else "")
        jobs[jid] = _p(jid, title, loc, href if href.startswith("http") else "https://jobs.arup.com" + href, None)
    return list(jobs.values())


def fetch_arup(p, terms):
    """(The first page is kept as app/debug/arup-sample.html, in case Arup changes its page.)
    Arup's own job site (10 jobs per page, no posted dates shown). Reads page 1, 2, 3... of the list you put on
    the Watchlist (/jobs/search/<id> or /latest-jobs) until a page adds nothing new."""
    base = "https://jobs.arup.com" + (p.get("path") or "/latest-jobs")
    out, style = {}, None
    for n in range(1, 151):
        if n == 1:
            urls = [base]
        elif style:
            urls = [style.format(base=base, n=n)]
        else:
            urls = ["{base}/page{n}", "{base}?page={n}"]  # find out which page style this list uses
        new = []
        for pattern in urls:
            url = pattern.format(base=base, n=n) if "{" in pattern else pattern
            r = hget(url)
            if n > 1 and r.status_code >= 400:
                continue
            r.raise_for_status()
            posts = parse_arup(r.text)
            if n == 1:
                try:
                    DEBUG_DIR.mkdir(exist_ok=True)
                    (DEBUG_DIR / "arup-sample.html").write_text(r.text)
                except Exception:
                    pass
            if n == 1 and not posts:
                _save_debug("arup", r.text)
                return []
            new = [j for j in posts if j["id"] not in out]
            if new:
                if n == 2:
                    style = pattern
                break
        if not new:
            break
        out.update({j["id"]: j for j in new})
        time.sleep(0.3)
    return list(out.values())


def fetch_breezy(p, terms):
    """Breezy HR: every company board has a public JSON list at <company>.breezy.hr/json."""
    base = f"https://{p['sub']}.breezy.hr"
    jobs = {}
    data = None
    try:
        r = get(f"{base}/json")
        if r.ok:
            data = r.json()
    except Exception:
        data = None
    for j in data if isinstance(data, list) else []:
        loc = j.get("location") or {}
        if isinstance(loc, dict):
            st = loc.get("state") or {}
            text = loc.get("name") or ", ".join(str(x) for x in (loc.get("city"), st.get("id") if isinstance(st, dict) else st) if x)
            country = (loc.get("country") or {}).get("name") if isinstance(loc.get("country"), dict) else loc.get("country")
            if country and not re.search(r"united states|^us$|^usa$", str(country), re.I) and str(country) not in text:
                text = f"{text}, {country}"
            if loc.get("is_remote"):
                text = (text + " (Remote)").strip()
        else:
            text = str(loc)
        jid = str(j.get("id") or j.get("friendly_id"))
        link = j.get("url") or f"{base}/p/{j.get('friendly_id') or jid}"
        jobs[jid] = _p(jid, j.get("name"), _clean_loc(text), link, _date_any(j.get("published_date")))
    if not jobs:  # no JSON list: read the board page
        r = hget(base + "/")
        for m in re.finditer(r'<a[^>]+href="(/p/([\w-]+))"[^>]*>(.*?)</a>', r.text, re.S):
            href, fid, inner = m.groups()
            tm = re.search(r"<h2[^>]*>(.*?)</h2>", inner, re.S)
            title = _text(tm.group(1)) if tm else _text(inner)
            lm = re.search(r'class="[^"]*location[^"]*"[^>]*>(.*?)</li>', inner, re.S)
            if title and fid not in jobs:
                jobs[fid] = _p(fid, title, _clean_loc(_text(lm.group(1))) if lm else "", base + href, None)
        if not jobs:
            _save_debug("breezy", r.text)
    return list(jobs.values())


def fetch_paylocity(p, terms):
    r = hget(f"https://recruiting.paylocity.com/Recruiting/Jobs/All/{p['guid']}")
    r.raise_for_status()
    data = _json_after(r.text, r"window\.pageData\s*=\s*")
    jobs = {}
    for o in _walk(data or {}):
        if isinstance(o, dict) and o.get("JobId") and isinstance(o.get("JobTitle"), str):
            jl = o.get("JobLocation") or {}
            loc = o.get("LocationName") or (", ".join(str(x) for x in (jl.get("City"), jl.get("State")) if x)
                                            if isinstance(jl, dict) else "")
            if o.get("IsRemote"):
                loc = (str(loc) + " (Remote)").strip()
            jid = str(o["JobId"])
            jobs[jid] = _p(jid, o["JobTitle"], _clean_loc(loc), f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{jid}",
                           _date_any(o.get("PublishedDate") or o.get("CreatedDate")))
    if not jobs:  # older page layout: read the job links
        for m in re.finditer(r'href="[^"]*/Recruiting/Jobs/Details/(\d+)[^"]*"[^>]*>(.*?)</a>', r.text, re.S):
            jid, title = m.group(1), _text(m.group(2))
            if title and jid not in jobs:
                jobs[jid] = _p(jid, title, "", f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{jid}", None)
    if not jobs:
        _save_debug("paylocity", r.text)
    return list(jobs.values())


FETCH = {"Apple": fetch_apple, "Google": fetch_google, "Workday": fetch_workday, "Greenhouse": fetch_greenhouse, "Lever": fetch_lever, "Ashby": fetch_ashby,
         "SmartRecruiters": fetch_smartrecruiters, "Eightfold": fetch_eightfold,
         "SuccessFactors": fetch_successfactors, "Phenom": fetch_phenom, "iCIMS": fetch_icims, "Oracle": fetch_oracle,
         "BambooHR": fetch_bamboohr, "Rippling": fetch_rippling, "Paylocity": fetch_paylocity, "Breezy": fetch_breezy,
         "Arup": fetch_arup}


# ------------------------------------------------------------------ matching
def parse_keywords(v):
    """Watchlist 'Extra title keywords': added to your main list, or with 'only:' used instead of it."""
    txt = str(v or "").strip()
    only = bool(re.match(r"only\s*:", txt, re.I))
    if only:
        txt = re.sub(r"^only\s*:", "", txt, flags=re.I)
    return split_list(txt), only


def title_ok(title, s, extra_terms, only=False):
    terms = list(extra_terms) if (only and extra_terms) else split_list(s.get("watch_terms")) + list(extra_terms)
    if terms and not any(title_has(t, title) for t in terms):
        return False, "title"
    skip = split_list(s.get("watch_exclude")) + split_list(s.get("dealbreakers"))
    if any(_kw_rx(w).search(title) for w in skip):
        return False, "skip word"
    if str(s.get("watch_skip_senior") or "Yes").lower().startswith("y") and is_senior_title(title, s):
        return False, "senior"
    return True, ""


def matches(job, s, extra_terms, geo_cfg, only=False):
    """Return (ok, reason, area_label, area_type)."""
    ok, why = title_ok(job["title"], s, extra_terms, only)
    if not ok:
        return False, why, None, None
    loc = job["location"]
    allowed = {a.strip().lower() for a in split_list(s.get("watch_areas"))}
    if geo.is_foreign(job["title"], loc) and not any(c.get("state") in geo.CODES for c in geo.locate(loc)):
        return ("outside us" in allowed), "location", "Outside US", "Outside US"
    if re.search(r"\bremote\b", loc, re.I):
        return ("remote" in allowed), "location", "Remote", "Remote"
    if re.fullmatch(r"\d+ locations?", loc.strip(), re.I) or not loc.strip():
        return True, "", "? (several/unknown locations)", None  # don't miss it: check by hand
    res = geo.classify(loc, geo_cfg)
    at = res.get("area_type")
    if at is None:
        return True, "", res.get("area") or "?", None
    return (at.lower() in allowed), "location", res.get("area"), at


# ------------------------------------------------------------------ state
def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"seen": {}, "first_run_done": {}}


def save_state(st):
    cutoff = (today() - dt.timedelta(days=240)).isoformat()
    st["seen"] = {k: v for k, v in st["seen"].items() if v >= cutoff}
    STATE_PATH.write_text(json.dumps(st, indent=1))


# ------------------------------------------------------------------ run
MIN_WINDOW = 7
HTML_SYSTEMS = {"Apple", "Google", "SuccessFactors", "Phenom", "iCIMS", "Paylocity", "Oracle", "BambooHR", "Rippling",
                "Breezy", "Arup"}
DEBUG_TAG = None


def window_for(w, s):
    """(days to look back, gap note). First scan: the scan window. Later: days since last scan + 2, between 7 and it."""
    cap = int(num(s.get("watch_days"), 14))
    last = to_date(w.get("checked"))
    if not isinstance(last, dt.date):
        return cap, ""
    gap = max(0, (today() - last).days)
    if gap + 2 > cap:
        return cap, f" (gap: last scanned {gap} days ago, so postings older than {cap} days weren't checked)"
    return max(min(MIN_WINDOW, cap), gap + 2), ""


def is_active(w):
    return bool(w.get("url")) and str(w.get("active") or "Yes").lower().startswith("y")


def priority_report(wl, s):
    """{priority: count} plus warning lines for groups getting close to the scan window."""
    import sheets
    cap, warn = int(num(s.get("watch_days"), 14)), int(num(s.get("watch_warn"), 10))
    groups = {}
    for w in wl:
        if is_active(w):
            groups.setdefault(sheets.priority_of(w), []).append(w)
    lines = []
    for p in sorted(groups):
        dates = [to_date(w.get("checked")) for w in groups[p]]
        dates = [d for d in dates if isinstance(d, dt.date)]
        if not dates:
            continue
        days = (today() - min(dates)).days
        if days + 2 > cap:
            lines.append(f"  ! Priority {p} last scanned {days} days ago - longer than the {cap}-day scan window, so "
                         f"some postings in the gap will be missed. Scan it today.")
        elif days >= warn:
            lines.append(f"  ! Priority {p} last scanned {days} days ago - scan it within {cap - 2 - days} day(s) "
                         f"or older postings will be skipped.")
    return {p: len(v) for p, v in sorted(groups.items())}, lines


def area_name(loc, geo_cfg):
    """Which of your areas a posting is in: an Areas-tab name, Home, Region, Elsewhere, Outside US or Remote."""
    loc = str(loc or "")
    if re.search(r"\bremote\b", loc, re.I):
        return "Remote"
    if geo.is_foreign("", loc) and not any(c.get("state") in geo.CODES for c in geo.locate(loc)):
        return "Outside US"
    res = geo.classify(loc, geo_cfg)
    if not res.get("area_type"):
        return None
    name = str(res.get("area") or "").split(" · ")[0].strip()
    return name if name and name != "?" else None


def area_hit(area, name):
    """Does what you typed (e.g. 'LA', 'philly') name this area? Matches the start of a word: 'LA' fits
    'LA metro' but not 'Wallops Island'. Takes an area name, a match label or a 'Where they post' part."""
    name = re.sub(r"\s+\d+$", "", str(name or "").split(" · ")[0]).strip().lower()
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(area.strip().lower()), name))


def where_summary(posts, geo_cfg, top=4):
    """'Boston metro 12 · LA metro 5 · Elsewhere 30' from the postings read in a scan."""
    counts = {}
    for pj in posts:
        for part in re.split(r";\s*", str(pj.get("location") or "")):
            a = area_name(part, geo_cfg)
            if a:
                counts[a] = counts.get(a, 0) + 1
                break
    if not counts:
        return None
    # your own areas first (biggest first), then the catch-alls
    tail = ("Region", "Elsewhere", "Remote", "Outside US")
    mine = sorted(((n, c) for n, c in counts.items() if n not in tail), key=lambda x: -x[1])
    rest = [(n, counts[n]) for n in tail if n in counts]
    shown = mine[:top] + rest
    more = len(mine) - top
    return " · ".join(f"{n} {c}" for n, c in shown) + (f" · +{more} more areas" if more > 0 else "")


def run(tr, interactive=True, priorities=None, area=None):
    """Scan the Watchlist. priorities = a set like {1} or {1, 2}; None = every active company.
    area = part of an area name (e.g. 'boston'): only matches there are listed."""
    global WINDOW_DAYS, DEBUG_TAG
    import sheets
    s = tr.s
    wl = sheets.read_watchlist(tr.wb)
    nm = sheets.read_new_matches(tr.wb)
    st = load_state()
    st.setdefault("seen", {})
    st.setdefault("first_run_done", {})
    st.setdefault("co", {})
    if st.get("v") != 2:
        # Earlier versions remembered every posting they looked at, so jobs hidden by your old settings could never
        # come back. Keep only the ones you were actually shown (they're on the New Matches tab).
        shown = {r.get("key") for r in nm if r.get("key")}
        st["seen"] = {k: v for k, v in st["seen"].items() if k in shown}
        st["v"] = 2
    geo_cfg = tr.geo_cfg
    terms = [t.strip("\"“”'") for t in split_list(s.get("watch_terms"))[:SEARCH_TERMS_MAX]]
    quiet_days = int(num(s.get("watch_quiet"), 30))
    global US_ONLY
    US_ONLY = "outside us" not in {a.strip().lower() for a in split_list(s.get("watch_areas"))}
    FETCH_NOTE.clear()
    on_list = {r.get("key") for r in nm if r.get("key")}
    tracked = {str(j.get("link") or "").split("?")[0].lower() for j in tr.jobs if j.get("link")}
    norm = lambda x: re.sub(r"[^a-z0-9]+", "", str(x or "").lower())
    tracked_titles = [(norm(j.get("company")), norm(j.get("title"))) for j in tr.jobs if j.get("company") and j.get("title")]

    def already_tracked(company, title):
        """Same title at the same company already in your tracker (e.g. added from LinkedIn or a referral link)."""
        c, t = norm(company), norm(title)
        return any(t == tt and c and tc and (c in tc or tc in c) for tc, tt in tracked_titles)
    small = int(num(s.get("watch_small"), 60))
    found = []

    active = [w for w in wl if is_active(w) and (priorities is None or sheets.priority_of(w) in priorities)]
    if not [w for w in wl if is_active(w)]:
        print("  Your Watchlist tab has no active companies yet. Add a company and its careers link there.")
    elif not active:
        print(f"  No active companies with priority {', '.join(map(str, sorted(priorities or [])))}.")
    for w in active:
        if not re.match(r"https?://", w["url"], re.I):
            w["url"] = "https://" + w["url"].lstrip("/")  # e.g. jobs.arup.com/... typed without https://
        name = w.get("company") or w["url"]
        sysname, params = detect(w["url"])
        note = ""
        cached = None
        try:
            cached = json.loads(w.get("feed") or "null")
        except ValueError:
            pass
        if not sysname and cached and cached.get("url") == w["url"]:
            sysname, params = cached["system"], cached["params"]  # found on an earlier run
        if not sysname:
            print(f"  {name}: looking up which hiring system its careers page uses...")
            sysname, params, note = discover(w["url"])
            if sysname:
                w["feed"] = json.dumps({"url": w["url"], "system": sysname, "params": params})
        if not sysname:
            w["result"], w["system"] = f"Not supported: {note}. Open one of its jobs, click Apply, and try that page's link (see README > Supported job sites).", "?"
            print(f"  {name}: {w['result']}")
            continue
        w["system"] = sysname
        window, gap_note = window_for(w, s)
        WINDOW_DAYS = window
        DEBUG_TAG = f"{sysname.lower()}-{re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')}"
        extra, only = parse_keywords(w.get("keywords"))
        search = [t.strip("\"“”'") for t in extra] if (only and extra) else terms + [t.strip("\"“”'") for t in extra]
        t0 = time.time()
        BOARD_SIZE.clear()
        try:
            posts = FETCH[sysname](params, search)
        except Exception as e:
            if sysname in HTML_SYSTEMS and getattr(getattr(e, "response", None), "status_code", 0) in (403, 429):
                w["result"] = f"{sysname} blocked the check for now (too many requests?); try again later"
                print(f"  {name} ({sysname}): {w['result']}")
                continue
            if isinstance(e, Timeout):
                w["result"] = f"{sysname}'s site didn't answer in time; try again later"
            elif isinstance(e, NotJobData):
                w["result"] = (f"{sysname} sent a web page instead of job data (usually maintenance or a temporary "
                               f"block); try again in a few hours. If it keeps happening, report it with the file "
                               f"app/debug/{DEBUG_TAG}.html")
            else:
                w["result"] = f"Error reading the job feed ({type(e).__name__}); try again later"
            print(f"  {name} ({sysname}): {w['result']}")
            continue
        w["where"] = where_summary(posts, geo_cfg) or w.get("where")
        first_scan = not isinstance(to_date(w.get("checked")), dt.date)
        board = BOARD_SIZE.get(sysname) or len(posts)
        if first_scan and small and board <= small:
            window = None  # small company, first look: every matching job that's still open
            gap_note = " (first scan: small company, so every open matching job was checked, however old)"
        company_key = f"{sysname}:{json.dumps(params, sort_keys=True)}"
        co = st["co"].setdefault(company_key, {"first": today().isoformat(), "last_match": None})
        new = 0
        if not posts and sysname in HTML_SYSTEMS:
            dbg = DEBUG_DIR / f"{DEBUG_TAG}.html"
            w["result"] = (f"0 postings read: the page may not be in the expected format. Report it (README > Contributing) with the file "
                           f"app/debug/{dbg.name}" if dbg.exists() else "0 postings read (no open jobs, or the page "
                           "format changed)")
            print(f"  {name} ({sysname}): {w['result']}")
            continue
        for pj in posts:
            key = f"{company_key}|{pj['id']}"
            if key in st["seen"] or key in on_list:
                continue  # already shown to you once
            if pj["link"] and pj["link"].split("?")[0].lower() in tracked:
                continue
            if already_tracked(name, pj["title"]):
                continue
            if window is not None and pj.get("posted") and (today() - pj["posted"]).days > window:
                continue  # older than this scan's window: not "new"
            if sysname == "Workday" and (re.fullmatch(r"\d+ locations?", pj["location"].strip(), re.I)
                                         or unclear_place(pj["location"])) and title_ok(pj["title"], s, extra, only)[0]:
                pj["location"] = workday_location(pj)  # "3 Locations" / "Caesarea" -> the actual places + country
            ok, why, label, at = matches(pj, s, extra, geo_cfg, only)
            if not ok:
                continue  # not remembered: re-checked next time, so changing your settings brings it back
            if area and not any(area_hit(a, str(label or "").split(" · ")[0]) for a in split_list(area)):
                continue  # outside the area you asked for this time: not remembered, so a normal scan still shows it
            st["seen"][key] = today().isoformat()
            fit_title, _, _ = keyword_score(pj["title"], "", split_list(s.get("fit_keywords")))
            found.append({"found": today(), "company": name, "title": pj["title"], "location": pj["location"],
                          "area": label, "posted": pj.get("posted"), "quick": round(fit_title or 0, 1),
                          "link": pj["link"], "action": None, "source": sysname, "key": key})
            new += 1
        if new:
            co["last_match"] = today().isoformat()
        st["first_run_done"][company_key] = today().isoformat()
        w["checked"] = today()
        w["result"] = (f"{len(posts)} postings scanned, {new} new match{'es' if new != 1 else ''}"
                       + (f" {FETCH_NOTE[sysname]}" if sysname in FETCH_NOTE else "") + gap_note)
        first, last = _iso(co.get("first") or ""), _iso(co.get("last_match") or "")
        if quiet_days and isinstance(first, dt.date) and (today() - first).days >= quiet_days and \
                not (isinstance(last, dt.date) and (today() - last).days < quiet_days):
            w["result"] += f" · quiet: no new matches in {quiet_days}+ days (consider Active = No)"
        print(f"  {name} ({sysname}): {w['result']}  [{time.time() - t0:.0f}s]")

    # newest first: today's finds on top, sorted by posted date then quick score
    found.sort(key=lambda r: (-(r["posted"] or dt.date(2000, 1, 1)).toordinal(), -r["quick"]))
    keep_days = 30
    old = [r for r in nm if r.get("found") and (today() - to_date(r["found"])).days <= keep_days
           and str(r.get("action") or "").lower() not in ("dismiss", "dismissed")]
    rows = found + old
    sheets.write_watchlist(tr.wb, wl)
    sheets.write_new_matches(tr.wb, rows, n_new=len(found))
    save_state(st)
    return found


def add_marked(tr, ai):
    """Add the New Matches rows you marked 'Add' in Excel (or chose at the prompt)."""
    import add_job
    import sheets
    rows = sheets.read_new_matches(tr.wb)
    todo = [r for r in rows if str(r.get("action") or "").strip().lower() == "add" and r.get("link")]
    for r in todo:
        print(f"\n  Adding: {r['company']} - {r['title']}")
        # the watcher read the title/location from the company's own job list: reuse them
        add_job.add_one(tr, ai, r["link"], hint={"title": r.get("title"), "location": r.get("location"),
                                                  "company": r.get("company"), "source": r.get("source"),
                                                  "posted": to_date(r.get("posted"))})
        r["action"] = "Added"
    if todo:
        sheets.write_new_matches(tr.wb, rows, n_new=0)
        tr.save()
    return len(todo)


def scan(tr, ai, priorities=None, area=None):
    found = run(tr, priorities=priorities, area=area)
    tr.save()
    print("\n  " + "-" * 50)
    if not found:
        print("  No new matching jobs since the last check.")
        return
    print(f"  {len(found)} new matching job(s) (also on the New Matches tab):\n")
    for i, r in enumerate(found[:40], 1):
        if r.get("posted"):
            ago = (today() - r["posted"]).days
            posted = f"posted {r['posted']:%b %d} ({'today' if ago <= 0 else f'{ago}d ago'})"
        else:
            posted = "posted ?"
        print(f"  {i:>2}. {r['company'][:18]:18} {r['title'][:46]:46} {str(r['area'] or r['location'])[:26]:26} {posted}")
    if len(found) > 40:
        print(f"  ...and {len(found) - 40} more on the New Matches tab.")
    try:
        ans = input("\n  Type numbers to add now (e.g. 1 3 4), or press Enter to finish\n"
                    "  (or mark Action = Add in Excel and choose 'a' next time): ").strip()
    except EOFError:
        ans = ""
    picks = [int(x) for x in re.findall(r"\d+", ans) if 1 <= int(x) <= min(40, len(found))]
    if not picks:
        return
    import sheets
    from common import AI
    rows = sheets.read_new_matches(tr.wb)
    keys = {found[i - 1]["key"] for i in picks}
    for r in rows:
        if r.get("key") in keys:
            r["action"] = "Add"
    sheets.write_new_matches(tr.wb, rows, n_new=len(found))
    ai = ai or AI(tr.s)
    print(f"  AI helper: {'on (' + ai.model + ')' if ai.enabled else 'off - ' + ai.reason}")
    add_marked(tr, ai)


def main():
    import sheets
    from common import AI
    from common import APP_VERSION
    print("=" * 60 + f"\n  CHECK JOBS (Watchlist)          Job Tracker update {APP_VERSION}\n" + "=" * 60)
    tr = Tracker()
    marked = [r for r in sheets.read_new_matches(tr.wb) if str(r.get("action") or "").strip().lower() == "add"]
    print("  s = scan for new jobs (quick, no AI)")
    print(f"  a = add the {len(marked)} job(s) marked 'Add' on New Matches (slower: reads each posting with the AI)"
          if marked else "  a = add jobs marked 'Add' on New Matches (none marked right now)")
    print("  b = both: add marked jobs, then scan")
    try:
        choice = (input("  Choose (Enter = s): ").strip().lower() or "s")[:1]
    except EOFError:
        choice = "s"
    ai = None
    if choice in ("a", "b"):
        if not marked:
            print("  No rows on New Matches have Action = Add." + ("" if choice == "b" else ""))
        else:
            ai = AI(tr.s)
            print(f"  AI helper: {'on (' + ai.model + ')' if ai.enabled else 'off - ' + ai.reason}")
            add_marked(tr, ai)
            print(f"\n  Added {len(marked)} job(s).")
        if choice == "a":
            return
    if choice not in ("s", "b"):
        print("  Not a choice; scanning.")
    pr = ask_priorities(tr)
    scan(tr, ai, pr, ask_area(tr))


def ask_area(tr):
    """Optional: just one area this time (e.g. 'Boston'). Enter = all your usual locations."""
    import sheets
    names = [a.get("name") for a in (tr.geo_cfg.get("areas") or []) if a.get("name")]
    hint = ", ".join(n for n in names[:6]) + (" ..." if len(names) > 6 else "")
    try:
        ans = input(f"  Just some areas this time? Enter = all your locations, or type part of a name (several: use commas)"
                    + (f"\n  ({hint}, Remote): " if hint else ": ")).strip()
    except EOFError:
        ans = ""
    return ans or None


def ask_priorities(tr):
    import sheets
    counts, warnings = priority_report(sheets.read_watchlist(tr.wb), tr.s)
    for line in warnings:
        print(line)
    if len(counts) <= 1:
        return None  # everything is one priority: scan it all
    print("  Priorities on your Watchlist: " + " · ".join(f"{p} ({n} compan{'ies' if n != 1 else 'y'})"
                                                          for p, n in counts.items()))
    try:
        ans = input("  Scan which priority? Enter = 1, or type e.g. 2  /  1 2  /  a = all: ").strip().lower()
    except EOFError:
        ans = ""
    if ans.startswith("a"):
        return None
    picks = {int(x) for x in re.findall(r"\d+", ans)} or {1}
    return picks


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        sys.exit(0)
