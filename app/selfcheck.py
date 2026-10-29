"""Quick check that the location lookup works, using your Settings and Areas tabs. Run by Setup and Install Update."""
import sys

import openpyxl

import geo
from common import WB_PATH, read_areas, read_settings


def main():
    print(f"  Job Tracker update {__import__('common').APP_VERSION}")
    n = len(geo.places())
    full = geo.CACHE.exists()
    print(f"  Place data: {n:,} US places" + ("" if full else " (built-in list only; small towns may show '?')"))
    if not WB_PATH.exists():
        return
    wb = openpyxl.load_workbook(WB_PATH, read_only=True)
    s, areas = read_settings(wb), read_areas(wb)
    cfg = geo.config(s, areas)
    home = s.get("home_city")
    if not home:
        print("  Home: not set yet - fill in 'Home (city, state)' on the Settings tab")
    else:
        print(f"  Home: {home} " + ("(found)" if cfg["home"] else "(NOT recognized - check the spelling on the Settings tab)"))
    missing = [a["name"] for a in cfg["areas"] if a.get("_missing")]
    if missing:
        print("  These Areas centers weren't recognized, check spelling (City, ST): " + ", ".join(missing))
    for t in ("Monument, CO", "Denver, CO", "Cambridge, MA", "Hoboken, NJ", "San Jose, CA", "Albany, NY", "Austin, TX"):
        print(f"    {t:16} -> {geo.classify(t, cfg).get('area')}")
    ai_speed(s)


def ai_speed(s):
    """Time a small AI request so we know what to expect on this Mac."""
    import time

    from common import AI
    ai = AI(s)
    if not ai.enabled:
        print(f"  AI: off ({ai.reason})")
        return
    print(f"  AI speed test ({ai.model}), up to ~2 minutes the first time...", end="", flush=True)
    schema = {"type": "object", "properties": {"days": {"type": "string"}, "quote": {"type": "string"}},
              "required": ["days", "quote"]}
    text = ("We are a hybrid team based in Denver. You'll be in the office three days a week. " * 3
            + "Responsibilities include reporting, dashboards, and stakeholder communication. " * 40)
    t0 = time.time()
    ai.json("How many office days per week? Quote the sentence.\n\n" + text, schema)   # loads the model
    load = time.time() - t0
    t1 = time.time()
    res = ai.json("How many office days per week? Quote the sentence.\n\n" + text, schema)
    run = time.time() - t1
    if not res:
        print(" no answer (see the note above).")
        return
    print(f" model load {load:.0f}s, one request {run:.0f}s.")
    if run <= 15:
        print("  -> Fast enough: Add Job will take roughly 20-45 seconds per job with the AI.")
    elif run <= 40:
        print("  -> Usable but slow (about 1-2 minutes per job). For speed, set Settings > AI model to qwen3:1.7b.")
    else:
        print("  -> Too slow on this Mac. Set Settings > AI model to qwen3:1.7b and run Setup, or set 'Use local AI' to No.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never block setup over a check
        print(f"  (location check skipped: {e})")
        sys.exit(0)
