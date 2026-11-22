from __future__ import annotations

import re

from fastapi import APIRouter

from .. import db
from ..answer import split_sentences
from ..config import settings
from ..retrieval import cache, rows_from_db
from ..schemas import ExtractRequest


router = APIRouter(prefix="/api", tags=["insights"])


def _grams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _best_snippet(query: str, text: str) -> str:
    query_grams = _grams(query)
    sentences = split_sentences(text) or [text]
    scored = sorted(
        sentences,
        key=lambda sentence: len(query_grams & _grams(sentence)),
        reverse=True,
    )
    snippet = scored[0].strip()
    return snippet[:180] + ("..." if len(snippet) > 180 else "")


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": settings.mode,
        "model": settings.openai_model if settings.openai_api_key else "local-tfidf",
        "version": settings.version,
    }


@router.get("/stats")
def stats() -> dict:
    return db.compute_stats(
        settings.db_path,
        settings.manual_minutes_per_query,
        settings.min_assistant_minutes,
        settings.manual_minutes_per_policy,
        settings.assistant_minutes_per_policy,
    )


@router.post("/extract")
def extract(payload: ExtractRequest) -> dict:
    rows = rows_from_db(db.all_chunks(settings.db_path))
    retrieved = cache.search(rows, payload.query, payload.top_k)
    table = []
    for index, item in enumerate(retrieved, start=1):
        table.append(
            {
                "index": index,
                "source": f"《{item.doc_title}》第 {item.ord + 1} 段",
                "snippet": _best_snippet(payload.query, item.text),
                "score": round(item.score, 4),
            }
        )
    return {
        "query": payload.query,
        "mode": settings.mode,
        "columns": ["序号", "来源", "相关片段", "匹配度"],
        "rows": table,
        "notice": (
            "本地模式：按问题相关度抽取原文片段，适合快速整理信息。"
            if not settings.openai_api_key
            else "在线模式：检索命中片段已按相关度排序。"
        ),
    }
