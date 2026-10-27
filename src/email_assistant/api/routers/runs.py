"""Run the sample emails through a stage from the UI (background job, polled)."""

import threading
import uuid

from fastapi import APIRouter, HTTPException

from email_assistant import config_store
from email_assistant.settings import get_settings
from email_assistant.stage_runner import run
from email_assistant.stages import STAGES

router = APIRouter(tags=["runs"])

_jobs: dict[str, dict] = {}


def _work(job_id: str, stage: str, gmail_count: int = 0) -> None:
    try:
        samples = None
        if gmail_count:
            from email_assistant.gmail.messages import recent

            samples = recent(gmail_count, config_store.section("gmail").query)
            if not samples:
                raise ValueError("No emails match the Gmail query")
        _jobs[job_id].update(status="done", rows=run(stage, samples))
    except Exception as e:
        _jobs[job_id].update(status="error", error=f"{type(e).__name__}: {e}")


@router.post("/runs/samples")
async def start(stage: str = list(STAGES)[-1]):
    if stage not in STAGES:
        raise HTTPException(404, f"Unknown stage {stage!r}")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"id": job_id, "stage": stage, "status": "running"}
    threading.Thread(target=_work, args=(job_id, stage), daemon=True).start()
    return _jobs[job_id]


@router.get("/runs/{job_id}")
async def get(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "Unknown run")
    return _jobs[job_id]


@router.post("/runs/gmail")
async def start_gmail(count: int = 0, stage: str = list(STAGES)[-1]):
    """Run your most recent Gmail emails (matching the gmail query) through a stage.

    Read-only on Gmail: nothing is marked read, labelled or sent; reply tools stay simulated.
    """
    if stage not in STAGES:
        raise HTTPException(404, f"Unknown stage {stage!r}")
    count = count or get_settings().gmail_preview_count
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"id": job_id, "stage": stage, "status": "running", "source": "gmail"}
    threading.Thread(target=_work, args=(job_id, stage, count), daemon=True).start()
    return _jobs[job_id]
