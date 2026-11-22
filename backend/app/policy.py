from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Sequence


FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "audience": ("适用对象", "申请条件", "谁能办", "对象", "条件", "范围", "人员"),
    "benefit": ("待遇与标准", "补贴标准", "待遇", "标准", "金额", "能领", "报销", "发放", "租金"),
    "materials": ("所需材料", "材料", "证件", "证明", "申请表", "复印件"),
    "steps": ("办理流程", "流程", "步骤", "怎么办理", "申请方式", "办理方式"),
    "deadline": ("办理时限", "时限", "截止", "期限", "有效期", "申报时间", "发放时间"),
    "pitfalls": ("注意事项", "注意", "提醒", "常见问题", "不予", "风险"),
    "contact": ("咨询方式", "咨询", "电话", "窗口", "地址", "热线"),
}

FIELD_LABELS = {
    "audience": "谁能办",
    "benefit": "能领什么",
    "materials": "要带什么",
    "steps": "怎么办",
    "deadline": "什么时候截止",
    "pitfalls": "常见坑",
    "contact": "找谁问",
}

BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.、)]|[（(]\d+[）)]|[①-⑳])\s*")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])")
DATE_RE = re.compile(
    r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?"
    r"|\d{1,2}\s*月\s*\d{1,2}\s*日"
    r"|\d+\s*个工作日"
    r"|\d+\s*个?月"
    r"|长期有效|每年|按月|按季度|次月"
)
MATERIAL_HINTS = (
    "身份证",
    "户口簿",
    "社保卡",
    "银行卡",
    "证明",
    "申请表",
    "复印件",
    "合同",
    "凭证",
    "居住证",
    "委托书",
    "毕业证",
    "记录",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_sections(content: str) -> list[dict]:
    sections: list[dict] = []
    current = {"heading": "", "lines": []}
    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = HEADING_RE.match(raw_line.strip())
        if match:
            if current["lines"] or current["heading"]:
                sections.append(current)
            current = {"heading": _clean_markdown(match.group(2)), "lines": []}
        else:
            current["lines"].append(raw_line)
    if current["lines"] or current["heading"]:
        sections.append(current)
    return [section for section in sections if section["heading"] or any(line.strip() for line in section["lines"])]


def _section_body(section: dict) -> str:
    return "\n".join(section["lines"]).strip()


def _split_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        is_bullet = bool(BULLET_RE.match(line))
        line = BULLET_RE.sub("", line).strip()
        line = _clean_markdown(line)
        if not line:
            continue
        if is_bullet:
            items.append(line)
            continue
        for sentence in SENTENCE_RE.split(line):
            sentence = sentence.strip()
            if sentence:
                items.append(sentence)
    return items


def _section_score(section: dict, keywords: Sequence[str]) -> int:
    heading = section["heading"]
    body = _section_body(section)
    score = 0
    for keyword in keywords:
        if keyword in heading:
            score += 6
        score += min(body.count(keyword), 3)
    return score


def _unique(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = item.strip("，,；; ")
        if len(item) < 4 or len(item) > 220:
            continue
        key = re.sub(r"\s+", "", item)[:60]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _collect_field(field: str, sections: list[dict], full_text: str) -> list[str]:
    keywords = FIELD_KEYWORDS[field]
    ranked = sorted(
        ((_section_score(section, keywords), index, section) for index, section in enumerate(sections)),
        key=lambda item: (-item[0], item[1]),
    )
    heading_hits = [item for item in ranked if item[0] >= 6]
    chosen = heading_hits[:2]
    if not chosen:
        chosen = [item for item in ranked if item[0] > 0][:2]

    items: list[str] = []
    for _, _, section in chosen:
        items.extend(_split_items(_section_body(section)))

    if not items:
        fallback = [sentence for sentence in _split_items(full_text) if any(key in sentence for key in keywords)]
        items.extend(fallback)

    if field == "materials":
        hinted = [item for item in items if any(hint in item for hint in MATERIAL_HINTS)]
        items = hinted or items
    if field == "deadline":
        dated = [item for item in items if DATE_RE.search(item)]
        items = dated or items
    if field == "pitfalls":
        warned = [item for item in items if any(key in item for key in ("不", "避免", "及时", "不能", "注意", "否则", "视为"))]
        items = warned or items

    return _unique(items)


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


def _attach_citations(items: Sequence[str], chunks: Sequence[dict]) -> list[dict]:
    result: list[dict] = []
    for item in items:
        item_grams = _bigrams(item)
        best_score = -1.0
        best_chunk = None
        for chunk in chunks:
            chunk_text = str(chunk["text"])
            if item in chunk_text:
                score = 100.0 + len(item)
            else:
                score = float(len(item_grams & _bigrams(chunk_text)))
            if score > best_score:
                best_score = score
                best_chunk = chunk
        citation = int(best_chunk["ord"]) + 1 if best_chunk else 1
        snippet = str(best_chunk["text"])[:200] if best_chunk else ""
        result.append({"text": item, "citation": citation, "snippet": snippet})
    return result


def _one_liner(title: str, audience: list[str], benefit: list[str], sections: list[dict]) -> str:
    for section in sections:
        if any(key in section["heading"] for key in ("一句话", "结论", "摘要", "速览")):
            items = _unique(_split_items(_section_body(section)))
            if items:
                return items[0]
    if audience and benefit:
        first_audience = audience[0].rstrip("。；;")
        first_benefit = benefit[0].rstrip("。；;")
        return f"{first_audience}，{first_benefit}。"
    return f"本卡根据《{title}》整理，重点说明谁能办、要带什么、怎么办。"


def build_policy_card(document: dict, chunks: Sequence[dict]) -> dict:
    content = str(document.get("content", ""))
    title = str(document.get("title", "未命名政策"))
    sections = parse_sections(content)
    plain_text = _clean_markdown(content)

    raw_fields = {field: _collect_field(field, sections, plain_text) for field in FIELD_KEYWORDS}
    materials = _attach_citations(raw_fields["materials"][:8], chunks)
    steps = _attach_citations(raw_fields["steps"][:6], chunks)
    audience = _attach_citations(raw_fields["audience"][:4], chunks)
    benefit = _attach_citations(raw_fields["benefit"][:4], chunks)
    deadline = _attach_citations(raw_fields["deadline"][:3], chunks)
    pitfalls = _attach_citations(raw_fields["pitfalls"][:5], chunks)
    contact = _attach_citations(raw_fields["contact"][:3], chunks)

    one_liner = _one_liner(
        title,
        [item["text"] for item in audience],
        [item["text"] for item in benefit],
        sections,
    )

    sources = [
        {
            "index": int(chunk["ord"]) + 1,
            "title": title,
            "chunk_index": int(chunk["ord"]),
            "snippet": str(chunk["text"])[:260],
        }
        for chunk in chunks
    ]

    return {
        "doc_id": document.get("id"),
        "title": title,
        "one_liner": one_liner,
        "audience": audience,
        "benefit": benefit,
        "materials": materials,
        "steps": steps,
        "deadline": deadline,
        "pitfalls": pitfalls,
        "contact": contact,
        "sources": sources,
        "counts": {
            "materials": len(materials),
            "steps": len(steps),
            "sources": len(sources),
        },
        "generated_at": _utc_now(),
        "mode": "heuristic",
        "disclaimer": "这张明白卡由 AI 辅助整理，具体条件、金额和时限以当地官方最新发布为准。",
    }
