"""Run the full pipeline over every sample claim (keyless path)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_pipeline_deterministic import _load
from src import checks, consistency, extraction, reporting, retrieval

EXPECTED = {
    "c001": "approve",
    "c002": "approve",
    "c003": "escalate",
    "c004": "escalate",
    "c005": "request_info",
    "c006": "request_info",
    "c007": "escalate",
    "c008": "reject",
}

failures = 0
for sid, expected in EXPECTED.items():
    p, d = _load(sid)
    docs = extraction.extract_all(p)
    cons = consistency.check_documents(docs, p)
    clauses = retrieval.retrieve_clauses(p, docs)
    check_results = checks.run_all(p, docs, clauses)
    report = reporting.build_report(p, docs, cons, clauses, check_results)
    mark = "OK " if report.disposition == expected else "FAIL"
    if report.disposition != expected:
        failures += 1
    n_contra = sum(1 for c in cons if c.severity == "contradiction")
    print(f"{mark} {sid}: got {report.disposition:12s} expected {expected:12s} contradictions={n_contra}")

print(f"\n{8 - failures} of 8 samples matched expected disposition")
sys.exit(1 if failures else 0)