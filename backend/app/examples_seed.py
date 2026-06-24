"""Seed bundled example graphs into the database on startup.

The deployed demo must show real, explorable graphs the instant a visitor
arrives — with no API key and no upload. We ship a few precomputed graph
payloads in ``app/examples/*.json`` (produced by ``scripts/generate_examples.py``)
and upsert them into the documents table on every boot. Re-seeding each time
makes them immune to Railway's ephemeral filesystem: even after a restart that
wipes the SQLite file, the examples are always present.

Each example is stored under a stable id (``example-<slug>``) so the frontend
can deep-link to it via ``?doc=example-<slug>`` using the existing reload path.
"""

import glob
import json
import os
from typing import Any, Optional

from .config import get_logger
from .database import save_document

logger = get_logger(__name__)

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "examples")

_meta_cache: Optional[list[dict[str, Any]]] = None


def _load_example_files() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fp in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.json"))):
        try:
            with open(fp, encoding="utf-8") as f:
                results.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load example file %s", fp)
    return results


def seed_examples() -> int:
    """Upsert every bundled example into the documents table. Returns the count."""
    count = 0
    for result in _load_example_files():
        doc_id = result.get("document_id")
        if not doc_id:
            continue
        try:
            save_document(doc_id, result.get("filename", "example.pdf"), result)
            count += 1
        except Exception:
            logger.exception("Failed to seed example %s", doc_id)
    logger.info("Seeded %d example graph(s)", count)
    return count


def list_example_meta() -> list[dict[str, Any]]:
    """Lightweight metadata for the landing-page example gallery (cached)."""
    global _meta_cache
    if _meta_cache is not None:
        return _meta_cache

    meta: list[dict[str, Any]] = []
    for result in _load_example_files():
        graph = result.get("graph") or {}
        gu = result.get("global_understanding") or {}
        nodes = graph.get("nodes") or []
        domains = sorted(
            {
                n.get("data", {}).get("domain")
                for n in nodes
                if n.get("data", {}).get("domain")
            }
        )
        meta.append(
            {
                "id": result.get("document_id"),
                "title": result.get("example_title") or result.get("filename"),
                "summary": (gu.get("document_summary") or "").strip()[:180],
                "node_count": len(nodes),
                "edge_count": len(graph.get("edges") or []),
                "domains": domains[:3],
            }
        )
    _meta_cache = meta
    return meta
