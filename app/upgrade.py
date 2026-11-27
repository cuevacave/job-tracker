"""Applies a new tracker layout right away (adds new columns/tabs/settings, keeps all your data)."""
import sys

from common import WB_PATH, Tracker

if __name__ == "__main__":
    if not WB_PATH.exists():
        sys.exit(0)
    try:
        tr = Tracker()
        for j in tr.jobs:  # tidy company names once ('1000 KLA Corporation' -> 'KLA', 'COV Covidien LP' -> 'Medtronic')
            if j.get("company"):
                j["company"] = tr.clean_company(j["company"], j.get("link"))
        import scoring
        for j in tr.jobs:  # update 29 split 'Systems & Integration' into Integration and Systems
            if j.get("role_type") == "Systems & Integration" and j.get("title"):
                j["role_type"] = scoring.role_of(j["title"], tr.s)
        if "New Matches" in tr.wb.sheetnames:
            import sheets
            import watcher
            rows = sheets.read_new_matches(tr.wb)
            old = [r for r in rows if r.get("role_type") == "Systems & Integration"]
            for r in old:
                r["role_type"] = None
            if old:
                watcher.fill_columns(tr, rows)
                sheets.write_new_matches(tr.wb, rows, n_new=0)
        counts = tr.save()
        print(f"  Tracker updated: To Apply {counts['To Apply']}, Applied {counts['Applied']}, Closed {counts['Closed']}.")
    except Exception as e:
        print(f"  (tracker will update on your next Add Job / Check Email run: {e})")
