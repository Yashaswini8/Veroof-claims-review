"""Local, deterministic parsing of the policy document into clause chunks.

This is a pure-Python parser (no LLM) so clause citation is grounded in the
actual document text. Used by the retrieval step as the chunk source.
"""

from __future__ import annotations

import os
import re
from typing import Optional

POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "policy.md")
_CHUNK_CACHE: Optional[list[dict]] = None


def read_policy() -> str:
    with open(
        os.path.join(os.path.dirname(__file__), "..", "data", "policy.md"),
        encoding="utf-8",
    ) as fh:
        return fh.read()


def chunk_policy() -> list[dict]:
    """Split the policy into numbered clause chunks.

    Returns a list of dicts: {number, title, text}.
    """
    global _CHUNK_CACHE
    if _CHUNK_CACHE is not None:
        return _CHUNK_CACHE

    text = read_policy()
    lines = text.splitlines()
    chunks: list[dict] = []
    current: Optional[dict] = None
    current_text: list[str] = []

    def flush():
        nonlocal current, current_text
        if current is not None:
            current["text"] = "\n".join(current_text).strip()
            chunks.append(current)
        current = None
        current_text = []

    clause_re = re.compile(
        r"^###\s+Clause\s+(\d+\.\d+)\s*[—-]\s*(.+)$", re.IGNORECASE
    )

    preamble = []
    in_cover = False
    for line in lines:
        stripped = line.strip()
        m = clause_re.match(stripped)
        if m:
            flush()
            if preamble:
                chunks.append({
                    "number": "PREAMBLE",
                    "title": "Cover sheet / definitions",
                    "text": "\n".join(preamble),
                })
                preamble = []
            current = {"number": m.group(1), "title": m.group(2).strip(), "text": ""}
            current_text = [stripped]
        else:
            if m is None and current is None:
                if stripped:
                    preamble.append(stripped)
            elif current is not None:
                current_text.append(line)
    flush()
    if preamble:
        chunks.append({
            "number": "PREAMBLE",
            "title": "Cover sheet / definitions",
            "text": "\n".join(preamble),
        })
    _CHUNK_CACHE = chunks
    return chunks


def get_clause(number: str) -> Optional[dict]:
    for c in chunk_policy():
        if c["number"].lower() == number.lower():
            return c
    return None