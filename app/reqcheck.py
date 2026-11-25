"""Reads a posting's requirements: years of experience (with Master's substitution), which degree fields it accepts,
and required-skill dealbreakers. Used by Check Jobs (to grey out or hide postings), Add Job (a note) and the fit score.
Every word list lives on the Settings tab, so nothing here is specific to one kind of job."""
from __future__ import annotations

import re

from common import split_list

DEFAULT_PREF_WORDS = "preferred, nice to have, nice-to-have, bonus, a plus, desired, desirable, ideally, ideal candidate"
DEFAULT_MY_FIELDS = ("engineering, mechanical, MechE, ME, BSME, MSME, civil, structural, aerospace, mechatronics, robotics, "
                     "manufacturing, industrial, materials, biomedical, chemical, physics, mathematics, math, "
                     "quantitative field, technical field, technical degree, technical discipline, STEM")
DEFAULT_OTHER_FIELDS = ("computer science and engineering, electrical and computer engineering, computer science, "
                        "computer engineering, software engineering, electrical engineering, information systems, "
                        "information technology, computer information systems, CSE, ECE, CompE, CS, EE, CIS, MIS")

LEVELS = {"none": 0, "high school": 0, "associate": 0, "bachelor": 1, "bachelor's": 1, "bs": 1, "master": 2,
          "master's": 2, "ms": 2, "phd": 3, "doctorate": 3}
PHD = re.compile(r"(?i:\bph\.?\s?d\b|\bdoctora(?:te|l)\b)")
MASTER = re.compile(r"(?i:\bmaster(?:'|’)?s?\b|advanced degree|graduate degree|\bm\.?eng\b|\bmba\b)"
                    r"|\bM\.?S\.?(?![\w.])(?!\s*(?:Office|Excel|Word|Project|Teams|Access|Visio))|\bM\.?Sc\b|\bMSME\b")
BACHELOR = re.compile(r"(?i:\bbachelor(?:'|’)?s?\b|undergraduate degree|(?:4|four)[- ]year degree|\bb\.?eng\b)"
                      r"|\bB\.?S\.?(?![\w.])|\bB\.?Sc\b|\bB\.?A\.?(?![\w.])|\bBSME\b")
ANY_DEGREE = re.compile(r"\bdegree\b", re.I)
EXPERIENCE = re.compile(r"experience|\bexp\b|working|industry|professional|background|track record|in (?:a|an) .{0,30}role|"
                        r"demonstrated (?:ability|skill|success)|proven (?:ability|skill|success)",
                        re.I)
YEARS_DOING = re.compile(r"(?:years?|yrs?)\+?\s+(?:of|in|with|writing|designing|developing|building|working|doing|leading|"
                         r"managing|using|supporting|performing|hands-on)\b", re.I)
NOT_EXPERIENCE = re.compile(r"years? (?:old|of age|ago|warranty)|founded|anniversary|history of|in business|"
                            r"years? (?:of|in) (?:college|university|school|coursework|study|a degree)|"
                            r"for (?:over |more than )?\d+ years,? (?:we|our|the company)|within (?:the )?(?:past|last)",
                            re.I)
EQUIVALENT = re.compile(r"equivalent|in lieu|instead of a degree|without a degree|in place of (?:a )?degree", re.I)
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "twelve": 12, "fifteen": 15}
YEARS = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:\+|or more|plus)?\s*(?:(?:-|–|—|to)\s*(\d{1,2}(?:\.\d)?)\s*)?\+?\s*"
                   r"(?:years?|yrs?)(?![\s-]*(?:degree|program|college|university|course|bachelor|undergrad|accredited|"
                   r"B\.?S\b|B\.?A\b))", re.I)
RELATED = re.compile(r"(?:a |any )?(?:closely |other )?related (?:technical |engineering |quantitative |scientific )?"
                     r"(?:field|discipline|area|major|degree|subject)s?|similar (?:field|discipline)s?|"
                     r"equivalent (?:field|discipline|degree)s?|\bor related\b(?=\s*(?:[.,;)]|$))", re.I)
# an open-ended list ("ME, CE, EE, etc.", "e.g. CS or EE", "such as") isn't exclusive: treated like "or related field"
OPEN_LIST = re.compile(r"\betc\b\.?|\be\.\s?g\.|\bsuch as\b|\bfor example\b|\bincluding\b", re.I)
FIELD_CONTEXT = re.compile(r"(?i:degree|major|discipline|field of study|bachelor|master|ph\.?\s?d)|\bB\.?S\b|\bM\.?S\b")


def _norm(text: str) -> str:
    t = str(text or "")
    t = re.sub(r"\b(" + "|".join(WORD_NUM) + r")\s*\((\d{1,2})\)", r"\2", t, flags=re.I)       # "five (5) years" -> 5
    t = re.sub(r"\b(" + "|".join(WORD_NUM) + r")(?=\s*\+?\s*(?:or more\s+)?(?:years?|yrs?)\b)",
               lambda m: str(WORD_NUM[m.group(1).lower()]), t, flags=re.I)                       # "five years" -> 5
    t = re.sub(r"\((\d{1,2})\)\s*(?=\+?\s*years?)", r"\1 ", t)                                  # "(5) years"
    return t.replace("’", "'")


def _term_rx(term: str):
    """List words: lowercase = any case; with capitals (CS, EE, MechE) = exactly as typed, as a separate word."""
    t = term.strip()
    body = re.escape(t).replace(r"\ ", r"[\s-]+")
    flags = 0 if any(c.isupper() for c in t) else re.I
    return re.compile(r"(?<![\w&/])" + body + r"(?![\w&])", flags)


def _lines(desc: str, pref_words) -> list:
    """(line, is_preferred) pairs. A 'Preferred qualifications' heading marks the lines under it, until the next
    heading. Lines that end in 'or' (or start with it) are joined, so 'BS + 5 years OR MS + 3 years' stays one item."""
    pref_rx = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in pref_words) + r")\b", re.I) if pref_words else None
    raw = [l.strip(" \t•·*-–—►▪●") for l in _norm(desc).splitlines()]
    raw = [l for l in raw if l]
    merged = []
    for l in raw:
        if merged and (re.search(r"\b(?:or|OR)$", merged[-1]) or re.match(r"^(?:or|OR)\b", l)):
            merged[-1] = merged[-1] + " " + l
        else:
            merged.append(l)
    out, in_pref = [], False
    for l in merged:
        short = len(l) < 80
        heading = short and (l.endswith(":") or re.fullmatch(r"[A-Z][A-Za-z '&/()-]{2,60}", l) is not None)
        if heading:
            # 'Preferred Qualifications' marks what follows as optional; 'Required/Preferred Education and
            # Experience' does not (it mixes both, so each line decides for itself)
            in_pref = bool(pref_rx and pref_rx.search(l)) and not re.search(r"\b(?:required|requirements?|minimum|basic|must)\b", l, re.I)
            continue
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", l):
            out.append((sent, in_pref or bool(pref_rx and pref_rx.search(sent))))
    return out


def _degree_levels(seg: str) -> set:
    """Degree levels an option names: 1 Bachelor's, 2 Master's, 3 PhD. A plain 'degree' counts as Bachelor's."""
    lv = set()
    if PHD.search(seg):
        lv.add(3)
    if MASTER.search(seg):
        lv.add(2)
    if BACHELOR.search(seg) or (not lv and ANY_DEGREE.search(seg)):
        lv.add(1)
    return lv


def _yrs(v):
    """'3' -> 3, '2.5' -> 2.5"""
    f = float(v)
    return int(f) if f.is_integer() else f


def years_required(desc: str, my_level: int = 1, pref_words=None):
    """(years, label, quote): the most experience any REQUIRED line asks of someone with your degree, using the
    low end of ranges ('3-5 years' = 3) and the Master's/PhD option when the posting offers one you hold.
    (None, 'years not stated', '') when no required line states years."""
    pref_words = split_list(pref_words) if isinstance(pref_words, str) else (pref_words or split_list(DEFAULT_PREF_WORDS))
    best, quote, alt = None, "", None
    group = None  # [need, bs_need, quote]: one requirement plus its "OR ..." alternatives on the following lines

    def close(g):
        nonlocal best, quote, alt
        if g and (best is None or g[0] > best):
            best, quote = g[0], g[2]
            alt = g[1] if (g[1] is not None and g[1] > g[0]) else None

    for sent, pref in _lines(desc, pref_words):
        is_alt = bool(re.match(r"\s*or\b", sent, re.I))
        if not is_alt and group is not None and not pref and YEARS.search(sent):
            close(group)
            group = None
        if pref or not YEARS.search(sent) or NOT_EXPERIENCE.search(sent) or \
                not (EXPERIENCE.search(sent) or YEARS_DOING.search(sent)):
            continue
        need, bs_need = None, None
        if my_level >= 1 and re.search(r"associate(?:'|’)?s?\s+degree|two[- ]year degree", sent, re.I) and not _degree_levels(
                re.sub(r"(?i)associate(?:'|’)?s?\s+degree", " ", sent)):
            continue  # an associate's-degree path ("Associate's degree or its equivalent and 4+ years"): not yours
        # "MS or PhD in Engineering plus 3+ years": the years belong to both degrees, so don't split between them
        sent_j = re.sub(r"(?i)\b(B\.?S\.?|M\.?S\.?|B\.?A\.?|Bachelor(?:'|’)?s|Master(?:'|’)?s|Ph\.?D\.?)\s+or\s+"
                        r"(?=(?:B\.?S|M\.?S|B\.?A|Bachelor|Master|Ph\.?D)\b)", r"\1/", sent)
        for seg in re.split(r"\s(?:or|OR)\s|;\s*|\s/\s", sent_j):
            ys = [_yrs(m.group(1)) for m in YEARS.finditer(seg) if float(m.group(1)) <= 20]
            if not ys:
                continue
            if my_level >= 1 and (
                    re.search(r"in lieu|instead of a degree|without a degree|in place of (?:a )?degree", seg, re.I)
                    or re.search(r"(?:years?|yrs?)\b[^.;]{0,40}equivalent|equivalent[^.;]{0,15}(?:experience|work)", seg, re.I)
                    or (re.search(r"associate(?:'|’)?s?\s+degree|\bA\.?A\.?S?\b|two[- ]year degree", seg, re.I)
                        and not _degree_levels(seg))):
                continue  # "...or 6 years of equivalent experience" / an associate's-degree path: not yours
            levels = _degree_levels(seg)
            if not levels:  # "Master's degree in Computer or Electrical Eng... and 1+ year": the degree is earlier on
                whole = _degree_levels(sent)
                levels = whole if len(set(whole)) == 1 else levels
            y = min(ys)
            if levels and min(levels) > my_level:
                continue  # an option for a higher degree than yours
            need = y if need is None else min(need, y)
            if not levels or 1 in levels:
                bs_need = y if bs_need is None else min(bs_need, y)
        if is_alt and group is not None:
            # "OR Master's degree ... and 1+ year": the easier path you qualify for wins
            if need is not None:
                if group[0] is None or need < group[0]:
                    group[0] = need
            if bs_need is not None:
                group[1] = bs_need if group[1] is None else min(group[1], bs_need)
            continue
        if need is None:
            continue
        close(group)
        group = [need, bs_need, sent]
    close(group)
    if best is None:
        return None, "years not stated", ""
    label = f"asks {best}+ yrs" + (f" (BS: {alt}+)" if alt is not None else "")
    return best, label, quote


def field_check(desc: str, my_fields, other_fields):
    """'ok' (one of your fields, or a general one like 'engineering' or 'technical degree', is accepted),
    'leaning' (only other fields, but 'or related field' too), 'other_only', or None (no field stated).
    Returns (status, other fields named, quote)."""
    my = [_term_rx(t) for t in sorted(split_list(my_fields), key=len, reverse=True)]
    other = [(t, _term_rx(t)) for t in sorted(split_list(other_fields), key=len, reverse=True)]
    named, related, mine, quote = [], False, False, ""
    for sent in re.split(r"\n|(?<=[.!?;])\s+", _norm(desc)):
        if not FIELD_CONTEXT.search(sent):
            continue
        # the field part of a degree line comes before its experience part ("BS in CS and 3 years of engineering...")
        cut = re.search(r"\d+\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs)|\bexperience\b", sent, re.I)
        part = sent[:cut.start()] if cut and FIELD_CONTEXT.search(sent[:cut.start()]) else sent
        hit_other = False
        for name, rx in other:
            if rx.search(part):
                hit_other = True
                if name not in named:
                    named.append(name)
                part = rx.sub(" ", part)
        if RELATED.search(part) or OPEN_LIST.search(part):
            if hit_other:
                related = True
            part = OPEN_LIST.sub(" ", RELATED.sub(" ", part))
        if any(rx.search(part) for rx in my):
            mine = True
        elif hit_other and not quote:
            quote = sent.strip()
    if mine:
        return "ok", named, ""
    if not named:
        return None, [], ""
    return ("leaning" if related else "other_only"), named, quote


def skill_dealbreakers(desc: str, words, pref_words=None):
    """The first dealbreaker phrase found in a REQUIRED line, with that line."""
    words = split_list(words)
    if not words:
        return None, ""
    pref_words = split_list(pref_words) if isinstance(pref_words, str) else (pref_words or split_list(DEFAULT_PREF_WORDS))
    rxs = [(w, _term_rx(w)) for w in words]
    for sent, pref in _lines(desc, pref_words):
        if pref:
            continue
        for w, rx in rxs:
            if rx.search(sent):
                return w, sent
    return None, ""


def my_degree_level(s) -> int:
    v = str((s or {}).get("my_degree") or "Bachelor's").strip().lower()
    for k, lv in sorted(LEVELS.items(), key=lambda x: -len(x[0])):
        if v.startswith(k):
            return lv
    return 1


def _short(q: str, n: int = 90) -> str:
    q = re.sub(r"\s+", " ", q or "").strip().lstrip("-•*·–— ").strip()
    return f"“{q[:n]}…”" if len(q) > n else (f"“{q}”" if q else "")


SHORT_NAMES = {"computer science and engineering": "CSE", "electrical and computer engineering": "ECE",
               "computer science": "CS", "computer engineering": "CompE", "electrical engineering": "EE",
               "software engineering": "SWE", "information systems": "IS", "information technology": "IT",
               "computer information systems": "CIS"}


def _names(named):
    out = []
    for n in named:
        x = SHORT_NAMES.get(str(n).lower(), n)
        if x not in out:
            out.append(x)
    return "/".join(out[:3])


def check(desc: str, s) -> dict:
    """Everything Check Jobs needs about one posting:
    {'filtered': short reason or None, 'kind': 'experience'|'degree'|'skill'|None, 'requirements': label for the
     New Matches tab, 'evidence': the posting's own words}."""
    s = s or {}
    pref = s.get("watch_pref_words") if s.get("watch_pref_words") is not None else DEFAULT_PREF_WORDS
    my_fields = s.get("watch_my_fields") if s.get("watch_my_fields") is not None else DEFAULT_MY_FIELDS
    other_fields = s.get("watch_other_fields") if s.get("watch_other_fields") is not None else DEFAULT_OTHER_FIELDS
    max_years = s.get("watch_max_years")
    try:
        max_years = int(float(max_years)) if max_years not in (None, "") else 4
    except (TypeError, ValueError):
        max_years = 4
    years, ylabel, yquote = years_required(desc, my_degree_level(s), pref)
    status, named, fquote = field_check(desc, my_fields, other_fields)
    skill, squote = skill_dealbreakers(desc, s.get("watch_skill_dealbreakers"), pref)
    label = ylabel
    if status == "leaning":
        label += " · " + _names(named) + "-leaning"
    out = {"filtered": None, "kind": None, "requirements": label, "evidence": ""}
    if max_years and years is not None and years >= max_years:
        out.update(filtered=f"{ylabel} {_short(yquote)}", kind="experience", evidence=yquote)
    elif status == "other_only":
        out.update(filtered=f"degree: {_names(named)} only {_short(fquote)}", kind="degree", evidence=fquote)
    elif skill:
        out.update(filtered=f"requires {skill} {_short(squote)}", kind="skill", evidence=squote)
    return out


# ------------------------------------------------------------------ plain-text summary (jobs.csv for the resume builder)
FIELD_NAMES = ["Mechanical", "Electrical", "Aerospace", "Biomedical", "Industrial", "Manufacturing", "Materials",
               "Chemical", "Civil", "Systems", "Computer Science", "Computer", "Physics", "Mechatronics", "Robotics",
               "Optical", "Plastics", "Nuclear", "Engineering Technology", "Engineering"]
SKILL_TERMS = ["GD&T", "SolidWorks", "Creo", "NX", "CATIA", "AutoCAD", "Inventor", "Fusion 360", "Onshape", "CAD", "FEA",
               "ANSYS", "Abaqus", "COMSOL", "CFD", "MATLAB", "Simulink", "Python", "C++", "LabVIEW", "Minitab", "JMP",
               "DFM", "DFMEA", "PFMEA", "FMEA", "Six Sigma", "Lean", "SPC", "DOE", "root cause", "8D", "tolerance analysis",
               "tolerance stack", "injection molding", "CNC", "machining", "sheet metal", "additive manufacturing",
               "3D printing", "PLC", "ISO 13485", "ISO 9001", "FDA", "21 CFR", "design controls", "PLM", "Windchill",
               "Teamcenter", "SAP", "ERP", "test fixtures", "data acquisition", "statistical analysis", "ROS",
               "thermal analysis", "structural analysis", "vibration", "drawings", "BOM", "ECO", "CAPA", "validation",
               "verification"]


def summary(desc: str, s=None) -> str:
    """'Years: 3+; Degree: BS Mechanical/Aerospace; Skills: GD&T, Creo; Citizenship: US' from a posting's REQUIRED
    lines (preferred ones are left out). Parts that aren't stated are omitted."""
    if not desc:
        return ""
    s = s or {}
    pref = split_list(s.get("watch_pref_words")) or split_list(DEFAULT_PREF_WORDS)
    out = []
    y, label, _ = years_required(desc, my_degree_level(s), pref)
    if y is not None:
        m = re.search(r"\(BS: (\d+(?:\.\d)?)\+\)", label or "")
        out.append(f"Years: {y}+" + (f" (BS: {m.group(1)}+)" if m else ""))
    req = [sent for sent, is_pref in _lines(desc, pref) if not is_pref]
    deg = None
    for sent in req:
        if not (BACHELOR.search(sent) or MASTER.search(sent) or PHD.search(sent) or ANY_DEGREE.search(sent)):
            continue
        lv = _degree_levels(sent)
        if not lv:
            continue
        fields = []
        for f in FIELD_NAMES:
            if re.search(r"\b" + re.escape(f) + r"\b", sent, re.I) and not any(f in x for x in fields):
                fields.append(f)
        if "Engineering" in fields and len(fields) > 1:
            fields.remove("Engineering")
        deg = {1: "BS", 2: "MS", 3: "PhD"}[min(lv)] + (" " + "/".join(fields[:4]) if fields else "")
        if RELATED.search(sent) or OPEN_LIST.search(sent):
            deg += " (or related)"
        break
    if deg:
        out.append(f"Degree: {deg}")
    text = "\n".join(req)
    skills = [k for k in SKILL_TERMS if re.search(r"(?<![\w&+])" + re.escape(k) + r"(?![\w&+])", text,
                                                  0 if k.isupper() or len(k) <= 3 else re.I)]
    if skills:
        out.append("Skills: " + ", ".join(skills[:12]))
    cit = None
    if re.search(r"\b(?:top secret|TS/SCI|secret|security) clearance\b|\bactive (?:secret|TS)\b", desc, re.I):
        lvl = re.search(r"\b(TS/SCI|top secret|secret)\b", desc, re.I)
        cit = "US (clearance" + (f": {lvl.group(1)}" if lvl else "") + ")"
    elif re.search(r"\bU\.?S\.? citizen(?:ship)?\b(?! or)", desc, re.I) and not re.search(r"citizen(?:ship)? or (?:permanent|green)", desc, re.I):
        cit = "US"
    elif re.search(r"\bITAR\b|\bU\.?S\.? person\b|export control", desc, re.I):
        cit = "US person (ITAR)"
    if cit:
        out.append(f"Citizenship: {cit}")
    return "; ".join(out)
