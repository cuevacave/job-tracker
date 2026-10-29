"""Creates a fresh, empty Job_Tracker.xlsx. Refuses to overwrite an existing tracker unless --force.
    app/.venv/bin/python app/make_workbook.py
"""
import sys

from common import WB_PATH
from sheets import new_workbook

if __name__ == "__main__":
    if WB_PATH.exists() and "--force" not in sys.argv:
        sys.exit(f"{WB_PATH.name} already exists. Not overwriting it.")
    wb = new_workbook()
    wb.calculation.fullCalcOnLoad = True
    wb.save(WB_PATH)
    print("Created", WB_PATH)
