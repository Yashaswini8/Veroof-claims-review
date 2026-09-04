"""Deterministic claim checks — pure Python, no LLM calls.

These functions reduce to arithmetic or lookups. They consume structured
fields (from extraction, possibly filled by the LLM) but never decide a
subjective question. Uncertain outcomes are returned as 'escalate'.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from src import models

# Allowed intimation windows per claim type (from policy Clause 6.1).
INTIMATION_WINDOW_HOURS = {
    "accident": 48,
    "theft": 7 * 24,  # theft intimated within 7 days of discovery/theft
}
THEFT_FIR_WINDOW_HOURS = 24  # FIR must be filed within 24h (Clause 6.2)
LATE_INTIMATION_DEDUCTIBLE_PCT = 10  # additional deductible, Clause 6.1(c)

# Required documents per claim type (policy Clause 6.3 / 6.4).
REQUIRED_DOCS = {
    "accident": ["claim_form", "repair_estimate"],
    "theft": [
        "claim_form",
        "fir",
        "rc",
        "policy_schedule",
        "key_handover",
        "noc_financier",
    ],
}


def parse_iso(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def check_doc_presence(payload: models.ReviewRequest, docs: list) -> models.DocPresence:
    """Return which required documents are present/missing for the claim type."""
    required = list(REQUIRED_DOCS[payload.claim_type])

    # The NOC is only required when the vehicle is hypothecated (Clause 6.4(f)).
    if "noc_financier" in required and not _is_hypothecated(docs):
        required.remove("noc_financier")

    present: list[str] = []
    missing: list[str] = []

    # Map which extracted documents we actually have.
    have = set()
    for doc in docs:
        have.add(doc.document_type)

    for req in required:
        if req in ("claim_form", "repair_estimate", "fir"):
            # These come from the typed document set.
            if _doc_present(req, payload, have):
                present.append(req)
            else:
                missing.append(req)
        else:
            # Other required docs (rc, policy_schedule, key_handover, noc) are
            # declared in the claim form's checklist / matched via flags.
            if _aux_present(req, docs):
                present.append(req)
            else:
                missing.append(req)

    return models.DocPresence(required=required, present=present, missing=missing)


def _is_hypothecated(docs: list) -> bool:
    for doc in docs:
        if doc.flags.get("vehicle_hypothecated") is True:
            return True
        if doc.flags.get("vehicle_hypothecated") is False:
            return False
    return True  # conservative: if unknown, assume financed so NOC stays required


def _doc_present(req: str, payload: models.ReviewRequest, have: set) -> bool:
    if req == "claim_form":
        return "claim_form" in have or bool(payload.claim_form.strip())
    if req == "repair_estimate":
        return payload.claim_type == "accident" and bool(payload.second_document.strip())
    if req == "fir":
        return payload.claim_type == "theft" and bool(payload.second_document.strip())
    return False


def _aux_present(req: str, docs: list) -> bool:
    flag_names = {
        "rc": "rc_submitted",
        "policy_schedule": "policy_schedule_submitted",
        "key_handover": "key_handover_submitted",
        "noc_financier": "noc_submitted",
    }
    key = flag_names.get(req)
    if key is None:
        return False
    for doc in docs:
        if doc.flags.get(key, None) is True:
            return True
        if key in doc.flags and doc.flags[key] is None:
            return False
    return False


def check_completeness(payload: models.ReviewRequest, docs: list) -> models.CheckResult:
    presence = check_doc_presence(payload, docs)
    if presence.missing:
        return models.CheckResult(
            name="completeness",
            label="Document completeness",
            status="warn",
            details=[
                f"Missing required document(s): {', '.join(presence.missing)}",
                "Request the missing items before a decision.",
            ],
        )
    return models.CheckResult(
        name="completeness",
        label="Document completeness",
        status="pass",
        details=["All required documents are present for this claim type."],
    )


def check_dates(
    payload: models.ReviewRequest,
    docs: list,
    incident_date: Optional[str],
    policy_from: Optional[str],
    policy_until: Optional[str],
    intimation_date: Optional[str],
    fir_date: Optional[str],
) -> list[models.CheckResult]:
    """Validate incident within policy period and intimation within window."""
    results: list[models.CheckResult] = []
    incident = parse_iso(incident_date)
    pfrom = parse_iso(policy_from)
    puntil = parse_iso(policy_until)
    intimated = parse_iso(intimation_date)
    fir = parse_iso(fir_date)

    # 1. Policy validity window.
    if incident is None or pfrom is None or puntil is None:
        results.append(
            models.CheckResult(
                name="policy_window",
                label="Incident within policy validity period",
                status="escalate",
                details=[
                    "Cannot determine policy validity period (missing fields).",
                    f"incident={incident_date!r} policy_from={policy_from!r} policy_until={policy_until!r}",
                ],
            )
        )
    elif not (pfrom <= incident <= puntil):
        results.append(
            models.CheckResult(
                name="policy_window",
                label="Incident within policy validity period",
                status="fail",
                details=[
                    f"Incident date {incident} falls outside the policy period "
                    f"({pfrom} to {puntil}). Not covered (Clause 2.1)."
                ],
            )
        )
    else:
        results.append(
            models.CheckResult(
                name="policy_window",
                label="Incident within policy validity period",
                status="pass",
                details=[
                    f"Incident date {incident} is within policy period "
                    f"({pfrom} to {puntil})."
                ],
            )
        )

    # 2. Intimation window.
    allowed = INTIMATION_WINDOW_HOURS[payload.claim_type]
    if incident is None or intimated is None:
        results.append(
            models.CheckResult(
                name="intimation_window",
                label="Claim filed within intimation window",
                status="escalate",
                details=[
                    "Cannot determine intimation timing (missing incident or intimation date)."
                ],
            )
        )
    else:
        delay_days = (intimated - incident).days
        if delay_days < 0:
            results.append(
                models.CheckResult(
                    name="intimation_window",
                    label="Claim filed within intimation window",
                    status="escalate",
                    details=[
                        f"Intimation date {intimated} precedes incident date {incident}. Contradiction in dates — escalate."
                    ],
                )
            )
        elif delay_days * 24 > allowed:
            results.append(
                models.CheckResult(
                    name="intimation_window",
                    label="Claim filed within intimation window",
                    status="fail",
                    details=[
                        f"Claim field {intimated} is {delay_days} day(s) after the incident {incident}; "
                        f"allowed window is {allowed} hour(s) (Clause 6.1). "
                        f"Late intimation triggers an additional deductible of "
                        f"{LATE_INTIMATION_DEDUCTIBLE_PCT}% (Clause 6.1(c))."
                    ],
                )
            )
        else:
            results.append(
                models.CheckResult(
                    name="intimation_window",
                    label="Claim filed within intimation window",
                    status="pass",
                    details=[
                        f"Claim field {intimated} is within the {allowed}-hour window after the incident {incident}."
                    ],
                )
            )

    # 3. Theft FIR registered within 24h (Clause 6.2).
    if payload.claim_type == "theft":
        if fir is None or incident is None:
            results.append(
                models.CheckResult(
                    name="theft_fir_window",
                    label="Theft FIR filed within 24 hours",
                    status="escalate",
                    details=["Cannot determine FIR timing (missing dates)."],
                )
            )
        else:
            fd = (fir - incident).days
            if fd < 0:
                results.append(
                    models.CheckResult(
                        name="theft_fir_window",
                        label="Theft FIR filed within 24 hours",
                        status="escalate",
                        details=[
                            f"FIR date {fir} precedes incident date {incident}. Contradiction — escalate."
                        ],
                    )
                )
            elif fd * 24 > THEFT_FIR_WINDOW_HOURS:
                results.append(
                    models.CheckResult(
                        name="theft_fir_window",
                        label="Theft FIR filed within 24 hours",
                        status="fail",
                        details=[
                            f"FIR filed {fir}, {fd} day(s) after the theft {incident}; "
                            f"must be within {THEFT_FIR_WINDOW_HOURS} hours (Clause 6.2)."
                        ],
                    )
                )
            else:
                results.append(
                    models.CheckResult(
                        name="theft_fir_window",
                        label="Theft FIR filed within 24 hours",
                        status="pass",
                        details=[
                            f"FIR filed {fir}, within the {THEFT_FIR_WINDOW_HOURS}-hour window of the theft."
                        ],
                    )
                )

    return results


def check_amount_vs_idv(
    claimed_amount: Optional[float],
    idv: Optional[float],
    claim_type: str = "accident",
) -> models.CheckResult:
    """Flag claims where amount meets/exceeds IDV (Clause 3.2)."""
    if claimed_amount is None or idv is None:
        return models.CheckResult(
            name="amount_vs_idv",
            label="Claimed amount vs Insured Declared Value",
            status="escalate",
            details=[
                "Cannot compare claimed amount to IDV (missing amount or IDV field).",
                f"claimed={claimed_amount!r} idv={idv!r}",
            ],
        )
    if claimed_amount > idv:
        return models.CheckResult(
            name="amount_vs_idv",
            label="Claimed amount vs Insured Declared Value",
            status="warn",
            details=[
                f"Claimed amount ₹{claimed_amount:,.0f} exceeds IDV ₹{idv:,.0f}.",
                "Clause 3.2: no claim may be recommended at an amount exceeding IDV; "
                "assess for total loss and flag for higher approval.",
            ],
        )
    if claim_type == "theft" and abs(claimed_amount - idv) <= 1:
        # For theft, the settlement basis IS the IDV (Clause 7.1).
        return models.CheckResult(
            name="amount_vs_idv",
            label="Claimed amount vs Insured Declared Value",
            status="pass",
            details=[
                f"Claimed amount ₹{claimed_amount:,.0f} equals the IDV ₹{idv:,.0f}, "
                "the correct settlement basis for a theft loss (Clause 7.1)."
            ],
        )
    if claimed_amount > 0.85 * idv:
        return models.CheckResult(
            name="amount_vs_idv",
            label="Claimed amount vs Insured Declared Value",
            status="warn",
            details=[
                f"Claimed amount ₹{claimed_amount:,.0f} is close to IDV ₹{idv:,.0f} "
                "(>85%). Consider total-loss assessment (Clause 3.2)."
            ],
        )
    if claim_type == "theft":
        # Theft claims normally claim the IDV; a lower claim should be flagged for review.
        return models.CheckResult(
            name="amount_vs_idv",
            label="Claimed amount vs Insured Declared Value",
            status="pass",
            details=[
                f"Claimed amount ₹{claimed_amount:,.0f} is below IDV ₹{idv:,.0f}."
            ],
        )
    return models.CheckResult(
        name="amount_vs_idv",
        label="Claimed amount vs Insured Declared Value",
        status="pass",
        details=[
            f"Claimed amount ₹{claimed_amount:,.0f} is below IDV ₹{idv:,.0f}."
        ],
    )


def check_exclusion_flags(docs: list) -> list[models.CheckResult]:
    """Evaluate exclusion-relevant flags extracted by the LLM, deterministically.

    The LLM only *extracts* flags (e.g. 'was the vehicle used commercially?');
    this function *applies* the policy and decides the outcome.
    """
    results: list[models.CheckResult] = []

    flags = {}
    for doc in docs:
        flags.update(doc.flags)

    # Commercial use (Clause 4.3).
    commercial = flags.get("commercial_use", None)
    if commercial is True:
        results.append(
            models.CheckResult(
                name="excl_commercial_use",
                label="Exclusion: commercial use of private vehicle",
                status="fail",
                details=[
                    "Extracted flag indicates the insured vehicle was used for hire/reward "
                    "or a commercial purpose under a private-use-only policy (Clause 4.3).",
                ],
            )
        )
    elif commercial is False:
        results.append(
            models.CheckResult(
                name="excl_commercial_use",
                label="Exclusion: commercial use of private vehicle",
                status="pass",
                details=["No commercial use indicated (Clause 4.3)."],
            )
        )
    elif commercial is None:
        results.append(
            models.CheckResult(
                name="excl_commercial_use",
                label="Exclusion: commercial use of private vehicle",
                status="pass",
                details=[
                    "Commercial-use flag not supplied by the customer; no adverse signal detected."
                ],
            )
        )

    # Valid license (Clause 4.1).
    lic = flags.get("valid_license", None)
    if lic is False:
        results.append(
            models.CheckResult(
                name="excl_license",
                label="Exclusion: driving without a valid license",
                status="fail",
                details=[
                    "Flag indicates the driver did not hold a valid driving license "
                    "covering the vehicle class (Clause 4.1)."
                ],
            )
        )
    elif lic is True:
        results.append(
            models.CheckResult(
                name="excl_license",
                label="Exclusion: driving without a valid license",
                status="pass",
                details=["Driver reported to hold a valid license (Clause 4.1)."],
            )
        )
    elif lic is None:
        results.append(
            models.CheckResult(
                name="excl_license",
                label="Exclusion: driving without a valid license",
                status="pass",
                details=["No adverse license signal. If unknown, treat as assumption."],
            )
        )

    # Under influence (Clause 4.2).
    dui = flags.get("under_influence", None)
    if dui is True:
        results.append(
            models.CheckResult(
                name="excl_dui",
                label="Exclusion: driving under influence",
                status="fail",
                details=[
                    "Flag indicates the driver was under the influence "
                    "of liquor or drugs (Clause 4.2)."
                ],
            )
        )
    elif dui is False:
        results.append(
            models.CheckResult(
                name="excl_dui",
                label="Exclusion: driving under influence",
                status="pass",
                details=["No indication of driving under influence (Clause 4.2)."],
            )
        )
    elif dui is None:
        results.append(
            models.CheckResult(
                name="excl_dui",
                label="Exclusion: driving under influence",
                status="pass",
                details=["No adverse influence signal."],
            )
        )

    # Pre-existing damage (Clause 4.4).
    preexisting = flags.get("pre_existing_damage", None)
    if preexisting is True:
        results.append(
            models.CheckResult(
                name="excl_pre_existing",
                label="Exclusion: pre-existing damage",
                status="warn",
                details=[
                    "Signal of possible pre-existing / unrelated damage (Clause 4.4). "
                    "Repairs unrelated to the incident are not covered; verify by survey."
                ],
            )
        )

    return results


def run_all(
    payload: models.ReviewRequest,
    docs: list,
    clause_hits: list,
) -> list[models.CheckResult]:
    """Run every deterministic check for the claim."""
    results: list[models.CheckResult] = []

    # Aggregate structured fields across the three documents.
    claim = _find(docs, "claim_form")
    second = _find(docs, payload.second_document_kind) or (
        _find(docs, "fir") if payload.claim_type == "theft" else _find(docs, "estimate")
    )
    incident = _find(docs, "incident_description")

    results.append(check_completeness(payload, docs))
    results.extend(
        check_dates(
            payload,
            docs,
            incident_date=_pick(claim, "incident_date") or _pick(incident, "incident_date"),
            policy_from=_pick(claim, "policy_valid_from") or _pick(docs, "policy_valid_from"),
            policy_until=_pick(claim, "policy_valid_until") or _pick(docs, "policy_valid_until"),
            intimation_date=_pick(claim, "intimation_date") or _pick(incident, "intimation_date"),
            fir_date=_pick(second, "fir_date"),
        )
    )
    results.append(
        check_amount_vs_idv(
            claimed_amount=_pick(claim, "claimed_amount") or _pick(second, "estimate_amount"),
            idv=_pick(claim, "idv") or _pick(second, "idv"),
            claim_type=payload.claim_type,
        )
    )
    results.extend(check_exclusion_flags(docs))
    return results


def _find(docs: list, document_type: str):
    for doc in docs:
        if doc.document_type == document_type:
            return doc
    return None


def _pick(doc_or_docs, attr: str):
    if isinstance(doc_or_docs, list):
        for d in doc_or_docs:
            val = _pick(d, attr)
            if val is not None:
                return val
        return None
    if doc_or_docs is None:
        return None
    if hasattr(doc_or_docs, attr):
        val = getattr(doc_or_docs, attr, None)
        if val is not None:
            return val
    # Normative dates live in the flags bag (set by extraction normalization).
    flags = getattr(doc_or_docs, "flags", {}) or {}
    if attr in flags and flags[attr] is not None:
        return flags[attr]
    return None