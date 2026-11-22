from __future__ import annotations

import re
from typing import Iterable, Sequence

from .retrieval import Retrieved


SYSTEM_PROMPT = """你是「明白办事」的政策助手。你的任务是把政策原文翻译成老百姓能听懂、能照着办的话。
你会收到若干带编号的政策片段，请遵守以下规则：
1. 只依据给出的片段回答，不要编造资格、金额、材料或时限。
2. 每个关键结论后面用 [1] [2] 这样的编号标注来源，编号必须对应片段。
3. 涉及年龄、户籍、金额、期限等硬条件时，提醒用户以当地官方最新发布为准。
4. 不提供法律、医疗、投资承诺；资料不足时直接说明不确定，并告诉用户可以问谁。
5. 居民版：用短句和大白话，先给结论，再给步骤，少用术语。
6. 工作者版：在准确的前提下，给出可以直接转述给居民的回复。
7. 不要输出与问题无关的寒暄。"""


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")
_BULLET_PREFIX = re.compile(r"^\s*(?:(?:[-*•]|\d+[.、)]|[（(]\d+[）)]|[①-⑳])\s*)+")
_HEADING_PREFIX = re.compile(r"^#{1,6}\s*")

FIELD_HINTS = {
    "materials": ("材料", "带什么", "准备", "证件", "证明", "毕业证", "复印件", "申请表"),
    "steps": ("流程", "怎么办", "步骤", "办理", "申请"),
    "deadline": ("多久", "时限", "截止", "时间", "工作日", "有效期"),
    "benefit": ("多少", "钱", "标准", "补贴", "报销", "金额", "待遇"),
    "audience": ("谁能办", "条件", "对象", "资格", "外地", "年龄", "户籍"),
    "pitfalls": ("注意", "坑", "避免", "风险", "不能"),
}


def _candidate_sentences(text: str):
    heading = ""
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = _HEADING_PREFIX.sub("", line).strip()
            parts = re.split(r"\s+(?=(?:[-*•]|\d+[.、)]|[（(]\d+[）)]))", body, maxsplit=1)
            if len(parts) < 2:
                heading = body
                continue
            heading = parts[0].strip()
            line = parts[1].strip()
        if line.startswith(">"):
            continue
        is_bullet = bool(_BULLET_PREFIX.match(line))
        line = _BULLET_PREFIX.sub("", line).strip()
        if not line:
            continue
        for part in _SENTENCE_SPLIT.split(line):
            part = part.strip()
            if len(part) >= 8:
                yield part, heading, is_bullet


def split_sentences(text: str) -> list[str]:
    return [sentence for sentence, _, _ in _candidate_sentences(text)]


def _grams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _detect_field(question: str) -> str | None:
    if any(hint in question for hint in ("材料", "带什么", "准备", "证件", "复印件", "申请表")):
        return "materials"
    if any(hint in question for hint in ("补贴", "报销", "多少", "金额", "标准", "比例", "待遇", "能领")):
        return "benefit"
    if any(hint in question for hint in ("流程", "怎么办", "步骤", "办理", "申请")):
        return "steps"
    if any(hint in question for hint in ("多久", "时限", "截止", "时间", "工作日", "有效期")):
        return "deadline"
    if any(hint in question for hint in ("条件", "对象", "资格", "外地", "年龄", "户籍", "谁能办")):
        return "audience"
    if any(hint in question for hint in ("注意", "坑", "避免", "风险")):
        return "pitfalls"
    return None


def local_extractive_answer(
    question: str,
    contexts: Sequence[Retrieved],
    persona: str = "resident",
) -> str:
    if not contexts:
        return (
            "知识库里暂时没有能支撑这个问题的内容。\n\n"
            "你可以换一种问法，或先在左侧上传相关文档后再试。"
        )

    question_grams = _grams(question)
    target_field = _detect_field(question)
    candidates: list[tuple[float, int, int, str, bool, bool]] = []
    for citation, context in enumerate(contexts, start=1):
        for sentence_index, (sentence, heading, is_bullet) in enumerate(_candidate_sentences(context.text)):
            overlap = len(question_grams & _grams(sentence))
            score = overlap / (len(question_grams) + 1e-6) + context.score * 0.35
            if is_bullet:
                score += 0.25
            heading_match = False
            sentence_match = False
            if target_field:
                hints = FIELD_HINTS[target_field]
                heading_match = any(hint in heading for hint in hints)
                sentence_match = any(hint in sentence for hint in hints)
                if heading_match:
                    score += 1.25
                if sentence_match:
                    score += 0.45
            candidates.append((score, citation, sentence_index, sentence, heading_match, sentence_match))

    if target_field:
        heading_pool = [candidate for candidate in candidates if candidate[4]]
        sentence_pool = [candidate for candidate in candidates if candidate[5]]
        if len(heading_pool) >= 2:
            extra = [candidate for candidate in sentence_pool if not candidate[4]][:3]
            candidates = heading_pool + extra
        elif len(sentence_pool) >= 2:
            candidates = sentence_pool

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    picked: list[tuple[int, int, str]] = []
    seen_normalized: list[str] = []
    limit = 8 if target_field == "materials" else 5
    for _, citation, sentence_index, sentence, _, _ in candidates:
        normalized = re.sub(r"[\s，。；;、]", "", sentence)
        if any(normalized in existing or existing in normalized for existing in seen_normalized):
            continue
        seen_normalized.append(normalized)
        picked.append((citation, sentence_index, sentence))
        if len(picked) >= limit:
            break

    picked.sort(key=lambda item: (item[0], item[1]))
    if persona == "worker":
        intro = "可以直接这样回复居民："
        outro = "以上内容来自当前政策原文。转述时请保留年龄、户籍、金额和时限等关键条件。"
    else:
        intro = {
            "materials": "这份政策需要带的材料有：",
            "steps": "办理流程可以分成这几步：",
            "deadline": "时间安排如下：",
            "benefit": "待遇标准如下：",
            "audience": "先看自己是否符合这些条件：",
            "pitfalls": "这几个地方容易踩坑：",
        }.get(target_field, "用大白话说，这份政策主要看这几点：")
        outro = "如果拿不准，建议拨打 12345 或到社区窗口再确认一次。"
    lines = [intro, ""]
    for citation, _, sentence in picked:
        sentence = sentence.strip()
        if not sentence.endswith(("。", "！", "？", ".", "!", "?")):
            sentence += "。"
        lines.append(f"- {sentence} [{citation}]")
    lines.extend(["", f"{outro}（引用自 {len(contexts)} 个片段）"])
    return "\n".join(lines)


def build_context_block(contexts: Sequence[Retrieved]) -> str:
    blocks = []
    for citation, context in enumerate(contexts, start=1):
        blocks.append(
            f"[{citation}] 《{context.doc_title}》 第 {context.ord + 1} 段\n{context.text.strip()}"
        )
    return "\n\n".join(blocks)


def build_messages(
    question: str,
    contexts: Sequence[Retrieved],
    history: Iterable[dict],
    persona: str = "resident",
    max_history_turns: int = 8,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    turns = [turn for turn in history if turn.get("role") in {"user", "assistant"} and turn.get("content")]
    for turn in turns[-max_history_turns:]:
        messages.append(
            {
                "role": str(turn["role"]),
                "content": str(turn["content"]).strip()[:2000],
            }
        )
    user_content = (
        f"资料片段：\n{build_context_block(contexts)}\n\n"
        f"问题：{question}\n\n"
        f"回答视角：{'社区工作者版，给出可直接转述的回复' if persona == 'worker' else '居民版，用大白话解释'}。\n"
        "请基于以上资料作答，并在关键结论后标注引用编号。"
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def stream_pieces(text: str, size: int = 6) -> list[str]:
    if size <= 0:
        return [text]
    return [text[i : i + size] for i in range(0, len(text), size)]
