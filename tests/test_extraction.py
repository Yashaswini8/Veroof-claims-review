"""Tests for the extraction module (deterministic fallback + normalization)."""

from __future__ import annotations

from src import extraction
from src import models

MANIFEST_CLAIM_FORM = """# Motor Vehicle Claim Form

- **Policy Number:** VR-2026-004118
- **Insured Name:** Rohan Mehta
- **Insured Declared Value (IDV):** \u20b962,000
- **Vehicle Registration:** MH-12-AB-4482
- **Date of Incident:** 10 Feb 2026
- **Amount claimed:** \u20b98,400
"""


def test_deterministic_extract_claim_form():
    doc = extraction.extract_one("claim_form", MANIFEST_CLAIM_FORM)
    assert isinstance(doc, models.ExtractedDocument)
    assert doc.document_type == "claim_form"
    assert doc.idv == 62000.0
    assert doc.claimed_amount == 8400.0
    assert doc.incident_date is not None


def test_parse_amount():
    assert extraction._parse_amount("₹8,400") == 8400.0
    assert extraction._parse_amount("Rs. 1,45,000") == 145000.0
    assert extraction._parse_amount(None) is None


def test_parse_date():
    assert extraction._parse_date("2026-02-10") == "2026-02-10"
    assert extraction._parse_date("10-02-2026") == "2026-02-10"
    assert extraction._parse_date(None) is None


def test_normalize_flags_only_bools_kept():
    data = {"flags": {"commercial_use": True, "valid_license": "maybe"}}
    doc = extraction._normalize(data, "claim_form")
    assert doc.flags.get("commercial_use") is True
    assert doc.flags.get("valid_license") is None


def test_empty_document_raises():
    import pytest

    with pytest.raises(ValueError):
        extraction.extract_one("claim_form", "   ")


def test_extract_all_returns_three_docs():
    payload = models.ReviewRequest(
        claim_type="accident",
        second_document_kind="estimate",
        claim_form=MANIFEST_CLAIM_FORM,
        second_document="# Repair Estimate\n**Total** || 8,400",
        incident_description="I skidded my bike on a wet road on 10 Feb 2026.",
    )
    docs = extraction.extract_all(payload)
    assert len(docs) == 3
    assert [d.document_type for d in docs] == [
        "claim_form",
        "estimate",
        "incident_description",
    ]