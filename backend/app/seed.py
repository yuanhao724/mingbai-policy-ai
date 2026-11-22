from __future__ import annotations

import re
from pathlib import Path

from . import db
from .chunking import chunk_text
from .config import settings


def seed_if_empty() -> int:
    if db.list_documents(settings.db_path):
        return 0
    if not settings.sample_dir.exists():
        return 0

    files = sorted(
        [path for path in settings.sample_dir.iterdir() if path.suffix.lower() in {".md", ".txt"}]
    )
    created = 0
    for file_path in files[:8]:
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            continue
        db.add_document(
            settings.db_path,
            title=re.sub(r"^\d+[_\-\s]*", "", file_path.stem).replace("_", " "),
            filename=file_path.name,
            content=text,
            size_bytes=len(text.encode("utf-8")),
            chunks=chunks,
        )
        created += 1
    return created
