from __future__ import annotations

import unittest

from app.retrieval import ChunkRow, IndexCache


class RetrievalTest(unittest.TestCase):
    def test_chinese_query_matches_expected_document(self) -> None:
        rows = [
            ChunkRow(
                chunk_id=1,
                doc_id="elder",
                doc_title="高龄老人津贴申领指南",
                ord=0,
                text="年满 80 周岁的本地户籍老人，可以申请高龄津贴，每月 100 元。",
            ),
            ChunkRow(
                chunk_id=2,
                doc_id="housing",
                doc_title="公共租赁住房申请指南",
                ord=0,
                text="城镇住房困难家庭可以申请公共租赁住房，审核通过后进入轮候。",
            ),
        ]
        results = IndexCache().search(rows, "80 岁老人每个月能领多少津贴", 2)
        self.assertTrue(results)
        self.assertEqual(results[0].doc_title, "高龄老人津贴申领指南")

    def test_empty_query_returns_nothing(self) -> None:
        rows = [ChunkRow(1, "d", "测试政策", 0, "这是一段政策文本。")]
        self.assertEqual(IndexCache().search(rows, "   ", 2), [])


if __name__ == "__main__":
    unittest.main()
