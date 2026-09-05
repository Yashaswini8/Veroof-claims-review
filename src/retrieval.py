"""Policy clause retrieval (RAG) with gemini-embedding-001.

Builds a small local index over the numbered clauses of policy.md and retrieves
the most relevant clauses for a given claim. Embeddings are produced by Gemini
(gemini-embedding-001). When no API key is present they are precomputed and
cached to disk under data/ so startup stays within the 90s budget.

The LLM/report may only cite clauses that were actually retrieved here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np

from src import policy

EMBED_MODEL = "gemini-embedding-001"
CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "embeddings_cache.json"
)
CACHE_BUNDLE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "embeddings_bundle.npz"
)

# Number of clauses to return per query.
TOP_K = 6


def _client():
    from google import genai

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)


def _embed_texts(client, texts: list[str]) -> list[list[float]]:
    """Embed a list of texts with gemini-embedding-001."""
    from src.ai_runner import call_embed_content

    result = call_embed_content(
        client,
        EMBED_MODEL,
        texts,
        config={"outputDimensionality": 768},
    )
    return [emb.values for emb in result.embeddings]


def _embed_one(client, text: str) -> list[float]:
    return _embed_texts(client, [text])[0]


def build_and_cache(client, chunks: list[dict]) -> None:
    """Embed all chunk texts and persist to disk as a numpy bundle."""
    texts = [c["text"] for c in chunks]
    vectors = _embed_texts(client, texts)
    meta = [{"number": c["number"], "title": c["title"]} for c in chunks]
    Path(CACHE_BUNDLE).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE_BUNDLE,
        vectors=np.array(vectors, dtype="float32"),
        numbers=np.array([m["number"] for m in meta], dtype=object),
        titles=np.array([m["title"] for m in meta], dtype=object),
    )
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return overriding_meta(meta)


def overriding_meta(meta):
    return meta


def _load_cache() -> Optional[dict]:
    """Load the persisted index if it matches the current policy chunks."""
    if not (os.path.exists(CACHE_BUNDLE) and os.path.exists(CACHE_PATH)):
        return None
    chunks = policy.chunk_policy()
    with open(CACHE_PATH, encoding="utf-8") as fh:
        cached_meta = json.load(fh)
    if [c["number"] for c in chunks] != [m["number"] for m in cached_meta]:
        return None
    data = np.load(CACHE_BUNDLE, allow_pickle=True)
    return {
        "vectors": data["vectors"].astype("float32"),
        "meta": cached_meta,
    }


def retrieve_clauses(payload, docs) -> list:
    """Retrieve the policy clauses relevant to this claim.

    Returns a list of ClauseHit models. The query fuses claim-type + extracted
    flags + narrative so theft claims retrieve the theft/intimation clauses and
    accident claims retrieve the relevant ones.
    """
    from src import models

    client = _client()
    if client is None:
        # No API key: never touch the cache (query embedding needs the API).
        return _lexical_retrieve(payload, docs)

    index = _load_cache()
    if index is None:
        # First run without a precomputed index.
        chunks = policy.chunk_policy()
        build_and_cache(client, chunks)
        index = _load_cache()
        if index is None:
            # No key and no cache: fall back to lexical scoring so the app still
            # returns grounded clause citations (never invented ones).
            return _lexical_retrieve(payload, docs)

    query = _build_query(payload, docs)
    qvec = np.array(_embed_texts(client, [query])[0], dtype="float32")
    return _score(index, qvec)


def _build_query(payload, docs) -> str:
    parts = [f"claim type: {payload.claim_type}"]
    flags = {}
    for d in docs:
        flags.update(d.flags)
    if payload.claim_type == "theft":
        parts.append("theft of insured vehicle")
        parts.append("FIR filing, intimation window, required theft documents")
    else:
        parts.append("own damage accidental damage claim")
        parts.append("repair estimate, intimation window, IDV comparison")
    if flags.get("commercial_use"):
        parts.append("commercial use of private vehicle exclusion")
    if flags.get("third_party_involved"):
        parts.append("third party involvement FIR requirement")
    if flags.get("under_influence"):
        parts.append("driving under influence exclusion")
    if flags.get("pre_existing_damage"):
        parts.append("pre existing damage exclusion")
    narrative = " ".join((d.description or "") for d in docs)
    if narrative:
        parts.append("narrative: " + narrative[:500])
    return "\n".join(parts)


def _score(index: dict, qvec: np.ndarray) -> list:
    from src import models

    vecs = index["vectors"]
    dots = vecs @ qvec
    norms = np.linalg.norm(vecs, axis=1) * np.linalg.norm(qvec)
    scores = dots / np.maximum(norms, 1e-8)
    top_idx = np.argsort(-scores)[:TOP_K]
    hits: list[models.ClauseHit] = []
    meta = index["meta"]
    for i in top_idx:
        number = meta[i]["number"]
        clause = policy.get_clause(number)
        if clause is None:
            continue
        hits.append(
            models.ClauseHit(
                number=number,
                title=clause["title"],
                quote=clause["text"][:400],
                relevance=f"Similarity {float(scores[i]):.2f}",
                full_text=clause["text"],
            )
        )
    return hits


def _lexical_retrieve(payload, docs) -> list:
    """Keyword-scoring fallback when no embeddings are available.

    Each clause is scored by how many claim-keywords it contains. Only clauses
    with the strongest lexical overlap are returned — always real clauses from
    policy.md, never invented.
    """
    from src import models

    keywords = _lexical_keywords(payload, docs)
    scored = []
    for c in policy.chunk_policy():
        text = c["text"].lower()
        hits = sum(1 for k in keywords if k in text)
        scored.append((hits, c))
    scored.sort(key=lambda t: -t[0])
    hits = []
    for count, c in scored:
        if count <= 0:
            continue
        hits.append(
            models.ClauseHit(
                number=c["number"],
                title=c["title"],
                quote=c["text"][:400],
                relevance=f"{count} keyword(s) matched",
                full_text=c["text"],
            )
        )
        if len(hits) >= TOP_K:
            break
    return hits


def _lexical_keywords(payload, docs) -> list[str]:
    base = {
        "accident": ["accident", "own-damage", "intimation", "repair estimate", "eligible repair"],
        "theft": ["theft", "first information report", "fir", "intimation", "key handover", "registration certificate"],
    }
    words = list(base.get(payload.claim_type, []))
    flags = {}
    for d in docs:
        flags.update(d.flags)
    if flags.get("commercial_use"):
        words += ["commercial purpose", "hire or reward", "commercial"]
    if flags.get("third_party_involved"):
        words += ["first information report", "third party"]
    if flags.get("under_influence"):
        words += ["under the influence"]
    return [w.lower() for w in words]


def warm_index() -> None:
    """Precompute and persist the embedding index if a key is present.

    Called at startup so a keyless / cached run stays fast.
    """
    if _load_cache() is not None:
        return
    client = _client()
    if client is None:
        return
    chunks = policy.chunk_policy()
    build_and_cache(client, chunks)

# Build the index at import time when a key is available, so startup warms it.
try:
    warm_index()
except Exception:  # noqa: BLE001 - a cold startup must not crash the app
    pass