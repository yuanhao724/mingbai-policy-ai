from __future__ import annotations

import re


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    pieces: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for part in _SENTENCE_SPLIT.split(line):
            part = part.strip()
            if part:
                pieces.append(part)
    return pieces


def _hard_slice(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    step = max(1, max_chars - overlap)
    return [text[i : i + max_chars] for i in range(0, len(text), step) if text[i : i + max_chars].strip()]


def chunk_text(text: str, max_chars: int = 520, overlap: int = 90) -> list[str]:
    """Split mixed Chinese/English text into overlapping, paragraph-aware chunks."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap, max_chars // 2))
    text = normalize_text(text)
    if not text:
        return []

    chunks: list[str] = []
    carry = ""
    for paragraph in _PARAGRAPH_SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{carry}\n{paragraph}".strip() if carry else paragraph
        if len(candidate) <= max_chars:
            carry = candidate
            continue

        sentences = split_sentences(paragraph)
        buffer = carry
        for sentence in sentences:
            if len(sentence) > max_chars:
                if buffer.strip():
                    chunks.append(buffer.strip())
                chunks.extend(_hard_slice(sentence, max_chars, overlap))
                buffer = ""
                continue
            joined = f"{buffer}\n{sentence}".strip() if buffer else sentence
            if len(joined) <= max_chars:
                buffer = joined
            else:
                if buffer.strip():
                    chunks.append(buffer.strip())
                tail = buffer[-overlap:] if overlap and buffer else ""
                buffer = f"{tail}\n{sentence}".strip()
                if len(buffer) > max_chars:
                    chunks.extend(_hard_slice(buffer, max_chars, overlap))
                    buffer = ""
        carry = buffer

    if carry.strip():
        chunks.append(carry.strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        chunk = chunk.strip()
        if chunk and chunk not in seen:
            seen.add(chunk)
            cleaned.append(chunk)
    return cleaned
