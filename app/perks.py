"""Reads perks, office days and the application deadline out of a job description.

How it works:
  1. Rules scan every sentence for clearly worded perks ("401(k) match up to 4%", "3 days a week in office").
  2. If the local AI is on, it reads the posting too and must copy the exact sentence behind each answer.
  3. Each AI answer is checked: the sentence must really be in the posting, the number must appear in it,
     the right keyword must be there, and it can't be negated ("relocation is not offered").
     Answers that fail are thrown away.
  4. Verified AI answers win; rules fill anything the AI missed.
"""
from __future__ import annotations

import datetime as dt
import re

from common import today

# ------------------------------------------------------------------ text helpers
NEG = re.compile(r"\b(no|not|n't|without|unavailable|unable|ineligible|cannot|none)\b|n't\b", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
NUMW = r"([1-5]|one|two|three|four|five)"
OFFICE = r"(?:in[- ](?:the[- ])?office|on[- ]?site|onsite|in[- ]person|at (?:the|our) (?:office|hub|campus))"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def sentences(text: str):
    for part in re.split(r"(?<=[.!?;])\s+|\n+|\s•\s|•", text or ""):
        p = part.strip(" -*\t")
        if len(p) > 3:
            yield p[:400]


def negated(sent: str, start: int, end: int) -> bool:
    win = sent[max(0, start - 45):end + 45]
    return bool(NEG.search(win)) and not re.search(r"no[- ]cost|not only|no matter|no later than", win, re.I)


def money(s: str):
    m = re.search(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|K)?\b", s)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) else v


def word_num(s):
    s = str(s).lower()
    return WORDNUM.get(s, None) if s in WORDNUM else (int(s) if s.isdigit() else None)


def parse_date(s: str):
    """Find a date in a sentence. Returns dt.date or None."""
    s2 = s.lower()
    m = re.search(r"(20\d\d)-(\d{1,2})-(\d{1,2})", s2)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", s2)
    if m:
        y = int(m.group(3)) if m.group(3) else None
        y = y + 2000 if y and y < 100 else y
        return _mk(y, int(m.group(1)), int(m.group(2)))
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?", s2)
    if m:
        return _mk(int(m.group(3)) if m.group(3) else None, MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+(20\d\d))?", s2)
    if m:
        return _mk(int(m.group(3)) if m.group(3) else None, MONTHS[m.group(2)], int(m.group(1)))
    return None


def _mk(y, mo, d):
    t = today()
    try:
        if y:
            return dt.date(y, mo, d)
        cand = dt.date(t.year, mo, d)
        return cand if cand >= t - dt.timedelta(days=60) else dt.date(t.year + 1, mo, d)
    except ValueError:
        return None


# ------------------------------------------------------------------ rules
P = {  # keyword patterns, also used to sanity-check AI answers
    "signon": re.compile(r"sign[- ]?on (bonus|incentive)|signing bonus|hiring bonus|joining bonus", re.I),
    "bonus": re.compile(r"\bbonus", re.I),
    "k401": re.compile(r"401\s?\(?k\)?|403\s?\(?b\)?|retirement (plan|savings|match|contribution)", re.I),
    "relocation": re.compile(r"relocat", re.I),
    "equity": re.compile(r"\bequity\b|stock options?|\brsus?\b|restricted stock|\bespp\b|employee stock purchase|stock grants?|"
                         r"stock awards?|ownership stake", re.I),
    "esop": re.compile(r"employee[- ]owned|\besop\b|employee stock ownership|employee[- ]ownership", re.I),
    "health": re.compile(r"health|medical|insurance|premium|coverage|benefits", re.I),
    "pto": re.compile(r"\bpto\b|paid time off|vacation|time off|leave", re.I),
    "gym": re.compile(r"\bgym\b|fitness|wellness|classpass|wellhub|gympass", re.I),
    "stipend": re.compile(r"stipend|allowance|reimburse|budget", re.I),
    "office": re.compile(OFFICE + r"|\boffice\b|hybrid|remote", re.I),
    "deadline": re.compile(r"apply by|deadline|accepted (through|until|till)|reviewed (through|until)|closing date|"
                           r"closes?\b|close on|open (through|until)|no later than|submit .{0,30}by", re.I),
}
NOT_EQUITY = re.compile(r"diversity|inclusion|pay equity|health equity|racial equity|\bequal|belonging|\bdei\b|de&i|"
                        r"equity,? (and|&) inclusion|social equity|private equity|equity research|equity analyst", re.I)
HEALTH_STRONG = re.compile(
    r"(100\s?%|fully|entirely|completely)\s*(?:employer[- ]|company[- ])?(?:paid|covered|funded|subsidi[sz]ed)"
    r"[^.]{0,50}(medical|health|insurance|premium|coverage|benefits)"
    r"|(medical|health|insurance|premiums?|coverage)[^.]{0,50}(100\s?%|fully|entirely)\s*(?:employer[- ]|company[- ])?"
    r"(?:paid|covered|funded)"
    r"|no[- ]cost (medical|health|insurance|coverage)|\$0 (premium|medical|health|deductible)"
    r"|(company|employer|we) (pays?|cover|covers) (100\s?%|all|the full|the entire|most)", re.I)
GYM_RE = re.compile(r"\bgym\b|fitness (stipend|reimbursement|membership|benefit|allowance|center|subsid|program)|"
                    r"wellness (stipend|program|reimbursement|allowance|benefit|subsid|budget)|on-?site fitness|"
                    r"classpass|wellhub|gympass", re.I)
STIPEND_RE = re.compile(r"(home[- ]office|remote[- ]work|work[- ]from[- ]home|wfh|internet|cell ?phone|phone|technology|tech|"
                        r"equipment|workspace|co-?working|remote)\s+(stipend|allowance|reimbursement|budget)", re.I)
OTHER_RE = [(re.compile(r"(4|four)[- ]day (work )?week", re.I), "4-day week"),
            (re.compile(r"\bpension\b", re.I), "Pension"),
            (re.compile(r"profit[- ]sharing", re.I), "Profit sharing"),
            (re.compile(r"student loan (repayment|assistance|contribution|paydown)", re.I), "Student loan help"),
            (re.compile(r"sabbatical", re.I), "Sabbatical")]


def rules(text: str) -> dict:
    """field -> (value, sentence)."""
    found = {}

    def put(k, v, sent):
        if k not in found and v not in (None, ""):
            found[k] = (v, sent)

    other = []
    for sent in sentences(text):
        low = sent.lower()
        # office days
        if "office_days" not in found and P["office"].search(sent):
            m = (re.search(NUMW + r"\s*(?:\+|or more)?\s*(?:-\s*[1-5]\s*)?(?:days?|x)\s*(?:per|a|/|each|every)\s*week\b"
                           r"[^.]{0,40}?" + OFFICE, low)
                 or re.search(OFFICE + r"[^.]{0,30}?\b" + NUMW + r"\s*\+?\s*(?:-\s*[1-5]\s*)?(?:days?|x)\s*"
                              r"(?:per|a|/|each|every)\s*week", low)
                 or re.search(r"\b" + NUMW + r"\s*days?\s*" + OFFICE, low)
                 or re.search(OFFICE + r"\s*" + NUMW + r"\s*days?\b", low))
            if m:
                n = word_num(m.group(1))
                if n:
                    put("office_days", n, sent)
            else:
                m = re.search(r"(monday|tuesday|wednesday|thursday|friday)s?\s*(?:-|–|through|thru|to)\s*"
                              r"(monday|tuesday|wednesday|thursday|friday)", low)
                if m and re.search(OFFICE + r"|\boffice\b", low):
                    n = WEEKDAYS.index(m.group(2)) - WEEKDAYS.index(m.group(1)) + 1
                    if 1 <= n <= 5:
                        put("office_days", n, sent)
        # sign-on
        m = P["signon"].search(sent)
        if m and not negated(sent, m.start(), m.end()):
            put("signon", money(sent) or "Yes", sent)
        # bonus (not sign-on)
        if not m:
            mb = (re.search(r"(\d{1,2}(?:\.\d+)?)\s?%\s*(?:of (?:base|salary)\s*)?(?:annual |target |performance |"
                            r"discretionary |annual target )*bonus", low)
                  or re.search(r"bonus[^.%$]{0,40}?(?:target|potential|opportunity|eligib\w*|of|up to|at)\s*(?:of\s*)?"
                               r"(?:up to\s*)?(\d{1,2}(?:\.\d+)?)\s?%", low))
            if mb and not negated(sent, mb.start(), mb.end()):
                put("bonus_pct", round(float(mb.group(1)) / 100, 4), sent)
            elif re.search(r"\b(annual|performance|quarterly|target|discretionary|year[- ]end)[- ]bonus|bonus "
                           r"(program|eligib|plan|potential|opportunit|structure)|eligible for (a |an )?bonus", low) \
                    and not negated(sent, 0, len(sent)):
                amt = money(sent) if re.search(r"bonus (of|up to)\s*\$", low) else None
                if amt and amt < 100000:
                    put("bonus_amt", amt, sent)
                else:
                    put("bonus_pct", "Yes", sent)
        # 401k
        m = P["k401"].search(sent)
        if m and re.search(r"match|contribut", low) and not negated(sent, m.start(), m.end()):
            pct = None
            mm = re.search(r"(\d{1,2}(?:\.\d+)?)\s?%\s*(?:match )?of (?:the first |your first |up to )?(\d{1,2}(?:\.\d+)?)\s?%", low)
            if mm:
                pct = float(mm.group(1)) * float(mm.group(2)) / 100
            else:
                mm = re.search(r"up to (\d{1,2}(?:\.\d+)?)\s?%", low)
                if mm:
                    pct = float(mm.group(1))
                else:
                    cands = [float(x) for x in re.findall(r"(\d{1,2}(?:\.\d+)?)\s?%", low) if 0 < float(x) <= 15]
                    pct = min(cands) if cands else None
            put("k401", round(pct / 100, 4) if pct else "Yes", sent)
        # relocation
        m = re.search(r"relocation (assistance|package|support|bonus|stipend|reimbursement|benefits?|allowance|"
                      r"(is )?(available|offered|provided))|offer(s|ing)? relocation|relocation\s*:\s*yes|"
                      r"(help|assist) (with )?relocat", low)
        if m and not negated(sent, m.start(), m.end()):
            put("relocation", "Yes", sent)
        # equity
        m = P["equity"].search(sent)
        if m and not NOT_EQUITY.search(sent[max(0, m.start() - 40):m.end() + 40]) and not negated(sent, m.start(), m.end()):
            put("equity", "Yes", sent)
        m = P["esop"].search(sent)
        if m and not negated(sent, m.start(), m.end()):
            put("esop", "Yes", sent)
        if HEALTH_STRONG.search(sent):
            put("health", "Yes", sent)
        # PTO
        m = re.search(r"unlimited (pto|paid time off|vacation|time off|leave)|flexible (pto|time off|vacation)|"
                      r"open (pto|vacation) policy|take the time (off )?you need", low)
        if m:
            put("pto", "Unlimited", sent)
        else:
            m = re.search(r"(\d{1,2})\+?\s*(days|weeks)\s*(?:of\s*)?(?:paid\s+)?(?:pto|paid time off|vacation|time off)", low) \
                or re.search(r"(?:pto|paid time off|vacation)\s*(?:of|:)?\s*(\d{1,2})\+?\s*(days|weeks)", low)
            if m:
                n = int(m.group(1)) * (5 if m.group(2) == "weeks" else 1)
                if 5 <= n <= 60:
                    put("pto", n, sent)
        m = GYM_RE.search(sent)
        if m and not negated(sent, m.start(), m.end()):
            put("gym", "Yes", sent)
        m = STIPEND_RE.search(sent)
        if m and not negated(sent, m.start(), m.end()):
            put("stipend", "Yes", sent)
        for rx, label in OTHER_RE:
            mo = rx.search(sent)
            if mo and label not in [o[0] for o in other] and not negated(sent, mo.start(), mo.end()):
                other.append((label, sent))
        # deadline
        if "deadline" not in found and P["deadline"].search(sent) and not re.search(r"open until filled", low):
            d = parse_date(sent)
            if d:
                put("deadline", d, sent)
    if other:
        found["other_perks"] = (", ".join(o[0] for o in other), other[0][1])
    return found


# ------------------------------------------------------------------ AI + verification
AI_FIELDS = {
    "office_days_per_week": "Days per week required in the office/on-site, as a number like '3'. '' if not stated or fully remote.",
    "sign_on_bonus": "Sign-on/signing bonus in dollars like '5000', 'yes' if mentioned without an amount, else ''.",
    "annual_bonus_percent": "Annual/target/performance bonus as a percent of salary, like '10'. 'yes' if a bonus is "
                            "mentioned without a percent. '' if none. Not the sign-on bonus.",
    "annual_bonus_amount": "Annual bonus in dollars if stated as an amount, like '5000'. Else ''.",
    "retirement_match_percent": "401(k)/403(b) employer match as a percent of salary, like '4'. 'yes' if a match is "
                                "mentioned without a percent. '' if no match is mentioned.",
    "relocation_assistance": "'yes' only if relocation help is offered. Else ''.",
    "equity": "'yes' if stock, RSUs, options, ESPP or equity compensation is offered. NOT 'diversity, equity and "
              "inclusion' or 'pay equity'. Else ''.",
    "employee_owned": "'yes' if the company is employee-owned or offers an ESOP. Else ''.",
    "strong_health_coverage": "'yes' only if the employer pays all or nearly all health premiums (e.g. 100% paid, "
                              "no-cost plan). Ordinary 'medical, dental, vision' is ''.",
    "pto_days": "Paid time off per year as a number of days like '20' (weeks x 5), or 'unlimited'. '' if not stated.",
    "gym_or_wellness": "'yes' if a gym, fitness or wellness stipend/membership/program is offered. Else ''.",
    "remote_work_stipend": "'yes' if a home-office, remote-work, internet or equipment stipend is offered. Else ''.",
    "other_perks": "Other genuinely notable perks, comma-separated, max 4, e.g. '4-day week, pension, profit sharing'. "
                   "Exclude standard medical/dental/vision, tuition, holidays and anything already covered. '' if none.",
    "application_deadline": "Last day to apply as YYYY-MM-DD if the posting states one. Else ''.",
    "base_pay_range": "Base salary or hourly pay range, numbers only, like '85000-105000 year' or '32-40 hour'. "
                      "'' if no pay is stated.",
}
FIELD_MAP = {"office_days_per_week": "office_days", "sign_on_bonus": "signon", "annual_bonus_percent": "bonus_pct",
             "annual_bonus_amount": "bonus_amt", "retirement_match_percent": "k401", "relocation_assistance": "relocation",
             "equity": "equity", "employee_owned": "esop", "strong_health_coverage": "health", "pto_days": "pto",
             "gym_or_wellness": "gym", "remote_work_stipend": "stipend", "other_perks": "other_perks",
             "application_deadline": "deadline", "base_pay_range": "pay"}
LABEL = {"office_days": "Office days", "signon": "Sign-on", "bonus_pct": "Bonus", "bonus_amt": "Bonus $", "k401": "401k",
         "relocation": "Relocation", "equity": "Equity", "esop": "Employee-owned", "health": "Health", "pto": "PTO",
         "gym": "Gym/wellness", "stipend": "WFH stipend", "other_perks": "Other", "deadline": "Deadline", "pay": "Pay"}


def _norm(s):
    return re.sub(r"[^a-z0-9%$]+", " ", str(s).lower()).strip()


def _quote_in_text(quote, text_norm, shingles):
    q = _norm(quote)
    if len(q) < 10:
        return False
    if q in text_norm:
        return True
    w = q.split()
    if len(w) < 4:
        return False
    qs = {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}
    return len(qs & shingles) / len(qs) >= 0.8


def _nums_in(s):
    out = set()
    for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k\b)?", s.lower()):
        v = float(m.group(1).replace(",", ""))
        out.add(v * 1000 if m.group(2) else v)
    for w, n in WORDNUM.items():
        if re.search(rf"\b{w}\b", s.lower()):
            out.add(float(n))
    return out


def _parse_val(v):
    v = str(v or "").strip().lower().replace("$", "").replace(",", "").replace("%", "")
    if v in ("", "no", "none", "n/a", "null", "false", "0"):
        return None
    if v in ("yes", "true"):
        return "yes"
    if v == "unlimited":
        return "unlimited"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(k)?$", v)
    if m:
        return float(m.group(1)) * (1000 if m.group(2) else 1)
    return v


def ai_extract(text: str, ai) -> dict:
    if not ai or not ai.enabled or not text:
        return {}
    props = {}
    for f, desc in AI_FIELDS.items():
        props[f] = {"type": "string", "description": desc}
        props[f + "_quote"] = {"type": "string", "description": "Exact sentence copied from the posting, or ''."}
    schema = {"type": "object", "properties": props, "required": list(props)}
    guide = "\n".join(f"- {k}: {v}" for k, v in AI_FIELDS.items())
    res = ai.json("Read this job posting and fill in each field. For every non-empty field, copy into <field>_quote "
                  "the exact sentence from the posting that states it. Use '' when the posting doesn't say. "
                  "Never guess.\n\nFIELDS:\n" + guide + "\n\nPOSTING:\n" + text[:9000], schema)
    if not res:
        return {}
    tn = _norm(text)
    tw = tn.split()
    shingles = {" ".join(tw[i:i + 3]) for i in range(len(tw) - 2)}
    out = {}
    for f, key in FIELD_MAP.items():
        if key == "pay":
            pv = _verify_pay(str(res.get(f) or ""), str(res.get(f + "_quote") or ""), tn, shingles)
            if pv:
                out["pay"] = (pv, str(res.get(f + "_quote"))[:300])
            continue
        v = _parse_val(res.get(f))
        quote = str(res.get(f + "_quote") or "").strip()
        if v is None or not quote or not _quote_in_text(quote, tn, shingles):
            continue
        ok = _verify(key, v, quote)
        if ok is not None:
            out[key] = (ok, quote[:300])
    return out


def _verify_pay(v, quote, tn, shingles):
    """'85000-105000 year' backed by a quote that really contains those numbers -> (min, max, unit)."""
    if not v or not quote or not _quote_in_text(quote, tn, shingles):
        return None
    nums = [float(x.replace(",", "")) * (1000 if k else 1) for x, k in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", v.lower())]
    nums = [n for n in nums if n >= 7]
    if not nums:
        return None
    qn = _nums_in(quote)
    if not all(any(abs(n - q) < 0.6 for q in qn) for n in nums):
        return None
    lo, hi = min(nums), max(nums)
    unit = "Hour" if ("hour" in v.lower() or lo < 300) else "Year"
    if (unit == "Year" and lo < 15000) or (unit == "Hour" and lo > 500):
        return None
    return (lo, hi, unit)


def _verify(key, v, quote):
    """Return the cleaned value if the quote supports it, else None."""
    low = quote.lower()
    nums = _nums_in(quote)

    def kw_ok(rx):
        m = rx.search(quote)
        return m and not negated(quote, m.start(), m.end())

    if key == "office_days":
        if isinstance(v, float) and 1 <= v <= 5 and v in nums and P["office"].search(quote):
            return int(v)
        return None
    if key in ("signon", "bonus_amt"):
        rx = P["signon"] if key == "signon" else P["bonus"]
        if not kw_ok(rx):
            return None
        if v == "yes":
            return "Yes" if key == "signon" else None
        return v if isinstance(v, float) and v in nums and 100 <= v <= 500000 else ("Yes" if key == "signon" else None)
    if key in ("bonus_pct", "k401"):
        rx = P["bonus"] if key == "bonus_pct" else P["k401"]
        if not kw_ok(rx):
            return None
        if key == "bonus_pct" and P["signon"].search(quote) and not re.search(r"annual|target|performance", low):
            return None
        if v == "yes":
            return "Yes"
        if isinstance(v, float) and 0 < v <= (60 if key == "bonus_pct" else 15):
            # the % itself, or a "50% of the first 6%" style product, must be backed by the sentence
            if v in nums or any(abs(a * b / 100 - v) < 0.01 for a in nums for b in nums):
                return round(v / 100, 4)
        return "Yes"
    if key == "pto":
        if not P["pto"].search(quote):
            return None
        if v == "unlimited":
            return "Unlimited" if re.search(r"unlimited|flexible|open|as much|time you need", low) else None
        if isinstance(v, float) and 5 <= v <= 60 and (v in nums or v / 5 in nums):
            return int(v)
        return None
    if key == "deadline":
        d = parse_date(quote)
        try:
            dv = dt.date.fromisoformat(str(v)[:10]) if not isinstance(v, float) else None
        except ValueError:
            dv = None
        if d and (dv is None or d == dv or (d.month, d.day) == (dv.month, dv.day)):
            return dv if dv and (d.month, d.day) == (dv.month, dv.day) else d
        return None
    if key == "other_perks":
        return str(v)[:80].strip(" ,").title() if isinstance(v, str) and len(v) > 2 else None
    # yes/no perks
    if v != "yes":
        return None
    checks = {"relocation": P["relocation"], "equity": P["equity"], "esop": P["esop"], "health": P["health"],
              "gym": P["gym"], "stipend": P["stipend"]}
    rx = checks.get(key)
    if not rx or not kw_ok(rx):
        return None
    if key == "equity" and NOT_EQUITY.search(quote):
        return None
    if key == "health" and not HEALTH_STRONG.search(quote) and not re.search(r"100\s?%|fully|no[- ]cost|\$0|free", low):
        return None
    return "Yes"


# ------------------------------------------------------------------ public
def enrich(job: dict, ai=None) -> dict:
    """Fill perk, office-day and deadline fields on a job dict (only blanks). Returns the job."""
    text = job.get("description") or ""
    if not text:
        return job
    r = rules(text)
    a = ai_extract(text, ai)
    merged, evidence = {}, []
    for key in LABEL:
        use_rule = key in r and key in a and a[key][0] == "Yes" and not isinstance(r[key][0], str)
        if key in a and not use_rule:  # verified AI answer, unless the rules found a more specific number
            merged[key] = a[key][0]
            evidence.append(f"[AI] {LABEL[key]}: \"{a[key][1][:180]}\"")
        elif key in r:
            merged[key] = r[key][0]
            evidence.append(f"[rule] {LABEL[key]}: \"{r[key][1][:180]}\"")
    pay = merged.pop("pay", None)
    if pay and not job.get("pay_min"):
        job["pay_min"], job["pay_max"], job["pay_unit"] = pay
    for k, v in merged.items():
        if job.get(k) in (None, ""):
            job[k] = v
    if evidence:
        job["evidence"] = "\n".join(evidence)
    od = job.get("office_days")
    if isinstance(od, (int, float)) and "office_days" in merged:
        job["work_mode"] = "On-site" if od >= 5 else "Hybrid"  # the posting's own words beat a generic tag
    return job
