"""Cross-document consistency check.

Compares the incident narratives in the three documents and surfaces
contradictions explicitly rather than reconciling them silently.

When GEMINI_API_KEY is present, Gemini performs the comparison.
When absent, a deterministic keyword/narrative comparator runs as fallback.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from src import models

MODEL = "gemini-2.0-flash"


def _client():
    from google import genai

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)

prompt_template = """You are a claim-document consistency reviewer. You are given three documents that form a single insurance claim. Compare the narratives across all three and find any factual contradictions or agreements.

Documents:
[CLAIM FORM]
{claim_form}

[SECOND DOCUMENT — {second_kind}]
{second_document}

[INCIDENT DESCRIPTION — from the customer]
{incident_description}

Findings you MUST surface:
1. Do the damage locations agree across the claim form, estimate/FIR, and incident description?
2. Do the incident dates agree across all documents?
3. Do the amounts (claimed vs estimated) agree?
4. Do the party/circumstance details (who hit whom, what happened) agree?
5. Is there any fact that one document states but another contradicts?

For each finding, return exactly one JSON object with these keys:
- severity: "contradiction" if facts disagree, "agreement" if facts align, "info" for notable details
- between: list of document names involved in the finding
- summary: one-line summary
- details: 1-2 sentence elaboration

Return a JSON array of findings. If the documents agree on all key facts, return a single agreement finding. If contradictions exist, list each as a separate finding.

Return ONLY the JSON array, no commentary, no markdown fences."""


def _llm_check(client, claim_form, second_kind, second_document, incident_description) -> list[models.ConsistencyFinding]:
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt_template.format(
            claim_form=claim_form,
            second_kind=second_kind,
            second_document=second_document,
            incident_description=incident_description,
        ),
    )
    raw = resp.text
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    arr = json.loads(raw)
    return [models.ConsistencyFinding(**f) for f in arr]


def check_documents(docs: list, payload) -> list[models.ConsistencyFinding]:
    """Run the consistency check across all three claim documents."""
    claim_form_doc = _find(docs, "claim_form")
    second_doc = (
        _find(docs, "estimate") or _find(docs, "fir")
    )
    incident_doc = _find(docs, "incident_description")
    second_kind = "repair estimate" if payload.second_document_kind == "estimate" else "FIR"

    claim_form = _raw_text(payload.claim_form)
    second_text = _raw_text(payload.second_document)
    incident_text = _raw_text(payload.incident_description)

    # LLM path.
    client = _client()
    if client is not None:
        try:
            return _llm_check(client, claim_form, second_kind, second_text, incident_text)
        except Exception:  # noqa: BLE001
            pass  # fall through to deterministic

    return _deterministic_check(
        claim_form, second_text, incident_text,
        claim_form_doc, second_doc, incident_doc,
        payload,
    )


def _deterministic_check(
    claim_form, second_text, incident_text,
    claim_form_doc, second_doc, incident_doc,
    payload,
) -> list[models.ConsistencyFinding]:
    """Keyword-based consistency comparison for the keyless fallback."""
    findings: list[models.ConsistencyFinding] = []

    # Compare incident dates.
    # For theft, "date last seen" and "date discovered" can differ by a day and
    # are both valid anchors; only flag when the gap is >= 2 days.
    cf_date = _pick_val(claim_form_doc, "incident_date") or _pick_from_flags(claim_form_doc, "incident_date")
    sd_date = None
    if payload.claim_type == "theft":
        sd_date = _pick_from_flags(second_doc, "fir_date")
    # Estimates contain no incident date; only FIR documents carry one.
    inc_date = _pick_val(incident_doc, "incident_date") or _pick_from_flags(incident_doc, "incident_date")

    date_tolerance = 1 if payload.claim_type == "theft" else 0

    def _date_gap(a, b):
        from src.checks import parse_iso

        da, db = parse_iso(a), parse_iso(b)
        if not da or not db:
            return None
        return abs((da - db).days)

    gap = _date_gap(cf_date, inc_date) if cf_date and inc_date else None
    if gap is not None and gap > date_tolerance:
        findings.append(models.ConsistencyFinding(
            severity="contradiction",
            between=["claim form", "incident description"],
            summary=f"Date mismatch: claim form says {cf_date}, incident description says {inc_date}.",
            details="The stated incident dates differ between documents.",
        ))
    elif cf_date and inc_date:
        findings.append(models.ConsistencyFinding(
            severity="agreement",
            between=["claim form", "incident description"],
            summary=f"Incident date agrees: {cf_date}.",
        ))

    if cf_date and sd_date:
        gap2 = _date_gap(cf_date, sd_date)
        if gap2 is not None and gap2 > date_tolerance:
            findings.append(models.ConsistencyFinding(
                severity="contradiction",
                between=["claim form", "second document"],
                summary=f"Date mismatch: claim form says {cf_date}, second document reports {sd_date}.",
            ))

    # Compare amounts.
    cf_amount = _pick_val(claim_form_doc, "claimed_amount")
    sd_estimate = _pick_val(second_doc, "estimate_amount")
    if cf_amount is not None and sd_estimate is not None and abs(cf_amount - sd_estimate) > 10:
        findings.append(models.ConsistencyFinding(
            severity="contradiction",
            between=["claim form", "second document"],
            summary=f"Amount mismatch: claimed ₹{cf_amount:,.0f} vs estimated ₹{sd_estimate:,.0f}.",
            details="The claimed amount does not agree with the repair estimate.",
        ))
    elif cf_amount is not None and sd_estimate is not None:
        findings.append(models.ConsistencyFinding(
            severity="agreement",
            between=["claim form", "second document"],
            summary=f"Amounts agree: ₹{cf_amount:,.0f}.",
        ))

    # Compare damage-direction buckets. "rear edge of the bonnet" alone should
    # not equal a rear-impact; we compare dominant direction per document.
    cf_dir = _direction_words(_raw_text(payload.claim_form))
    inc_dir = _direction_words(_raw_text(payload.incident_description))
    est_dir = _direction_words(_raw_text(payload.second_document))

    if _opposite_direction(cf_dir, est_dir):
        findings.append(models.ConsistencyFinding(
            severity="contradiction",
            between=["claim form", "second document"],
            summary="Damage direction conflicts: the claim form describes one side of the vehicle, the estimate/FIR the opposite.",
            details=(
                f"Claim form direction: {_fmt_direction(cf_dir)}. "
                f"Estimate/FIR direction: {_fmt_direction(est_dir)}."
            ),
        ))
    if _opposite_direction(cf_dir, inc_dir):
        findings.append(models.ConsistencyFinding(
            severity="contradiction",
            between=["claim form", "incident description"],
            summary="Damage direction conflicts between the claim form and the incident description.",
            details=(
                f"Claim form direction: {_fmt_direction(cf_dir)}. "
                f"Incident description direction: {_fmt_direction(inc_dir)}."
            ),
        ))

    # If no contradictions found, surface at least one agreement.
    if not any(f.severity == "contradiction" for f in findings):
        findings.append(models.ConsistencyFinding(
            severity="agreement",
            between=["all documents"],
            summary="No contradictions detected in the deterministic check.",
        ))

    return findings


def _find(docs, doc_type):
    for d in docs:
        if d.document_type == doc_type:
            return d
    return None


def _pick_val(doc, attr):
    if doc is None:
        return None
    return getattr(doc, attr, None)


def _pick_from_flags(doc, key):
    if doc is None:
        return None
    return (doc.flags or {}).get(key)


def _raw_text(text: str) -> str:
    return (text or "").strip()


_DIR_FRONT = {"front", "headlamp", "grille", "bonnet"}
_DIR_REAR = {"rear", "tail", "boot", "trunk", "back"}


def _direction_words(text: str) -> dict:
    low = text.lower()
    counts = {"front": 0, "rear": 0}
    for w in _DIR_FRONT:
        counts["front"] += len(re.findall(rf"(?<![a-z-]){re.escape(w)}(?![a-z-])", low))
    for w in _DIR_REAR:
        counts["rear"] += len(re.findall(rf"(?<![a-z-]){re.escape(w)}(?![a-z-])", low))
    return counts


def _dominant(counts: dict) -> Optional[str]:
    if counts["front"] + counts["rear"] == 0:
        return None
    if counts["front"] >= 2 * counts["rear"]:
        return "front"
    if counts["rear"] >= 2 * counts["front"]:
        return "rear"
    return None


def _opposite_direction(a: dict, b: dict) -> bool:
    da, db = _dominant(a), _dominant(b)
    return bool(da and db and da != db)


def _fmt_direction(counts: dict) -> str:
    parts = []
    if counts["front"]:
        parts.append(f"{counts['front']} front-side mention(s)")
    if counts["rear"]:
        parts.append(f"{counts['rear']} rear-side mention(s)")
    if not parts:
        return "no directional mentions"
    return ", ".join(parts)