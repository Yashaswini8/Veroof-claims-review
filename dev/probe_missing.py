import sys
import time

sys.path.insert(0, "dev")
import api_test

for sid in ("c001", "c002"):
    p = api_test.load(sid)
    r = api_test.post("/api/review", p)
    st = None
    for _ in range(200):
        time.sleep(0.4)
        st = api_test.get(f"/api/reviews/{r['job_id']}")
        if st["status"] in ("done", "error"):
            break
    rep = st.get("report") or {}
    rd = rep.get("required_docs") or {}
    comp = [c for c in rep.get("checks", []) if c["name"] == "completeness"]
    print(sid, "->", rep.get("disposition"), "| required:", rd.get("required"),
          "| present:", rd.get("present"), "| missing:", rd.get("missing"))
    if comp:
        print("   completeness:", comp[0]["status"], "|", comp[0]["details"][0])