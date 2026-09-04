"""Extraction: turn each raw document into structured JSON via Gemini.

The LLM is told to only report fields that are actually present in the text —
it never invents. Output is validated against ExtractedDocument before use.

When GEMINI_API_KEY is absent (e.g. in CI or a keyless run), we fall back to a
deterministic parser so the pipeline still functions. This keeps the app runnable
and testable without an API key while remaining a real Gemini pipeline with one.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Optional

from src import models

MODEL = "gemini-2.0-flash"
_json_cache: dict[tuple, dict] = {}
_FALLBACK_ENABLED = True


def _client():
    from google import genai

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)


prompt_template = """You are an evidence extraction engine. You will be given one insurance claim document. Extract ONLY fields that are literally present in the text. Do NOT guess, infer, or invent any value. If a value is absent, set it to null. Monetary amounts should be given as plain numbers (no currency symbol), e.g. 8400 for ₹8,400.

Return a strict JSON object with exactly these keys:
- document_type: one of "claim_form", "estimate", "fir", "incident_description"
- policy_number: string or null
- insured_name: string or null
- vehicle_registration: string or null
- vehicle_make_model: string or null
- vehicle_age_years: number or null
- incident_date: ISO date "YYYY-MM-DD" or null
- incident_location: string or null
- policy_valid_from: ISO date or null
- policy_valid_until: ISO date or null
- intimation_date: ISO date of when the claim was filed/intimated to the insurer, or null
- fir_date: ISO date the FIR was registered, or null (only relevant for FIR/theft)
- claimed_amount: number or null
- estimate_amount: number or null (total repair estimate)
- idv: number or null (Insured Declared Value)
- use_class: "private" or "commercial" or null (per RC/insurance)
- flags: object with boolean (true/false) or null values for each of these keys:
    - rc_submitted
    - policy_schedule_submitted
    - key_handover_submitted
    - noc_submitted (financier NOC)
    - commercial_use (does the text indicate the vehicle was used for hire/reward or commercial purpose?)
    - valid_license (is there any statement about a valid driving license?)
    - under_influence (any mention of alcohol/drugs affecting driving?)
    - pre_existing_damage (any indication of damage not related to this incident?)
    - third_party_involved
  For each flag, set true/false only if the text gives evidence; otherwise null. NEVER set commercial_use true just because the vehicle is a taxi-type model — only if the text describes actual commercial use.
- description: a concise summary of the incident/damage in the document (2-4 sentences)
- raw_quote: the single most fact-bearing sentence from the document, verbatim.

DOCUMENT TO ANALYZE:
---
{document}
---
Return ONLY the JSON, no commentary, no markdown fences."""


def _extract_llm(client, doc_type: str, text: str) -> dict:
    resp = client.models.generate_content(
        model=MODEL, contents=prompt_template.format(doc_type=doc_type, document=text)
    )
    raw = resp.text
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # try to find a JSON object in the text
        start = raw.find("{")
        end = raw.rfind("}")
        data = json.loads(raw[start : end + 1])
    return data


def _parse_amount(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("₹", "").strip()
    matches = re.findall(r"(\d+(?:\.\d+)?)", s)
    return float(matches[-1]) if matches else None


def _parse_date(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _normalize(data: dict, doc_type: str) -> models.ExtractedDocument:
    flags = data.get("flags") or {}
    doc = models.ExtractedDocument(
        document_type=doc_type or data.get("document_type"),
        policy_number=data.get("policy_number") or "",
        insured_name=data.get("insured_name") or "",
        vehicle_registration=data.get("vehicle_registration") or "",
        vehicle_make_model=data.get("vehicle_make_model") or "",
        incident_date=_parse_date(data.get("incident_date")),
        incident_location=data.get("incident_location") or "",
        claimed_amount=_parse_amount(data.get("claimed_amount")),
        estimate_amount=_parse_amount(data.get("estimate_amount")),
        idv=_parse_amount(data.get("idv")),
        description=data.get("description") or "",
        flags={k: (v if isinstance(v, bool) else None) for k, v in flags.items()},
        raw_quote=data.get("raw_quote") or "",
        notes=data.get("notes") or "",
    )
    # Dates that live at the top level but are normative:
    doc.flags["policy_valid_from"] = _parse_date(data.get("policy_valid_from"))
    doc.flags["policy_valid_until"] = _parse_date(data.get("policy_valid_until"))
    doc.flags["intimation_date"] = _parse_date(data.get("intimation_date"))
    doc.flags["fir_date"] = _parse_date(data.get("fir_date"))
    doc.flags["use_class"] = data.get("use_class") or None
    return doc


def extract_one(doc_type: str, text: str) -> models.ExtractedDocument:
    """Extract structured fields from one raw document text."""
    if not (text or "").strip():
        raise ValueError(f"Empty {doc_type} document — cannot extract.")

    client = _client()
    if client is not None:
        try:
            data = _extract_llm(client, doc_type, text)
            return _normalize(data, doc_type)
        except Exception as exc:  # noqa: BLE001 - fall back to deterministic
            if not _FALLBACK_ENABLED:
                raise
            # Log note and fall through to deterministic parser.
            note = str(exc)

    doc = _deterministic_extract(doc_type, text)
    if client is not None and _FALLBACK_ENABLED:
        doc.notes = "LLM extraction failed; used deterministic fallback."
    return doc


def extract_all(payload: models.ReviewRequest) -> list[models.ExtractedDocument]:
    """Run extraction for all three documents of a claim."""
    docs = []
    docs.append(extract_one("claim_form", payload.claim_form))
    second_kind = (
        "estimate" if payload.second_document_kind == "estimate" else "fir"
    )
    docs.append(extract_one(second_kind, payload.second_document))
    inc = extract_one("incident_description", payload.incident_description)
    # Copy any normative dates/flags the incident description contributes.
    docs.append(inc)
    return docs


# ---------------------------------------------------------------------------
# Deterministic fallback parser (regex-based), no LLM.
# Used only when GEMINI_API_KEY is absent or the LLM call fails.
# ---------------------------------------------------------------------------

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_DMY = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")


def _extract_date(text: str) -> Optional[str]:
    m = _ISO.search(text)
    if m:
        return m.group(0)
    m = _DMY.search(text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # Month-name formats: "10 Feb 2026", "10 February 2026"
    m = re.search(
        r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        return f"{m.group(3)}-{months[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def _deterministic_extract(doc_type: str, text: str) -> models.ExtractedDocument:
    """Minimal keyless parser — enough to keep the pipeline testable.

    Strips markdown bold markers first so `**Label:** value` patterns match.
    """
    clean = re.sub(r"\*\*", "", text)
    line_items = re.findall(r"(?:Busy )?([^:\n]+):\s*([^\n]+)", clean)
    kv = {k.strip().lower(): v.strip() for k, v in line_items}

    def get(*names):
        for n in names:
            for k, v in kv.items():
                if n in k:
                    return v
        return None

    doc = models.ExtractedDocument(document_type=doc_type, description="", flags={})

    doc.policy_number = get("policy") or ""
    doc.insured_name = get("insured name") or ""
    doc.vehicle_registration = get("vehicle registration", "registration") or ""
    doc.vehicle_make_model = get("vehicle make/model", "make/model") or ""

    idv_txt = get("insured declared value", "idv")
    amt_txt = get("amount claimed")
    if idv_txt:
        doc.idv = _extract_money(idv_txt)
    if amt_txt:
        doc.claimed_amount = _extract_money(amt_txt)

    doc.incident_date = _extract_date(
        get("date of incident", "incident date", "date theft discovered", "date of theft", "date of incident") or clean
    )

    # Normative dates, looked up by label.
    def flag_date(*labels):
        v = get(*labels)
        return _extract_date(v) if v else None

    doc.flags["intimation_date"] = flag_date(
        "date of intimation", "date of signing"
    )
    doc.flags["fir_date"] = flag_date("fir date", "date of report")
    doc.flags["incident_date"] = doc.incident_date
    policy_start = get("policy start date", "policy valid from")
    policy_end = get("policy end date", "policy valid until")
    period_txt = get("policy period")
    if policy_start:
        doc.flags["policy_valid_from"] = _extract_date(policy_start)
    if policy_end:
        doc.flags["policy_valid_until"] = _extract_date(policy_end)
    if period_txt and "to" in period_txt.lower():
        left, _, right = period_txt.partition("to")
        doc.flags["policy_valid_from"] = _extract_date(left) or doc.flags.get(
            "policy_valid_from"
        )
        doc.flags["policy_valid_until"] = _extract_date(right) or doc.flags.get(
            "policy_valid_until"
        )

    # Heuristic flag scan (fallback path only; the LLM path does this properly).
    low = clean.lower()
    if any(k in low for k in [
        "delivery", "drop off", "dropping off", "for hire", "for reward",
        "airport transfer", "commercial", "fare", "passenger for payment",
        "picking up fares", "ride-hailing", "zomato", "swiggy", "uber", "ola",
        "taxi", "cab service",
    ]):
        doc.flags["commercial_use"] = True
    negated = any(k in low for k in [
        "no other vehicle", "no third party", "not involved", "neither ... hurt",
        "no third-party", "none involved", "no other person",
    ])
    if negated:
        doc.flags["third_party_involved"] = False
    elif any(k in low for k in [
        "third party", "another vehicle", "hit by a truck", "other vehicle",
        "two-wheeler from behind", "hit me from behind", "rear-end",
        "second vehicle",
    ]):
        doc.flags["third_party_involved"] = True
    if any(k in low for k in ["under the influence", "drunk", "intoxicated", "alcohol"]):
        doc.flags["under_influence"] = True
    if any(k in low for k in ["no license", "without a license", "without a valid driving license"]):
        doc.flags["valid_license"] = False
    return doc


def _extract_money(text: str) -> Optional[float]:
    vals = []
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)", text):
        vals.append(float(m.group(1).replace(",", "")))
    return max(vals) if vals else None