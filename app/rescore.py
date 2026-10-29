"""Rescore Jobs: recompute Fit (and so Priority) for jobs already in the tracker.
Use it after changing fit keywords, dealbreakers, background or years of experience on the Settings tab."""
import sys
import time

import scoring
from common import AI, Tracker
from extract import looks_like_posting


def main():
    print("=" * 60 + f"\n  RESCORE JOBS                    Job Tracker update {__import__('common').APP_VERSION}\n" + "=" * 60)
    tr = Tracker()
    ai = AI(tr.s)
    print(f"  AI helper: {'on (' + ai.model + ')' if ai.enabled else 'off - ' + ai.reason}")
    todo = [j for j in tr.jobs if j.get("applied") != "Yes" and j.get("status") not in ("Skipped",)]
    try:
        ans = input(f"  Rescore the {len(todo)} jobs on To Apply? (Enter = yes, a = every job incl. applied, q = quit): ").strip().lower()
    except EOFError:
        ans = ""
    if ans == "q":
        return
    if ans == "a":
        todo = list(tr.jobs)
    if not todo:
        print("  Nothing to rescore.")
        return
    t0 = time.time()
    incomplete = []
    for n, j in enumerate(todo, 1):
        name = f"{j.get('company') or '?'} - {j.get('title') or '?'}"[:52]
        if not looks_like_posting(j.get("description")):
            # Don't score menus / "about us" / legal text as if it were the posting
            j["fit_score"] = None
            j["fit_notes"] = "Posting text looks incomplete: re-capture it (Add Job with the link, then r)"
            incomplete.append(j)
            print(f"  [{n}/{len(todo)}] {name:52} skipped: saved posting looks incomplete")
            continue
        old_fit, old_p = j.get("fit_score"), scoring.priority(j, tr.s)
        j["fit_score"], j["fit_notes"] = scoring.fit(j, tr.s, ai)
        new_p = scoring.priority(j, tr.s)
        pr = f"   priority {old_p} -> {new_p}" if new_p is not None else ""
        print(f"  [{n}/{len(todo)}] {name:52} fit {old_fit} -> {j['fit_score']}{pr}")
    tr.save()
    print(f"\n  Done in {time.time() - t0:.0f}s. To Apply is re-sorted by the new priorities.")
    if incomplete:
        print(f"\n  {len(incomplete)} job(s) need the posting re-captured (their Fit is left neutral until then):")
        for j in incomplete:
            print(f"    #{j.get('id')}  {j.get('company')} - {j.get('title')}\n         {j.get('link') or '(no link: add it in Excel or use Add Job)'}")
        print("  To fix one: copy its link, run Add Job, press Enter, then type  r")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped. Nothing was saved.")
        sys.exit(0)
