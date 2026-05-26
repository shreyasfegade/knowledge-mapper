import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from ..config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Simple in-memory job tracker
# In production, use Redis or a database.
JOBS: dict[str, dict] = {}

def create_job(job_id: str):
    JOBS[job_id] = {
        "status": "pending",
        "progress_message": "Initializing...",
        "result": None,
        "error": None,
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
            break

        if job["status"] == "completed":
            import json
            yield {
                "event": "complete",
                "data": json.dumps(job["result"])
            }
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
