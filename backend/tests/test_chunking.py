from __future__ import annotations

import unittest

from app.answer import split_sentences
from app.chunking import chunk_text


class ChunkingTest(unittest.TestCase):
    def test_preserves_markdown_structure(self) -> None:
        text = (
            "# 测试政策\n\n"
            "## 所需材料\n"
            "- 身份证。\n"
            "- 户口簿。\n\n"
            "## 办理流程\n"
            "1. 到社区申请。\n"
            "2. 等待审核。"
        )
        chunks = chunk_text(text, max_chars=200, overlap=20)
        joined = "\n".join(chunks)
        self.assertIn("## 所需材料", joined)
        self.assertIn("- 身份证。", joined)
        self.assertIn("## 办理流程", joined)

    def test_respects_max_chars(self) -> None:
        text = "这是一段用于测试切块长度的政策内容。" * 40
        chunks = chunk_text(text, max_chars=120, overlap=20)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))

    def test_empty_text(self) -> None:
        self.assertEqual(chunk_text("   \n\n  "), [])

    def test_answer_splitter_skips_headings_and_quotes(self) -> None:
        text = (
            "# 标题\n> 免责声明\n## 所需材料\n"
            "- 本人身份证原件及复印件。\n"
            "- 户口簿首页和本人页复印件。"
        )
        sentences = split_sentences(text)
        self.assertEqual(sentences, ["本人身份证原件及复印件。", "户口簿首页和本人页复印件。"])


if __name__ == "__main__":
    unittest.main()
