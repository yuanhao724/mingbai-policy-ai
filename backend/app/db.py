from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'draft',
    reviewer TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ord);
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    mode TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
        migrations = {
            "review_status": "TEXT NOT NULL DEFAULT 'draft'",
            "reviewer": "TEXT NOT NULL DEFAULT ''",
            "reviewed_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def session(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_document(
    path: Path,
    *,
    title: str,
    filename: str,
    content: str,
    size_bytes: int,
    chunks: Sequence[str],
    review_status: str = "draft",
    reviewer: str = "",
) -> dict:
    doc_id = uuid.uuid4().hex[:12]
    created = utc_now()
    reviewed_at = created if review_status == "approved" else ""
    with session(path) as conn:
        conn.execute(
            "INSERT INTO documents "
            "(id, title, filename, content, size_bytes, chunk_count, created_at, review_status, reviewer, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                title,
                filename,
                content,
                size_bytes,
                len(chunks),
                created,
                review_status,
                reviewer,
                reviewed_at,
            ),
        )
        conn.executemany(
            "INSERT INTO chunks (doc_id, ord, text) VALUES (?, ?, ?)",
            [(doc_id, idx, text) for idx, text in enumerate(chunks)],
        )
    return {
        "id": doc_id,
        "title": title,
        "filename": filename,
        "size_bytes": size_bytes,
        "chunk_count": len(chunks),
        "created_at": created,
        "review_status": review_status,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
    }


def list_documents(path: Path) -> list[dict]:
    with session(path) as conn:
        rows = conn.execute(
            "SELECT id, title, filename, size_bytes, chunk_count, created_at, "
            "review_status, reviewer, reviewed_at "
            "FROM documents ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_document(path: Path, doc_id: str) -> dict | None:
    with session(path) as conn:
        row = conn.execute(
            "SELECT id, title, filename, content, size_bytes, chunk_count, created_at, "
            "review_status, reviewer, reviewed_at "
            "FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_document(path: Path, doc_id: str) -> bool:
    with session(path) as conn:
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return cur.rowcount > 0


def review_document(
    path: Path,
    doc_id: str,
    *,
    status: str,
    reviewer: str,
    note: str = "",
) -> dict | None:
    reviewed_at = utc_now()
    with session(path) as conn:
        cursor = conn.execute(
            "UPDATE documents SET review_status = ?, reviewer = ?, reviewed_at = ? WHERE id = ?",
            (status, reviewer, reviewed_at, doc_id),
        )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "INSERT INTO audit_logs (action, actor, target, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                "policy.review",
                reviewer,
                doc_id,
                json.dumps({"status": status, "note": note}, ensure_ascii=False),
                reviewed_at,
            ),
        )
        row = conn.execute(
            "SELECT id, title, filename, size_bytes, chunk_count, created_at, "
            "review_status, reviewer, reviewed_at FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    return dict(row) if row else None


def recent_audit(path: Path, limit: int = 40) -> list[dict]:
    with session(path) as conn:
        rows = conn.execute(
            "SELECT id, action, actor, target, detail, created_at "
            "FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def all_chunks(path: Path) -> list[dict]:
    with session(path) as conn:
        rows = conn.execute(
            "SELECT c.id AS chunk_id, c.doc_id, d.title AS doc_title, c.ord, c.text "
            "FROM chunks c JOIN documents d ON d.id = c.doc_id "
            "ORDER BY d.created_at DESC, c.ord ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def chunks_for_document(path: Path, doc_id: str) -> list[dict]:
    with session(path) as conn:
        rows = conn.execute(
            "SELECT id AS chunk_id, doc_id, ord, text FROM chunks "
            "WHERE doc_id = ? ORDER BY ord ASC",
            (doc_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def record_query(
    path: Path,
    *,
    question: str,
    answer: str,
    mode: str,
    sources: list[dict],
    latency_ms: float,
) -> int:
    with session(path) as conn:
        cur = conn.execute(
            "INSERT INTO queries (question, answer, mode, sources_json, latency_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                question,
                answer,
                mode,
                json.dumps(sources, ensure_ascii=False),
                latency_ms,
                utc_now(),
            ),
        )
        return int(cur.lastrowid)


def compute_stats(
    path: Path,
    manual_minutes: float,
    min_assistant_minutes: float,
    manual_minutes_per_policy: float = 30.0,
    assistant_minutes_per_policy: float = 5.0,
) -> dict:
    with session(path) as conn:
        documents = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        agg = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(AVG(latency_ms), 0) AS avg_ms, "
            "COALESCE(MAX(latency_ms), 0) AS max_ms FROM queries"
        ).fetchone()
        last = conn.execute("SELECT latency_ms FROM queries ORDER BY id DESC LIMIT 1").fetchone()

    queries = int(agg["n"])
    avg_ms = float(agg["avg_ms"])
    assistant_minutes = max(min_assistant_minutes, avg_ms / 60000.0) if queries else min_assistant_minutes
    saved_per_query = max(0.0, manual_minutes - assistant_minutes)
    policy_saved = max(0.0, manual_minutes_per_policy - assistant_minutes_per_policy) * documents
    query_saved = queries * saved_per_query
    return {
        "documents": int(documents),
        "chunks": int(chunks),
        "queries": queries,
        "avg_latency_ms": round(avg_ms, 1),
        "max_latency_ms": round(float(agg["max_ms"]), 1),
        "last_latency_ms": round(float(last["latency_ms"]), 1) if last else None,
        "time_saved_minutes": round(policy_saved + query_saved, 1),
        "breakdown": {
            "from_policy_cards": round(policy_saved, 1),
            "from_questions": round(query_saved, 1),
        },
        "assumptions": {
            "estimate": True,
            "manual_minutes_per_query": manual_minutes,
            "assistant_minutes_per_query": round(assistant_minutes, 2),
            "manual_minutes_per_policy": manual_minutes_per_policy,
            "assistant_minutes_per_policy": assistant_minutes_per_policy,
        },
    }
