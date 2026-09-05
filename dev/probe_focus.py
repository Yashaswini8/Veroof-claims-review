import sys
import time

sys.path.insert(0, "dev")
import api_test

FOCUS = {"c002": "approve", "c005": "request_info", "c006": "request_info"}

for sid, expected in FOCUS.items():
    p = api_test.load(sid)
    r = api_test.post("/api/review", p)
    st = None
    for _ in range(200):
        time.sleep(0.4)
        st = api_test.get(f"/api/reviews/{r['job_id']}")
        if st["status"] in ("done", "error"):
            break
    if st["status"] == "error":
        print(sid, "ERROR:", str(st.get("error"))[:120])
        continue
    rep = st.get("report") or {}
    fir = [c for c in rep.get("checks", []) if c["name"] == "theft_fir_window"]
    rd = rep.get("required_docs") or {}
    print(f"{sid}: disposition={rep.get('disposition')} expected={expected} "
          f"| fir_check={fir[0]['status'] if fir else 'n/a'} | missing={rd.get('missing')} | checks={len(rep.get('checks', []))}")