"""Priority scoring.

Two copies of the same math live here:
  * excel_formulas(r): the formulas written into the spreadsheet, so editing a cell re-scores instantly.
  * the Python functions below: used by the scripts to print scores and sort the To Apply tab.
They must stay identical (test_scoring checks this against a real recalculation).
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal

from common import L, num, split_list, today, to_date


# ------------------------------------------------------------------ Excel formulas
def excel_formulas(r: int) -> dict:
    c = {k: f"{L(k)}{r}" for k in (
        "id", "posted", "deadline", "location", "work_mode", "office_days", "pay_min", "pay_max", "pay_unit", "total_comp",
        "applied", "fit_score", "loc_score", "pay_score", "perks_score", "signon", "bonus_pct", "bonus_amt", "k401",
        "relocation", "equity", "esop", "health", "pto", "gym", "stipend", "other_perks", "area_type", "miles",
        "area_bonus")}
    pay_rng = f"{L('pay_min')}{r}:{L('pay_max')}{r}"
    od, mode, at, mi = c["office_days"], c["work_mode"], c["area_type"], c["miles"]
    relo = f'{c["relocation"]}="Yes"'
    base = (f'IF(NOT(ISNUMBER({od})),IF({mode}="Hybrid",LOC_HYBRID,LOC_ONSITE),'
            f'CHOOSE(MIN(5,MAX(0,ROUND({od},0)))+1,LOC_REMOTE,LOC_D1,LOC_D2,LOC_D3,LOC_D4,LOC_ONSITE))')
    days = f'IF(ISNUMBER({od}),MIN(5,MAX(0,{od})),IF({mode}="Hybrid",3,5))'
    floor = f'(LOC_ELSE+IF({relo},RELO_ELSE,0))'  # a preferred place never scores below 'anywhere else'
    pen = (f'IF(ISNUMBER({mi}),MAX(0,MIN(1,({mi}-COMMUTE_FREE)/MAX(1,HOME_RADIUS-COMMUTE_FREE)))'
           f'*COMMUTE_PEN*{days}/5,0)')
    loc = (f'=IF({mode}="Remote",LOC_REMOTE,'
           f'IF(AND({mode}="",NOT(ISNUMBER({od})),{c["location"]}=""),LOC_UNKNOWN,'
           f'IF({at}="Home",MAX(0,{base}-{pen}),'
           f'IF({at}="Area",MIN(10,MAX({floor},{base}+N({c["area_bonus"]})+IF({relo},RELO_AREA,0))),'
           f'IF({at}="Region",MIN(10,MAX({floor},{base}-REGION_PEN+IF({relo},RELO_AREA,0))),'
           f'IF({at}="Elsewhere",MIN(10,{floor}),'
           f'LOC_UNKNOWN))))))')
    comp = (f'=IF(COUNT({pay_rng})=0,"",AVERAGE({pay_rng})*IF(OR(LEFT({c["pay_unit"]},1)="H",AVERAGE({pay_rng})<300),2080,1)'
            f'*(1+N({c["bonus_pct"]})+N({c["k401"]}))+N({c["bonus_amt"]})+N({c["signon"]})/MAX(1,SIGNON_YEARS))')
    mn = 'IF(AND(N(MIN_PAY)>0,N(MIN_PAY)<N(TARGET_PAY)),N(MIN_PAY),N(TARGET_PAY)*0.7)'
    pay = (f'=IF({c["total_comp"]}="",PAY_NONE,IF(N(TARGET_PAY)<=0,5,'
           f'MAX(0,MIN(10,10*({c["total_comp"]}-{mn})/(N(TARGET_PAY)-{mn})))))')
    perks = (f'=MIN(10,IF({c["equity"]}="Yes",P_EQUITY,0)+IF({c["esop"]}="Yes",P_ESOP,0)'
             f'+IF({c["health"]}="Yes",P_HEALTH,0)'
             f'+IF(OR({c["k401"]}="Yes",N({c["k401"]})>0),P_401K,0)'
             f'+IF(OR({c["pto"]}="Unlimited",AND(ISNUMBER({c["pto"]}),N({c["pto"]})>=PTO_MIN)),P_PTO,0)'
             f'+IF({c["gym"]}="Yes",P_GYM,0)+IF({c["stipend"]}="Yes",P_STIPEND,0)'
             f'+IF({c["other_perks"]}<>"",P_OTHER,0))')
    prio = (f'=IF(OR({c["id"]}="",{c["applied"]}="Yes"),"",'
            f'ROUND((W_LOC*{c["loc_score"]}+W_PAY*{c["pay_score"]}'
            f'+W_FIT*IF(ISNUMBER({c["fit_score"]}),{c["fit_score"]},5)+W_PERKS*{c["perks_score"]})'
            f'/MAX(0.0001,W_LOC+W_PAY+W_FIT+W_PERKS)*10,0))')
    days = f'=IF(ISNUMBER({c["deadline"]}),{c["deadline"]}-TODAY(),"")'
    ago = f'=IF(ISNUMBER({c["posted"]}),MAX(0,TODAY()-{c["posted"]}),"")'
    s, bp, ba, k, o = c["signon"], c["bonus_pct"], c["bonus_amt"], c["k401"], c["other_perks"]
    summary = ("=TRIM(MID("
               f'IF(ISNUMBER({s}),"· Sign-on $"&TEXT({s},"#,##0")&" ",IF({s}="Yes","· Sign-on bonus ",""))'
               f'&IF(ISNUMBER({bp}),"· Bonus "&ROUND({bp}*100,1)&"% ",IF({bp}="Yes","· Bonus ",""))'
               f'&IF(ISNUMBER({ba}),"· Bonus $"&TEXT({ba},"#,##0")&" ","")'
               f'&IF(ISNUMBER({k}),"· 401k "&ROUND({k}*100,1)&"% ",IF({k}="Yes","· 401k match ",""))'
               f'&IF({c["relocation"]}="Yes","· Relocation ","")'
               f'&IF({c["equity"]}="Yes","· Equity ","")'
               f'&IF({c["esop"]}="Yes","· Employee-owned ","")'
               f'&IF({c["health"]}="Yes","· Strong health ","")'
               f'&IF(ISNUMBER({c["pto"]}),"· "&{c["pto"]}&" days PTO ",IF({c["pto"]}="Unlimited","· Unlimited PTO ",""))'
               f'&IF({c["gym"]}="Yes","· Gym/wellness ","")'
               f'&IF({c["stipend"]}="Yes","· WFH stipend ","")'
               f'&IF({o}<>"","· "&{o}&" ","")'
               ",3,1000))")
    return {"loc_score": loc, "total_comp": comp, "pay_score": pay, "perks_score": perks,
            "priority": prio, "days_left": days, "days_posted": ago, "perks": summary}


# ------------------------------------------------------------------ Python mirror
def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _N(v):
    return float(v) if _isnum(v) else 0.0


def _eq(v, word):
    """Excel's  cell="Yes"  (case-insensitive, exact)."""
    return isinstance(v, str) and v.lower() == word.lower()


def _blank(v):
    return v is None or v == ""


def rhu(x, nd=0):
    q = Decimal(1).scaleb(-nd)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def S(s, key):
    return num(s.get(key), 0.0)


def loc_score(j, s):
    mode, od, loc = j.get("work_mode"), j.get("office_days"), j.get("location")
    at, mi, relo = j.get("area_type"), j.get("miles"), _eq(j.get("relocation"), "Yes")
    if _eq(mode, "Remote"):
        return S(s, "loc_remote")
    if _blank(mode) and not _isnum(od) and _blank(loc):
        return S(s, "loc_unknown")
    if not _isnum(od):
        base = S(s, "loc_hybrid") if _eq(mode, "Hybrid") else S(s, "loc_onsite")
    else:
        base = S(s, ["loc_remote", "loc_d1", "loc_d2", "loc_d3", "loc_d4", "loc_onsite"][int(min(5, max(0, rhu(od))))])
    if _eq(at, "Home"):
        days = min(5, max(0, od)) if _isnum(od) else (3 if _eq(mode, "Hybrid") else 5)
        pen = 0.0
        if _isnum(mi):
            free, rad = S(s, "commute_free"), S(s, "home_radius")
            pen = max(0.0, min(1.0, (mi - free) / max(1, rad - free))) * S(s, "commute_pen") * days / 5
        return max(0.0, base - pen)
    floor = S(s, "loc_else") + (S(s, "relo_else") if relo else 0)  # preferred places never score below 'anywhere else'
    if _eq(at, "Area"):
        return min(10.0, max(floor, base + _N(j.get("area_bonus")) + (S(s, "relo_area") if relo else 0)))
    if _eq(at, "Region"):
        return min(10.0, max(floor, base - S(s, "region_pen") + (S(s, "relo_area") if relo else 0)))
    if _eq(at, "Elsewhere"):
        return min(10.0, floor)
    return S(s, "loc_unknown")


def total_comp(j, s):
    vals = [float(v) for v in (j.get("pay_min"), j.get("pay_max")) if _isnum(v)]
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    mult = 2080 if str(j.get("pay_unit") or "")[:1].lower() == "h" or avg < 300 else 1
    return (avg * mult * (1 + _N(j.get("bonus_pct")) + _N(j.get("k401"))) + _N(j.get("bonus_amt"))
            + _N(j.get("signon")) / max(1, S(s, "signon_years")))


def pay_score(j, s):
    c = total_comp(j, s)
    if c is None:
        return S(s, "pay_none")
    tgt, mnp = S(s, "target_pay"), S(s, "min_pay")
    if tgt <= 0:
        return 5.0
    mn = mnp if 0 < mnp < tgt else tgt * 0.7
    return max(0.0, min(10.0, 10 * (c - mn) / (tgt - mn)))


def perks_score(j, s):
    k, pto = j.get("k401"), j.get("pto")
    pts = ((S(s, "p_equity") if _eq(j.get("equity"), "Yes") else 0)
           + (S(s, "p_esop") if _eq(j.get("esop"), "Yes") else 0)
           + (S(s, "p_health") if _eq(j.get("health"), "Yes") else 0)
           + (S(s, "p_401k") if (_eq(k, "Yes") or _N(k) > 0) else 0)
           + (S(s, "p_pto") if (_eq(pto, "Unlimited") or (_isnum(pto) and pto >= S(s, "pto_min"))) else 0)
           + (S(s, "p_gym") if _eq(j.get("gym"), "Yes") else 0)
           + (S(s, "p_stipend") if _eq(j.get("stipend"), "Yes") else 0)
           + (S(s, "p_other") if not _blank(j.get("other_perks")) else 0))
    return min(10.0, pts)


def priority(j, s):
    if _blank(j.get("id")) or _eq(j.get("applied"), "Yes"):
        return None
    fit = j.get("fit_score") if _isnum(j.get("fit_score")) else 5
    w = [S(s, k) for k in ("w_loc", "w_pay", "w_fit", "w_perks")]
    tot = (w[0] * loc_score(j, s) + w[1] * pay_score(j, s) + w[2] * fit + w[3] * perks_score(j, s))
    return int(rhu(tot / max(0.0001, sum(w)) * 10))


def days_since_posted(j):
    d = to_date(j.get("posted"))
    return max(0, (today() - d).days) if isinstance(d, dt.date) else None


def days_left(j):
    d = to_date(j.get("deadline"))
    return (d - today()).days if isinstance(d, dt.date) else None


def perks_summary(j) -> str:
    parts = []
    sg, bp, ba, k, pto = (j.get(x) for x in ("signon", "bonus_pct", "bonus_amt", "k401", "pto"))
    if _isnum(sg):
        parts.append(f"Sign-on ${sg:,.0f}")
    elif _eq(sg, "Yes"):
        parts.append("Sign-on bonus")
    if _isnum(bp):
        parts.append(f"Bonus {rhu(bp * 100, 1):g}%")
    elif _eq(bp, "Yes"):
        parts.append("Bonus")
    if _isnum(ba):
        parts.append(f"Bonus ${ba:,.0f}")
    if _isnum(k):
        parts.append(f"401k {rhu(k * 100, 1):g}%")
    elif _eq(k, "Yes"):
        parts.append("401k match")
    for key, label in (("relocation", "Relocation"), ("equity", "Equity"), ("esop", "Employee-owned"),
                       ("health", "Strong health")):
        if _eq(j.get(key), "Yes"):
            parts.append(label)
    if _isnum(pto):
        parts.append(f"{pto:g} days PTO")
    elif _eq(pto, "Unlimited"):
        parts.append("Unlimited PTO")
    for key, label in (("gym", "Gym/wellness"), ("stipend", "WFH stipend")):
        if _eq(j.get(key), "Yes"):
            parts.append(label)
    if not _blank(j.get("other_perks")):
        parts.append(str(j["other_perks"]))
    return " · ".join(parts)


def to_apply_sort_key(j, s):
    p = priority(j, s) or 0
    dl = days_left(j)
    expired = dl is not None and dl < 0
    boost = 15 if dl is not None and 0 <= dl <= 3 else (7 if dl is not None and 0 <= dl <= 7 else 0)
    d = to_date(j.get("date_added"))
    return (1 if expired else 0, -(p + boost), -(d.toordinal() if isinstance(d, dt.date) else 0))


# ------------------------------------------------------------------ fit (Python only; stored as a value)
# Sentences about benefits, EEO, legal and pay say nothing about fit ("medical, dental and vision" is not a medical job)
BOILER = re.compile(r"insurance|dental|vision\b|401\s?\(?k|equal (employment )?opportunit|\beeo\b|veteran|disabilit|"
                    r"paid time off|\bpto\b|holiday|benefits? (package|program|include)|reasonable accommodation|e-verify|"
                    r"background check|drug screen|privacy|cookie|sign in|apply now|pay range|base pay|compensation|"
                    r"salary|wellness|parental leave|tuition|stock purchase|retirement", re.I)
REQ_HEAD = re.compile(r"^\W*(minimum|basic|required|preferred|key|your|desired)?\s*(qualifications?|requirements?|skills)\b|"
                      r"what you(?:'|’)?ll (need|bring)|what we(?:'|’)?re looking for|who you are|you (have|bring)|about you|"
                      r"must have|nice to have", re.I)
RESP_HEAD = re.compile(r"^\W*(responsibilities|what you(?:'|’)?ll do|what you will do|the role|role overview|job description|"
                       r"duties|your impact|primary impact|day.to.day|as a .{3,60}, you will)", re.I)
DEFAULT_SENIOR_WORDS = ("Senior, Sr, Snr, Staff, Principal, Prin, Princ, Lead, Leader, Manager, Mgr, Director, Dir, Head of, "
                        "Chief, Vice President, VP, SVP, EVP, Distinguished, Fellow")
DEFAULT_LEVEL_WORDS = "III, IV, V, VI, 3, 4, 5, 6, 7, 8, 9, Level 3, Level 4, Level 5, Grade 5, P4, P5, P6, L4, L5, L6, E4, E5, E6"
_TOK_L, _TOK_R = r"(?<![\w&/.+#-])", r"(?![\w&/+#]|-\w|\.\d)"  # a separate word: not part of V&V, II/III, 3D, 3-5, 2.5
RANGE_RX = re.compile(_TOK_L + r"([IVX]+|\d)\s*[/-]\s*([IVX]+|\d)" + _TOK_R + r"(?!\s*(?:\+|years?|yrs?|yoe)\b)", re.I)


def _lists(s=None):
    from common import split_list
    s = s or {}
    senior = split_list(s.get("watch_senior_words")) if s.get("watch_senior_words") is not None else split_list(DEFAULT_SENIOR_WORDS)
    levels = split_list(s.get("watch_level_words")) if s.get("watch_level_words") is not None else split_list(DEFAULT_LEVEL_WORDS)
    return senior, levels


def _level_rx(w):
    return re.compile(_TOK_L + re.escape(w.strip()).replace(r"\ ", r"\s*") + _TOK_R, re.I)


def senior_reason(title: str, s=None):
    """The word from your Settings lists that makes this title senior, or None."""
    t = str(title or "")
    senior, levels = _lists(s)
    lv = {x.strip().lower() for x in levels}
    for m in RANGE_RX.finditer(t):  # 'II/III' kept, 'III/IV' skipped: the lowest level decides
        if m.group(1).lower() in lv:
            return m.group(0)
    t = RANGE_RX.sub(" ", t)
    for w in senior:
        if _kw_rx(w).search(t):
            return w
    for w in levels:
        if _level_rx(w).search(t):
            return w
    return None


def is_senior_title(title: str, s=None) -> bool:
    return senior_reason(title, s) is not None


def title_has(term: str, title: str) -> bool:
    """Every word of the term appears in the title, in any order ('test engineer' matches 'Engineer, Test').
    In quotes ("product engineer") the words must appear together, in that order."""
    t = term.strip()
    if len(t) > 2 and t[0] in "\"“”'" and t[-1] in "\"“”'":
        words = [w for w in re.split(r"[\s/,]+", t[1:-1].strip()) if w]
        return bool(words) and bool(re.search(r"(?<![\w&])" + r"[\s,/-]+".join(re.escape(w) for w in words) + r"(?![\w&])",
                                              title or "", re.I))
    words = [w for w in re.split(r"[\s/,]+", term.strip()) if w]
    return bool(words) and all(_kw_rx(w).search(title or "") for w in words)


def _sentences(text):
    import perks
    return list(perks.sentences(text or ""))


def relevant_text(desc: str) -> str:
    return "\n".join(x for x in _sentences(desc) if not BOILER.search(x))


def focus_text(desc: str, limit=4500) -> str:
    """The parts of a posting that decide fit: responsibilities + qualifications (not 'About us' or benefits)."""
    lines = [l for l in (desc or "").splitlines() if l.strip()]
    resp = next((i for i, l in enumerate(lines) if len(l) < 90 and RESP_HEAD.search(l.strip())), None)
    req = next((i for i, l in enumerate(lines) if len(l) < 90 and REQ_HEAD.search(l.strip())), None)
    parts = []
    if resp is not None:
        parts.append("RESPONSIBILITIES:\n" + "\n".join(lines[resp + 1:resp + 25])[:1600])
    if req is not None:
        parts.append("QUALIFICATIONS:\n" + "\n".join(lines[req + 1:req + 45])[:3200])
    if not parts or sum(len(p) for p in parts) < 400:
        parts = [relevant_text(desc)[:limit]]
    return "\n\n".join(parts)[:limit]


YEARS_RX = re.compile(r"(\d{1,2})\s*(?:\+|or more)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?)", re.I)


def required_years(desc: str):
    """Fewest years of experience the posting requires (preferred/nice-to-have lines are ignored)."""
    best = None
    for x in _sentences(desc):
        if not re.search(r"experience|\bexp\b", x, re.I) or re.search(r"prefer|nice to have|bonus|\bplus\b|ideal", x, re.I):
            continue
        for m in YEARS_RX.finditer(x):
            n = int(m.group(1))
            if n <= 20:
                best = n if best is None else min(best, n)
    return best


def level_score(req, my_years, title="", s=None):
    if is_senior_title(title, s) if (s is None or str(s.get("watch_skip_senior") or "Yes").lower().startswith("y")) \
            else is_senior_title(title, {}):
        return 1.0
    if req is None:
        return None
    gap = req - my_years
    return 10.0 if gap <= 1 else 7.0 if gap <= 2 else 4.0 if gap <= 3 else 1.0 if gap <= 5 else 0.0


def _kw_rx(k):
    base = k.lower().strip()
    base = base[:-1] if len(base) > 4 and base.endswith("s") else base
    return re.compile(r"(?<!\w)" + re.escape(base).replace(r"\ ", r"[\s-]") + r"s?(?!\w)", re.I)


def keyword_score(title, desc, kws):
    """Title matches count most; mentions in benefits/legal text don't count; 5 strong matches = 10/10."""
    if not kws:
        return None, [], []
    rel = relevant_text(desc)
    credit, hits = 0.0, []
    for k in kws:
        rx = _kw_rx(k)
        if rx.search(title or ""):
            credit += 1.5
            hits.append(k + " (title)")
        else:
            n = len(rx.findall(rel))
            if n:
                credit += 1.0 if n >= 2 else 0.5
                hits.append(k)
    missing = [k for k in kws if not any(h.split(" (")[0] == k for h in hits)]
    return min(10.0, 10 * credit / min(len(kws), 5)), hits, missing


AI_FIT_SCHEMA = {
    "type": "object",
    "properties": {
        "role_match": {"type": "integer"}, "skills_match": {"type": "integer"}, "level_match": {"type": "integer"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string"},
    },
    "required": ["role_match", "skills_match", "level_match", "strengths", "gaps", "verdict"],
}
AI_FIT_GUIDE = """Score this job for this candidate. Use the whole 0-10 range; most jobs should NOT get 7-8.
role_match: 10 = exactly the kind of work the candidate wants; 7 = closely related; 4 = adjacent field
  (e.g. manufacturing, quality, field service for a design-minded engineer); 0 = different field (software-only, sales, clinical).
skills_match: how many of the job's REQUIRED qualifications the candidate clearly has. 10 = nearly all; 5 = about half; 2 = few.
level_match: 10 = entry level / new grad / up to ~3 years required; 6 = 4-5 years; 2 = 6-7 years; 0 = senior/staff/manager or 8+.
strengths: up to 3 short phrases (max 6 words each) naming specific overlaps (tools, domains, tasks).
gaps: up to 2 short phrases naming specific required things the candidate lacks. [] if none.
verdict: one sentence, max 15 words, saying whether it's worth applying and why."""


def fit(job: dict, s: dict, ai=None):
    """Returns (fit_score 0-10, notes). Combines: role/skills (AI), experience level (rules, else AI), keywords (rules)."""
    title, desc = str(job.get("title") or ""), str(job.get("description") or "")
    if len(desc) < 200:  # e.g. a job added from a confirmation email: nothing to judge yet
        if title and any(_kw_rx(d).search(title) for d in split_list(s.get("dealbreakers"))):
            return 0.0, "DEALBREAKER (in title)"
        return None, "Not scored yet: no posting text (run Add Job with the link, then Rescore Jobs)"
    low = f"{title}\n{desc}"
    # Dealbreakers: words checked against the TITLE only; phrases checked anywhere in the posting
    tb = [d for d in split_list(s.get("dealbreakers")) if _kw_rx(d).search(title)]
    pb = [d for d in split_list(s.get("deal_phrases")) if re.search(re.escape(d.lower()), low.lower())]
    my_years = num(s.get("my_years"), 2)
    req = required_years(desc)
    lvl = level_score(req, my_years, title, s)
    kw, hits, missing = keyword_score(title, desc, split_list(s.get("fit_keywords")))

    ai_res = None
    bg = str(s.get("background") or "").strip()
    if ai and ai.enabled and bg and desc:
        r = ai.json(AI_FIT_GUIDE + f"\n\nCANDIDATE ({my_years:g} years of experience):\n{bg}\n\n"
                    f"JOB: {title} at {job.get('company')}\n{focus_text(desc)}", AI_FIT_SCHEMA)
        if r and all(_isnum(r.get(k)) for k in ("role_match", "skills_match", "level_match")):
            ai_res = {k: max(0.0, min(10.0, float(r[k]))) for k in ("role_match", "skills_match", "level_match")}
            ai_res.update(strengths=[str(x)[:60] for x in (r.get("strengths") or [])[:3]],
                          gaps=[str(x)[:60] for x in (r.get("gaps") or [])[:2]], verdict=str(r.get("verdict") or "")[:140])

    # Relevance first (what the job is), then experience level scales it: a perfect-level job in the wrong
    # field stays low, and a perfect-field job that wants 8+ years drops.
    if ai_res:
        level = lvl if lvl is not None else ai_res["level_match"]
        relevance = (0.5 * ai_res["role_match"] + 0.3 * ai_res["skills_match"]
                     + 0.2 * (kw if kw is not None else ai_res["skills_match"]))
    else:
        level = lvl
        relevance = kw if kw is not None else 5.0
    level_factor = 0.4 + 0.06 * level if level is not None else 0.9
    score = relevance * level_factor

    bits = []
    if ai_res:
        bits.append(f"Role {ai_res['role_match']:g} · Skills {ai_res['skills_match']:g}")
    if level is not None:
        bits.append(f"Level {level:g}" + (f" (asks {req}+ yrs)" if req is not None else ""))
    if kw is not None:
        bits.append(f"Keywords {rhu(kw, 1):g}")
    notes = [" · ".join(bits)]
    if ai_res and ai_res["strengths"]:
        notes.append("+ " + ", ".join(ai_res["strengths"]))
    if ai_res and ai_res["gaps"]:
        notes.append("- " + ", ".join(ai_res["gaps"]))
    if ai_res and ai_res["verdict"]:
        notes.append("AI: " + ai_res["verdict"])
    if hits:
        notes.append("Matched: " + ", ".join(hits))
    if missing and not ai_res:
        notes.append("Missing: " + ", ".join(missing))
    if tb or pb:
        score = 0.0
        notes.insert(0, "DEALBREAKER: " + ", ".join(tb + pb) + (" (in title)" if tb else ""))
    return rhu(score, 1), " | ".join(n for n in notes if n)


def breakdown(j, s) -> str:
    fitv = j.get("fit_score") if _isnum(j.get("fit_score")) else 5
    return (f"location {rhu(loc_score(j, s), 1):g}, pay {rhu(pay_score(j, s), 1):g}, "
            f"fit {rhu(fitv, 1):g}, perks {rhu(perks_score(j, s), 1):g}  (each out of 10)")
