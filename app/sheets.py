"""Builds and rewrites the workbook's sheets (layout, formulas, formatting)."""
from __future__ import annotations

import datetime as dt

from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from common import (COL, COLUMNS, GROUP_KEYS, H, JOB_TABS, KEYS, LEGACY_LABELS, SETTING_LABELS, SETTINGS,
                    STATUSES, TABLE_NAMES, L)

FONT = "Arial"
BODY = Font(name=FONT, size=10)
HDR_FILL = PatternFill("solid", fgColor="1F3A5F")
CALC_HDR_FILL = PatternFill("solid", fgColor="3E5C82")
HDR_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
THIN = Side(style="thin", color="D0D5DD")
INPUT_FILL = PatternFill("solid", fgColor="FFF4CC")
SECTION_FILL = PatternFill("solid", fgColor="E8EEF6")
TAB_COLORS = {"To Apply": "2E7D32", "Applied": "1565C0", "Closed": "9E9E9E"}
SLACK = 300  # rows below the data that keep dropdowns/colors for rows you type in by hand

STATUS_COLORS = {
    "Saved": ("F2F4F7", "475467"), "Applied": ("DCEBFF", "1849A9"), "Screening": ("EDE7FF", "5925DC"),
    "Assessment": ("FFF0D9", "B54708"), "Interview": ("FFE8C7", "93370D"), "Offer": ("D1FADF", "05603A"),
    "Rejected": ("FEE4E2", "912018"), "Withdrawn": ("F2F4F7", "98A2B3"), "Ghosted": ("F2F4F7", "98A2B3"),
    "Skipped": ("F2F4F7", "98A2B3"), "Declined": ("F2F4F7", "98A2B3"),
}
FORMATS = {
    "posted": "m/d/yy", "deadline": "m/d/yy", "date_applied": "m/d/yy", "last_update": "m/d/yy", "date_added": "m/d/yy",
    "pay_min": "[<300]$#,##0.00;$#,##0", "pay_max": "[<300]$#,##0.00;$#,##0", "total_comp": "$#,##0",
    "signon": "$#,##0", "bonus_amt": "$#,##0", "bonus_pct": "0.0%", "k401": "0.0%",
    "office_days": "0", "days_left": "0", "days_posted": "0", "priority": "0", "miles": "0",
    "fit_score": "0.0", "loc_score": "0.0", "pay_score": "0.0", "perks_score": "0.0",
}
YESNO_KEYS = ["applied", "relocation", "equity", "esop", "health", "gym", "stipend"]


def _hdr(ws, headers, widths):
    for i, h in enumerate(headers, 1):
        c = ws.cell(1, i, h)
        c.font, c.fill = HDR_FONT, HDR_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = widths[i - 1]
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


# ------------------------------------------------------------------ job tabs
def write_job_tab(wb, title, jobs, index, widths=None, group_hidden=True):
    from scoring import excel_formulas
    widths = widths or {}
    if title in wb.sheetnames:
        wb.remove(wb[title])
    ws = wb.create_sheet(title, index)
    ws.sheet_properties.tabColor = TAB_COLORS.get(title)
    ncol = len(COLUMNS)
    for i, (k, h, w, kind) in enumerate(COLUMNS, 1):
        c = ws.cell(1, i, h)
        c.font = HDR_FONT
        c.fill = CALC_HDR_FILL if kind == "calc" else HDR_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30

    for n, job in enumerate(jobs):
        r = n + 2
        f = excel_formulas(r)
        for k in KEYS:
            if k in f:
                ws.cell(r, COL[k], f[k])
                continue
            v = job.get(k)
            if v is None:
                continue
            if k == "description" and isinstance(v, str):
                v = v[:32000]
            cell = ws.cell(r, COL[k], v)
            if isinstance(v, str) and v.startswith("="):
                cell.data_type = "s"  # pasted text that starts with "=" stays text, never a formula
            if k == "link" and isinstance(v, str) and v.startswith("http"):
                cell.hyperlink = v
                cell.font = Font(name=FONT, size=10, color="0563C1", underline="single")
    last = max(2, len(jobs) + 1)

    # formats, fonts and alignment for data rows (+ slack rows)
    for k, fmt in FORMATS.items():
        col = COL[k]
        for r in range(2, last + 1):
            ws.cell(r, col).number_format = fmt
    for r in range(2, last + 1):
        ws.row_dimensions[r].height = 15  # keep rows one line tall even when hidden cells hold multi-line text
        ws.cell(r, COL["priority"]).font = Font(name=FONT, size=10, bold=True)
        for k in ("description", "email_log", "evidence"):
            ws.cell(r, COL[k]).alignment = Alignment(wrap_text=False, vertical="top")

    end = last + SLACK
    tab = Table(displayName=TABLE_NAMES[title], ref=f"A1:{get_column_letter(ncol)}{last}")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(tab)

    def dv(key, values):
        d = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
        d.add(f"{L(key)}2:{L(key)}{end}")
        ws.add_data_validation(d)

    dv("status", STATUSES)
    dv("work_mode", ["Remote", "Hybrid", "On-site"])
    dv("pay_unit", ["Year", "Hour"])
    for k in YESNO_KEYS:
        dv(k, ["Yes", "No"])

    st = L("status")
    for s, (bg, fg) in STATUS_COLORS.items():
        ws.conditional_formatting.add(f"{st}2:{st}{end}", CellIsRule(
            operator="equal", formula=[f'"{s}"'], fill=PatternFill("solid", fgColor=bg), font=Font(color=fg, bold=True)))
    pr = L("priority")
    rng = f"{pr}2:{pr}{end}"
    for cond, color in ((f"{pr}2>=70", "D1FADF"), (f"AND({pr}2>=45,{pr}2<70)", "FEF7C3"), (f"{pr}2<45", "F2F4F7")):
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f"AND(ISNUMBER({pr}2),{cond})"],
                                                       fill=PatternFill("solid", fgColor=color)))
    dl = L("days_left")
    ws.conditional_formatting.add(f"{dl}2:{dl}{end}", FormulaRule(
        formula=[f"AND(ISNUMBER({dl}2),{dl}2>=0,{dl}2<=3)"], fill=PatternFill("solid", fgColor="FEE4E2"),
        font=Font(color="B42318", bold=True)))
    ws.conditional_formatting.add(f"{dl}2:{dl}{end}", FormulaRule(
        formula=[f"AND(ISNUMBER({dl}2),{dl}2<0)"], font=Font(color="98A2B3", strike=True)))
    dp = L("days_posted")  # fresh postings green, a month or older grey
    ws.conditional_formatting.add(f"{dp}2:{dp}{end}", FormulaRule(
        formula=[f"AND(ISNUMBER({dp}2),{dp}2<=7)"], fill=PatternFill("solid", fgColor="D1FADF"), font=Font(color="05603A")))
    ws.conditional_formatting.add(f"{dp}2:{dp}{end}", FormulaRule(
        formula=[f"AND(ISNUMBER({dp}2),{dp}2>=30)"], font=Font(color="98A2B3")))
    na = L("next_action")
    ws.conditional_formatting.add(f"{na}2:{na}{end}", FormulaRule(
        formula=[f"LEN({na}2)>0"], font=Font(color="B42318", bold=True)))

    # widths + collapsed detail group
    for k, h, w, kind in COLUMNS:
        cd = ws.column_dimensions[L(k)]
        cd.width = widths.get(k, w)
        if k in GROUP_KEYS:
            cd.outlineLevel = 1
            cd.hidden = group_hidden
    ws.sheet_format.outlineLevelCol = 1
    ws.freeze_panes = "E2"
    return ws


# ------------------------------------------------------------------ settings
def build_settings(wb, old_values=None, index=None):
    old_values = old_values or {}
    if "Settings" in wb.sheetnames:
        index = wb.sheetnames.index("Settings") if index is None else index
        wb.remove(wb["Settings"])
    se = wb.create_sheet("Settings", index)
    _hdr(se, ["Setting", "Your value", "What it does"], [52, 40, 80])
    r = 2
    for key, label, default, help_, fill, name in SETTINGS:
        if key == H:
            if r > 2:
                r += 1
            c = se.cell(r, 1, label)
            c.font = Font(name=FONT, bold=True, size=10, color="1F3A5F")
            for i in range(1, 4):
                se.cell(r, i).fill = SECTION_FILL
            r += 1
            continue
        se.cell(r, 1, label).font = BODY
        v = se.cell(r, 2, old_values.get(key, default))
        v.font = Font(name=FONT, size=10, color="0000FF")
        v.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        if fill:
            v.fill = INPUT_FILL
        if key in ("target_pay", "min_pay"):
            v.number_format = "$#,##0"
        if key == "background":
            v.alignment = Alignment(wrap_text=True, vertical="top")
            se.row_dimensions[r].height = 60
        hc = se.cell(r, 3, help_)
        hc.font = Font(name=FONT, size=9, color="667085")
        hc.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    se.cell(r, 1, "Yellow cells are yours to fill in; blue values can be changed any time. "
                  "Don't rename or reorder column A - the tracker finds settings by these labels.").font = \
        Font(name=FONT, size=9, italic=True, color="667085")
    return se


def define_names(wb):
    """(Re)create the named cells the formulas use, by finding each label on the Settings sheet."""
    se = wb["Settings"]
    rows = {}
    for row in se.iter_rows(min_row=1, max_col=1):
        lab = str(row[0].value or "").strip()
        if lab in SETTING_LABELS:
            rows[SETTING_LABELS[lab]] = row[0].row
    for key, _, _, _, _, name in SETTINGS:
        if name and key in rows:
            wb.defined_names[name] = DefinedName(name, attr_text=f"Settings!$B${rows[key]}")
    if "PREF_LOCS" in wb.defined_names:
        del wb.defined_names["PREF_LOCS"]


# ------------------------------------------------------------------ other sheets
HOW_TO = [
    ("JOB TRACKER: QUICK GUIDE", "title"),
    ("", None),
    ("THE TABS", "h"),
    ("To Apply - jobs you haven't applied to yet, best first. Jobs closing within 3 days get a boost and a red Days Left.", None),
    ("Applied - jobs in progress. Anything with a Next Action is at the top.", None),
    ("Closed - Rejected, Ghosted, Withdrawn, Skipped (decided not to apply) and Declined.", None),
    ("Jobs move between tabs automatically every time you run Add Job or Check Email.", None),
    ("To move one yourself: change its Status or Applied? cell. It moves on the next run.", None),
    ("", None),
    ("ADD A JOB", "h"),
    ("Copy the job link > double-click Add Job > press Enter > answer 'Applied already?' (y/n).", None),
    ("If a site blocks reading (Indeed often does), select the whole posting in your browser (Cmd+A, Cmd+C) and press Enter.", None),
    ("From your phone: email the link to yourself with 'job' in the subject ('job applied' if you applied). Check Email adds it.", None),
    ("", None),
    ("PRIORITY (0-100, To Apply only)", "h"),
    ("A weighted mix of four 0-10 scores: Location, Pay, Fit and Perks. Weights and every score value are on the Settings tab.", None),
    ("Location: remote scores 10. Otherwise it depends on WHERE (the Area column) and office days per week:", None),
    ("   Home = within your max commute (long commutes lose a little); Area = a preferred area on the Areas tab", None),
    ("   (no moving penalty, + its extra points); Region = elsewhere in your preferred states; Elsewhere = low.", None),
    ("   Relocation help adds points outside Home. A '?' in Area means the Location text wasn't recognized - fix it.", None),
    ("Pay uses Est. Total Comp = base + bonus + 401k match + sign-on bonus spread over 2 years.", None),
    ("Perks adds up points for equity, employee ownership, strong health coverage, 401k, PTO, gym, WFH stipend, other perks.", None),
    ("", None),
    ("FIXING A WRONG VALUE", "h"),
    ("Columns with a lighter header (Priority, Days Since Posted, Days Left, Est. Total Comp, Perks) are formulas - don't type in them. Days Since Posted is green for the first week; a month or older turns grey.", None),
    ("Click the [+] above the far-right columns to show the scoring details: each perk has its own cell.", None),
    ("Fix the cell (e.g. 401k Match 4%, Sign-on Bonus 5000, Relocation Yes) and Perks, Total Comp and Priority update instantly.", None),
    ("Perk Evidence shows the sentence each perk came from; [AI] = found by the local AI and checked against the posting.", None),
    ("", None),
    ("CHECK JOBS (job watcher)", "h"),
    ("Put the companies you care about on the Watchlist tab (name + careers link). Double-click Check Jobs to scan them.", None),
    ("New postings whose titles match your watch keywords, in places you'd consider, land on the New Matches tab", None),
    ("(yellow = found this run). Type numbers at the end to add jobs right away, or set Action to Add in Excel and the", None),
    ("next Check Jobs adds them; Dismiss hides one. Watch keywords/skip words/locations are on the Settings tab.", None),
    ("", None),
    ("CHECK EMAIL", "h"),
    ("Reads both Gmail accounts (read-only), moves Status forward, sets Next Action, adds jobs from confirmation emails,", None),
    ("suggests follow-ups and marks Ghosted after the days set on Settings. Every change is on the Activity Log tab;", None),
    ("anything it isn't sure about goes to Needs Review.", None),
    ("", None),
    ("TIPS", "h"),
    ("Close the tracker in Excel before running Add Job or Check Email. A backup is saved in app/backups before each change.", None),
    ("Sorting/filtering in Excel is safe: each tab is an Excel table, so whole rows always stay together.", None),
]


def build_how_to(wb):
    if "How To" in wb.sheetnames:
        wb.remove(wb["How To"])
    ht = wb.create_sheet("How To")
    ht.column_dimensions["A"].width = 120
    for i, (t, kind) in enumerate(HOW_TO, 1):
        c = ht.cell(i, 1, t)
        c.font = (Font(name=FONT, bold=True, size=14, color="1F3A5F") if kind == "title" else
                  Font(name=FONT, bold=True, size=11, color="1F3A5F") if kind == "h" else BODY)


def build_areas(wb):
    from common import AREA_DEFAULTS
    if "Areas" in wb.sheetnames:
        return
    ws = wb.create_sheet("Areas")
    _hdr(ws, ["Area name", "Center: \"City, ST\" (or a 2-letter state = whole state)", "Radius (miles)", "Extra points"],
         [22, 40, 14, 12])
    for i, (n, c, r, b) in enumerate(AREA_DEFAULTS, 2):
        for j, v in enumerate((n, c, r, b), 1):
            cell = ws.cell(i, j, v)
            cell.font = Font(name=FONT, size=10, color="0000FF")
            cell.fill = INPUT_FILL
    for i in range(len(AREA_DEFAULTS) + 2, 31):
        for j in range(1, 5):
            ws.cell(i, j).fill = INPUT_FILL
    notes = ["Preferred areas you'd move to (no penalty for moving). A job inside one scores like a local job:",
             "its office-days score + Extra points (+ the relocation-help bonus if offered).",
             "Your home and commute radius are on the Settings tab; other states in your preferred region are there too.",
             "Order matters: a job counts toward the first row (top to bottom) it falls in.",
             "Examples:   Boston metro | Boston, MA | 40 | 1        Colorado | CO | (blank) | 0        SF Bay Area | Sunnyvale, CA | 45 | 0",
             "Add, remove or change rows any time; jobs are re-checked on the next Add Job / Check Email run."]
    for k, t in enumerate(notes):
        ws.cell(2 + k, 6, t).font = Font(name=FONT, size=9, italic=True, color="667085")
    ws.column_dimensions["F"].width = 95


WATCH_DEFAULTS = [  # examples for a new tracker, paused (Active = No): turn on the ones you want, or replace them
    ("Medtronic", "https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers", "", "No", "Example (medical devices): set Active = Yes to use"),
    ("SpaceX", "https://job-boards.greenhouse.io/spacex", "", "No", "Example (aerospace): set Active = Yes to use"),
    ("Boston Dynamics", "https://bostondynamics.wd1.myworkdayjobs.com/Boston_Dynamics", "", "No", "Example (robotics): set Active = Yes to use"),
    ("AECOM", "https://careers.smartrecruiters.com/AECOM2", "", "No", "Example (civil): set Active = Yes to use"),
    ("KLA", "https://kla.wd1.myworkdayjobs.com/Search", "", "No", "Example (semiconductors): set Active = Yes to use"),
]
WL_HEAD = ["Company", "Careers link", "Extra title keywords", "Active", "Priority", "My notes", "Where they post (auto)",
           "System", "Last checked", "Last result", "Feed (auto)"]
WL_KEYS = ["company", "url", "keywords", "active", "priority", "notes", "where", "system", "checked", "result", "feed"]
WL_INPUTS = 6  # yellow columns you fill in
NM_HEAD = ["Found", "Company", "Title", "Location", "Area", "Posted", "Days Ago", "Quick Fit", "Link", "Action", "Source", "Key"]
NM_KEYS = ["found", "company", "title", "location", "area", "posted", "ago", "quick", "link", "action", "source", "key"]


def read_watchlist(wb):
    """Read by header, so older layouts (before the Priority column) still read correctly."""
    if "Watchlist" not in wb.sheetnames:
        return []
    ws = wb["Watchlist"]
    by_head = {str(c.value or "").strip(): i for i, c in enumerate(ws[1]) if c.value}
    idx = {k: by_head.get(h) for k, h in zip(WL_KEYS, WL_HEAD)}
    out = []
    for row in ws.iter_rows(min_row=2, max_col=max(len(WL_HEAD), ws.max_column), values_only=True):
        v = {k: (row[i] if i is not None and i < len(row) else None) for k, i in idx.items()}
        if v["url"] and str(v["url"]).strip():
            v["url"] = str(v["url"]).strip()
            out.append(v)
    return out


def priority_of(r) -> int:
    try:
        return max(1, int(float(str(r.get("priority") or 1).strip())))
    except ValueError:
        return 1


def write_watchlist(wb, rows):
    idx = wb.sheetnames.index("Watchlist") if "Watchlist" in wb.sheetnames else None
    if idx is not None:
        wb.remove(wb["Watchlist"])
    ws = wb.create_sheet("Watchlist", idx)
    _hdr(ws, WL_HEAD, [20, 46, 22, 8, 8, 28, 42, 15, 12, 64, 12])
    for i, r in enumerate(rows, 2):
        for j, k in enumerate(WL_KEYS, 1):
            v = r.get(k)
            if k == "active":
                v = v or "Yes"
            if k == "priority":
                v = priority_of(r)
            c = ws.cell(i, j, v)
            c.font = Font(name=FONT, size=10, color="0000FF" if j <= WL_INPUTS else "000000")
            if j <= WL_INPUTS:
                c.fill = INPUT_FILL
            if k == "checked":
                c.number_format = "m/d/yy"
    for i in range(len(rows) + 2, len(rows) + 60):
        for j in range(1, WL_INPUTS + 1):
            ws.cell(i, j).fill = INPUT_FILL
    d = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    d.add("D2:D500")
    ws.add_data_validation(d)
    d2 = DataValidation(type="list", formula1='"1,2,3"', allow_blank=True)
    d2.add("E2:E500")
    ws.add_data_validation(d2)
    ws.column_dimensions["K"].hidden = True
    for k, t in enumerate(["Add a company: its name + the link to its careers/job-search page (yellow cells).",
                           "Priority 1/2/3 (blank = 1): Check Jobs asks which priority to scan, so big or slow",
                           "companies can be scanned on other days.",
                           "Extra title keywords are added to your main list for that company. Start them with",
                           "only:  (e.g.  only: mechanical, design engineer) to use just those for this company.",
                           "Where they post (auto): which of your areas the company's postings were in, last scan.",
                           "My notes is yours (e.g. 'HQ Philly, big in Boston'): it's kept on every scan.",
                           "Check Jobs can also scan just one area (e.g. Boston) and skip companies not posting there.",
                           "Active = No pauses a company. Then double-click Check Jobs."]):
        ws.cell(2 + k, 13, t).font = Font(name=FONT, size=9, italic=True, color="667085")
    ws.column_dimensions["M"].width = 84
    return ws


def read_new_matches(wb):
    if "New Matches" not in wb.sheetnames:
        return []
    ws = wb["New Matches"]
    by_head = {str(c.value or "").strip(): i for i, c in enumerate(ws[1])}  # read by header: works for older layouts
    idx = {k: by_head.get(h) for k, h in zip(NM_KEYS, NM_HEAD)}
    out = []
    for row in ws.iter_rows(min_row=2, max_col=max(len(NM_HEAD), ws.max_column)):
        v = {k: (row[i].value if i is not None and i < len(row) else None) for k, i in idx.items()}
        if not (v["title"] or v["link"]):
            continue
        li = idx["link"]
        if li is not None and not (isinstance(v["link"], str) and v["link"].startswith("http")) and row[li].hyperlink:
            v["link"] = row[li].hyperlink.target
        v.pop("ago", None)
        out.append(v)
    return out


def write_new_matches(wb, rows, n_new=0):
    from openpyxl.utils import get_column_letter as gcl
    idx = wb.sheetnames.index("New Matches") if "New Matches" in wb.sheetnames else None
    if idx is not None:
        wb.remove(wb["New Matches"])
    ws = wb.create_sheet("New Matches", idx)
    ws.sheet_properties.tabColor = "F79009"
    _hdr(ws, NM_HEAD, [10, 18, 44, 26, 24, 10, 8, 9, 40, 10, 13, 6])
    col = {k: i + 1 for i, k in enumerate(NM_KEYS)}
    L = {k: gcl(i) for k, i in col.items()}
    ws.freeze_panes = "D2"
    new_fill = PatternFill("solid", fgColor="FEF7C3")
    for i, r in enumerate(rows, 2):
        for k, j in col.items():
            v = f'=IF(ISNUMBER({L["posted"]}{i}),MAX(0,TODAY()-{L["posted"]}{i}),"")' if k == "ago" else r.get(k)
            c = ws.cell(i, j, v)
            c.font = BODY
            if k in ("found", "posted"):
                c.number_format = "m/d/yy"
            if i - 2 < n_new and j <= 3:
                c.fill = new_fill
        lc = ws.cell(i, col["link"])
        if isinstance(r.get("link"), str) and r["link"].startswith("http"):
            lc.hyperlink = r["link"]
            lc.font = Font(name=FONT, size=10, color="0563C1", underline="single")
    ws.column_dimensions[L["key"]].hidden = True
    last = max(2, len(rows) + 1)
    act, lastvis = L["action"], L["source"]
    ws.auto_filter.ref = f"A1:{lastvis}{last}"
    d = DataValidation(type="list", formula1='"Add,Dismiss"', allow_blank=True)
    d.add(f"{act}2:{act}{last + 300}")
    ws.add_data_validation(d)
    ws.conditional_formatting.add(f"A2:{lastvis}{last + 300}", FormulaRule(
        formula=[f'OR(${act}2="Dismiss",${act}2="Added")'], font=Font(color="98A2B3")))
    ws.conditional_formatting.add(f"{act}2:{act}{last + 300}", CellIsRule(operator="equal", formula=['"Add"'],
                                  fill=PatternFill("solid", fgColor="D1FADF"), font=Font(color="05603A", bold=True)))
    ag = L["ago"]
    ws.conditional_formatting.add(f"{ag}2:{ag}{last + 300}", FormulaRule(
        formula=[f"AND(ISNUMBER({ag}2),{ag}2<=7)"], fill=PatternFill("solid", fgColor="D1FADF"), font=Font(color="05603A")))
    return ws


def build_watch_sheets(wb):
    if "Watchlist" not in wb.sheetnames:
        write_watchlist(wb, [{"company": c, "url": u, "keywords": k, "active": a, "notes": n} for c, u, k, a, n in WATCH_DEFAULTS])
    elif [str(c.value or "").strip() for c in wb["Watchlist"][1]][:len(WL_HEAD)] != WL_HEAD:
        write_watchlist(wb, read_watchlist(wb))  # older layout: rewrite with the new columns, keeping every row
    if "New Matches" not in wb.sheetnames:
        write_new_matches(wb, [])
    elif [str(c.value or "").strip() for c in wb["New Matches"][1]][:len(NM_HEAD)] != NM_HEAD:
        write_new_matches(wb, read_new_matches(wb))


def build_logs(wb):
    if "Needs Review" not in wb.sheetnames:
        nr = wb.create_sheet("Needs Review")
        _hdr(nr, ["Date", "Account", "From", "Subject", "Looks like", "Company guess", "Why it's here", "Email", "Done?"],
             [10, 24, 28, 44, 13, 20, 36, 14, 8])
        d = DataValidation(type="list", formula1='"Yes"', allow_blank=True)
        d.add("I2:I5000")
        nr.add_data_validation(d)
    if "Activity Log" not in wb.sheetnames:
        al = wb.create_sheet("Activity Log")
        _hdr(al, ["Date", "Account", "From", "Subject", "Category", "Job ID", "Company", "What changed"],
             [10, 24, 28, 44, 13, 7, 20, 44])


def ensure_structure(wb):
    """Adds anything missing (new settings, sheets, names) without touching your data."""
    needed = set(SETTING_LABELS)
    have = set()
    old = {}
    if "Settings" in wb.sheetnames:
        for row in wb["Settings"].iter_rows(min_row=1, max_col=2, values_only=True):
            lab = str(row[0] or "").strip()
            if lab in SETTING_LABELS:
                have.add(lab)
                old[SETTING_LABELS[lab]] = row[1]
            elif lab in LEGACY_LABELS and row[1] not in (None, ""):
                old.setdefault(LEGACY_LABELS[lab], row[1])
        # carry over values from the first version's single-cell settings
        for row in wb["Settings"].iter_rows(min_row=1, max_col=2, values_only=True):
            lab = str(row[0] or "").strip()
            if lab == "Preferred locations" and row[1]:
                for i, p in enumerate([x.strip() for x in str(row[1]).split(",") if x.strip()][:6], 1):
                    old.setdefault(f"pref_loc{i}", p)
            if lab == "Target pay (yearly $)" and row[1]:
                old.setdefault("target_pay", row[1])
            if lab == "Minimum acceptable pay (yearly $)" and row[1]:
                old.setdefault("min_pay", row[1])
    if needed - have:
        build_settings(wb, old)
    build_logs(wb)
    build_areas(wb)
    build_watch_sheets(wb)
    for t in JOB_TABS:
        if t not in wb.sheetnames:
            write_job_tab(wb, t, [], 0)
    define_names(wb)


def finalize(wb):
    """Sheet order and opening tab. (The old How To tab is removed: the README replaces it.)"""
    if "How To" in wb.sheetnames:
        wb.remove(wb["How To"])
    order = ["To Apply", "New Matches", "Applied", "Closed", "Needs Review", "Activity Log", "Watchlist", "Settings",
             "Areas"]
    wb._sheets.sort(key=lambda ws: order.index(ws.title) if ws.title in order else 99)
    for ws in wb.worksheets:
        ws.sheet_view.tabSelected = False
    wb.active = 0
    wb.worksheets[0].sheet_view.tabSelected = True
    define_names(wb)


def new_workbook():
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    build_settings(wb)
    build_logs(wb)
    build_areas(wb)
    build_watch_sheets(wb)
    for i, t in enumerate(JOB_TABS):
        write_job_tab(wb, t, [], i)
    define_names(wb)
    finalize(wb)
    return wb
