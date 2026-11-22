from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .. import db
from ..config import settings
from ..schemas import DocumentOut, ReviewRequest


router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("")
def list_reviews() -> dict:
    return {
        "documents": db.list_documents(settings.db_path),
        "audit": db.recent_audit(settings.db_path),
    }


@router.post("/{doc_id}", response_model=DocumentOut)
def review_document(
    doc_id: str,
    payload: ReviewRequest,
    x_mori_role: str | None = Header(default=None, alias="X-Mori-Role"),
) -> dict:
    if x_mori_role not in {"reviewer", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="需要审核员角色。演示环境请带 X-Mori-Role: reviewer",
        )
    updated = db.review_document(
        settings.db_path,
        doc_id,
        status=payload.status,
        reviewer=payload.reviewer,
        note=payload.note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="政策不存在")
    return updated
