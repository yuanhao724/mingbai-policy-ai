from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import db
from ..chunking import chunk_text
from ..config import settings
from ..schemas import DocumentOut


router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".csv"}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _unique_title(existing: list[dict], base: str) -> str:
    titles = {item["title"] for item in existing}
    if base not in titles:
        return base
    index = 2
    while f"{base} ({index})" in titles:
        index += 1
    return f"{base} ({index})"


@router.get("", response_model=list[DocumentOut])
def list_documents() -> list[dict]:
    return db.list_documents(settings.db_path)


@router.post("", response_model=list[DocumentOut])
async def upload_documents(files: list[UploadFile] = File(...)) -> list[dict]:
    if not files:
        raise HTTPException(status_code=400, detail="请至少选择一个文件")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="一次最多上传 10 个文件")

    limit = settings.max_upload_mb * 1024 * 1024
    created: list[dict] = []
    for upload in files:
        filename = upload.filename or "未命名文档.txt"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"暂不支持 {suffix or '未知'} 格式，请上传 txt / md / csv 文件",
            )
        raw = await upload.read()
        if len(raw) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"{filename} 超过 {settings.max_upload_mb}MB 限制",
            )
        text = _decode(raw).strip()
        if not text:
            raise HTTPException(status_code=400, detail=f"{filename} 内容为空")
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise HTTPException(status_code=400, detail=f"{filename} 无法切分")

        existing = db.list_documents(settings.db_path)
        title = _unique_title(existing, Path(filename).stem or "未命名文档")
        created.append(
            db.add_document(
                settings.db_path,
                title=title,
                filename=filename,
                content=text,
                size_bytes=len(raw),
                chunks=chunks,
            )
        )
    return created


@router.get("/{doc_id}")
def get_document(doc_id: str) -> dict:
    document = db.get_document(settings.db_path, doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    document["chunks"] = db.chunks_for_document(settings.db_path, doc_id)
    return document


@router.delete("/{doc_id}")
def delete_document(doc_id: str) -> dict:
    if not db.delete_document(settings.db_path, doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"ok": True, "id": doc_id}
