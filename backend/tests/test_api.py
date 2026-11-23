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
        self.assertTrue(all(document["review_status"] == "approved" for document in documents))

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
        self.assertEqual(payload[0]["review_status"], "draft")
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

    def test_07_eval_report(self) -> None:
        response = self.client.get("/api/eval/latest")
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["dataset"]["total"], 100)
        self.assertEqual(report["dataset"]["answerable"], 80)
        self.assertEqual(report["dataset"]["unanswerable"], 20)
        self.assertEqual(report["metrics"]["total"], 100)
        self.assertEqual(report["metrics"]["hit_at_3"], 1.0)

    def test_08_observability(self) -> None:
        response = self.client.get("/api/health")
        headers = {key.lower(): value for key, value in response.headers.items()}
        self.assertIn("x-request-id", headers)
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertIn("content-security-policy", headers)

        metrics = self.client.get("/api/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("mori_http_requests_total", metrics.text)
        self.assertIn('path="/api/health"', metrics.text)

        ready = self.client.get("/api/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ready")

    def test_09_review_workflow(self) -> None:
        content = "# 待审核政策\n\n## 所需材料\n- 测试材料。\n\n## 办理流程\n1. 去社区。"
        created = self.client.post(
            "/api/documents",
            files=[("files", ("待审核政策.txt", content.encode("utf-8"), "text/plain"))],
        )
        self.assertEqual(created.status_code, 200)
        doc_id = created.json()[0]["id"]

        reviews = self.client.get("/api/reviews")
        self.assertEqual(reviews.status_code, 200)
        self.assertIn("documents", reviews.json())
        self.assertIn("audit", reviews.json())

        denied = self.client.post(
            f"/api/reviews/{doc_id}",
            json={"status": "approved", "reviewer": "测试审核员", "note": "无权限"},
        )
        self.assertEqual(denied.status_code, 403)

        approved = self.client.post(
            f"/api/reviews/{doc_id}",
            headers={"X-Mori-Role": "reviewer"},
            json={"status": "approved", "reviewer": "测试审核员", "note": "材料已核对"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["review_status"], "approved")
        self.assertEqual(approved.json()["reviewer"], "测试审核员")

        audit = self.client.get("/api/reviews").json()["audit"]
        self.assertTrue(any(item["target"] == doc_id and item["actor"] == "测试审核员" for item in audit))
        self.client.delete(f"/api/documents/{doc_id}")


if __name__ == "__main__":
    unittest.main()
