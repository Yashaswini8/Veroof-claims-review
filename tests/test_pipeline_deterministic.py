"""Integration test: extraction -> deterministic checks on real sample claims.

These exercises the keyless fallback path so the pipeline stays testable in CI.
"""

from __future__ import annotations

import os

from src import checks, extraction, models, sample_loader

ROOT = os.path.dirname(os.path.dirname(__file__))


def _load(sample_id):
    sample = sample_loader.load_sample(sample_id)
    d = os.path.join(ROOT, "data", "claims", sample["dir"])
    with open(os.path.join(d, sample["claim_form"]), encoding="utf-8") as fh:
        form = fh.read()
    with open(os.path.join(d, sample["second_document"]), encoding="utf-8") as fh:
        second = fh.read()
    with open(os.path.join(d, sample["incident_description"]), encoding="utf-8") as fh:
        incident = fh.read()
    return (
        models.ReviewRequest(
            claim_type=sample["claim_type"],
            second_document_kind=sample["second_document_kind"],
            claim_form=form,
            second_document=second,
            incident_description=incident,
        ),
        sample,
    )


def test_c001_clean_accident_passes_checks():
    payload, _ = _load("c001")
    docs = extraction.extract_all(payload)
    results = checks.run_all(payload, docs, [])
    # No check should hard-fail.
    fails = [r for r in results if r.status == "fail"]
    assert not fails, f"unexpected fails: {fails}"


def test_c004_amount_exceeds_idv_warns():
    payload, _ = _load("c004")
    docs = extraction.extract_all(payload)
    results = checks.run_all(payload, docs, [])
    by_name = {r.name: r for r in results}
    assert by_name["amount_vs_idv"].status == "warn"


def test_c006_late_intimation_fails():
    payload, _ = _load("c006")
    docs = extraction.extract_all(payload)
    results = checks.run_all(payload, docs, [])
    by_name = {r.name: r for r in results}
    assert by_name["intimation_window"].status == "fail"


def test_c008_commercial_use_rejects():
    payload, _ = _load("c008")
    docs = extraction.extract_all(payload)
    results = checks.run_all(payload, docs, [])
    by_name = {r.name: r for r in results}
    assert by_name["excl_commercial_use"].status == "fail"