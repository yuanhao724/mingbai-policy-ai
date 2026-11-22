from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(tempfile.mkdtemp(prefix="mori_test_"))
os.environ["MORI_DB_PATH"] = str(TEST_DIR / "mori_test.db")
os.environ["MORI_STREAM_DELAY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_01_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "local")

    def test_02_seeded_documents(self) -> None:
        response = self.client.get("/api/documents")
        self.assertEqual(response.status_code, 200)
        documents = response.json()
        self.assertGreaterEqual(len(documents), 4)
        self.assertTrue(all(document["chunk_count"] > 0 for document in documents))

    def test_03_policy_card(self) -> None:
        documents = self.client.get("/api/documents").json()
        doc = next(item for item in documents if "高龄" in item["title"])
        response = self.client.get(f"/api/policy/{doc['id']}/card")
        self.assertEqual(response.status_code, 200)
        card = response.json()
        self.assertTrue(card["one_liner"])
        self.assertGreaterEqual(card["counts"]["materials"], 3)
        self.assertGreaterEqual(card["counts"]["steps"], 3)
        self.assertGreaterEqual(card["counts"]["sources"], 1)

    def test_04_chat_is_scoped_to_current_policy(self) -> None:
        documents = self.client.get("/api/documents").json()
        doc = next(item for item in documents if "高龄" in item["title"])
        payload = {
            "doc_id": doc["id"],
            "question": "需要准备哪些材料？",
            "persona": "resident",
        }
        with self.client.stream("POST", "/api/chat/stream", json=payload) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())
        self.assertIn("event: meta", body)
        tokens: list[str] = []
        source_titles: set[str] = set()
        for block in body.strip().split("\n\n"):
            event = ""
            data = ""
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
            if not data:
                continue
            parsed = json.loads(data)
            if event == "token":
                tokens.append(parsed.get("text", ""))
            elif event == "meta":
                source_titles.update(source["title"] for source in parsed.get("sources", []))
        answer = "".join(tokens)
        self.assertIn("老人本人身份证", answer)
        self.assertEqual(source_titles, {"高龄老人津贴申领指南"})
        self.assertNotIn("公共租赁住房申请表", answer)

    def test_05_upload_and_delete(self) -> None:
        content = "# 测试政策\n\n## 所需材料\n- 测试材料。\n\n## 办理流程\n1. 去社区。"
        files = [("files", ("测试政策.txt", content.encode("utf-8"), "text/plain"))]
        created = self.client.post("/api/documents", files=files)
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(len(payload), 1)
        doc_id = payload[0]["id"]
        card = self.client.get(f"/api/policy/{doc_id}/card")
        self.assertEqual(card.status_code, 200)
        deleted = self.client.delete(f"/api/documents/{doc_id}")
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.get(f"/api/policy/{doc_id}/card")
        self.assertEqual(missing.status_code, 404)

    def test_06_stats(self) -> None:
        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        stats = response.json()
        self.assertGreaterEqual(stats["documents"], 4)
        self.assertGreaterEqual(stats["chunks"], 12)
        self.assertGreater(stats["time_saved_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
