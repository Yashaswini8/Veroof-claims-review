"""Step 9 verification: run every sample claim through the live HTTP API.

Asserts each sample produces the expected disposition (no smoothed-over
approvals). Exits non-zero on any mismatch.
"""

import sys
import time

import api_test

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


def run_one(sample_id):
    payload = api_test.load(sample_id)
    result = api_test.post("/api/review", payload)
    job_id = result["job_id"]
    state = None
    for _ in range(150):
        time.sleep(0.4)
        state = api_test.get(f"/api/reviews/{job_id}")
        if state["status"] in ("done", "error"):
            break
    return state


def main():
    failures = 0
    for sid, expected in EXPECTED.items():
        state = run_one(sid)
        status = state.get("status")
        if status == "error":
            print(f"ERR  {sid}: pipeline error: {state.get('error')}")
            failures += 1
            continue
        report = state.get("report") or {}
        got = report.get("disposition", "MISSING_REPORT")
        n_contra = sum(
            1 for c in report.get("contradictions", []) if c.get("severity") == "contradiction"
        )
        ok = got == expected
        if not ok:
            failures += 1
        print(
            f"{'OK  ' if ok else 'FAIL'} {sid}: live={got:12s} expected={expected:12s} contradictions={n_contra}"
        )
        if not ok:
            contra = [c.get("summary") for c in report.get("contradictions", []) if c.get("severity") == "contradiction"]
            fails = [c.get("label") for c in report.get("checks", []) if c.get("status") == "fail"]
            print("      contradictions:", contra)
            print("      failed checks:  ", fails)
    print(f"\n{8 - failures} of 8 samples matched expected disposition via the live API")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())