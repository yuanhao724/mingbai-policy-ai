from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..answer import build_messages, local_extractive_answer, stream_pieces
from ..config import settings
from ..llm import stream_chat
from ..retrieval import Retrieved, cache, rows_from_db
from ..schemas import ChatRequest


router = APIRouter(prefix="/api/chat", tags=["chat"])


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    started = time.perf_counter()
    document = db.get_document(settings.db_path, payload.doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="当前政策不存在")
    chunk_rows = rows_from_db(
        [row for row in db.all_chunks(settings.db_path) if row["doc_id"] == payload.doc_id]
    )
    if not chunk_rows:
        raise HTTPException(status_code=422, detail="当前政策还没有可检索的文本片段")
    top_k = payload.top_k or settings.top_k
    hits = cache.search(chunk_rows, question, top_k)
    score_by_chunk = {hit.chunk_id: hit.score for hit in hits}
    ordered_rows = sorted(chunk_rows, key=lambda row: row.ord)[:12]
    retrieved = [
        Retrieved(
            chunk_id=row.chunk_id,
            doc_id=row.doc_id,
            doc_title=row.doc_title,
            ord=row.ord,
            text=row.text,
            score=score_by_chunk.get(row.chunk_id, 0.0),
        )
        for row in ordered_rows
    ]
    sources = [item.to_source(index) for index, item in enumerate(retrieved, start=1)]
    history = [turn.model_dump() for turn in payload.history]

    async def generate():
        mode = "openai" if settings.openai_api_key else "local"
        yield sse(
            "meta",
            {
                "sources": sources,
                "mode": mode,
                "documents": 1,
                "chunks": len(chunk_rows),
            },
        )
        pieces: list[str] = []
        emitted = False

        if mode == "openai":
            try:
                messages = build_messages(
                    question,
                    retrieved,
                    history,
                    persona=payload.persona,
                    max_history_turns=settings.max_history_turns,
                )
                async for delta in stream_chat(
                    messages,
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    model=settings.openai_model,
                ):
                    emitted = True
                    pieces.append(delta)
                    yield sse("token", {"text": delta})
            except Exception as exc:  # noqa: BLE001 - degrade gracefully
                if not emitted:
                    mode = "local"
                    yield sse(
                        "notice",
                        {
                            "message": "在线模型不可用，已自动切换到本地检索模式。",
                            "detail": str(exc)[:180],
                        },
                    )
                    fallback = local_extractive_answer(question, retrieved, payload.persona)
                    for piece in stream_pieces(fallback, 5):
                        pieces.append(piece)
                        yield sse("token", {"text": piece})
                        if settings.stream_delay > 0:
                            await asyncio.sleep(settings.stream_delay)
                else:
                    yield sse("notice", {"message": "在线模型连接中断，回答可能不完整。"})
        else:
            local_answer = local_extractive_answer(question, retrieved, payload.persona)
            for piece in stream_pieces(local_answer, 5):
                pieces.append(piece)
                yield sse("token", {"text": piece})
                if settings.stream_delay > 0:
                    await asyncio.sleep(settings.stream_delay)

        answer = "".join(pieces).strip()
        latency_ms = (time.perf_counter() - started) * 1000
        query_id = db.record_query(
            settings.db_path,
            question=question,
            answer=answer,
            mode=mode,
            sources=sources,
            latency_ms=latency_ms,
        )
        yield sse(
            "done",
            {
                "latency_ms": round(latency_ms, 1),
                "mode": mode,
                "query_id": query_id,
                "sources": sources,
            },
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
