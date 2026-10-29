"""Reads a job posting from a link (or pasted text) and returns structured fields."""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from common import AI, detect_mode, parse_pay

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}

FIELDS = ["company", "title", "location", "work_mode", "pay_min", "pay_max", "pay_unit",
          "emp_type", "posted", "description", "source"]


class Blocked(Exception):
    pass


def html_to_text(h: str) -> str:
    if not h:
        return ""
    soup = BeautifulSoup(h, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
    for blk in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "tr", "section"]):
        blk.insert_after("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)
    return "\n".join(l.strip() for l in text.splitlines()).strip()


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=20, **kw)
    return r


def _date(v):
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def site_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for key, name in [("greenhouse", "Greenhouse"), ("lever.co", "Lever"), ("myworkdayjobs", "Workday"),
                      ("linkedin", "LinkedIn"), ("indeed", "Indeed"), ("ashbyhq", "Ashby"),
                      ("smartrecruiters", "SmartRecruiters"), ("glassdoor", "Glassdoor"),
                      ("ziprecruiter", "ZipRecruiter"), ("joinhandshake", "Handshake"),
                      ("icims", "iCIMS"), ("jobvite", "Jobvite"), ("bamboohr", "BambooHR"),
                      ("wellfound", "Wellfound"), ("usajobs", "USAJOBS"), ("dice.com", "Dice"),
                      ("monster", "Monster"), ("builtin", "Built In"), ("taleo", "Taleo"),
                      ("successfactors", "SuccessFactors"), ("paylocity", "Paylocity"),
                      ("adp.com", "ADP"), ("rippling", "Rippling"), ("workable", "Workable")]:
        if key in host:
            return name
    return host.replace("www.", "")


def relative_date(s: str):
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", s or "", re.I)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2).lower()
    days = {"minute": 0, "hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[u]
    return dt.date.today() - dt.timedelta(days=days)


# ------------------------------------------------------------------ site APIs
def from_greenhouse(url):
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url)
    q = parse_qs(urlparse(url).query)
    if not m:
        if "for" in q and "token" in q:
            board, jid = q["for"][0], q["token"][0]
        elif "gh_jid" in q:
            # Company career site powered by Greenhouse: guess the board from the domain name.
            labels = [l for l in urlparse(url).netloc.lower().split(".")
                      if l not in ("www", "careers", "jobs", "job", "com", "io", "co", "org", "net", "ai")]
            if not labels:
                return None
            board, jid = labels[-1], q["gh_jid"][0]
        else:
            return None
    else:
        board, jid = m.group(1), m.group(2)
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}?pay_transparency=true")
    if r.status_code != 200:
        return None
    j = r.json()
    desc = html_to_text(htmllib.unescape(j.get("content") or ""))
    d = {"title": j.get("title"), "company": j.get("company_name") or board.replace("-", " ").title(),
         "location": (j.get("location") or {}).get("name"), "description": desc,
         "posted": _date(j.get("first_published") or j.get("updated_at")),
         "deadline": _date(j.get("application_deadline"))}
    ranges = j.get("pay_input_ranges") or []
    if ranges:
        p = ranges[0]
        lo, hi = p.get("min_cents"), p.get("max_cents")
        if lo:
            d["pay_min"], d["pay_max"] = lo / 100, (hi or lo) / 100
            d["pay_unit"] = "Hour" if d["pay_min"] < 300 else "Year"
    return d


def from_lever(url):
    m = re.search(r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    api = "api.eu.lever.co" if ".eu." in url else "api.lever.co"
    r = get(f"https://{api}/v0/postings/{m.group(1)}/{m.group(2)}")
    if r.status_code != 200:
        return None
    j = r.json()
    cat = j.get("categories") or {}
    parts = [j.get("descriptionPlain") or ""]
    for lst in j.get("lists") or []:
        parts.append(lst.get("text", ""))
        parts.append(html_to_text(lst.get("content", "")))
    parts.append(j.get("additionalPlain") or "")
    d = {"title": j.get("text"), "company": m.group(1).replace("-", " ").title(),
         "location": cat.get("location") or ", ".join(cat.get("allLocations") or []),
         "emp_type": cat.get("commitment"), "description": "\n".join(p for p in parts if p).strip()}
    wt = (j.get("workplaceType") or "").lower()
    d["work_mode"] = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}.get(wt, "")
    sr = j.get("salaryRange") or {}
    if sr.get("min"):
        d["pay_min"], d["pay_max"] = sr["min"], sr.get("max") or sr["min"]
        d["pay_unit"] = "Hour" if "hour" in str(sr.get("interval", "")).lower() else "Year"
    if j.get("createdAt"):
        d["posted"] = dt.date.fromtimestamp(j["createdAt"] / 1000)
    # Lever doesn't return the company's display name; try the page title.
    try:
        page = get(url)
        t = BeautifulSoup(page.text, "html.parser").find("meta", property="og:title")
        if t and " - " in (t.get("content") or ""):
            d["company"] = t["content"].split(" - ")[0].strip()
    except Exception:
        pass
    return d


def from_workday(url):
    u = urlparse(url)
    parts = [p for p in u.path.split("/") if p]
    if "myworkdaysite.com" in u.netloc and "recruiting" in parts:  # wd5.myworkdaysite.com/recruiting/<co>/<site>/job/...
        k = parts.index("recruiting")
        if len(parts) <= k + 2:
            return None
        tenant = parts[k + 1]
        parts = parts[k + 2:]
    elif "myworkdayjobs.com" in u.netloc:
        tenant = u.netloc.split(".")[0]
    else:
        return None
    if "job" not in parts:
        return None
    i = parts.index("job")
    site_parts = [p for p in parts[:i] if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p)]
    if not site_parts:
        return None
    site = site_parts[-1]
    rest = "/".join(parts[i + 1:])
    r = requests.get(f"https://{u.netloc}/wday/cxs/{tenant}/{site}/job/{rest}",
                     headers={**HEADERS, "Accept": "application/json"}, timeout=20)
    if r.status_code != 200:
        return None
    j = r.json()
    info = j.get("jobPostingInfo") or {}
    d = {"title": info.get("title"), "location": info.get("location"),
         "company": (j.get("hiringOrganization") or {}).get("name") or tenant.title(),
         "description": html_to_text(info.get("jobDescription") or ""),
         "emp_type": info.get("timeType"),
         "posted": _date(info.get("startDate")) or relative_date(str(info.get("postedOn") or "").replace("Posted ", "")),
         "deadline": _date(info.get("endDate"))}
    extra = info.get("additionalLocations") or []
    if extra:
        d["location"] = f"{d['location']} (+{len(extra)} more)"
    rt = str(info.get("remoteType") or "").lower()
    if "remote" in rt:
        d["work_mode"] = "Remote"
    elif "hybrid" in rt:
        d["work_mode"] = "Hybrid"
    return d


def from_ashby(url):
    m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    org, jid = m.group(1), m.group(2)
    r = get(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true")
    if r.status_code != 200:
        return None
    for j in r.json().get("jobs", []):
        if j.get("id") == jid:
            d = {"title": j.get("title"), "company": org.replace("-", " ").title(),
                 "location": j.get("location"), "emp_type": j.get("employmentType"),
                 "description": j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
                 "posted": _date(j.get("publishedAt"))}
            wt = str(j.get("workplaceType") or "").lower()
            d["work_mode"] = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}.get(wt, "")
            if j.get("isRemote") and not d["work_mode"]:
                d["work_mode"] = "Remote"
            comp = (j.get("compensation") or {}).get("compensationTierSummary")
            if comp:
                d["_pay_text"] = comp
            return d
    return None


def from_smartrecruiters(url):
    m = re.search(r"smartrecruiters\.com/([\w-]+)/(\d+)", url)
    if not m:
        return None
    r = get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
    if r.status_code != 200:
        return None
    j = r.json()
    loc = j.get("location") or {}
    secs = (j.get("jobAd") or {}).get("sections") or {}
    desc = "\n\n".join(html_to_text((secs.get(k) or {}).get("text", ""))
                       for k in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
    d = {"title": j.get("name"), "company": (j.get("company") or {}).get("name"),
         "location": ", ".join(x for x in [loc.get("city"), loc.get("region")] if x),
         "description": desc.strip(), "emp_type": (j.get("typeOfEmployment") or {}).get("label"),
         "posted": _date(j.get("releasedDate"))}
    if loc.get("remote"):
        d["work_mode"] = "Remote"
    elif loc.get("hybrid"):
        d["work_mode"] = "Hybrid"
    return d


def from_linkedin(url):
    m = re.search(r"(?:currentJobId=|/jobs/view/(?:[^/?]*?-)?)(\d{7,})", url)
    if "linkedin.com" not in url or not m:
        return None
    r = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}")
    if r.status_code != 200 or len(r.text) < 500:
        raise Blocked("LinkedIn didn't share this posting")
    s = BeautifulSoup(r.text, "html.parser")

    def txt(sel):
        el = s.select_one(sel)
        return el.get_text(" ", strip=True) if el else None

    d = {"title": txt("h2.top-card-layout__title") or txt("h1"),
         "company": txt("a.topcard__org-name-link") or txt(".topcard__flavor"),
         "location": txt("span.topcard__flavor--bullet"),
         "description": html_to_text(str(s.select_one("div.show-more-less-html__markup") or "")),
         "_pay_text": txt("div.salary") or txt(".compensation__salary"),
         "posted": relative_date(txt("span.posted-time-ago__text") or txt(".posted-time-ago__text") or "")}
    for li in s.select("li.description__job-criteria-item"):
        h, v = li.select_one("h3"), li.select_one("span")
        if h and v and "employment type" in h.get_text().lower():
            d["emp_type"] = v.get_text(strip=True)
    d["_canonical"] = f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    return d


def from_eightfold(url):
    """Career sites powered by Eightfold (e.g. apply.omnicell.com/careers/job/123, *.eightfold.ai)."""
    u = urlparse(url)
    q = parse_qs(u.query)
    m = re.search(r"/careers/job/(\d+)", u.path)
    pid = m.group(1) if m else (q.get("pid") or [None])[0]
    if not pid or not (m or "/careers" in u.path):
        return None
    host = u.netloc
    if "eightfold.ai" in host:
        domain = (q.get("domain") or [host.split(".")[0] + ".com"])[0]
    else:
        domain = (q.get("domain") or [".".join(host.split(".")[-2:])])[0]
    r = requests.get(f"https://{host}/api/apply/v2/jobs/{pid}", params={"domain": domain},
                     headers={**HEADERS, "Accept": "application/json"}, timeout=20)
    if r.status_code != 200 or "json" not in r.headers.get("content-type", "json"):
        return None
    j = r.json()
    if not j.get("name"):
        return None
    locs = [str(x).replace(", United States", "") for x in (j.get("locations") or ([j["location"]] if j.get("location") else []))]
    d = {"title": j.get("name") or j.get("posting_name"), "company": domain.split(".")[0].replace("-", " ").title(),
         "location": "; ".join(locs[:3]) + (f" (+{len(locs) - 3} more)" if len(locs) > 3 else ""),
         "description": html_to_text(j.get("job_description") or ""), "source": "Eightfold"}
    wl = str(j.get("work_location_option") or j.get("location_flexibility") or "").lower()
    if "remote" in wl:
        d["work_mode"] = "Remote"
    elif "hybrid" in wl:
        d["work_mode"] = "Hybrid"
    elif "onsite" in wl or "on-site" in wl or "office" in wl:
        d["work_mode"] = "On-site"
    return d


ATS_HOSTS = ("greenhouse", "lever.co", "myworkdayjobs", "workday", "linkedin", "indeed", "ashbyhq", "smartrecruiters",
             "glassdoor", "ziprecruiter", "joinhandshake", "icims", "jobvite", "bamboohr", "wellfound", "usajobs", "dice.com",
             "monster", "builtin", "taleo", "successfactors", "paylocity", "adp.com", "rippling", "workable", "eightfold",
             "oraclecloud", "ultipro", "applytojob", "bamboohr", "rippling", "myworkdaysite", "phenompeople", "breezy", "recruitee", "jazzhr", "teamtailor", "simplyhired", "google.com")


def from_bamboohr(url):
    u = urlparse(url)
    m = re.search(r"/careers/(\d+)", u.path)
    if not u.netloc.endswith(".bamboohr.com") or not m:
        return None
    r = requests.get(f"https://{u.netloc}/careers/{m.group(1)}/detail", headers={**HEADERS, "Accept": "application/json"},
                     timeout=20)
    if r.status_code != 200:
        return None
    j = ((r.json() or {}).get("result") or {}).get("jobOpening") or {}
    if not j.get("jobOpeningName"):
        return None
    loc = j.get("location") or j.get("atsLocation") or {}
    d = {"title": j["jobOpeningName"], "description": html_to_text(j.get("description") or ""), "source": "BambooHR",
         "location": ", ".join(str(x) for x in (loc.get("city"), loc.get("state")) if x) if isinstance(loc, dict) else None,
         "posted": _date(j.get("datePosted")), "emp_type": j.get("employmentStatusLabel")}
    if j.get("compensation"):
        d["_pay_text"] = str(j["compensation"])
    if j.get("isRemote") or "remote" in str(j.get("locationType") or "").lower():
        d["work_mode"] = "Remote"
    return d


def from_oracle(url):
    """Oracle Recruiting Cloud: .../sites/CX_1/job/12345"""
    u = urlparse(url)
    m = re.search(r"/sites/(CX_\w+)/job/(\d+)", u.path)
    if not m:
        return None
    site, jid = m.groups()
    r = requests.get(f"https://{u.netloc}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
                     params={"expand": "all", "onlyData": "true", "finder": f'ById;Id="{jid}",siteNumber={site}'},
                     headers={**HEADERS, "Accept": "application/json"}, timeout=20)
    if r.status_code != 200:
        return None
    items = (r.json() or {}).get("items") or []
    if not items:
        return None
    j = items[0]
    desc = "\n\n".join(html_to_text(j.get(k) or "") for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                                                               "ExternalQualificationsStr", "CorporateDescriptionStr")
                        if j.get(k))
    return {"title": j.get("Title"), "location": j.get("PrimaryLocation"), "description": desc, "source": "Oracle",
            "posted": _date(j.get("ExternalPostedStartDate")), "deadline": _date(j.get("ExternalPostedEndDate"))}


def company_from_url(url) -> str | None:
    """apply.omnicell.com -> Omnicell. Not for job boards / hiring systems."""
    u = urlparse(url or "")
    host = u.netloc.lower()
    if host.endswith("google.com") and "/careers" in u.path:
        return "Google"
    if not host or any(a in host for a in ATS_HOSTS):
        return None
    parts = [p for p in host.split(".") if p not in ("www", "careers", "career", "jobs", "job", "apply", "boards",
                                                    "recruiting", "talent", "work", "hire", "join", "search")]
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return None


_NAME = r"([A-Z][\w&.'’-]*(?:\s(?:&\s)?[A-Z][\w&.'’-]*){0,3})"
COMPANY_CLUES = [
    r"\bAt " + _NAME + r",?\s(?:we|we’re|we're|our|you|success|every)\b",
    r"\bWhy (?:join|work at|work for|choose) " + _NAME + r"\??",
    r"(?m)^\s*About " + _NAME + r"\s*$",
    r"\b" + _NAME + r" is an? (?:equal opportunity|equal employment|EEO|e-verify|proud equal)",
    r"\bJoin " + _NAME + r"(?:’s|'s)? (?:team|today|and|as)\b",
    r"\b" + _NAME + r" logo\b",
    r"©\s*(?:20\d\d\s*)?" + _NAME,
    r"\b" + _NAME + r" (?:welcomes applications|is committed to|offers (?:a|competitive)|was founded|is a (?:leading|global))",
    r"\bLife at " + _NAME,
    r"\b" + _NAME + r" (?:benefits|culture|values)\b",
]
NOT_COMPANY = {"we", "our", "us", "the", "the company", "this", "you", "your", "equal", "job", "jobs", "careers", "the role",
               "the team", "applicants", "all", "about", "about us", "company", "employer", "join", "life", "home",
               "benefits", "culture", "values", "why", "at", "position", "location", "department", "the position"}


def company_from_text(text: str, url: str | None = None):
    """Most-mentioned company name in the posting's own sentences. Returns (name, confident)."""
    t = (text or "")[:20000]
    votes = {}
    for rx in COMPANY_CLUES:
        for m in re.finditer(rx, t):
            name = re.sub(r"\s+(Inc\.?|LLC|Corp\.?|Corporation|Co\.|Ltd\.?|plc|L\.P\.)$", "", m.group(1).strip(" .,'’"))
            if name.lower() in NOT_COMPANY or len(name) < 2 or len(name) > 40:
                continue
            key = name.lower()
            v = votes.setdefault(key, [name, 0])
            v[1] += 1
    if not votes:
        return None, False
    host = urlparse(url or "").netloc.lower().replace("-", "")
    for key, v in votes.items():
        if key.replace(" ", "").replace("&", "") and key.replace(" ", "").replace("&", "") in host:
            v[1] += 3  # the web address agrees
    name, score = max(votes.values(), key=lambda v: v[1])
    return name, score >= 2  # named in 2+ separate sentences, or once + matches the web address


FOOTER = re.compile(r"\n\s*(similar jobs|insights from previous hires|people also viewed|recommended jobs|more jobs|"
                    r"jobs you may like|related jobs|share this job|slide \d+ of)\b", re.I)


def trim_page(text: str) -> str:
    """Drop the 'similar jobs' / footer junk that follows the posting on most career pages."""
    t = text or ""
    m = FOOTER.search(t, int(len(t) * 0.3))
    return t[:m.start()].strip() if m else t.strip()


_GLOC = re.compile(r"^[A-Z][\w .'-]+, (?:[A-Z]{2}, )?(?:USA|[A-Z][a-z]+(?: [A-Z][a-z]+)*)$")


def _walk(o):
    yield o
    if isinstance(o, dict):
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def from_google(url):
    """Google Careers: the page holds the job's data (and other search results); use only this job's entry."""
    m = re.search(r"/jobs/results/(\d{12,22})", url)
    if "google.com" not in url or not m:
        return None
    jid = m.group(1)
    r = get(url)
    if r.status_code != 200:
        return None
    for cb in re.finditer(r"AF_initDataCallback\((\{.*?\})\);?\s*</script>", r.text, re.S):
        dm = re.search(r"data:(\[.*\])\s*,\s*sideChannel", cb.group(1), re.S) or re.search(r"data:(\[.*\])", cb.group(1), re.S)
        try:
            data = json.loads(dm.group(1)) if dm else None
        except Exception:
            continue
        for a in _walk(data):
            if not (isinstance(a, list) and len(a) > 3 and a[0] == jid and isinstance(a[1], str)):
                continue
            parts, locs = [], []
            for o in _walk(a[2:]):
                if isinstance(o, str):
                    if _GLOC.match(o) and len(o) < 60 and o not in locs:
                        locs.append(o)
                    elif len(o) > 80 and not o.startswith("http"):
                        t = html_to_text(o) if "<" in o else o
                        if t not in parts:
                            parts.append(t)
            desc = "\n\n".join(parts)
            if len(desc) < 200:
                continue
            return {"title": a[1], "company": "Google", "_company_sure": True, "source": "Google Careers",
                    "location": "; ".join(l.replace(", USA", "") for l in locs[:4]), "description": desc}
    return None


SITE_HANDLERS = [from_google, from_bamboohr, from_oracle, from_greenhouse, from_lever, from_workday, from_ashby, from_smartrecruiters, from_eightfold, from_linkedin]


# ------------------------------------------------------------------ generic page
def _iter_jsonld(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    yield x
                if "@graph" in x:
                    stack.append(x["@graph"])


def from_jsonld(soup):
    for jp in _iter_jsonld(soup):
        org = jp.get("hiringOrganization") or {}
        if isinstance(org, list):
            org = org[0] if org else {}
        locs = jp.get("jobLocation") or []
        if isinstance(locs, dict):
            locs = [locs]
        names = []
        for l in locs:
            a = (l or {}).get("address") or {}
            if isinstance(a, str):
                names.append(a)
                continue
            n = ", ".join(x for x in [a.get("addressLocality"), a.get("addressRegion")] if x)
            if not n:
                n = a.get("addressCountry") if isinstance(a.get("addressCountry"), str) else ""
            if n and n not in names:
                names.append(n)
        d = {"title": htmllib.unescape(str(jp.get("title") or "")).strip() or None,
             "company": (org.get("name") if isinstance(org, dict) else str(org)) or None,
             "location": "; ".join(names[:3]) + (f" (+{len(names) - 3} more)" if len(names) > 3 else ""),
             "description": html_to_text(htmllib.unescape(str(jp.get("description") or ""))),
             "posted": _date(jp.get("datePosted"))}
        vt = _date(jp.get("validThrough"))
        if vt and d["posted"] and (vt - d["posted"]).days in (30, 31, 45, 60, 90, 180, 365):
            vt = None  # looks like an automatic listing expiry, not a real deadline
        if vt and dt.date.today() - dt.timedelta(days=1) <= vt <= dt.date.today() + dt.timedelta(days=366):
            d["deadline"] = vt
        et = jp.get("employmentType")
        d["emp_type"] = ", ".join(et) if isinstance(et, list) else et
        if "TELECOMMUTE" in str(jp.get("jobLocationType", "")).upper():
            d["work_mode"] = "Remote"
        bs = jp.get("baseSalary") or jp.get("estimatedSalary")
        if isinstance(bs, list):
            bs = bs[0] if bs else None
        if isinstance(bs, dict):
            v = bs.get("value") if isinstance(bs.get("value"), dict) else bs
            lo = v.get("minValue") or v.get("value")
            hi = v.get("maxValue") or lo
            unit = str(v.get("unitText") or bs.get("unitText") or "").upper()
            try:
                lo, hi = float(lo), float(hi)
                if lo > 0:
                    d["pay_min"], d["pay_max"] = lo, hi
                    d["pay_unit"] = "Hour" if unit == "HOUR" or lo < 300 else "Year"
                    if unit == "MONTH":
                        d["pay_min"], d["pay_max"], d["pay_unit"] = lo * 12, hi * 12, "Year"
            except (TypeError, ValueError):
                pass
        return d
    return None


JOB_SIGNALS = re.compile(r"responsibilit|qualification|requirement|what you(?:'|’)ll do|what you will do|you will|"
                         r"experience (?:with|in)|years of experience|skills|degree|about the role|the role|"
                         r"what we(?:'|’)re looking for|key duties|preferred|must have|nice to have|benefits", re.I)


def looks_like_posting(text: str) -> bool:
    """True if the text reads like an actual job posting, not just a page's menus/about/legal text."""
    t = text or ""
    if len(t) < 250:
        return False
    return len(set(m.group(0).lower()[:12] for m in JOB_SIGNALS.finditer(t[:30000]))) >= 3


DESC_KEYS = re.compile(r"description|summary|qualification|responsibilit|requirement|duties|about.?the.?role|"
                       r"jobdetail|posting.?body|content", re.I)
TITLE_KEYS = ("postingTitle", "jobTitle", "JobTitle", "postingName", "title", "Title", "name")  # best first


def _title_value(v):
    v = v.strip()
    return 3 < len(v) < 120 and " " in v and not re.search(r"[{}<>=]|https?:", v)
LOC_KEYS = ("location", "locationName", "primaryLocation", "city", "jobLocation")


def from_hidden_data(soup) -> dict:
    """Job data that JavaScript-built pages (e.g. Apple) embed in <script> tags instead of the visible page."""
    blobs = []
    for tag in soup.find_all("script"):
        if (tag.get("type") or "").lower() == "application/ld+json":
            continue
        txt = tag.string or tag.get_text() or ""
        if len(txt) < 300:
            continue
        for m in re.finditer(r"JSON\.parse\((['\"])(.+?)\1\)", txt, re.S):  # JSON.parse("...escaped...")
            try:
                blobs.append(json.loads(json.loads('"' + m.group(2).replace('\\\'', "'") + '"')))
            except Exception:
                pass
        stripped = txt.strip()
        if stripped[:1] in "{[":
            try:
                blobs.append(json.loads(stripped))
            except Exception:
                pass
        for m in re.finditer(r"(?:phApp\.ddo|window\.pageData|window\.__\w+__|var \w+|window\.\w+)\s*=\s*(?=[\{\[])", txt):
            try:  # data assigned in a script: read exactly one JSON value from there
                blobs.append(json.JSONDecoder().raw_decode(txt[m.end():])[0])
            except ValueError:
                pass
        for m in re.finditer(r"=\s*(\{.*\})\s*;?\s*$", txt, re.S):  # window.__DATA__ = {...};
            try:
                blobs.append(json.loads(m.group(1)))
            except Exception:
                pass
    best = {"parts": [], "title": None, "title_rank": 99, "location": None}

    def walk(x, depth=0):
        if depth > 12:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str):
                    if len(v) > 150 and DESC_KEYS.search(k):
                        best["parts"].append(html_to_text(v) if "<" in v else v)
                    elif k in TITLE_KEYS and _title_value(v) and TITLE_KEYS.index(k) < best["title_rank"]:
                        best["title"], best["title_rank"] = v.strip(), TITLE_KEYS.index(k)
                    elif k in LOC_KEYS and 2 < len(v) < 100 and not best["location"]:
                        best["location"] = v.strip()
                elif "location" in k.lower() and isinstance(v, (list, dict)) and not best["location"]:
                    first = v[0] if isinstance(v, list) and v else v
                    if isinstance(first, dict):
                        for nk in ("name", "displayName", "city", "locationName", "label"):
                            if isinstance(first.get(nk), str) and 2 < len(first[nk]) < 100:
                                st = first.get("stateProvince") or first.get("state") or first.get("region")
                                best["location"] = first[nk] + (f", {st}" if isinstance(st, str) and st else "")
                                break
                    elif isinstance(first, str) and 2 < len(first) < 100:
                        best["location"] = first
                    walk(v, depth + 1)
                elif isinstance(v, list) and v and all(isinstance(i, str) for i in v) and DESC_KEYS.search(k):
                    joined = "\n".join(v)
                    if len(joined) > 150:
                        best["parts"].append(html_to_text(joined) if "<" in joined else joined)
                else:
                    walk(v, depth + 1)
        elif isinstance(x, list):
            for i in x[:200]:
                walk(i, depth + 1)

    for b in blobs:
        walk(b)
    seen, parts = set(), []
    for p in best["parts"]:
        key = p[:80]
        if key not in seen:
            seen.add(key)
            parts.append(p.strip())
    desc = "\n\n".join(parts)
    if not looks_like_posting(desc):
        return {}
    return {"description": desc, "title": best["title"], "location": best["location"]}


def from_page(url):
    r = get(url, allow_redirects=True)
    body = r.text or ""
    low = body[:20000].lower()
    if r.status_code in (401, 403, 429, 999) or "captcha" in low or "verify you are human" in low \
            or "just a moment..." in low or "access denied" in low[:3000]:
        raise Blocked(f"{site_name(url)} blocked automated reading")
    if r.status_code >= 400:
        raise Blocked(f"page returned error {r.status_code}")
    soup = BeautifulSoup(body, "html.parser")
    d = from_jsonld(soup) or {}

    def meta(prop):
        t = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return (t.get("content") or "").strip() if t else ""

    if not d.get("company"):
        d["company"] = meta("og:site_name") or None
    if not d.get("title"):
        d["title"] = meta("og:title") or (soup.title.get_text(strip=True) if soup.title else None)
        d["_title_guess"] = True
    page_text = html_to_text(body)
    if not d.get("description"):
        tag = soup.find(attrs={"itemprop": "description"})
        if tag and len(tag.get_text(" ", strip=True)) > 300:
            d["description"] = html_to_text(str(tag))
            t = soup.find(attrs={"itemprop": "title"})
            if t and t.get_text(strip=True) and d.get("_title_guess"):
                d["title"], d["_title_guess"] = t.get_text(strip=True), False
    if not d.get("description") or not looks_like_posting(d.get("description")):
        hidden = from_hidden_data(soup)
        if hidden:
            d["description"] = hidden["description"]
            if d.get("_title_guess") and hidden.get("title"):
                d["title"], d["_title_guess"] = hidden["title"], False
            d.setdefault("location", hidden.get("location"))
            if not d.get("location"):
                d["location"] = hidden.get("location")
        elif not d.get("description"):
            d["description"] = trim_page(page_text)
            d["_desc_is_page"] = True
    d["_page_text"] = page_text
    return d


# ------------------------------------------------------------------ AI fill-in
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"}, "title": {"type": "string"}, "location": {"type": "string"},
        "work_mode": {"type": "string", "enum": ["Remote", "Hybrid", "On-site", ""]},
        "pay_min": {"type": "number"}, "pay_max": {"type": "number"},
        "pay_unit": {"type": "string", "enum": ["Year", "Hour", ""]},
        "employment_type": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["company", "title", "location", "work_mode", "pay_min", "pay_max", "pay_unit"],
}


def ai_fill(d: dict, text: str, ai: AI | None, want_desc=False):
    """Ask the AI only for the short fields (never to rewrite the description: that's slow)."""
    if not ai or not ai.enabled or not text:
        return d
    schema = json.loads(json.dumps(AI_SCHEMA))
    schema["properties"].pop("description")
    prompt = ("Extract the job posting details from this text. Use empty strings or 0 when a value "
              "isn't stated; don't guess pay. pay_min/pay_max are numbers only (e.g. 85000 or 32.5). "
              "company = the hiring company's name only.\n\nTEXT:\n" + text[:8000])
    res = ai.json(prompt, schema)
    if not res:
        return d
    mapping = {"employment_type": "emp_type"}
    low = re.sub(r"\s+", " ", text.lower())
    for k, v in res.items():
        k = mapping.get(k, k)
        if v in (None, "", 0):
            continue
        if k in ("company", "title", "location"):
            if re.sub(r"\s+", " ", str(v).lower().strip()) not in low:
                continue  # the AI's answer must actually appear in the posting
            if k == "company" and not d.get("_company_sure", True):
                d["company"], d["_company_sure"] = v, True
                continue
        if k in ("pay_min", "pay_max") and d.get("pay_min"):
            continue
        if not d.get(k) or (d.get("_title_guess") and k == "title"):
            d[k] = v
    d["_ai_used"] = True
    return d


# ------------------------------------------------------------------ main entry points
def finish(d: dict, url: str | None) -> dict:
    desc = d.get("description") or ""
    if not d.get("pay_min"):
        pm = parse_pay(d.get("_pay_text") or "") if d.get("_pay_text") else (None, None, None)
        if not pm[0]:
            pm = parse_pay(desc)
        if pm[0]:
            d["pay_min"], d["pay_max"], d["pay_unit"] = pm
    if not d.get("work_mode"):
        d["work_mode"] = detect_mode(d.get("location") or "", d.get("title") or "", desc)
    if d.get("title") and d.get("_title_guess"):
        t = re.split(r"\s+[|\-–]\s+", d["title"])
        d["title"] = t[0].strip()
    for k in ("company", "title", "location"):
        if isinstance(d.get(k), str):
            d[k] = re.sub(r"\s+", " ", d[k]).strip() or None
    if url:
        d["link"] = d.get("_canonical") or url
        d.setdefault("source", site_name(url))
        weak = not d.get("company") or re.search(r"logo|careers?|positions|jobs?\b|home", str(d.get("company")), re.I)
        if weak:
            name, sure = company_from_text(d.get("description") or "", url)
            if name and (sure or not d.get("company")):
                d["company"], d["_company_sure"] = name, sure
            elif company_from_url(url):
                d["company"], d["_company_sure"] = company_from_url(url), False
    return d


def extract(url: str, ai: AI | None = None) -> dict:
    """Raises Blocked if the site won't share the posting."""
    d = None
    for h in SITE_HANDLERS:
        try:
            d = h(url)
        except Blocked:
            raise
        except Exception:
            d = None
        if d and d.get("title"):
            break
    if not d or not d.get("title"):
        page_url = url
        if ".icims.com" in urlparse(url).netloc and "in_iframe" not in url:
            page_url = url + ("&" if "?" in url else "?") + "in_iframe=1"
        d = from_page(page_url)
    if not d.get("company"):
        name, sure = company_from_text(d.get("description") or "", url)
        d["company"], d["_company_sure"] = (name, sure) if name else (company_from_url(url), False)
    # AI only when the basics are missing or guessed (pay/perks are handled later in one AI pass)
    if not d.get("company") or not d.get("_company_sure", True) or not d.get("title") or d.get("_title_guess"):
        d = ai_fill(d, d.get("description") or d.get("_page_text") or "", ai)
    return finish(d, url)


JUNK_LINE = re.compile(r"^(skip to|sign in|log ?in|sign up|apply( now| for this job)?|save( job)?|share|jobs?|dashboard|"
                       r"profile|home|menu|search|view all|back to|join|careers?|positions?|add to cart|single position|"
                       r"matching skills|job description|job details|hybrid|remote|on-?site|full[- ]time|part[- ]time|"
                       r"about (us|the job)|overview)\b", re.I)
LOC_LINE = re.compile(r"^[A-Z][\w .'-]{1,40},\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)\b")


def _is_location_line(l: str) -> bool:
    """'Warrendale, PA, United States' yes; 'Engineer II, Mechanical Design' no."""
    from geo import CODES, STATES
    m = LOC_LINE.match(l)
    if not m or len(l) >= 60:
        return False
    st = m.group(1)
    return st in CODES or st.lower() in STATES


def extract_from_text(text: str, url: str | None, ai: AI | None = None) -> dict:
    """For a posting copied from a site that blocks reading (the whole page, so skip the menus)."""
    text = trim_page(text)
    d = {"description": text}
    lines = [l.strip() for l in text.splitlines() if l.strip()][:80]
    loc_i = next((i for i, l in enumerate(lines) if _is_location_line(l)), None)
    name, sure = company_from_text(text, url)
    if loc_i is not None:
        d["location"] = re.sub(r",?\s*United States.*$", "", lines[loc_i]).strip()
        ok = lambda l: 2 <= len(l) < 90 and not JUNK_LINE.match(l) and "logo" not in l.lower()  # noqa: E731
        above = [lines[k] for k in range(max(0, loc_i - 2), loc_i)]
        if len(above) == 2 and ok(above[0]) and ok(above[1]) and len(above[1]) < 50:
            # "Title / Company / Location" (Indeed, LinkedIn) unless the text says the first line is the company
            if name and above[0].lower().startswith(name.lower()):
                d["title"] = above[1]
            else:
                d["title"] = above[0]
                if not name or not sure:
                    name, sure = re.sub(r"\s*[·|-].*$", "", above[1]).strip(), bool(name and name.lower() in above[1].lower())
        else:
            for k in range(loc_i - 1, -1, -1):
                if ok(lines[k]) and len(lines[k]) > 4:
                    d["title"] = lines[k]
                    break
    if not d.get("title"):
        cand = [l for l in lines[:15] if 4 < len(l) < 90 and not JUNK_LINE.match(l) and "logo" not in l.lower()]
        if cand:
            d["title"] = cand[0]
    if name:
        d["company"], d["_company_sure"] = name, sure
    else:
        d["company"], d["_company_sure"] = (company_from_url(url) if url else None), False
    d["_title_guess"] = True
    if ai and ai.enabled:
        d = ai_fill(d, text, ai)
    return finish(d, url)
