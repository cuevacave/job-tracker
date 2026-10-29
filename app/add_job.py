"""Add Job: copy a job link, run this, press Enter, answer one question."""
from __future__ import annotations

import re
import sys
import time

import perks
import scoring
from common import (AI, POSTINGS_DIR, Tracker, clipboard_get, clipboard_set, fmt_money, fmt_pay, norm_url, num,
                    safe_name, today, yes)
from extract import Blocked, extract, extract_from_text, looks_like_posting
from common import parse_pay

URL_RE = re.compile(r"https?://[^\s<>\"']+")
POSTING_FIELDS = ("company", "title", "location", "work_mode", "pay_min", "pay_max", "pay_unit", "emp_type",
                  "posted", "deadline", "description", "source", "link")


def flush_input():
    """Throw away anything typed or pasted while the script was busy, so it can't answer later questions."""
    try:
        import termios
        time.sleep(0.15)
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def ask(prompt, default=""):
    flush_input()
    try:
        v = input(prompt)
    except EOFError:
        v = ""
    return v.strip() or default


def ask_yn(prompt):
    while True:
        v = ask(prompt).lower()
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        print("  Please type y or n.")


def resume_default(company, title):
    t = re.sub(r"\b(senior|sr|junior|jr|associate|i{1,3}|iv)\b\.?", "", title or "", flags=re.I)
    return f"Resume_{safe_name(company, 20)}_{safe_name(t, 25)}".replace("__", "_")


def mark_applied(job):
    dflt = resume_default(job.get("company"), job.get("title"))
    job["resume"] = ask(f"  Resume version [{dflt}]: ", dflt)
    job["applied"] = "Yes"
    job["date_applied"] = job.get("date_applied") or today()
    job["last_update"] = today()
    if str(job.get("status") or "") in ("", "Saved", "Skipped", "Ghosted"):
        job["status"] = "Applied"
    if str(job.get("next_action") or "").lower().startswith(("apply", "follow up", "add resume")):
        job["next_action"] = None


def read_copied_page(url, ai, why=None):
    """Use the page the user copied in their browser as the posting."""
    if why:
        print(f"\n  Hmm, {why}.")
    print("  1. In your browser, select the whole posting page (Cmd+A) and copy it (Cmd+C).")
    print("  2. Come back here and just press Enter. Don't paste here; I read it from your clipboard.")
    ans = ask("  Press Enter when copied (or type s to skip): ")
    flush_input()  # if the posting was pasted here anyway, ignore the rest of it
    if ans.lower() == "s":
        return None
    text = clipboard_get()
    if URL_RE.fullmatch(text.strip() or "x") or len(text.strip()) < 150:
        print("  The clipboard doesn't look like a posting (it has a link or very little text). Skipping.")
        return None
    if not looks_like_posting(text):
        print("  Note: that doesn't look much like a job posting, but I'll use it.")
    return extract_from_text(text, url, ai)


def get_posting(url, ai):
    print("  Reading the posting...")
    try:
        d = extract(url, ai)
        desc = d.get("description") or ""
        structured = not d.get("_desc_is_page")  # came from the site's own job data, not scraped page text
        if d.get("title") and (looks_like_posting(desc) or (structured and len(desc) >= 300)):
            return d
        why = ("this page didn't include the posting itself (only its menus/about/legal text; the site builds "
               "it with JavaScript)")
    except Blocked as e:
        why = str(e)
    except Exception as e:
        why = f"couldn't open the page ({type(e).__name__})"
    return read_copied_page(url, ai, why)


def show(j, s):
    loc = j.get("location") or "location not listed"
    mode = j.get("work_mode") or ""
    if j.get("office_days") and mode == "Hybrid":
        mode = f"Hybrid, {j['office_days']:g} days/wk in office" if isinstance(j["office_days"], (int, float)) else mode
    print(f"\n  {j.get('title')}  @  {j.get('company')}")
    print(f"  {loc}" + (f"  ({mode})" if mode else "") + (f"   -> {j['area']}" if j.get("area") else ""))
    tc = scoring.total_comp(j, s)
    print(f"  Pay: {fmt_pay(j.get('pay_min'), j.get('pay_max'), j.get('pay_unit'))}"
          + (f"   (est. total comp {fmt_money(tc)}/yr)" if tc else ""))
    ps = scoring.perks_summary(j)
    print(f"  Perks: {ps or 'none listed'}")
    dates = []
    if j.get("posted"):
        ago = scoring.days_since_posted(j)
        dates.append(f"posted {j['posted']:%b %d}" + (f" ({ago} days ago)" if ago and ago > 0 else " (today)"))
    if j.get("deadline"):
        dl = scoring.days_left(j)
        dates.append(f"apply by {j['deadline']:%b %d}" + (f" ({dl} days left)" if dl is not None and dl >= 0 else " (passed)"))
    if dates:
        print("  " + ", ".join(dates))


FIX_HELP = ("  Press Enter if that looks right, or type fixes like:\n"
            "    title=Data Analyst   company=Acme   location=Denver, CO   pay=70000-85000   days=3   deadline=11/14\n"
            "  Wrong or missing posting text? Copy the posting page in your browser and type  c\n  > ")


def apply_fixes(j, fix):
    for k, v in re.findall(r"(\w+)\s*=\s*([^=]+?)(?=\s+\w+\s*=|$)", fix):
        k, v = k.lower(), v.strip()
        if k == "pay":
            nums = [float(x.replace(",", "").replace("$", "").lower().rstrip("k")) * (1000 if x.lower().endswith("k") else 1)
                    for x in re.findall(r"\$?[\d,.]+k?", v, re.I)]
            if nums:
                j["pay_min"], j["pay_max"] = nums[0], nums[-1]
                j["pay_unit"] = "Hour" if nums[0] < 300 else "Year"
        elif k == "mode":
            j["work_mode"] = {"r": "Remote", "h": "Hybrid", "o": "On-site"}.get(v[:1].lower(), v)
        elif k == "days":
            j["office_days"] = int(num(v, 0)) or None
            if j["office_days"]:
                j["work_mode"] = "On-site" if j["office_days"] >= 5 else "Hybrid"
        elif k == "deadline":
            j["deadline"] = perks.parse_date(v) or j.get("deadline")
        elif k in ("location", "company", "title"):
            j[k] = v


LAST = {"posting": None}


PERK_KEYS = ("office_days", "signon", "bonus_pct", "bonus_amt", "k401", "relocation", "equity", "esop", "health", "pto",
             "gym", "stipend", "other_perks", "evidence")


def review(job, d, url, ai, tr):
    """Fill gaps, read perks, show what was found, and let the user fix it or swap in the copied page (c)."""
    s = tr.s
    # Only ask when unsure; the guess is pre-filled, so Enter accepts it
    if not job.get("company") or d.get("_company_sure") is False:
        job["company"] = ask(f"  Company [{job.get('company') or '?'}] (Enter = keep): ", job.get("company") or "") or None
    if not job.get("title"):
        job["title"] = ask("  Job title: ") or None
    print("  Checking pay, perks, office days and deadline" + (" with the AI..." if ai.enabled else "..."), end="", flush=True)
    t0 = time.time()
    perks.enrich(job, ai)
    print(f" done ({time.time() - t0:.0f}s)")
    tr.locate(job)
    show(job, s)
    fix = ask(FIX_HELP)
    if fix.lower() in ("c", "copy", "paste", "p"):
        d2 = read_copied_page(url, ai)
        if d2:
            for k in POSTING_FIELDS:
                v = d2.get(k)
                if v in (None, ""):
                    continue
                if k == "description" or not job.get(k) or (k == "company" and d2.get("_company_sure")):
                    job[k] = v
            for k in PERK_KEYS:
                job.pop(k, None)  # re-read perks from the real posting
            print("  Re-checking pay, perks, office days and deadline...", end="", flush=True)
            t0 = time.time()
            perks.enrich(job, ai)
            print(f" done ({time.time() - t0:.0f}s)")
            job["geo_key"] = None
            tr.locate(job)
            show(job, s)
            fix = ask("  Press Enter if that looks right, or type fixes (title=..., pay=..., etc.)\n  > ")
    if fix and fix.lower() not in ("c", "copy", "paste", "p"):
        apply_fixes(job, fix)
        job["geo_key"] = None
        tr.locate(job)
        show(job, s)


def posting_header(job, url):
    return (f"{job.get('title')}\n{job.get('company')}\n{job.get('location') or ''} {job.get('work_mode') or ''}\n"
            f"Pay: {fmt_pay(job.get('pay_min'), job.get('pay_max'), job.get('pay_unit'))}\n"
            f"Perks: {scoring.perks_summary(job) or '-'}\n{url}\n\n")


def write_posting_file(job, url):
    POSTINGS_DIR.mkdir(exist_ok=True)
    for old in POSTINGS_DIR.glob(f"{int(job['id']):04d}_*.txt"):
        old.unlink()  # replace an earlier (incomplete) capture
    fname = POSTINGS_DIR / f"{int(job['id']):04d}_{safe_name(job.get('company'), 25)}_{safe_name(job.get('title'), 35)}.txt"
    fname.write_text(posting_header(job, url) + (job.get("description") or ""), encoding="utf-8")


def recapture(tr, ai, old, url):
    """Re-read the posting for a job already in the tracker; keep status, notes, resume, dates."""
    s = tr.s
    d = get_posting(url, ai)
    if not d:
        return
    new = {k: d.get(k) for k in POSTING_FIELDS}
    for k in ("company", "title"):  # keep the names you already have (fix them on the next screen if needed)
        if old.get(k) and not str(old[k]).startswith("("):
            new[k] = old[k]
    d["_company_sure"] = True if new.get("company") else d.get("_company_sure")
    review(new, d, url, ai, tr)
    for k in PERK_KEYS:
        old.pop(k, None)
    for k, v in new.items():
        if k == "link":
            continue
        if v not in (None, "") or k in PERK_KEYS:
            old[k] = v
    old["geo_key"] = None
    tr.locate(old)
    if ai.enabled and s.get("background"):
        print("  Rating fit with the AI...", end="", flush=True)
    t0 = time.time()
    old["fit_score"], old["fit_notes"] = scoring.fit(old, s, ai)
    if ai.enabled and s.get("background"):
        print(f" done ({time.time() - t0:.0f}s)")
    old["notes"] = ((str(old.get("notes") or "") + " ").lstrip() + f"Posting re-captured {today():%m/%d}.").strip()
    write_posting_file(old, url)
    tr.save()
    p = scoring.priority(old, s)
    print(f"\n  Updated #{old['id']}." + (f"  PRIORITY: {p}/100   ({scoring.breakdown(old, s)})" if p is not None else ""))
    if old.get("fit_notes"):
        print(f"  {str(old['fit_notes'])[:300]}")
    LAST["posting"] = posting_header(old, url) + (old.get("description") or "")


def looks_like_code(t) -> bool:
    """'data-analytics-activitymap-region-id' is a page attribute, not a job title."""
    t = str(t or "").strip()
    return not t or (" " not in t and bool(re.search(r"[-_.]", t))) or bool(re.fullmatch(r"[a-z0-9_-]+", t))


def use_hint(d, hint):
    if not hint:
        return d
    if hint.get("title") and (looks_like_code(d.get("title")) or d.get("_title_guess")
                              or hint.get("source") in ("Apple", "Google", "Workday", "Eightfold", "SuccessFactors",
                                                        "Phenom", "iCIMS", "Paylocity", "Oracle", "BambooHR", "Rippling", "Breezy", "Arup")):
        d["title"], d["_title_guess"] = hint["title"], False
    loc = str(hint.get("location") or "")
    if loc and not re.fullmatch(r"\d+ locations?", loc.strip(), re.I) and \
            (not d.get("location") or hint.get("source") in ("Google", "Phenom", "Paylocity", "iCIMS", "Arup")):
        d["location"] = loc
    if hint.get("source") == "Google" and d.get("source") != "Google Careers" and hint.get("title"):
        # Google's page also lists other search results: keep just this job's section (for pay, perks, fit)
        desc, t = d.get("description") or "", hint["title"]
        starts = [m.start() for m in re.finditer(re.escape(t), desc)]
        for st in reversed(starts):
            part = desc[st:st + 15000]
            if re.search(r"qualifications", part[:6000], re.I):
                d["description"] = part
                pm = parse_pay(part)
                d["pay_min"], d["pay_max"], d["pay_unit"] = pm if pm[0] else (None, None, None)
                break
    if hint.get("posted") and not d.get("posted"):
        d["posted"] = hint["posted"]
    if hint.get("company") and (not d.get("company") or d.get("_company_sure") is False):
        d["company"], d["_company_sure"] = hint["company"], True
    return d


def add_one(tr, ai, url, hint=None):
    s = tr.s
    existing = tr.find_by_link(url)
    if existing:
        print(f"\n  Already tracked: #{existing['id']} {existing.get('title')} @ {existing.get('company')} "
              f"(status: {existing.get('status') or 'Saved'})")
        bad = not looks_like_posting(existing.get("description"))
        opts = "  r = re-capture the posting (re-reads pay, perks, location, fit)"
        if bad:
            opts += "  <- recommended, the saved posting looks incomplete"
        print(opts)
        if existing.get("applied") != "Yes":
            print("  a = mark it as applied")
        v = ask("  Choose (Enter = leave it as is): ").lower()
        if v == "r":
            recapture(tr, ai, existing, url)
        elif v == "a" and existing.get("applied") != "Yes":
            mark_applied(existing)
            tr.save()
            print("  Updated. It's now on the Applied tab.")
        return

    d = get_posting(url, ai)
    if not d:
        return
    d = use_hint(d, hint)
    if looks_like_code(d.get("title")):
        d["title"] = None  # asked for below instead of saving junk
    job = {k: d.get(k) for k in POSTING_FIELDS}
    review(job, d, url, ai, tr)
    # A row added earlier from a confirmation email (same company, no link yet)? Fill it in instead of duplicating.
    cname = re.sub(r"[^a-z0-9]", "", str(job.get("company") or "").lower())
    for other in tr.jobs:
        oname = re.sub(r"[^a-z0-9]", "", str(other.get("company") or "").lower())
        if cname and oname and (cname in oname or oname in cname) and not other.get("link"):
            print(f"\n  You have #{other['id']} {other.get('title') or '(no title)'} @ {other.get('company')} "
                  f"(from your email, status {other.get('status')}).")
            if ask_yn("  Is this the same job? (y/n): "):
                for k in list(job):
                    if job.get(k) not in (None, "") and (other.get(k) in (None, "") or k in ("link", "description")):
                        other[k] = job[k]
                if str(other.get("next_action") or "").startswith("Add link"):
                    other["next_action"] = None if other.get("resume") else "Add resume version"
                other["fit_score"], other["fit_notes"] = scoring.fit(other, s, ai)
                other["geo_key"] = None
                write_posting_file(other, url)
                tr.save()
                print(f"  Filled in #{other['id']} with the posting details.")
                return
            break
    for other in tr.jobs:
        if str(other.get("company") or "").lower() == str(job.get("company") or "").lower() \
                and str(other.get("title") or "").lower() == str(job.get("title") or "").lower():
            print(f"  Note: you already have #{other['id']} with the same title at this company.")
            break

    applied = ask_yn("\n  Applied already? (y/n): ")
    job.update({"id": tr.next_id(), "date_added": today(), "last_update": today()})
    if d.get("_ai_used"):
        job["notes"] = "Some details read by local AI; double-check."
    if applied:
        job["status"] = "Applied"
        mark_applied(job)
    else:
        job.update({"applied": "No", "status": "Saved"})
    t0 = time.time()
    if ai.enabled and s.get("background"):
        print("  Rating fit with the AI...", end="", flush=True)
    job["fit_score"], job["fit_notes"] = scoring.fit(job, s, ai)
    if ai.enabled and s.get("background"):
        print(f" done ({time.time() - t0:.0f}s)")
    tr.add(job)
    if not applied:
        p = scoring.priority(job, s)
        print(f"\n  PRIORITY: {p}/100   ({scoring.breakdown(job, s)})")
        if job.get("fit_notes"):
            print(f"  {job['fit_notes'][:300]}")

    header = posting_header(job, url)
    write_posting_file(job, url)

    tr.save()
    print(f"  Saved as #{job['id']} on the {'Applied' if applied else 'To Apply'} tab.")
    LAST["posting"] = header + (job.get("description") or "")
    if not applied and yes(s.get("copy_desc")):
        clip = clipboard_get().strip()
        if URL_RE.fullmatch(clip or "x") and norm_url(clip) != norm_url(url):
            # You've already copied your next link: don't overwrite it.
            print("  (Not copying the posting so your next link stays on the clipboard. Type  c  at the next prompt to copy it.)")
        else:
            clipboard_set(LAST["posting"])
            print("  The posting is copied. Paste it into your AI chat or notes to tailor your resume.")


def main():
    print("=" * 60 + f"\n  ADD JOB                         Job Tracker update {__import__('common').APP_VERSION}\n" + "=" * 60)
    tr = Tracker()
    s = tr.s
    ai = AI(s)
    print(f"  AI helper: {'on (' + ai.model + ')' if ai.enabled else 'off - ' + ai.reason}")
    if not s.get("target_pay"):
        print("  Tip: fill in the yellow cells on the Settings tab for better priority scores.")
    used = set()
    while True:
        clip = clipboard_get().strip()
        clip_url = clip if URL_RE.fullmatch(clip or "x") and clip not in used else ""
        prompt = "\n  Paste a job link"
        if clip_url:
            short = clip_url if len(clip_url) < 70 else clip_url[:67] + "..."
            prompt += f" (Enter = copied link {short})"
        v = ask(prompt + (", c to copy the last posting" if LAST["posting"] else "") + ", or q to quit: ", clip_url)
        if v.lower() in ("q", "quit", "exit"):
            break
        if v.lower() == "c" and LAST["posting"]:
            clipboard_set(LAST["posting"])
            print("  Copied the last posting.")
            continue
        urls = URL_RE.findall(v)
        if not urls:
            print("  That doesn't look like a link.")
            continue
        for u in urls:
            try:
                add_one(tr, ai, u.rstrip(").,"))
            except KeyboardInterrupt:
                print("\n  Skipped.")
        used.update(urls)
    print("  Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        sys.exit(0)
