"""SQLite persistence for processed documents.

A processed document is stored as a single row holding its canonical graph
payload (the same shape the upload pipeline streams to the client) plus a few
queryable metadata columns. This is intentionally a JSON-blob design: the client
renders and searches the whole graph in memory, so normalizing concepts and
relationships into separate tables would add storage with no reader. Persisting
the canonical payload keeps a shared/reloaded graph byte-for-byte identical to
the one produced at upload time.
"""

import json
import os
import sqlite3
from typing import Any, Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    filename     TEXT    NOT NULL,
    title        TEXT,
    status       TEXT    NOT NULL DEFAULT 'ready',
    char_count   INTEGER DEFAULT 0,
    node_count   INTEGER DEFAULT 0,
    edge_count   INTEGER DEFAULT 0,
    result_json  TEXT    NOT NULL,
    created_at   TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_document(doc_id: str, filename: str, result: dict[str, Any]) -> None:
    """Persist (or replace) a processed document's full graph payload."""
    graph = result.get("graph") or {}
    global_understanding = result.get("global_understanding") or {}
    title = (global_understanding.get("document_summary") or "").strip()
    # Use a short, human-readable title rather than the full summary paragraph.
    title = title.split(".")[0][:120] if title else filename

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO documents
                (id, filename, title, status, char_count, node_count, edge_count, result_json)
            VALUES (?, ?, ?, 'ready', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                filename    = excluded.filename,
                title       = excluded.title,
                status      = excluded.status,
                char_count  = excluded.char_count,
                node_count  = excluded.node_count,
                edge_count  = excluded.edge_count,
                result_json = excluded.result_json
            """,
            (
                doc_id,
                filename,
                title,
                int(result.get("char_count", 0) or 0),
                len(graph.get("nodes", []) or []),
                len(graph.get("edges", []) or []),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_document(doc_id: str) -> Optional[dict[str, Any]]:
    """Return the stored graph payload for a document, or None if absent."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT result_json FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    try:
        return json.loads(row["result_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def list_documents(limit: int = 20) -> list[dict[str, Any]]:
    """Return lightweight metadata for recently processed documents."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, title, node_count, edge_count, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
