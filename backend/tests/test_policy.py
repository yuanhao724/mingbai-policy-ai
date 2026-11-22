from __future__ import annotations

import unittest

from app.policy import build_policy_card


CONTENT = """# 测试补贴申领指南

## 一句话
符合条件的本地居民可以申请每月补贴。

## 适用对象
- 本地户籍居民。
- 年满 60 周岁。

## 待遇与标准
- 每人每月 100 元。

## 所需材料
- 身份证。
- 户口簿。

## 办理流程
1. 到社区提交申请。
2. 等待街道审核。

## 办理时限
- 一般在 5 个工作日内完成。

## 注意事项
- 不要重复申请同一项补贴。

## 咨询方式
- 社区服务热线 12345。
"""


class PolicyCardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = {"id": "demo", "title": "测试补贴申领指南", "content": CONTENT}
        self.chunks = [{"ord": 0, "text": CONTENT}]
        self.card = build_policy_card(self.document, self.chunks)

    def test_extracts_structured_fields(self) -> None:
        self.assertEqual(self.card["counts"]["materials"], 2)
        self.assertEqual(self.card["counts"]["steps"], 2)
        self.assertIn("本地户籍", self.card["audience"][0]["text"])
        self.assertIn("100", self.card["benefit"][0]["text"])
        self.assertIn("5 个工作日", self.card["deadline"][0]["text"])
        self.assertIn("重复", self.card["pitfalls"][0]["text"])
        self.assertIn("12345", self.card["contact"][0]["text"])

    def test_one_liner_and_citations(self) -> None:
        self.assertIn("符合条件", self.card["one_liner"])
        self.assertTrue(self.card["disclaimer"])
        self.assertEqual(self.card["sources"][0]["index"], 1)
        self.assertEqual(self.card["materials"][0]["citation"], 1)


if __name__ == "__main__":
    unittest.main()
