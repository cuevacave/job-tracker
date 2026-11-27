"""The shared "apply first" order, used by the Review screen, New Matches, To Apply and jobs.csv.

Groups come from two Settings rows (your data, kept in the workbook): "Apply: referral companies" and
"Apply: top companies". Every other company is Other.

Order:
  1. Location Tier: Tier 1 first, then Tier 2, then jobs whose place is unclear, then Tier 3, then Tier 4
  2. within a tier: Referral, then Top, then Other
  3. within a group: jobs whose fit is below "Apply: fit threshold" go last (never hidden); then fit in steps of 2
     (8-10, 6-8, ...); within a step, years asked 0-2, then not stated, then more; then fit, highest first;
     then newest posting first.
"""
from __future__ import annotations

import datetime as dt
import re

GROUPS = ("Referral", "Top", "Other")


def _list(v) -> list:
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def _num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def years_number(v):
    """Years Asked / Years / Requirements in any of their forms -> a number, or None when not stated."""
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"\s*(?:asks\s+)?(\d+(?:\.\d)?)\+?", str(v or ""))
    return float(m.group(1)) if m else None


class ApplyRules:
    def __init__(self, s: dict, watchlist: list):
        from common import Tracker
        self.norm, self.site_key = Tracker._norm_name, Tracker._site_key
        self.referral = [self.norm(x) for x in _list(s.get("apply_referral"))]
        self.top = [self.norm(x) for x in _list(s.get("apply_top"))]
        self.fit_min = _num(s.get("apply_fit_min"))
        if self.fit_min is None:
            self.fit_min = 5.0
        # the company behind a job's link (a Medtronic job filed under 'COV Covidien LP')
        self.sites = {}
        for w in watchlist or []:
            name = str(w.get("company") or "").strip()
            if not name:
                continue
            if w.get("url"):
                self.sites.setdefault(self.site_key(w["url"]), name)
            host = Tracker._feed_host(w)
            if host:
                self.sites.setdefault(self.site_key("https://" + host + "/"), name)

    def _hit(self, names: list, cands: list) -> bool:
        for n in names:
            if not n:
                continue
            rx = re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])")
            if any(c and (c == n or rx.search(c)) for c in cands):
                return True
        return False

    def group(self, company, link=None) -> str:
        cands = [self.norm(company)]
        if link:
            site = self.sites.get(self.site_key(link))
            if site:
                cands.append(self.norm(site))
        if self._hit(self.referral, cands):
            return "Referral"
        if self._hit(self.top, cands):
            return "Top"
        return "Other"

    def key(self, company, link, tier, years, fit, posted):
        """Sort key: smaller = apply first."""
        g = GROUPS.index(self.group(company, link))
        t = _num(tier)
        t = 2.5 if t is None else t
        f = _num(fit)
        low = 1 if (f is not None and f < self.fit_min) else 0
        fv = f if f is not None else 5.0
        band = min(4, int(fv // 2))  # 8-10, 6-8, 4-6, 2-4, 0-2
        y = years_number(years)
        yb = 0 if (y is not None and y <= 2) else (1 if y is None else 2)
        p = _date(posted)
        return (t, g, low, -band, yb, -fv, -(p.toordinal() if p else 0))

    def job_key(self, j: dict):
        """For a tracker job (To Apply / jobs.csv)."""
        return self.key(j.get("company"), j.get("link"), j.get("loc_tier"), j.get("years_req"), j.get("fit_score"),
                        j.get("posted") or j.get("date_added"))

    def row_key(self, r: dict):
        """For a New Matches row."""
        return self.key(r.get("company"), r.get("link"), r.get("loc_tier"),
                        r.get("years") if r.get("years") not in (None, "") else r.get("requirements"),
                        r.get("fit"), r.get("posted") or r.get("found"))
