from __future__ import annotations

import unittest

from app.observability import MetricsRegistry, TokenBucket


class TokenBucketTest(unittest.TestCase):
    def test_allow_then_refill(self) -> None:
        bucket = TokenBucket(60, capacity=2)
        bucket.tokens = 2.0
        bucket.updated = 0.0
        self.assertTrue(bucket.allow(0.0))
        self.assertTrue(bucket.allow(0.0))
        self.assertFalse(bucket.allow(0.0))
        self.assertTrue(bucket.allow(2.0))


class MetricsRegistryTest(unittest.TestCase):
    def test_render_prometheus(self) -> None:
        registry = MetricsRegistry("test")
        registry.observe_request("GET", "/api/health", 200, 0.02)
        text = registry.render()
        self.assertIn('mori_app_info{version="test"} 1', text)
        self.assertIn(
            'mori_http_requests_total{method="GET",path="/api/health",status="200"} 1',
            text,
        )
        self.assertIn("mori_http_request_duration_seconds_bucket", text)
        self.assertIn('le="+Inf"', text)


if __name__ == "__main__":
    unittest.main()
