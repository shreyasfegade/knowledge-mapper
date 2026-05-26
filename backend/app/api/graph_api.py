from fastapi import APIRouter
from .upload import upload_pdf

router = APIRouter()

@router.get("/graph/{doc_id}")
def get_graph(doc_id: str):
    """Return Cytoscape-ready graph for a document."""
    # Re-read the stored document concepts from the upload result
    # For V1, we'll use the upload endpoint response directly
    return {"message": "Graph endpoint — use /upload for full pipeline data"}
