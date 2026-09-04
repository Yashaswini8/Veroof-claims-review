import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_pipeline_deterministic import _load
from src import consistency

p, d = _load("c007")

for name, txt in [("claim_form", p.claim_form), ("estimate", p.second_document), ("incident_description", p.incident_description)]:
    low = txt.lower()
    found = consistency._extract_location_words(txt)
    print(name, "->", sorted(found))

print()
cons = consistency._deterministic_check(
    p.claim_form, p.second_document, p.incident_description,
    None, None, None, p,
)
for f in cons:
    print(f.severity, f.summary)