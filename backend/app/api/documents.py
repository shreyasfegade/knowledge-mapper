"""Retrieval endpoints for previously processed documents.

These back the shareable-link / reload-on-refresh experience: once a document
has been processed, its graph is persisted and can be fetched by id without
re-running the (slow, paid) LLM pipeline.
"""

from fastapi import APIRouter, HTTPException

from ..config import get_logger
from ..database import get_document, list_documents
from ..examples_seed import list_example_meta

logger = get_logger(__name__)
router = APIRouter()


@router.get("/examples")
def examples():
    """List the bundled example graphs for the landing-page gallery.

    Each entry deep-links to ``?doc=<id>`` and loads instantly from the seeded
    database — no API key or upload required.
    """
    return {"examples": list_example_meta()}


@router.get("/documents")
def recent_documents(limit: int = 20):
    """List recently processed documents (lightweight metadata only)."""
    limit = max(1, min(limit, 100))
    return {"documents": list_documents(limit)}


@router.get("/document/{doc_id}")
def document(doc_id: str):
    """Return the full stored graph payload for a processed document."""
    result = get_document(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
