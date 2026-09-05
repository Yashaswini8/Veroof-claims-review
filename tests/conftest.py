"""Force the deterministic (keyless) paths for every test.

The unit suite must be fast, offline and reproducible no matter whether
GEMINI_API_KEY is set in the environment. We stub the two _client()
factories so extraction always uses the deterministic parser and retrieval
always uses lexical scoring.
"""

import pytest


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    from src import extraction, retrieval

    monkeypatch.setattr(extraction, "_client", lambda: None)
    monkeypatch.setattr(retrieval, "_client", lambda: None)
    yield