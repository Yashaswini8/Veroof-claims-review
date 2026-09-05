import os
import sys

sys.path.insert(0, os.getcwd())
from src import extraction

# Simulate the broken case: the LLM "succeeds" but returns fir_date = null.
fir_text = open("data/claims/c002-clean-theft/fir.md", encoding="utf-8").read()
dummy = extraction._deterministic_extract("fir", "No date labels at all — nothing here.")
dummy.flags.clear()
print("before backfill: fir_date =", dummy.flags.get("fir_date"), "| incident =", dummy.incident_date)
extraction._backfill_normative_dates(dummy, "fir", fir_text)
print("after  backfill: fir_date =", dummy.flags.get("fir_date"), "| incident =", dummy.incident_date)