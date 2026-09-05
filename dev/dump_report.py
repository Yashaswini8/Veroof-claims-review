"""Dump a full report JSON for a sample for quality review."""

import json
import sys
import time

import api_test

sid = sys.argv[1] if len(sys.argv) > 1 else "c001"
payload = api_test.load(sid)
result = api_test.post("/api/review", payload)
state = None
for _ in range(150):
    time.sleep(0.4)
    state = api_test.get(f"/api/reviews/{result['job_id']}")
    if state["status"] in ("done", "error"):
        break
print(json.dumps(state, indent=2, default=str)[:6000])