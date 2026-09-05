TRACK_ID=PS02

# VeRoof — Claims Evidence Review Assistant

VeRoof is a claims-evidence review assistant for motor insurance. It reads a
claim submission (claim form, repair estimate / FIR, incident description),
extracts structured facts with Gemini, cross-checks the documents for
contradictions, retrieves the relevant clauses of the VeRoof Motor Insurance
Policy, applies deterministic policy checks, and produces a decision-ready
report: **approve**, **escalate**, **request_info** or **reject**.

Every verdict is evidence-based. Contradictions are surfaced, never smoothed
over; exclusions that bar the claim end in a clear reject; amounts above the
insured declared value or ambiguity that needs human judgement escalate to an
investigator.

## Highlights

- **Deterministic decider, grounded in policy text.** The final disposition is
  derived by pure-Python rules from structured checks — the LLM never decides
  the outcome, it only extracts facts and surfaces contradictions.
- **Retrieval-augmented citations.** The report shows the exact policy clauses
  that drove the decision, ranked by relevance (semantic + keyword fallback).
- **Working end-to-end without any API key.** Every feature — extraction,
  consistency, retrieval, checks, report — has a deterministic fallback so the
  demo runs fully offline.
- **Sample claims shipped.** Eight realistic claim folders
  (`data/claims/c001…c008`) covering approve/escalate/request_info/reject
  outcomes, loadable in one click from the UI.

## Quick start

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\pip install -r requirements.txt
#  macOS/Linux: ./.venv/bin/pip install -r requirements.txt
python app.py
```

Then open http://localhost:8000.

The demo runs without configuration. To enable the Gemini extraction /
embedding path, set a Google API key:

```bash
set GEMINI_API_KEY=your-key        # Windows
export GEMINI_API_KEY=your-key     # macOS/Linux
```

With a key present, extraction uses `gemini-2.0-flash` and policy embedding
uses `gemini-embedding-001`, cached in `data/embeddings`. Without a key,
deterministic parsers and lexicon retrieval produce the same structured
output and the same dispositions for all shipped samples.

## API

| Endpoint | Description |
| --- | --- |
| `POST /api/review` | Submit a claim, returns a `job_id` |
| `GET /api/reviews/{job_id}` | Poll job progress + final report |
| `GET /api/samples` | List the shipped sample claims |
| `GET /api/sample-file?sample=…&file=…` | Fetch a sample document |
| `GET /api/health` | Health check |

## Project layout

```
app.py                    FastAPI app + job queue
src/
  extraction.py           Gemini extraction + deterministic fallback
  consistency.py          Cross-document contradiction detection
  retrieval.py            Clause retrieval (semantic embeddings + lexical fallback)
  checks.py               Deterministic policy checks
  reporting.py            Report assembly + disposition decision
  models.py               Pydantic schemas for the whole pipeline
  sample_loader.py        Sample-claim registry
data/
  policy.md               The VeRoof Motor Insurance Policy (synthetic, generated)
  claims/                 Eight sample claim folders + manifest
frontend/                 Single-page review UI (vanilla HTML/CSS/JS)
tests/                    Unit tests (32 passing, runnable without a key)
dev/                      Server launcher + end-to-end verification scripts
```

## Running the checks and tests

```bash
python -m pytest tests/ -q                          # unit tests (32 pass, no key needed)
python dev/verify_live.py                           # all 8 samples through the live HTTP API
python dev/run_all_samples.py                       # in-process end-to-end pass
```

## Note on the data

All policy text and sample claims are synthetic and generated for this
prototype to demonstrate the review flow. The policy deliberately includes a
headline exclusion, a sub-limit, a 7-day theft intimation window and a 24-hour
FIR window so every disposition path is reachable.

## Demo video

> Demo video placeholder — link to be added.