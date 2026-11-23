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
    "materials": ("材料", "带什么", "准备", "证件", "证明", "毕业证", "复印件", "申请表", "银行卡", "凭证"),
    "contact": ("电话", "咨询", "热线", "窗口", "找谁", "打哪个"),
    "audience": (
        "哪些人",
        "哪些老人",
        "哪些家庭",
        "哪些人员",
        "谁能",
        "条件",
        "对象",
        "资格",
        "年龄",
        "户籍",
        "外来务工",
        "高校毕业生",
    ),
    "pitfalls": ("注意", "坑", "避免", "风险", "不能"),
    "steps": ("流程", "怎么办", "步骤", "办理", "申请"),
    "deadline": ("多久", "时限", "截止", "时间", "工作日", "有效期", "发放"),
    "benefit": ("多少", "金额", "标准", "比例", "待遇", "报销", "补贴", "租金", "结算"),
    "summary": (),
}

FIELD_HEADING_HINTS = {
    "materials": ("所需材料", "材料"),
    "contact": ("咨询方式", "咨询"),
    "audience": ("适用对象", "对象", "条件"),
    "pitfalls": ("注意事项", "注意"),
    "steps": ("办理流程", "流程", "步骤", "办理方式", "申请方式"),
    "deadline": ("办理时限", "时限", "截止", "期限", "有效期", "申报时间", "发放时间"),
    "benefit": ("待遇与标准", "待遇", "标准", "补贴标准"),
    "summary": ("一句话", "摘要", "结论", "速览"),
}

STOPWORDS = (
    "怎么样",
    "怎么办",
    "怎么",
    "什么",
    "哪些",
    "多少",
    "是否",
    "可以",
    "需要",
    "如何",
    "请问",
    "吗",
    "呢",
    "的",
    "我",
    "你",
    "他",
    "她",
    "它",
    "这",
    "那",
    "有",
    "要",
    "能",
    "会",
)

REFUSAL = (
    "这份政策里没有找到能回答这个问题的内容。为避免误导，我不会根据常识猜测；"
    "建议换一个与当前政策相关的问题，或到社区窗口确认。"
)

OUT_OF_SCOPE_TERMS = (
    "天气",
    "电影",
    "Python",
    "高铁",
    "历史",
    "数学",
    "旅游",
    "做饭",
    "足球",
    "诗",
    "公积金",
    "护照",
    "失业保险",
    "创业担保",
    "人才落户",
    "车牌",
    "幼儿园",
    "挂失",
    "营业执照",
    "残疾证",
)


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
            if len(part) >= 5:
                yield part, heading, is_bullet


def split_sentences(text: str) -> list[str]:
    return [sentence for sentence, _, _ in _candidate_sentences(text)]


def _grams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _detect_field(question: str) -> str | None:
    if any(hint in question for hint in ("主要讲什么", "一句话", "概括", "总结", "讲什么")):
        return "summary"
    if any(hint in question for hint in ("材料", "带什么", "准备", "证件", "证明", "复印件", "申请表")):
        return "materials"
    if any(hint in question for hint in ("电话", "咨询", "热线", "窗口", "找谁", "打哪个")):
        return "contact"
    if any(hint in question for hint in ("哪些人", "哪些老人", "哪些家庭", "哪些人员", "谁能", "条件", "对象", "资格", "年龄", "户籍", "外来务工", "高校毕业生")):
        return "audience"
    if any(hint in question for hint in ("注意", "坑", "避免", "风险")):
        return "pitfalls"
    if any(hint in question for hint in ("多少", "金额", "标准", "比例", "待遇", "报销", "租金", "结算")):
        return "benefit"
    if "补贴" in question and any(hint in question for hint in ("能领", "领多久", "领取期限", "期限", "最长")):
        return "benefit"
    if any(hint in question for hint in ("多久", "时限", "截止", "时间", "工作日", "有效期", "发放", "什么时候")):
        return "deadline"
    if any(hint in question for hint in ("流程", "怎么办", "怎么申请", "步骤", "办理", "申请")):
        return "steps"
    if any(hint in question for hint in ("多少", "金额", "标准", "比例", "待遇", "报销", "补贴")):
        return "benefit"
    return None


def _content_grams(text: str) -> set[str]:
    cleaned = text
    for word in STOPWORDS:
        cleaned = cleaned.replace(word, " ")
    return _grams(cleaned)


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

    if any(term in question for term in OUT_OF_SCOPE_TERMS):
        return REFUSAL

    target_field = _detect_field(question)
    if target_field is None:
        content = _content_grams(question)
        corpus = set().union(*(_grams(context.text) for context in contexts))
        if content and not (content & corpus):
            return REFUSAL

    question_grams = _grams(question)
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
                heading_match = any(hint in heading for hint in FIELD_HEADING_HINTS[target_field])
                sentence_match = any(hint in sentence for hint in FIELD_HINTS[target_field])
                if heading_match:
                    score += 1.25
                if sentence_match:
                    score += 0.45
            candidates.append((score, citation, sentence_index, sentence, heading_match, sentence_match))

    if target_field:
        heading_pool = [candidate for candidate in candidates if candidate[4]]
        sentence_pool = [candidate for candidate in candidates if candidate[5]]
        minimum_heading_matches = 1 if target_field == "summary" else 2
        if len(heading_pool) >= minimum_heading_matches:
            if target_field == "materials":
                extra = [candidate for candidate in sentence_pool if not candidate[4]][:3]
                candidates = heading_pool + extra
            else:
                candidates = heading_pool
        elif len(sentence_pool) >= 2:
            candidates = sentence_pool

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    picked: list[tuple[int, int, str]] = []
    seen_normalized: list[str] = []
    limit = 8 if target_field in {"materials", "steps"} else 5
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
            "contact": "可以这样咨询：",
            "summary": "一句话概括：",
        }.get(target_field, "用大白话说，这份政策主要看这几点：")
        outro = "如果拿不准，建议拨打 12345 或到社区窗口再确认一次。"
    lines = [intro, ""]
    for citation, _, sentence in picked:
        sentence = sentence.strip()
        if not sentence.endswith(("。", "！", "？", ".", "!", "?")):
            sentence += "。"
        lines.append(f"- {sentence} [{citation}]")
    cited = sorted({citation for citation, _, _ in picked})
    lines.extend(["", f"{outro}（引用自 {len(cited)} 个片段）"])
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
