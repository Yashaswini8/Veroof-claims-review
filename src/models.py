"""Pydantic models shared across the review pipeline."""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    claim_type: str = Field(..., description="'accident' or 'theft'")
    claim_form: str
    second_document: str
    second_document_kind: str = Field(
        ..., description="'estimate' for accident, 'fir' for theft"
    )
    incident_description: str

    def sections_present(self) -> dict[str, bool]:
        return {
            "claim_form": bool((self.claim_form or "").strip()),
            "second_document": bool((self.second_document or "").strip()),
            "incident_description": bool((self.incident_description or "").strip()),
        }


def validate_request(payload: ReviewRequest) -> None:
    if payload.claim_type not in ("accident", "theft"):
        raise ValueError("claim_type must be 'accident' or 'theft'")
    expected_kind = "estimate" if payload.claim_type == "accident" else "fir"
    if payload.second_document_kind != expected_kind:
        raise ValueError(
            f"second_document_kind must be '{expected_kind}' for claim_type '{payload.claim_type}'"
        )
    missing = [k for k, v in payload.sections_present().items() if not v]
    if missing:
        raise ValueError(f"Missing input sections: {', '.join(missing)}")


class ExtractedDocument(BaseModel):
    """Structured fields pulled out of one raw document."""

    document_type: str = ""
    policy_number: str = ""
    insured_name: str = ""
    vehicle_registration: str = ""
    vehicle_make_model: str = ""
    incident_date: Optional[str] = None  # ISO date if found
    incident_location: str = ""
    claimed_amount: Optional[float] = None
    estimate_amount: Optional[float] = None
    idv: Optional[float] = None
    description: str = ""
    flags: dict[str, Any] = Field(default_factory=dict)
    raw_quote: str = ""
    notes: str = ""


class ConsistencyFinding(BaseModel):
    severity: str  # "contradiction" | "agreement" | "info"
    between: list[str]
    summary: str
    details: str = ""


class DatedCheck(BaseModel):
    incident_date: Optional[str] = None
    policy_valid_from: Optional[str] = None
    policy_valid_until: Optional[str] = None
    claim_filed_date: Optional[str] = None
    allowed_intimation_hours: int = 0


class DocPresence(BaseModel):
    required: list[str]
    present: list[str]
    missing: list[str]


class CheckResult(BaseModel):
    name: str
    label: str
    status: str  # pass | fail | warn | escalate
    details: list[str] = Field(default_factory=list)
    severity: str = ""


class ClauseHit(BaseModel):
    number: str
    title: str
    quote: str = ""
    relevance: str = ""
    full_text: str = ""


class ReportFinding(BaseModel):
    id: str
    kind: str  # completeness | consistency | exclusion | amount | date | clause | recommendation
    status: str  # pass | fail | warn | escalate | info
    title: str
    detail: str
    references: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    disposition: str  # approve | reject | request_info | escalate
    summary: str
    checks: list[CheckResult]
    contradictions: list[ConsistencyFinding]
    clauses: list[ClauseHit]
    findings: list[ReportFinding]
    recommendation: str
    required_docs: DocPresence
    staged: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    job_id: str
    status: str  # started | running | done | error
    stages: list[str] = Field(default_factory=list)
    report: Optional[ReviewReport] = None
    error: Optional[str] = None