from __future__ import annotations

import unittest

from app.answer import REFUSAL, local_extractive_answer
from app.retrieval import Retrieved
from eval.metrics import (
    citation_coverage,
    citation_support,
    citation_validity,
    evaluate_result,
    groundedness,
    keyword_recall,
    refusal_ok,
    retrieval_metrics,
    summarize,
)
from eval.build_gold_set import build as build_gold_set


def context(text: str, score: float = 1.0, ordinal: int = 0) -> Retrieved:
    return Retrieved(
        chunk_id=ordinal + 1,
        doc_id="demo",
        doc_title="测试政策",
        ord=ordinal,
        text=text,
        score=score,
    )


class MetricsTest(unittest.TestCase):
    def test_gold_set_has_100_questions(self) -> None:
        records = build_gold_set()
        self.assertEqual(len(records), 100)
        self.assertEqual(sum(1 for item in records if item["answerable"]), 80)
        self.assertEqual(sum(1 for item in records if not item["answerable"]), 20)

    def test_retrieval_metrics(self) -> None:
        hits = [
            context("这是一段与问题无关的内容。", 0.1),
            context("申请材料包括身份证和户口簿。", 0.2, 1),
        ]
        metrics = retrieval_metrics(hits, ["身份证"])
        self.assertEqual(metrics["hit_at_1"], 0.0)
        self.assertEqual(metrics["hit_at_3"], 1.0)
        self.assertEqual(metrics["mrr"], 0.5)

    def test_citation_metrics(self) -> None:
        contexts = [context("申请材料包括身份证和户口簿。")]
        answer = "- 需要身份证。 [1]"
        self.assertEqual(citation_validity(answer, 1), 1.0)
        self.assertEqual(citation_coverage(answer), 1.0)
        self.assertEqual(citation_support(answer, contexts, ["身份证"]), 1.0)
        self.assertEqual(keyword_recall(answer, ["身份证", "户口簿"]), 0.5)

    def test_groundedness_ignores_citation_markers(self) -> None:
        contexts = [context("申请材料包括身份证和户口簿。")]
        answer = "申请材料包括身份证和户口簿。 [1]"
        self.assertGreaterEqual(groundedness(answer, contexts), 0.9)

    def test_refusal(self) -> None:
        self.assertEqual(refusal_ok(REFUSAL, False), 1.0)
        self.assertIsNone(refusal_ok(REFUSAL, True))

    def test_summary(self) -> None:
        contexts = [context("申请材料包括身份证和户口簿。")]
        answerable = evaluate_result(
            question="需要哪些材料？",
            answer="申请材料包括身份证和户口簿。 [1]",
            contexts=contexts,
            ranked_hits=contexts,
            keywords=["身份证"],
            answerable=True,
            latency_ms=1.0,
        )
        unanswerable = evaluate_result(
            question="今天天气怎么样？",
            answer=REFUSAL,
            contexts=contexts,
            ranked_hits=[],
            keywords=[],
            answerable=False,
            latency_ms=1.0,
        )
        summary = summarize([answerable, unanswerable])
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["answerable"], 1)
        self.assertEqual(summary["unanswerable"], 1)
        self.assertEqual(summary["refusal_accuracy"], 1.0)
        self.assertEqual(summary["hit_at_3"], 1.0)


class AnswerGuardTest(unittest.TestCase):
    def test_out_of_scope_is_refused(self) -> None:
        contexts = [context("## 所需材料\n- 本人身份证原件及复印件。")]
        answer = local_extractive_answer("今天天气怎么样？", contexts, "resident")
        self.assertEqual(answer, REFUSAL)

    def test_material_intent(self) -> None:
        contexts = [context("## 所需材料\n- 本人身份证原件及复印件。\n- 户口簿首页和本人页复印件。")]
        answer = local_extractive_answer("申请需要哪些材料？", contexts, "resident")
        self.assertIn("身份证", answer)
        self.assertIn("户口簿", answer)


if __name__ == "__main__":
    unittest.main()
