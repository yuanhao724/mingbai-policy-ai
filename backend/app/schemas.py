from __future__ import annotations

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    doc_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list)
    top_k: int | None = Field(default=None, ge=1, le=8)
    persona: str = Field(default="resident", pattern="^(resident|worker)$")


class ExtractRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=6, ge=1, le=10)


class DocumentOut(BaseModel):
    id: str
    title: str
    filename: str
    size_bytes: int
    chunk_count: int
    created_at: str
