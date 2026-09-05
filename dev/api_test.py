"""Test the live HTTP API end-to-end with a sample claim."""

import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:8000"


def load(sample_id):
    manifest = json.load(open(os.path.join(ROOT, "data/claims/manifest.json"), encoding="utf-8"))
    sample = next(s for s in manifest["samples"] if s["id"] == sample_id)
    d = os.path.join(ROOT, "data/claims", sample["dir"])
    def rd(p):
        return open(os.path.join(d, p), encoding="utf-8").read()
    return {
        "claim_type": sample["claim_type"],
        "second_document_kind": sample["second_document_kind"],
        "claim_form": rd(sample["claim_form"]),
        "second_document": rd(sample["second_document"]),
        "incident_description": rd(sample["incident_description"]),
    }


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.load(urllib.request.urlopen(req, timeout=60))


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=10))


if __name__ == "__main__":
    sample_id = sys.argv[1] if len(sys.argv) > 1 else "c006"
    result = post("/api/review", load(sample_id))
    job_id = result["job_id"]
    print("job:", job_id)
    for _ in range(20):
        time.sleep(0.5)
        state = get(f"/api/reviews/{job_id}")
        if state["status"] in ("done", "error"):
            break
    print("final status:", state["status"])
    print("stages:", " | ".join(state.get("stages", [])))
    if state.get("report"):
        print("disposition:", state["report"]["disposition"])
        print("summary:", state["report"]["summary"][:160])
    if state.get("error"):
        print("error:", state["error"])