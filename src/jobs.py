"""In-memory job store; lets the frontend poll real pipeline-stage progress."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Job:
    id: str
    created_at: float
    status: str = "running"
    stages: list[str] = field(default_factory=list)
    report: Optional[dict] = None
    error: Optional[str] = None
    summary: dict = field(default_factory=dict)

    def record_stage(self, label: str) -> None:
        self.stages.append(label)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "stages": list(self.stages),
            "report": self.report,
            "error": self.error,
            "summary": self.summary,
        }


_LOCK = threading.Lock()
_JOBS: dict[str, Job] = {}
_RECENT: list[str] = []
_MAX_RECENT = 25


def create() -> Job:
    job = Job(id=uuid.uuid4().hex[:12], created_at=time.time())
    with _LOCK:
        _JOBS[job.id] = job
        _RECENT.insert(0, job.id)
        del _RECENT[_MAX_RECENT:]
    return job


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def list_review_summaries() -> list[dict]:
    with _LOCK:
        out = []
        for jid in _RECENT:
            job = _JOBS[jid]
            if job.report is not None:
                out.append(job.summary)
        return out