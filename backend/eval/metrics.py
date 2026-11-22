from __future__ import annotations

import math
import re
from statistics import mean
from typing import Sequence

from app.retrieval import Retrieved


CITATION_RE = re.compile(r"\[(\d+)\]")
SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])|\n+")

GENERIC_PREFIXES = (
    "这份政策需要带的材料有",
    "办理流程可以分成",
    "时间安排如下",
    "待遇标准如下",
    "先看自己是否符合",
    "这几个地方容易踩坑",
    "可以这样咨询",
    "用大白话说",
    "可以直接这样回复",
    "如果拿不准",
    "（引用自",
    "以上内容",
    "可在来源面板",
)


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def citation_numbers(answer: str) -> list[int]:
    return [int(number) for number in CITATION_RE.findall(answer)]


def keyword_recall(answer: str, keywords: Sequence[str]) -> float | None:
    if not keywords:
        return None
    hits = sum(1 for keyword in keywords if _contains(answer, keyword))
    return hits / len(keywords)


def citation_validity(answer: str, source_count: int) -> float | None:
    numbers = citation_numbers(answer)
    if not numbers:
        return 0.0
    valid = sum(1 for number in numbers if 1 <= number <= source_count)
    return valid / len(numbers)


def citation_coverage(answer: str) -> float:
    return 1.0 if citation_numbers(answer) else 0.0


def citation_support(
    answer: str,
    contexts: Sequence[Retrieved],
    keywords: Sequence[str],
) -> float | None:
    numbers = citation_numbers(answer)
    if not numbers:
        return 0.0
    supported = 0
    for number in numbers:
        if not 1 <= number <= len(contexts):
            continue
        text = contexts[number - 1].text
        if not keywords or any(_contains(text, keyword) for keyword in keywords):
            supported += 1
    return supported / len(numbers)


def groundedness(answer: str, contexts: Sequence[Retrieved]) -> float:
    corpus = _bigrams(" ".join(context.text for context in contexts))
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT.split(answer)
        if len(sentence.strip()) >= 8 and not sentence.strip().startswith(GENERIC_PREFIXES)
    ]
    if not sentences:
        return 0.0
    grounded = 0
    for sentence in sentences:
        cleaned = CITATION_RE.sub("", sentence)
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned)
        grams = _bigrams(cleaned)
        overlap = len(grams & corpus) / max(1, len(grams))
        if overlap >= 0.25:
            grounded += 1
    return grounded / len(sentences)


def retrieval_metrics(ranked_hits: Sequence[Retrieved], keywords: Sequence[str]) -> dict:
    if not keywords:
        return {"hit_at_1": None, "hit_at_3": None, "mrr": None, "relevant": []}
    relevant = [
        any(_contains(hit.text, keyword) for keyword in keywords)
        for hit in ranked_hits
    ]
    hit_at_1 = 1.0 if relevant and relevant[0] else 0.0
    hit_at_3 = 1.0 if any(relevant[:3]) else 0.0
    mrr = 0.0
    for rank, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            mrr = 1.0 / rank
            break
    return {"hit_at_1": hit_at_1, "hit_at_3": hit_at_3, "mrr": mrr, "relevant": relevant}


def refusal_ok(answer: str, answerable: bool) -> float | None:
    if answerable:
        return None
    markers = ("没有找到", "不能回答", "不会根据常识", "缺少", "不确定")
    return 1.0 if any(marker in answer for marker in markers) else 0.0


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (p / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def evaluate_result(
    *,
    question: str,
    answer: str,
    contexts: Sequence[Retrieved],
    ranked_hits: Sequence[Retrieved],
    keywords: Sequence[str],
    answerable: bool,
    latency_ms: float,
) -> dict:
    retrieval = retrieval_metrics(ranked_hits, keywords) if answerable else None
    metrics = {
        "retrieval": retrieval,
        "keyword_recall": keyword_recall(answer, keywords) if answerable else None,
        "citation_validity": citation_validity(answer, len(contexts)) if answerable else None,
        "citation_coverage": citation_coverage(answer) if answerable else None,
        "citation_support": citation_support(answer, contexts, keywords) if answerable else None,
        "groundedness": groundedness(answer, contexts) if answerable else None,
        "refusal_ok": refusal_ok(answer, answerable),
    }
    return {
        "question": question,
        "answer": answer,
        "answerable": answerable,
        "citation_count": len(citation_numbers(answer)),
        "latency_ms": round(latency_ms, 2),
        "metrics": metrics,
    }


def _average(values: Sequence[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return round(mean(filtered), 4) if filtered else None


def summarize(results: Sequence[dict]) -> dict:
    answerable = [result for result in results if result["answerable"]]
    unanswerable = [result for result in results if not result["answerable"]]
    retrievals = [
        result["metrics"]["retrieval"]
        for result in answerable
        if result["metrics"]["retrieval"]
    ]
    latencies = [result["latency_ms"] for result in results]
    return {
        "total": len(results),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "hit_at_1": _average([item["hit_at_1"] for item in retrievals]),
        "hit_at_3": _average([item["hit_at_3"] for item in retrievals]),
        "mrr": _average([item["mrr"] for item in retrievals]),
        "keyword_recall": _average(
            [result["metrics"]["keyword_recall"] for result in answerable]
        ),
        "citation_validity": _average(
            [result["metrics"]["citation_validity"] for result in answerable]
        ),
        "citation_coverage": _average(
            [result["metrics"]["citation_coverage"] for result in answerable]
        ),
        "citation_support": _average(
            [result["metrics"]["citation_support"] for result in answerable]
        ),
        "groundedness": _average(
            [result["metrics"]["groundedness"] for result in answerable]
        ),
        "refusal_accuracy": _average(
            [result["metrics"]["refusal_ok"] for result in unanswerable]
        ),
        "latency_p50_ms": round(percentile(latencies, 50), 2),
        "latency_p95_ms": round(percentile(latencies, 95), 2),
    }
