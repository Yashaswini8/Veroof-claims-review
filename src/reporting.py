"""Assemble a structured ReviewReport from deterministic checks, consistency
findings, clause citations and extraction outputs.

This module is purely deterministic — it decides the disposition based on the
collected evidence without any LLM calls. The LLM is only responsible for
phrasing (done later by the frontend display layer), never for deciding the
result.
"""

from __future__ import annotations

from src import models, policy


# ── Disposition logic (deterministic) ──────────────────────────────────────


def _decide_disposition(
    checks: list[models.CheckResult],
    contradictions: list[models.ConsistencyFinding],
) -> str:
    """Derive the final disposition from the collected checks.

    Order of precedence:
    1. Any hard-fail exclusion → reject
    2. Any contradiction that raises uncertainty → escalate
    3. Any escalate from checks → escalate
    4. Amount exceeds IDV → escalate (needs higher approval per 3.2)
    5. Any completeness or date fail → request_info
    6. All pass → approve
    """
    status_rank = {"fail": 0, "escalate": 1, "warn": 2, "pass": 3}
    statuses = [status_rank.get(c.status, 3) for c in checks]

    # 1. Exclusion hard-fail → reject.
    exclusion_names = [
        "excl_commercial_use",
        "excl_license",
        "excl_dui",
        "excl_pre_existing",
    ]
    for c in checks:
        if c.name in exclusion_names and c.status == "fail":
            return "reject"

    # 2. Contradiction → escalate.
    contradiction_count = sum(
        1 for f in contradictions if f.severity == "contradiction"
    )
    if contradiction_count > 0:
        return "escalate"

    # 3. Any escalate → escalate.
    if any(c.status == "escalate" for c in checks):
        return "escalate"

    # 4. Amount exceeds IDV → escalate (Clause 3.2 requires higher approval).
    for c in checks:
        if c.name == "amount_vs_idv" and c.status == "warn":
            return "escalate"

    # 5. Completeness/date failures → request_info.
    critical_warns = ["completeness", "intimation_window", "policy_window", "theft_fir_window"]
    for c in checks:
        if c.name in critical_warns and c.status in ("fail", "warn"):
            return "request_info"

    # 6. All good → approve.
    return "approve"


def _build_findings(
    checks: list[models.CheckResult],
    contradictions: list[models.ConsistencyFinding],
    clauses: list[models.ClauseHit],
    payload: models.ReviewRequest,
) -> list[models.ReportFinding]:
    """Turn every check and contradiction into a flat list of ReportFindings."""
    findings: list[models.ReportFinding] = []
    idx = 0

    for c in checks:
        idx += 1
        kind = "completeness"
        if c.name.startswith("excl"):
            kind = "exclusion"
        elif "date" in c.name or "window" in c.name or "intimation" in c.name:
            kind = "date"
        elif "amount" in c.name:
            kind = "amount"
        elif "pre_existing" in c.name:
            kind = "exclusion"
        findings.append(
            models.ReportFinding(
                id=f"chk-{idx}",
                kind=kind,
                status=c.status,
                title=c.label,
                detail="\n".join(c.details),
                references=[],
            )
        )

    for f in contradictions:
        idx += 1
        findings.append(
            models.ReportFinding(
                id=f"con-{idx}",
                kind="consistency",
                status=f.severity,
                title=f.summary,
                detail=f.details,
                references=[],
            )
        )

    return findings


def _build_summary(
    payload: models.ReviewRequest,
    disposition: str,
    contradictions: list[models.ConsistencyFinding],
    checks: list[models.CheckResult],
    clauses: list[models.ClauseHit],
) -> str:
    """One-paragraph executive summary of the review."""
    parts = []
    parts.append(
        f"VeRoof has reviewed the {payload.claim_type} claim "
        f"for the insured vehicle."
    )
    n_contra = sum(1 for f in contradictions if f.severity == "contradiction")
    if n_contra > 0:
        parts.append(f"{n_contra} cross-document contradiction(s) were identified.")
    n_fail = sum(1 for c in checks if c.status == "fail")
    n_warn = sum(1 for c in checks if c.status in ("warn",))
    if n_fail:
        parts.append(f"{n_fail} policy check(s) failed.")
    if n_warn:
        parts.append(f"{n_warn} policy check(s) returned warnings.")
    if clauses:
        clause_nums = ", ".join(c.number for c in clauses[:3] if c.number != "PREAMBLE")
        if clause_nums:
            parts.append(f"Key policy clauses: {clause_nums}.")
    disposition_text = {
        "approve": "The recommendation is to APPROVE the claim.",
        "reject": "The recommendation is to REJECT the claim.",
        "request_info": "Additional information has been requested before a decision can be made.",
        "escalate": "This claim is ESCALATED to a human investigator for manual review.",
    }
    parts.append(disposition_text.get(disposition, ""))
    return " ".join(parts)


def _build_recommendation(
    disposition: str,
    checks: list[models.CheckResult],
    contradictions: list[models.ConsistencyFinding],
    payload: models.ReviewRequest,
) -> str:
    reasons = []
    for c in checks:
        if c.status in ("fail", "warn"):
            reasons.append(c.details[0] if c.details else c.label)
    n_contra = sum(1 for f in contradictions if f.severity == "contradiction")
    if n_contra > 0:
        reasons.append(f"{n_contra} cross-document contradiction(s) flagged.")

    base = {
        "approve": "Approve the claim for payment of the assessed amount.",
        "reject": "Reject the claim as it is not eligible under the policy.",
        "request_info": "Request the specific missing or inconsistent items before proceeding.",
        "escalate": "Escalate to a senior investigator for manual review.",
    }
    rec = base[disposition]
    if reasons:
        rec += " Reason(s): " + "; ".join(reasons) + "."
    return rec


# ── Main entry point ───────────────────────────────────────────────────────


def build_report(
    payload: models.ReviewRequest,
    docs: list[models.ExtractedDocument],
    contradictions: list[models.ConsistencyFinding],
    clauses: list[models.ClauseHit],
    checks: list[models.CheckResult],
) -> models.ReviewReport:
    from src import checks as checks_mod

    disposition = _decide_disposition(checks, contradictions)
    findings = _build_findings(checks, contradictions, clauses, payload)
    completeness = checks_mod.check_doc_presence(payload, docs)
    summary = _build_summary(payload, disposition, contradictions, checks, clauses)
    recommendation = _build_recommendation(disposition, checks, contradictions, payload)

    return models.ReviewReport(
        disposition=disposition,
        summary=summary,
        checks=checks,
        contradictions=contradictions,
        clauses=clauses,
        findings=findings,
        recommendation=recommendation,
        required_docs=completeness,
        staged=[],
    )


def _completeness_status(checks: list[models.CheckResult]) -> models.DocPresence:
    """Extract the DocPresence from the checks list."""
    from src.checks import REQUIRED_DOCS

    for c in checks:
        if c.name == "completeness":
            # Reconstruct DocPresence from the check result.
            if c.status == "pass":
                return models.DocPresence(required=[], present=[], missing=[])
            detail = c.details[0] if c.details else ""
            missing = (
                detail.replace("Missing required document(s): ", "").split(", ")
                if "Missing" in detail
                else []
            )
            return models.DocPresence(
                required=["claim_form", "repair_estimate"],
                present=[],
                missing=missing,
            )
    return models.DocPresence(required=[], present=[], missing=[])