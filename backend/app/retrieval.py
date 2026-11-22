from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: int
    doc_id: str
    doc_title: str
    ord: int
    text: str


@dataclass(frozen=True)
class Retrieved:
    chunk_id: int
    doc_id: str
    doc_title: str
    ord: int
    text: str
    score: float

    def to_source(self, index: int) -> dict:
        return {
            "index": index,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.doc_title,
            "chunk_index": self.ord,
            "score": round(self.score, 4),
            "snippet": self.text[:260],
        }


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class _Index:
    def __init__(self, rows: list[ChunkRow]) -> None:
        self.rows = rows
        self.vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 3),
            min_df=1,
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform([_clean(row.text) for row in rows])

    def search(self, query: str, k: int) -> list[Retrieved]:
        cleaned = _clean(query)
        if not cleaned or not self.rows:
            return []
        try:
            query_vector = self.vectorizer.transform([cleaned])
        except ValueError:
            return []
        scores = cosine_similarity(query_vector, self.matrix)[0]
        order = scores.argsort()[::-1][: max(1, k)]
        results: list[Retrieved] = []
        for idx in order:
            score = float(scores[int(idx)])
            if score <= 1e-6:
                continue
            row = self.rows[int(idx)]
            results.append(
                Retrieved(
                    chunk_id=row.chunk_id,
                    doc_id=row.doc_id,
                    doc_title=row.doc_title,
                    ord=row.ord,
                    text=row.text,
                    score=score,
                )
            )
        return results


class IndexCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signature = ""
        self._index: _Index | None = None

    @staticmethod
    def _signature_for(rows: list[ChunkRow]) -> str:
        digest = hashlib.sha1()
        for row in rows:
            digest.update(f"{row.chunk_id}|{row.doc_title}|{row.text}".encode("utf-8", "ignore"))
        return digest.hexdigest()

    def search(self, rows: list[ChunkRow], query: str, k: int) -> list[Retrieved]:
        signature = self._signature_for(rows)
        with self._lock:
            if signature != self._signature:
                self._signature = signature
                try:
                    self._index = _Index(rows) if rows else None
                except ValueError:
                    self._index = None
            index = self._index
        return index.search(query, k) if index else []


cache = IndexCache()


def rows_from_db(items: list[dict]) -> list[ChunkRow]:
    return [
        ChunkRow(
            chunk_id=int(item["chunk_id"]),
            doc_id=str(item["doc_id"]),
            doc_title=str(item["doc_title"]),
            ord=int(item["ord"]),
            text=str(item["text"]),
        )
        for item in items
    ]
