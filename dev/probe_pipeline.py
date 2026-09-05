import json
import sys

sys.path.insert(0, ".")
from src import extraction, jobs, models, pipeline

extraction._FALLBACK_ENABLED = False

m = json.load(open("data/claims/manifest.json", encoding="utf-8"))
s = next(x for x in m["samples"] if x["id"] == "c008")
base = "data/claims/" + s["dir"]
payload = models.ReviewRequest(
    claim_type=s["claim_type"],
    claim_form=open(base + "/" + s["claim_form"], encoding="utf-8").read(),
    second_document_kind=s["second_document_kind"],
    second_document=open(base + "/" + s["second_document"], encoding="utf-8").read(),
    incident_description=open(base + "/" + s["incident_description"], encoding="utf-8").read(),
)
job = jobs.create()
pipeline.run_review(job, payload)
if job.status == "error":
    print("job error:", job.error)
    sys.exit(1)
rep = job.report
print("disposition:", rep["disposition"])
print("clauses:", [(c["number"], c["relevance"]) for c in rep["clauses"]][:3])
print(
    "commercial_use exclusion failed:",
    any(f["title"].startswith("Exclusion: commercial") and f["status"] == "fail" for f in rep["findings"]),
)