"""Sample claim loader: lists and returns the bundled claims from data/claims/."""

from __future__ import annotations

import json
import os
from typing import Optional

CLAIMS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "claims")


def _manifest() -> dict:
    path = os.path.join(CLAIMS_DIR, "manifest.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"samples": []}


def list_samples() -> list[dict]:
    return _manifest().get("samples", [])


def load_sample(sample_id: str) -> Optional[dict]:
    for sample in _manifest().get("samples", []):
        if sample["id"] == sample_id:
            return sample
    return None


def read_sample_file(sample_id: str, file_name: str) -> Optional[str]:
    """Read one document file (claim_form.md / estimate.md / etc.) for a sample."""
    sample = load_sample(sample_id)
    if sample is None:
        return None
    allowed = {
        sample.get("claim_form"),
        sample.get("second_document"),
        sample.get("incident_description"),
    }
    if file_name not in allowed:
        return None
    path = os.path.join(CLAIMS_DIR, sample["dir"], file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()