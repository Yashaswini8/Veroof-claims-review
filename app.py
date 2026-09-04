"""VeRoof — Claims Evidence Review Assistant.

Run:  python app.py  ->  http://localhost:8000
"""

import os
import threading
import uuid

import uvicorn

from src import jobs
from src import models
from src import pipeline
from src import sample_loader


def create_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="VeRoof", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory="frontend"), name="static")

    @app.get("/")
    def index():
        return FileResponse("frontend/index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "VeRoof"}

    @app.get("/api/samples")
    def list_samples():
        return sample_loader.list_samples()

    @app.get("/api/reviews")
    def list_reviews():
        return {"reviews": jobs.list_review_summaries()}

    @app.get("/api/reviews/{job_id}")
    def get_review(job_id: str):
        state = jobs.get(job_id)
        if state is None:
            return JSONResponse(status_code=404, content={"error": "not found"})
        return state.snapshot()

    @app.post("/api/review")
    def start_review(payload: models.ReviewRequest):
        try:
            models.validate_request(payload)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        job = jobs.create()
        job.record_stage("queueing", "Queued for review")
        thread = threading.Thread(
            target=pipeline.run_review, args=(job, payload), daemon=True
        )
        thread.start()
        return {"job_id": job.id, "status": "started"}

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")