"""Sanity tests for the sample claims data and policy document."""

import os

import pytest

from src import sample_loader

ROOT = os.path.dirname(os.path.dirname(__file__))
POLICY = os.path.join(ROOT, "data", "policy.md")


def test_policy_exists_and_has_numbered_clauses():
    assert os.path.exists(POLICY), "policy.md is missing"
    with open(POLICY, encoding="utf-8") as fh:
        text = fh.read()
    assert "Clause 4.2" in text, "policy must contain Clause 4.2 (exclusion)"
    assert "Clause 6.1" in text, "policy must contain Clause 6.1 (intimation)"
    assert "Clause 3.2" in text, "policy must contain Clause 3.2 (IDV cap)"


def test_eight_samples_exist():
    samples = sample_loader.list_samples()
    assert len(samples) == 8, f"expected 8 samples, got {len(samples)}"


@pytest.mark.parametrize(
    "sample_id, claim_type, second_kind",
    [
        ("c001", "accident", "estimate"),
        ("c002", "theft", "fir"),
        ("c003", "theft", "fir"),
        ("c004", "accident", "estimate"),
        ("c005", "theft", "fir"),
        ("c006", "accident", "estimate"),
        ("c007", "accident", "estimate"),
        ("c008", "accident", "estimate"),
    ],
)
def test_sample_files_exist(sample_id, claim_type, second_kind):
    sample = sample_loader.load_sample(sample_id)
    assert sample is not None, f"sample {sample_id} missing from manifest"
    assert sample["claim_type"] == claim_type, f"sample {sample_id} claim_type mismatch"
    assert (
        sample["second_document_kind"] == second_kind
    ), f"sample {sample_id} second kind mismatch"
    d = os.path.join(CLAIMS_DIR(), sample["dir"])
    for rel in [
        sample["claim_form"],
        sample["second_document"],
        sample["incident_description"],
    ]:
        assert os.path.exists(os.path.join(d, rel)), f"missing file {rel} in {d}"


def CLAIMS_DIR():
    return os.path.join(ROOT, "data", "claims")

def test_policy_chunks_cover_exclusions_and_requirements():
    from src import policy
    chunks = policy.chunk_policy()
    numbers = [c['number'] for c in chunks]
    for num in ['4.1','4.2','4.3','4.4','3.2','6.1','6.3','6.4']:
        assert num in numbers, f'missing clause {num}'

