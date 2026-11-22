from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import db  # noqa: E402
from app.answer import local_extractive_answer  # noqa: E402
from app.config import settings  # noqa: E402
from app.qa import scoped_contexts  # noqa: E402
from app.retrieval import cache, rows_from_db  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402
from eval.metrics import evaluate_result, summarize  # noqa: E402


def load_gold(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _failure_reason(result: dict) -> str:
    metrics = result["metrics"]
    reasons = []
    if result["answerable"]:
        retrieval = metrics["retrieval"] or {}
        if retrieval.get("hit_at_3") == 0:
            reasons.append("检索未命中")
        if (metrics["keyword_recall"] or 0) < 0.8:
            reasons.append("关键词召回不足")
        if (metrics["citation_support"] or 0) < 0.8:
            reasons.append("引用支撑不足")
        if (metrics["citation_validity"] or 0) < 1:
            reasons.append("引用编号越界")
    elif metrics["refusal_ok"] != 1:
        reasons.append("未正确拒答")
    return "、".join(reasons) or "通过"


def run(output_dir: Path, top_k: int = 4) -> dict:
    db.init_db(settings.db_path)
    seed_if_empty()
    documents = {item["title"]: item for item in db.list_documents(settings.db_path)}
    all_rows = rows_from_db(db.all_chunks(settings.db_path))
    gold = load_gold(Path(__file__).parent / "gold_set.jsonl")

    results: list[dict] = []
    for item in gold:
        document = documents.get(item["doc"])
        if not document:
            raise RuntimeError(f"Gold document not found: {item['doc']}")
        doc_rows = [row for row in all_rows if row.doc_id == document["id"]]
        ranked_hits = cache.search(doc_rows, item["question"], top_k)
        contexts = scoped_contexts(
            settings.db_path,
            document["id"],
            item["question"],
            top_k=top_k,
        )
        started = time.perf_counter()
        answer = local_extractive_answer(item["question"], contexts, "resident")
        latency_ms = (time.perf_counter() - started) * 1000
        evaluated = evaluate_result(
            question=item["question"],
            answer=answer,
            contexts=contexts,
            ranked_hits=ranked_hits,
            keywords=item["expected_keywords"],
            answerable=item["answerable"],
            latency_ms=latency_ms,
        )
        evaluated.update(
            {
                "id": item["id"],
                "doc": item["doc"],
                "intent": item["intent"],
                "expected_keywords": item["expected_keywords"],
            }
        )
        evaluated["failure_reason"] = _failure_reason(evaluated)
        retrieval = evaluated["metrics"]["retrieval"] or {}
        evaluated["top1_miss"] = bool(
            evaluated["answerable"] and retrieval.get("hit_at_1") == 0
        )
        results.append(evaluated)

    metrics = summarize(results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": settings.mode,
        "top_k": top_k,
        "dataset": {
            "total": metrics["total"],
            "answerable": metrics["answerable"],
            "unanswerable": metrics["unanswerable"],
            "source": "backend/eval/gold_set.jsonl",
        },
        "metrics": metrics,
        "results": results,
        "retrieval_misses": [
            {
                "id": result["id"],
                "doc": result["doc"],
                "question": result["question"],
                "hit_at_3": (result["metrics"]["retrieval"] or {}).get("hit_at_3"),
            }
            for result in results
            if result["top1_miss"]
        ],
        "method": {
            "retrieval": "字符 2-3 gram TF-IDF，按相关片段关键词计算 Hit@1 / Hit@3 / MRR",
            "citation": "检查引用编号是否越界、是否覆盖回答、引用片段是否包含预期关键词",
            "groundedness": "回答句子与上下文的字符 bigram 重合率代理指标，不等同于人工事实核查",
            "refusal": "4 条跨域问题，检查是否拒绝根据常识猜测",
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    with (output_dir / "report.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "doc",
                "question",
                "intent",
                "answerable",
                "hit_at_3",
                "keyword_recall",
                "citation_validity",
                "citation_support",
                "groundedness",
                "refusal_ok",
                "latency_ms",
                "failure_reason",
            ],
        )
        writer.writeheader()
        for result in results:
            metrics = result["metrics"]
            retrieval = metrics["retrieval"] or {}
            writer.writerow(
                {
                    "id": result["id"],
                    "doc": result["doc"],
                    "question": result["question"],
                    "intent": result["intent"],
                    "answerable": result["answerable"],
                    "hit_at_3": retrieval.get("hit_at_3"),
                    "keyword_recall": metrics["keyword_recall"],
                    "citation_validity": metrics["citation_validity"],
                    "citation_support": metrics["citation_support"],
                    "groundedness": metrics["groundedness"],
                    "refusal_ok": metrics["refusal_ok"],
                    "latency_ms": result["latency_ms"],
                    "failure_reason": result["failure_reason"],
                }
            )
    return report


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict) -> str:
    metrics = report["metrics"]
    failures = [result for result in report["results"] if result["failure_reason"] != "通过"]
    lines = [
        "# 明白办事 · 离线评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 模式：{report['mode']}",
        f"- 数据集：{report['dataset']['total']} 条（可回答 {report['dataset']['answerable']}，跨域拒答 {report['dataset']['unanswerable']}）",
        "",
        "## 总览",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
        f"| Hit@1 | {_pct(metrics['hit_at_1'])} |",
        f"| Hit@3 | {_pct(metrics['hit_at_3'])} |",
        f"| MRR | {metrics['mrr']:.3f} |",
        f"| 关键词召回 | {_pct(metrics['keyword_recall'])} |",
        f"| 引用有效率 | {_pct(metrics['citation_validity'])} |",
        f"| 引用覆盖率 | {_pct(metrics['citation_coverage'])} |",
        f"| 引用支撑率 | {_pct(metrics['citation_support'])} |",
        f"| Groundedness 代理 | {_pct(metrics['groundedness'])} |",
        f"| 拒答准确率 | {_pct(metrics['refusal_accuracy'])} |",
        f"| P50 延迟 | {metrics['latency_p50_ms']:.2f} ms |",
        f"| P95 延迟 | {metrics['latency_p95_ms']:.2f} ms |",
        "",
        "## 失败样例",
        "",
    ]
    if not failures:
        lines.append("本次评测没有失败样例。")
    else:
        lines.extend(["| 问题 | 文档 | 原因 |", "| --- | --- | --- |"])
        for result in failures[:12]:
            lines.append(
                f"| {result['question']} | {result['doc']} | {result['failure_reason']} |"
            )
    lines.extend(["", "## Top1 未命中样例", ""])
    misses = report.get("retrieval_misses", [])
    if not misses:
        lines.append("没有 Top1 未命中样例。")
    else:
        lines.extend(["| 问题 | 文档 | Hit@3 |", "| --- | --- | --- |"])
        for miss in misses:
            lines.append(
                f"| {miss['question']} | {miss['doc']} | {_pct(miss['hit_at_3'])} |"
            )
        lines.append("")
        lines.append("Top1 未命中不代表答案不可用；Top3 命中仍可支撑回答，这里用于分析排序优化空间。")
    lines.extend(
        [
            "",
            "## 方法说明",
            "",
            "- 检索：字符 2-3 gram TF-IDF，按相关片段关键词计算 Hit@1、Hit@3、MRR。",
            "- 引用：检查编号是否越界、是否覆盖回答、引用片段是否包含预期关键词。",
            "- Groundedness：回答句子与上下文的字符 bigram 重合率代理指标，不等同于人工事实核查。",
            "- 拒答：4 条跨域问题，检查是否拒绝根据常识猜测。",
            "",
            "> 这是离线小样本评测，不等同于真实社区场景的效果验证。正式上线前需要扩大标注集并做人工抽检。",
            "",
        ]
    )
    return "\n".join(lines)


def check_thresholds(metrics: dict) -> list[str]:
    thresholds = {
        "hit_at_3": 0.85,
        "citation_validity": 0.95,
        "citation_coverage": 0.90,
        "keyword_recall": 0.75,
        "groundedness": 0.85,
        "refusal_accuracy": 0.80,
    }
    failures = []
    for key, threshold in thresholds.items():
        value = metrics.get(key)
        if value is None or value < threshold:
            failures.append(f"{key}={value} < {threshold}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Mori offline evaluation")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--check", action="store_true", help="Fail if quality thresholds are not met")
    args = parser.parse_args()

    report = run(args.output_dir, args.top_k)
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    if args.check:
        failures = check_thresholds(report["metrics"])
        if failures:
            print("Quality gate failed:")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print("Quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
