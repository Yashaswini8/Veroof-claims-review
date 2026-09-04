import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_pipeline_deterministic import _load
from src import checks, extraction, consistency, reporting, retrieval

for sid in ["c002", "c005", "c006", "c007"]:
    p, d = _load(sid)
    docs = extraction.extract_all(p)
    cons = consistency.check_documents(docs, p)
    print(f"--- {sid} ---")
    for f in cons:
        print(" ", f.severity, f.summary)
    print("  docs:", [(x.document_type, x.incident_date, x.claimed_amount, x.estimate_amount) for x in docs])