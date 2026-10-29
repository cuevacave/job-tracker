"""Check Email: reads your Gmail accounts (read-only) and updates the tracker."""
from __future__ import annotations

import datetime as dt
import email
import imaplib
import json
import re
import sys
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import quote

import perks
import scoring
from common import (ACCOUNTS_PATH, AI, Tracker, add_log, load_state, norm_url, num, save_state, status_rank,
                    to_date, today, yes)

KEYRING_SERVICE = "JobTracker-Gmail"

# ------------------------------------------------------------------ filters
ATS_DOMAINS = ["greenhouse", "lever.co", "hire.lever", "myworkday", "workday", "icims", "smartrecruiters",
               "ashbyhq", "jobvite", "taleo", "bamboohr", "successfactors", "breezy", "workable",
               "recruitee", "jazzhr", "applytojob", "paylocity", "ultipro", "ukg", "adp", "dayforce",
               "oraclecloud", "rippling", "pinpointhq", "teamtailor", "gem.com", "goodtime", "calendly",
               "hirevue", "codesignal", "hackerrank", "karat", "talentlyft", "eightfold", "phenom",
               "avature", "brassring", "indeedemail", "indeed.com", "linkedin.com", "joinhandshake",
               "ziprecruiter", "wellfound", "glassdoor", "dice.com", "usajobs"]
SUBJECT_HINTS = re.compile(
    r"applica|applying|applied|interview|candida|position|role\b|opportunit|recruit|talent|career|"
    r"hiring|offer|assessment|unfortunately|next steps|your (resume|profile)|thank you for your interest|"
    r"phone screen|schedule|availability|coding challenge|take[- ]home|follow[- ]up", re.I)
ALERT_PATTERNS = re.compile(
    r"job alert|jobs? (you may|for you|matching|recommended)|new jobs?|recommended jobs?|jobs? near|"
    r"is hiring|are hiring|top job picks|jobs that match|similar jobs|people also viewed|"
    r"jobalerts|jobs-noreply@linkedin|alert@indeed|newsletter|webinar|your weekly|digest|"
    r"profile views?|who viewed|invitation to connect|connect with|promoted|sale|% off|unsubscribe",
    re.I)

RULES = [  # (category, regex) checked in order
    ("Offer", r"pleased to (offer|extend)|extend (you )?an offer|offer letter|job offer|formal offer|verbal offer"),
    ("Rejected", r"unfortunately|not (to )?(be )?moving forward|move forward with other|decided to (pursue|proceed with) other|"
                 r"other candidates|not been selected|were not selected|won't be moving|will not be moving|"
                 r"position has (been|now been) filled|regret to inform|decided not to proceed|not a match at this time|"
                 r"no longer under consideration|not able to offer you|pursue other applicants|closed the position"),
    ("Assessment", r"assessment|coding challenge|hackerrank|codesignal|take[- ]home|online test|skills test|"
                   r"case study|exercise to complete|questionnaire to complete|hirevue|video interview link|karat"),
    ("Screening", r"phone screen|recruiter (call|screen)|initial (call|conversation|screen|chat)|introductory call|"
                  r"quick call|brief call|screening call"),
    ("Interview", r"invit\w* you to (an? |the )?(interview|meet|speak|chat|a call)|schedule (an?|your|the|some) "
                  r"(interview|call|time|conversation)|interview (with|on|at|is scheduled|confirm\w*|invit\w*|request|"
                  r"details|availability)|your availability|calendly\.com|next round|on-?site interview|"
                  r"like to (meet|speak|talk|chat) with you|love to (meet|speak|talk|chat)|move you forward to"),
    ("Applied", r"thank(s| you) for (applying|your application|your interest)|application (has been )?(received|submitted)|"
                r"received your application|we('ve| have) received|successfully (applied|submitted)|application confirmation|"
                r"your application (to|for)|you applied|application was sent"),
    ("Recruiter message", r"came across your (profile|resume|background)|opportunity (that|you) (might|may)|"
                          r"open to (a quick chat|new opportunities|hearing|exploring)|reaching out (about|regarding|with) "
                          r"(a|an) (new )?(role|position|opportunity)|your background (looks|seems|is a)"),
]
RULES = [(c, re.compile(p, re.I)) for c, p in RULES]
STATUS_OF = {"Applied": "Applied", "Screening": "Screening", "Interview": "Interview", "Assessment": "Assessment",
             "Rejected": "Rejected", "Offer": "Offer"}

AI_SCHEMA = {
    "type": "object",
    "properties": {
        "about_my_job_application": {"type": "boolean"},
        "category": {"type": "string", "enum": ["Applied", "Screening", "Interview", "Assessment", "Rejected",
                                                "Offer", "Recruiter message", "Job alert or marketing", "Other"]},
        "company": {"type": "string"},
        "job_title": {"type": "string"},
        "interview_time": {"type": "string"},
        "needs_reply": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["about_my_job_application", "category", "company", "job_title", "needs_reply", "summary"],
}
AI_SYSTEM = ("You sort a job seeker's emails. 'Applied' = confirmation that an application was received. "
             "'Screening' = recruiter/phone screen request. 'Interview' = interview invite or scheduling. "
             "'Assessment' = test, coding challenge or questionnaire to complete. 'Rejected' = they are not moving "
             "forward (often polite and indirect). 'Offer' = job offer. 'Recruiter message' = a recruiter reaching "
             "out or replying that doesn't fit the others. 'Job alert or marketing' = job recommendations, newsletters, "
             "ads. company = the hiring company (not the ATS like Greenhouse/Workday/LinkedIn). interview_time = "
             "date/time if one is proposed or confirmed, else empty.")

STOP = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "the", "group", "holdings", "plc", "lp",
        "technologies", "technology", "solutions", "services", "international", "usa", "us", "na", "careers",
        "jobs", "talent", "team", "recruiting", "hiring", "hr", "noreply", "no", "reply", "do", "not"}


def norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower())
    return " ".join(w for w in s.split() if w not in STOP)


# ------------------------------------------------------------------ email parsing
def dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return str(v or "")


def body_text(msg) -> str:
    plain, html = [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get_filename():
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            txt = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain":
            plain.append(txt)
        elif ctype == "text/html":
            html.append(txt)
    if plain and len(" ".join(plain).strip()) > 40:
        text = "\n".join(plain)
    elif html:
        from extract import html_to_text
        text = html_to_text("\n".join(html))
    else:
        text = "\n".join(plain)
    # drop quoted replies
    text = re.split(r"\n\s*On .{5,80} wrote:\s*\n|\n-{2,}\s*Original Message", text)[0]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def gmail_link(account, msgid):
    mid = msgid.strip("<>")
    return f"https://mail.google.com/mail/u/{account}/#search/rfc822msgid%3A{quote(mid)}"


# ------------------------------------------------------------------ classification
def rule_classify(subject, body):
    text = f"{subject}\n{body[:4000]}"
    for cat, rx in RULES:
        if rx.search(text):
            return cat
    return None


def classify(m, ai):
    """m: dict(subject, body, from_name, from_addr). Returns dict(category, company, title, when, needs_reply, summary)."""
    rule = rule_classify(m["subject"], m["body"])
    res = {"category": rule, "company": "", "title": "", "when": "", "needs_reply": False, "summary": "", "ai": False}
    if ai and ai.enabled:
        out = ai.json(f"From: {m['from_name']} <{m['from_addr']}>\nSubject: {m['subject']}\n\n{m['body'][:5000]}",
                      AI_SCHEMA, AI_SYSTEM)
        if out:
            cat = out.get("category")
            if not out.get("about_my_job_application") and cat not in ("Recruiter message",):
                cat = None if cat != "Job alert or marketing" else "Alert"
            if cat in ("Other",):
                cat = None
            # Rejections are often worded softly; trust a strong rule hit over the model.
            if rule == "Rejected" and cat not in ("Offer",):
                cat = "Rejected"
            if cat is None and rule in ("Rejected", "Offer"):
                cat = rule
            res.update(category=cat, company=out.get("company") or "", title=out.get("job_title") or "",
                       when=out.get("interview_time") or "", needs_reply=bool(out.get("needs_reply")),
                       summary=out.get("summary") or "", ai=True)
    if not res["company"]:
        res["company"] = guess_company(m)
    return res


def guess_company(m):
    subj, body, name = m["subject"], m["body"][:1500], m["from_name"]
    pats = [r"(?:applying|application|interest) (?:to|at|with) ([A-Z][\w&.\- ]{1,40}?)(?:[!.,:]| for| -|$)",
            r"^(?:Your application|Thank you for applying)[^|:\-]*[|:\-–]\s*([A-Z][\w&.\- ]{1,40})$",
            r"([A-Z][\w&.\- ]{1,40}?) (?:Hiring|Recruiting|Talent|Careers|People) Team",
            r"at ([A-Z][\w&.\-]+(?: [A-Z][\w&.\-]+){0,3})(?: and| has|,|\.)"]
    for src in (subj, name, body):
        for p in pats:
            mm = re.search(p, src or "", re.M)
            if mm:
                return mm.group(1).strip(" -")
    dom = m["from_addr"].split("@")[-1].lower()
    if not any(a in dom for a in ATS_DOMAINS + ["gmail", "outlook", "yahoo", "icloud", "hotmail"]):
        parts = dom.split(".")
        return parts[-2].title() if len(parts) >= 2 else ""
    if name and not re.search(r"no.?reply|notification|talent acquisition|careers|recruit|jobs", name, re.I):
        return ""
    return ""


def match_job(jobs, m, cls):
    """Find the best tracked job for this email. Returns the job dict or None."""
    hay_subject = norm(m["subject"])
    hay_from = norm(m["from_name"] + " " + m["from_addr"].split("@")[-1].replace(".", " "))
    hay_body = norm(m["body"][:3000])
    guess = norm(cls.get("company"))
    best, best_score = None, 0
    for j in jobs:
        comp = norm(j.get("company"))
        if not comp:
            continue
        sc = 0
        first = comp.split()[0] if comp.split() else comp
        if guess and (guess == comp or (len(first) > 3 and first in guess.split()) or comp in guess):
            sc += 4
        if re.search(rf"\b{re.escape(comp)}\b", hay_subject):
            sc += 3
        compact = comp.replace(" ", "")
        if re.search(rf"\b{re.escape(comp)}\b", hay_from) or (len(first) > 3 and re.search(rf"\b{re.escape(first)}\b", hay_from)) \
                or (len(compact) > 3 and compact in m["from_addr"].split("@")[-1]):
            sc += 3
        if re.search(rf"\b{re.escape(comp)}\b", hay_body):
            sc += 1
        if sc == 0:
            continue
        title = norm(j.get("title"))
        if title and (title in hay_subject or title in hay_body or (cls.get("title") and norm(cls["title"]) == title)):
            sc += 2
        if j.get("status") in ("Rejected", "Withdrawn", "Declined"):
            sc -= 1
        if j.get("applied") == "Yes":
            sc += 0.5
        if sc > best_score:
            best, best_score = j, sc
    return best if best is not None and best_score >= 3 else None


# ------------------------------------------------------------------ apply changes
def apply_update(job, cat, cls, m, when_date):
    """Move status forward only. Returns a description of what changed."""
    changes = []
    new_status = STATUS_OF.get(cat)
    cur = job.get("status") or "Saved"
    if new_status and status_rank(new_status) > status_rank(cur):
        job["status"] = new_status
        changes.append(f"Status {cur} -> {new_status}")
    if cat in STATUS_OF and job.get("applied") != "Yes":
        job["applied"] = "Yes"
        changes.append("Applied? -> Yes")
    if cat in STATUS_OF and not job.get("date_applied"):
        job["date_applied"] = when_date
    na = None
    if cat in ("Interview", "Screening"):
        na = f"{'Screen' if cat == 'Screening' else 'Interview'}: {cls['when']}" if cls.get("when") else "Reply to schedule interview"
    elif cat == "Assessment":
        na = "Complete assessment"
    elif cat == "Offer":
        na = "Review offer"
    elif cat == "Recruiter message" or (cls.get("needs_reply") and cat not in ("Rejected", "Applied")):
        na = f"Reply to {m['from_name'] or m['from_addr']}"
    elif cat == "Rejected":
        na = ""
    if na is not None and na != (job.get("next_action") or ""):
        job["next_action"] = na or None
        if na:
            changes.append(f"Next Action: {na}")
    if cat in ("Recruiter message", "Screening", "Interview") and not job.get("contact") \
            and not re.search(r"no.?reply|notifications?@", m["from_addr"], re.I):
        job["contact"] = f"{m['from_name']} <{m['from_addr']}>".strip()
    last = to_date(job.get("last_update"))
    if not isinstance(last, dt.date) or when_date >= last:
        job["last_update"] = when_date
    line = f"{when_date:%Y-%m-%d} {cat}: {m['subject'][:90]}"
    old = str(job.get("email_log") or "")
    if line not in old:
        job["email_log"] = (line + ("\n" + old if old else ""))[:3000]
    return "; ".join(changes) or "Logged (no status change)"


# ------------------------------------------------------------------ IMAP
def connect(addr, pw):
    im = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    im.login(addr, pw)
    return im


def select_all_mail(im):
    for box in ('"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "INBOX"):
        typ, _ = im.select(box, readonly=True)
        if typ == "OK":
            return box
    raise RuntimeError("couldn't open the mailbox")


def fetch_headers(im, uids):
    out = {}
    for i in range(0, len(uids), 250):
        chunk = b",".join(uids[i:i + 250])
        typ, data = im.uid("fetch", chunk, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
        if typ != "OK":
            continue
        for item in data:
            if not isinstance(item, tuple):
                continue
            mm = re.search(rb"UID (\d+)", item[0])
            if mm:
                out[mm.group(1)] = email.message_from_bytes(item[1])
    return out


def fetch_body(im, uid):
    typ, data = im.uid("fetch", uid, "(BODY.PEEK[])")
    for item in data or []:
        if isinstance(item, tuple):
            return email.message_from_bytes(item[1])
    return None


# ------------------------------------------------------------------ phone capture
def handle_phone_link(tr, ai, m, acct, when_date, results):
    from extract import Blocked, extract
    urls = re.findall(r"https?://[^\s<>\"')\]]+", m["subject"] + "\n" + m["body"])
    urls = [u.rstrip(".,") for u in urls if not re.search(r"mail\.google|apple\.com/|icloud\.com", u)]
    applied = "applied" in m["subject"].lower()
    for u in dict.fromkeys(urls):
        if tr.find_by_link(u):
            continue
        print(f"  Phone link: {u[:80]}")
        try:
            d = extract(u, ai)
            note = "Added from phone"
        except Blocked as e:
            d, note = {"link": u}, f"Added from phone. {e}; open the link and fill in the details"
        except Exception as e:
            d, note = {"link": u}, f"Added from phone. Couldn't open link ({type(e).__name__})"
        job = {k: d.get(k) for k in ("company", "title", "location", "work_mode", "pay_min", "pay_max", "pay_unit",
                                     "emp_type", "posted", "deadline", "description", "source", "link")}
        job["link"] = job.get("link") or u
        job["company"] = job.get("company") or "(open link)"
        job.update({"date_added": when_date, "last_update": when_date, "notes": note})
        perks.enrich(job, ai)
        if applied:
            job.update({"applied": "Yes", "status": "Applied", "date_applied": when_date,
                        "next_action": "Add resume version"})
        else:
            job.update({"applied": "No", "status": "Saved"})
        job["fit_score"], job["fit_notes"] = scoring.fit(job, tr.s, ai)
        tr.add(job)
        add_log(tr.wb, "Activity Log", [when_date, acct, "you (phone)", m["subject"][:200], "Phone link",
                                        job["id"], job["company"], f"Added {job.get('title') or u}"])
        results["added"] += 1


# ------------------------------------------------------------------ main
def load_accounts():
    if not ACCOUNTS_PATH.exists():
        return []
    return json.loads(ACCOUNTS_PATH.read_text()).get("accounts", [])


def get_password(addr):
    import keyring
    return keyring.get_password(KEYRING_SERVICE, addr)


def process_message(tr, ai, acct, my_addrs, msg_hdr, im, uid, state, results):
    s = tr.s
    subject = dec(msg_hdr.get("Subject"))
    from_name, from_addr = parseaddr(dec(msg_hdr.get("From")))
    from_addr = from_addr.lower()
    msgid = (msg_hdr.get("Message-ID") or f"{acct}-{uid.decode()}").strip()
    if msgid in state["seen"]:
        return
    try:
        when = parsedate_to_datetime(msg_hdr.get("Date"))
        when_date = when.astimezone().date() if when.tzinfo else when.date()
    except Exception:
        when_date = today()

    kw = str(s.get("phone_keyword") or "job").lower()
    if from_addr in my_addrs:
        if kw and re.search(rf"\b{re.escape(kw)}\b", subject.lower()):
            full = fetch_body(im, uid)
            m = {"subject": subject, "body": body_text(full) if full else "", "from_name": "", "from_addr": from_addr}
            handle_phone_link(tr, ai, m, acct, when_date, results)
        state["seen"][msgid] = str(when_date)
        return

    is_ats = any(a in from_addr for a in ATS_DOMAINS)
    if ALERT_PATTERNS.search(subject) or ALERT_PATTERNS.search(from_addr):
        if not RULES[1][1].search(subject):  # still let "unfortunately..." through
            return
    if not (is_ats or SUBJECT_HINTS.search(subject)):
        return

    full = fetch_body(im, uid)
    if full is None:
        return
    m = {"subject": subject, "body": body_text(full), "from_name": from_name, "from_addr": from_addr}
    cls = classify(m, ai)
    cat = cls["category"]
    state["seen"][msgid] = str(when_date)
    if cat in (None, "Alert"):
        return
    results["emails"] += 1
    link = gmail_link(acct, msgid)
    job = match_job(tr.jobs, m, cls)

    if job is not None:
        what = apply_update(job, cat, cls, m, when_date)
        add_log(tr.wb, "Activity Log", [when_date, acct, f"{from_name} <{from_addr}>", subject[:200], cat,
                                        job.get("id"), job.get("company"), what])
        results["updated"] += 1 if ("->" in what or "Next Action" in what) else 0
        print(f"  #{job.get('id')} {job.get('company')}: {cat}. {what}")
        return

    company = (cls.get("company") or "").strip()
    if cat == "Applied" and yes(s.get("auto_add")) and company and len(company) < 60:
        title = cls.get("title") or ""
        if not title:
            tm = re.search(r"(?:for|position:?|role:?)\s+(?:the\s+)?([A-Z][\w/&,\-() ]{3,60}?)(?:\s+(?:position|role|at)\b|[.!\n]|$)",
                           subject + "\n" + m["body"][:800])
            title = tm.group(1).strip() if tm else ""
        job = tr.add({"company": company, "title": title or None, "applied": "Yes", "status": "Applied",
                      "date_applied": when_date, "last_update": when_date, "source": "Email",
                      "next_action": "Add link / resume version",
                      "notes": "Auto-added from an application confirmation email.",
                      "email_log": f"{when_date:%Y-%m-%d} Applied: {subject[:90]}"})
        add_log(tr.wb, "Activity Log", [when_date, acct, f"{from_name} <{from_addr}>", subject[:200], cat,
                                        job["id"], company, "New job added from confirmation email"])
        results["added"] += 1
        print(f"  Added #{job['id']} {company} (from confirmation email)")
        return

    add_log(tr.wb, "Needs Review", [when_date, acct, f"{from_name} <{from_addr}>", subject[:200], cat,
                                    company, "Couldn't match this to a job in your tracker.", link, None])
    results["review"] += 1


def followups(tr, results):
    s = tr.s
    fu, gh = int(num(s.get("followup_days"), 10)), int(num(s.get("ghost_days"), 30))
    t = today()
    for j in tr.jobs:
        if j.get("status") != "Applied":
            continue
        ref = to_date(j.get("last_update") or j.get("date_applied"))
        if not isinstance(ref, dt.date):
            continue
        days = (t - ref).days
        if gh and days >= gh:
            j["status"], j["next_action"] = "Ghosted", None
            results["ghosted"] += 1
        elif fu and days >= fu and not j.get("next_action"):
            j["next_action"] = f"Follow up? ({days} days, no reply)"
            results["followups"] += 1


def main():
    print("=" * 60 + f"\n  CHECK EMAIL                     Job Tracker update {__import__('common').APP_VERSION}\n" + "=" * 60)
    accounts = load_accounts()
    if not accounts:
        sys.exit("  No Gmail accounts set up yet. Double-click 'Setup' first.")
    tr = Tracker()
    ai = AI(tr.s)
    print(f"  AI helper: {'on (' + ai.model + ')' if ai.enabled else 'off - ' + ai.reason}")
    state = load_state()
    state.setdefault("seen", {})
    state.setdefault("last_run", {})
    results = {"emails": 0, "updated": 0, "added": 0, "review": 0, "followups": 0, "ghosted": 0}
    my_addrs = {a.lower() for a in accounts}

    for acct in accounts:
        pw = get_password(acct)
        if not pw:
            print(f"  No saved password for {acct}. Run Setup to add it.")
            continue
        last = state["last_run"].get(acct)
        since = (dt.date.fromisoformat(last) - dt.timedelta(days=2)) if last else \
            today() - dt.timedelta(days=int(num(tr.s.get("lookback_days"), 60)))
        print(f"\n  {acct}: checking mail since {since:%b %d}...")
        try:
            im = connect(acct, pw)
        except imaplib.IMAP4.error as e:
            print(f"  Couldn't log in ({e}). Check the app password by running Setup again.")
            continue
        except OSError as e:
            print(f"  Couldn't reach Gmail ({e}). Are you online?")
            continue
        try:
            select_all_mail(im)
            typ, data = im.uid("search", None, "SINCE", since.strftime("%d-%b-%Y"))
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            headers = fetch_headers(im, uids)
            print(f"  {len(headers)} emails to scan.")
            for n, (uid, hdr) in enumerate(headers.items(), 1):
                try:
                    process_message(tr, ai, acct, my_addrs, hdr, im, uid, state, results)
                except Exception as e:  # one bad email shouldn't stop the run
                    print(f"  (skipped one email: {type(e).__name__})")
                if ai.enabled and n % 50 == 0:
                    print(f"  ...{n}/{len(headers)}")
            state["last_run"][acct] = today().isoformat()
        finally:
            try:
                im.logout()
            except Exception:
                pass

    followups(tr, results)
    cutoff = (today() - dt.timedelta(days=200)).isoformat()
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= cutoff}
    counts = tr.save()
    save_state(state)
    print("\n  " + "-" * 40)
    print(f"  Job emails found:     {results['emails']}")
    print(f"  Jobs updated:         {results['updated']}")
    print(f"  Jobs added:           {results['added']}")
    print(f"  Follow-ups suggested: {results['followups']}")
    print(f"  Marked ghosted:       {results['ghosted']}")
    print(f"  Needs your review:    {results['review']}" + ("  (see the Needs Review tab)" if results["review"] else ""))
    print(f"\n  To Apply: {counts['To Apply']}   Applied: {counts['Applied']}   Closed: {counts['Closed']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped. Nothing was saved from this run.")
