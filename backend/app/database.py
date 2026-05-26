import sqlite3
import os
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    filename        TEXT    NOT NULL,
    title           TEXT,
    page_count      INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'pending',
    error_message   TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concepts (
    id              TEXT PRIMARY KEY,
    document_id     TEXT    NOT NULL REFERENCES documents(id),
    name            TEXT    NOT NULL,
    definition      TEXT,
    importance      REAL    DEFAULT 0.5,
    embedding       BLOB,
    cluster_id      INTEGER
);

CREATE TABLE IF NOT EXISTS relationships (
    id              TEXT PRIMARY KEY,
    source_id       TEXT    NOT NULL REFERENCES concepts(id),
    target_id       TEXT    NOT NULL REFERENCES concepts(id),
    type            TEXT    NOT NULL,
    direction       TEXT    DEFAULT 'forward',
    explanation     TEXT,
    confidence      REAL    DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_concepts_doc ON concepts(document_id);
CREATE INDEX IF NOT EXISTS idx_relationships_src ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_tgt ON relationships(target_id);
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
