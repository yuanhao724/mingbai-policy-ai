from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..config import settings
from ..policy import build_policy_card


router = APIRouter(prefix="/api/policy", tags=["policy"])


@router.get("/{doc_id}/card")
def get_policy_card(doc_id: str) -> dict:
    document = db.get_document(settings.db_path, doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="政策文件不存在")
    chunks = db.chunks_for_document(settings.db_path, doc_id)
    if not chunks:
        raise HTTPException(status_code=422, detail="该文件还没有可用的文本片段")
    return build_policy_card(document, chunks)
