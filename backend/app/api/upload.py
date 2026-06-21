import os
import time
import uuid
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from ..config import (
    UPLOAD_DIR,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_RESPONSE_TEXT_CHARS,
    get_logger,
)
from ..services.text_extractor import extract_text
from ..services.text_cleaner import clean_text
from ..services.global_understanding import async_extract_global_understanding
from ..services.concept_extractor import async_extract_concepts
from ..services.hierarchy_assembly import assemble_hierarchy
from ..services.topology_inference import async_assemble_topology
from ..services.graph_transformer import transform_graph
from ..database import save_document
from .stream import create_job, update_job_progress, complete_job, fail_job

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf"}


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


async def process_document_background(job_id: str, filename: str, cleaned_text: str):
    try:
        t0 = time.monotonic()
        
        # ── Stage 1: Global Document Understanding ──
        logger.info("=== Stage 1: Global Document Understanding ===")
        update_job_progress(job_id, "Understanding global context...")
        try:
            global_understanding = await async_extract_global_understanding(cleaned_text)
        except Exception as e:
            logger.exception("Global understanding failed, continuing without context")
            global_understanding = {
                "document_summary": "Global understanding unavailable.",
                "major_themes": [],
                "conceptual_domains": [],
                "root_concepts": [],
                "educational_structure": "Not available.",
                "learning_flow": "Not available.",
            }

        # ── Stage 2: Hierarchical Concept Extraction ──
        logger.info("=== Stage 2: Hierarchical Concept Extraction ===")
        update_job_progress(job_id, "Extracting concepts...")
        
        def concept_progress(msg):
            update_job_progress(job_id, msg)
            
        try:
            raw_concepts = await async_extract_concepts(cleaned_text, global_understanding=global_understanding, status_callback=concept_progress)
            
            update_job_progress(job_id, "Assembling concept hierarchy...")
            concepts = assemble_hierarchy(raw_concepts)
        except Exception as e:
            logger.exception("Concept extraction failed")
            fail_job(job_id, f"Failed to extract concepts: {e}")
            return

        # ── Stage 3: Knowledge Topology Inference ──
        logger.info("=== Stage 3: Knowledge Topology Inference ===")
        update_job_progress(job_id, "Building knowledge topology...")
        
        def topology_progress(msg):
            update_job_progress(job_id, msg)
            
        try:
            relationships, hub_concepts = await async_assemble_topology(concepts, global_understanding=global_understanding, status_callback=topology_progress)
        except Exception as e:
            logger.exception("Topology inference failed, continuing without relationships")
            relationships = []
            hub_concepts = []

        # ── Graph assembly (Cytoscape-ready) ──
        update_job_progress(job_id, "Finalizing graph data...")
        try:
            graph_data = transform_graph(concepts, relationships, hub_concepts)
        except Exception as e:
            logger.exception("Graph assembly failed")
            graph_data = {"nodes": [], "edges": [], "hub_concept_ids": []}

        # ── Response ──
        response_text = cleaned_text
        text_truncated = False
        if len(cleaned_text) > MAX_RESPONSE_TEXT_CHARS:
            response_text = cleaned_text[:MAX_RESPONSE_TEXT_CHARS]
            text_truncated = True

        safe_concepts = concepts if isinstance(concepts, list) else []
        safe_relationships = relationships if isinstance(relationships, list) else []
        safe_hub_concepts = hub_concepts if isinstance(hub_concepts, list) else []
        safe_global = global_understanding if isinstance(global_understanding, dict) else {}

        t_total = time.monotonic() - t0
        
        result = {
            "document_id": job_id,
            "filename": filename,
            "char_count": len(cleaned_text),
            "text": response_text,
            "text_truncated": text_truncated,
            "global_understanding": safe_global,
            "concepts": safe_concepts,
            "relationships": safe_relationships,
            "hub_concepts": safe_hub_concepts,
            "graph": graph_data,
        }
        
        # Persist before signaling completion so a shared/reloaded link always
        # resolves to a stored graph. Persistence failure must not break the
        # live response — the client already has the result via SSE.
        try:
            save_document(job_id, filename, result)
        except Exception:
            logger.exception("Failed to persist document %s", job_id)

        complete_job(job_id, result)
        logger.info("Job %s completed in %.1fs", job_id, t_total)

    except Exception as e:
        logger.exception("Background processing failed")
        fail_job(job_id, f"Processing failed: {str(e)}")


@router.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    t0 = time.monotonic()
    filename = file.filename or "unknown"
    logger.info("=== Upload start: %s ===", filename)

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("Rejected: bad extension '%s'", ext)
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    logger.info("Read %d bytes from upload", len(content))

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        limit_mb = MAX_UPLOAD_SIZE_BYTES // 1024 // 1024
        actual_mb = len(content) / (1024 * 1024)
        logger.warning("Rejected: file too large %.1fMB > %dMB", actual_mb, limit_mb)
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({actual_mb:.1f}MB). Maximum is {limit_mb}MB.",
        )

    job_id = uuid.uuid4().hex[:12]
    safe_filename = f"{job_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except OSError as exc:
        logger.exception("Failed to save upload to disk")
        raise HTTPException(status_code=507, detail=f"Failed to save uploaded file: {exc}")
    logger.info("Saved upload as %s", safe_filename)

    # We do text extraction synchronously here so we can fail early if the PDF is
    # unreadable. It's usually fast enough not to block for long. The uploaded file
    # is only needed for this step, so we remove it once the text is in hand.
    t1 = time.monotonic()
    try:
        raw_text = extract_text(file_path)
    except ValueError as e:
        logger.error("Text extractor rejected: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Text extraction failed")
        raise HTTPException(status_code=422, detail=f"Failed to extract text: {e}")
    finally:
        _remove_quietly(file_path)

    t2 = time.monotonic()
    cleaned_text = clean_text(raw_text)

    if not cleaned_text.strip():
        logger.warning("No usable text extracted from %s", filename)
        raise HTTPException(
            status_code=422,
            detail="No readable text found. The PDF may be scanned images or empty.",
        )

    t3 = time.monotonic()
    logger.info(
        "Text pipeline: extract=%.1fs clean=%.1fs final_chars=%d",
        t2 - t1,
        t3 - t2,
        len(cleaned_text),
    )

    create_job(job_id)
    background_tasks.add_task(process_document_background, job_id, filename, cleaned_text)

    return {"job_id": job_id, "status": "processing"}
