"""Unit tests for the deterministic checks module."""

from __future__ import annotations

from src import checks, models


def _claim(doc_type="claim_form", **kw):
    base = dict(
        document_type=doc_type,
        policy_number="",
        insured_name="",
        vehicle_registration="",
        vehicle_make_model="",
        incident_date=None,
        incident_location="",
        claimed_amount=None,
        estimate_amount=None,
        idv=None,
        description="",
        flags={},
        raw_quote="",
        notes="",
    )
    base.update(kw)
    return models.ExtractedDocument(**base)


def _payload(claim_type, second_kind, form="x", second="x", desc="x"):
    return models.ReviewRequest(
        claim_type=claim_type,
        second_document_kind=second_kind,
        claim_form=form,
        second_document=second,
        incident_description=desc,
    )


def test_clean_accident_completeness_pass():
    docs = [
        _claim("claim_form"),
        _claim("estimate"),
        _claim("incident_description"),
    ]
    presence = checks.check_doc_presence(_payload("accident", "estimate"), docs)
    assert presence.missing == []


def test_clean_theft_completeness_pass():
    docs = [
        _claim("claim_form", flags={
            "rc_submitted": True,
            "policy_schedule_submitted": True,
            "key_handover_submitted": True,
            "noc_submitted": True,
        }),
        _claim("fir"),
        _claim("incident_description"),
    ]
    presence = checks.check_doc_presence(_payload("theft", "fir"), docs)
    assert presence.missing == []
    assert "key_handover" in presence.present


def test_theft_missing_key_handover():
    docs = [
        _claim("claim_form", flags={
            "rc_submitted": True,
            "policy_schedule_submitted": True,
            "key_handover_submitted": False,
            "noc_submitted": True,
        }),
        _claim("fir"),
        _claim("incident_description"),
    ]
    presence = checks.check_doc_presence(_payload("theft", "fir"), docs)
    assert "key_handover" in presence.missing


def test_amount_exceeds_idv_flag():
    r = checks.check_amount_vs_idv(claimed_amount=810000, idv=720000)
    assert r.status == "warn"
    assert "exceeds IDV" in r.details[0]


def test_amount_within_idv_pass():
    r = checks.check_amount_vs_idv(claimed_amount=8400, idv=62000)
    assert r.status == "pass"


def test_incident_outside_policy_period_fail():
    results = checks.check_dates(
        _payload("accident", "estimate"),
        [],
        incident_date="2024-01-01",
        policy_from="2026-01-01",
        policy_until="2026-12-31",
        intimation_date="2026-01-02",
        fir_date=None,
    )
    by_name = {r.name: r for r in results}
    assert by_name["policy_window"].status == "fail"


def test_late_intimation_fail():
    # accident must be intimated within 48h; filed 6 days later -> fail
    results = checks.check_dates(
        _payload("accident", "estimate"),
        [],
        incident_date="2026-06-12",
        policy_from="2026-01-01",
        policy_until="2026-12-31",
        intimation_date="2026-06-18",
        fir_date=None,
    )
    by_name = {r.name: r for r in results}
    assert by_name["intimation_window"].status == "fail"


def test_intimation_date_before_incident_escalates():
    results = checks.check_dates(
        _payload("theft", "fir"),
        [],
        incident_date="2026-03-15",
        policy_from="2026-01-01",
        policy_until="2026-12-31",
        intimation_date="2026-03-14",
        fir_date="2026-03-15",
    )
    by_name = {r.name: r for r in results}
    assert by_name["intimation_window"].status == "escalate"


def test_theft_fir_too_late_fail():
    results = checks.check_dates(
        _payload("theft", "fir"),
        [],
        incident_date="2026-02-20",
        policy_from="2026-01-01",
        policy_until="2026-12-31",
        intimation_date="2026-02-27",
        fir_date="2026-02-26",
    )
    by_name = {r.name: r for r in results}
    assert by_name["theft_fir_window"].status == "fail"


def test_commercial_use_exclusion():
    docs = [
        _claim("claim_form", flags={"commercial_use": True}),
        _claim("estimate"),
        _claim("incident_description"),
    ]
    results = checks.check_exclusion_flags(docs)
    by_name = {r.name: r for r in results}
    assert by_name["excl_commercial_use"].status == "fail"


def test_no_adverse_exclusion_pass():
    docs = [
        _claim("claim_form", flags={
            "commercial_use": False,
            "valid_license": True,
            "under_influence": False,
        }),
        _claim("estimate"),
        _claim("incident_description"),
    ]
    results = checks.check_exclusion_flags(docs)
    for r in results:
        assert r.status != "fail"