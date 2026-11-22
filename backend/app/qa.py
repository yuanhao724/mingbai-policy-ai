from __future__ import annotations

from pathlib import Path

from . import db
from .retrieval import Retrieved, cache, rows_from_db


def scoped_contexts(
    db_path: Path,
    doc_id: str,
    question: str,
    top_k: int = 4,
    max_chunks: int = 12,
) -> list[Retrieved]:
    """Build the single-policy context used by both chat and evaluation.

    Retrieval scores decide which chunks are relevant, while the context is
    returned in original document order so citation numbers stay stable.
    """
    doc_rows = [
        row
        for row in rows_from_db(db.all_chunks(db_path))
        if row.doc_id == doc_id
    ]
    if not doc_rows:
        return []

    hits = cache.search(doc_rows, question, top_k)
    score_by_chunk = {hit.chunk_id: hit.score for hit in hits}
    ordered = sorted(doc_rows, key=lambda row: row.ord)[:max_chunks]
    return [
        Retrieved(
            chunk_id=row.chunk_id,
            doc_id=row.doc_id,
            doc_title=row.doc_title,
            ord=row.ord,
            text=row.text,
            score=score_by_chunk.get(row.chunk_id, 0.0),
        )
        for row in ordered
    ]
