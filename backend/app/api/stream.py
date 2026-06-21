import asyncio
import time
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from ..config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory tracker for in-flight jobs. Finished graphs are persisted to SQLite,
# so this only needs to hold a job while it's processing and being streamed.
# A single-process deployment is assumed; scale-out would move this to Redis.
JOBS: dict[str, dict] = {}
JOB_TTL_SECONDS = 30 * 60


def _evict_stale_jobs() -> None:
    """Drop jobs that finished (or stalled) long enough ago to be safe to forget."""
    now = time.monotonic()
    stale = [
        jid for jid, job in JOBS.items()
        if now - job.get("created", now) > JOB_TTL_SECONDS
    ]
    for jid in stale:
        JOBS.pop(jid, None)
    if stale:
        logger.info("Evicted %d stale job(s)", len(stale))


def create_job(job_id: str):
    _evict_stale_jobs()
    JOBS[job_id] = {
        "status": "pending",
        "progress_message": "Initializing...",
        "result": None,
        "error": None,
        "created": time.monotonic(),
        "event": asyncio.Event()
    }

def update_job_progress(job_id: str, message: str):
    if job_id in JOBS:
        JOBS[job_id]["progress_message"] = message
        JOBS[job_id]["event"].set()

def complete_job(job_id: str, result: dict):
    if job_id in JOBS:
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["result"] = result
        JOBS[job_id]["event"].set()

def fail_job(job_id: str, error: str):
    if job_id in JOBS:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = error
        JOBS[job_id]["event"].set()

async def event_generator(request: Request, job_id: str) -> AsyncGenerator[dict, None]:
    if job_id not in JOBS:
        yield {
            "event": "error",
            "data": "Job not found"
        }
        return

    job = JOBS[job_id]
    last_message = None

    while True:
        if await request.is_disconnected():
            logger.info("Client disconnected from stream %s", job_id)
            break

        if job["status"] == "failed":
            yield {
                "event": "error",
                "data": job["error"]
            }
            JOBS.pop(job_id, None)
            break

        if job["status"] == "completed":
            import json
            yield {
                "event": "complete",
                "data": json.dumps(job["result"])
            }
            JOBS.pop(job_id, None)
            break

        if job["progress_message"] != last_message:
            last_message = job["progress_message"]
            yield {
                "event": "progress",
                "data": last_message
            }

        # Wait for the next update
        job["event"].clear()
        try:
            await asyncio.wait_for(job["event"].wait(), timeout=15.0)
        except asyncio.TimeoutError:
            # Send a ping to keep connection alive
            yield {
                "event": "ping",
                "data": "keep-alive"
            }

@router.get("/stream/{job_id}")
async def stream_progress(request: Request, job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return EventSourceResponse(event_generator(request, job_id))
