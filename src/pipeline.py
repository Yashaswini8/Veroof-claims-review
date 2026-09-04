"""Orchestrates the full review pipeline for a claim."""

from __future__ import annotations

from src import jobs
from src import models


def run_review(job: jobs.Job, payload: models.ReviewRequest) -> None:
    """Entry point run in a background thread; populates job stages + report."""
    from src import checks, consistency, extraction, reporting, retrieval

    try:
        job.record_stage("Extracting documents…")
        docs = extraction.extract_all(payload)

        job.record_stage("Checking consistency…")
        cons = consistency.check_documents(docs, payload)

        job.record_stage("Matching policy clauses…")
        clause_hits = retrieval.retrieve_clauses(payload, docs)

        job.record_stage("Running policy checks…")
        check_results = checks.run_all(payload, docs, clause_hits)

        job.record_stage("Finalizing report…")
        report = reporting.build_report(
            payload, docs, cons, clause_hits, check_results
        )
        job.report = report.model_dump()
        job.status = "done"
        job.summary = {
            "job_id": job.id,
            "disposition": report.disposition,
            "title": _short_title(payload),
            "claim_type": payload.claim_type,
        }
    except Exception as exc:  # noqa: BLE001 - surface as job error, never crash the app
        job.status = "error"
        job.error = str(exc)


def _short_title(payload: models.ReviewRequest) -> str:
    first_line = (payload.claim_form or "").strip().splitlines()
    for line in first_line:
        if "policy" in line.lower() or "#" in line:
            return line.strip()[:60]
    return f"{payload.claim_type.title()} claim – {payload.claim_form.strip()[:40]}"