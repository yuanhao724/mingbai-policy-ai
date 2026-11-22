from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict


logger = logging.getLogger("mori.http")

SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (
        b"content-security-policy",
        b"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        b"script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; "
        b"base-uri 'self'; frame-ancestors 'none'",
    ),
)

LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
SKIP_RATE_LIMIT = {"/api/health", "/api/live", "/api/ready", "/api/metrics"}


def setup_logging() -> None:
    level_name = os.getenv("MORI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(message)s")
    else:
        root.setLevel(level)


def normalize_path(path: str) -> str:
    path = re.sub(r"^/api/documents/[^/]+$", "/api/documents/:id", path)
    path = re.sub(r"^/api/policy/[^/]+/card$", "/api/policy/:id/card", path)
    path = re.sub(r"^/api/documents/[^/]+/chunks$", "/api/documents/:id/chunks", path)
    return path


def _label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_sum: dict[tuple[str, str, int], float] = defaultdict(float)
        self._latency_count: dict[tuple[str, str, int], int] = defaultdict(int)
        self._hist: dict[tuple[str, str, int], list[int]] = defaultdict(
            lambda: [0 for _ in LATENCY_BUCKETS]
        )

    def observe_request(self, method: str, path: str, status: int, duration: float) -> None:
        key = (method, path, status)
        with self._lock:
            self._requests[key] += 1
            self._latency_sum[key] += duration
            self._latency_count[key] += 1
            for index, bucket in enumerate(LATENCY_BUCKETS):
                if duration <= bucket:
                    self._hist[key][index] += 1

    def render(self) -> str:
        lines = [
            "# HELP mori_app_info Application build information.",
            "# TYPE mori_app_info gauge",
            f'mori_app_info{{version="{_label(self.version)}"}} 1',
            "# HELP mori_http_requests_total Total HTTP requests.",
            "# TYPE mori_http_requests_total counter",
        ]
        with self._lock:
            requests = dict(self._requests)
            latency_sum = dict(self._latency_sum)
            latency_count = dict(self._latency_count)
            hist = {key: list(value) for key, value in self._hist.items()}

        for key in sorted(requests):
            method, path, status = key
            labels = (
                f'method="{_label(method)}",path="{_label(path)}",status="{status}"'
            )
            lines.append(f"mori_http_requests_total{{{labels}}} {requests[key]}")

        lines.extend(
            [
                "# HELP mori_http_request_duration_seconds HTTP request latency.",
                "# TYPE mori_http_request_duration_seconds histogram",
            ]
        )
        for key in sorted(requests):
            method, path, status = key
            base = f'method="{_label(method)}",path="{_label(path)}",status="{status}"'
            counts = hist[key]
            for bucket, count in zip(LATENCY_BUCKETS, counts):
                lines.append(
                    f"mori_http_request_duration_seconds_bucket{{{base},le=\"{bucket}\"}} {count}"
                )
            lines.append(
                f'mori_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {latency_count[key]}'
            )
            lines.append(
                f"mori_http_request_duration_seconds_sum{{{base}}} {latency_sum[key]:.6f}"
            )
            lines.append(
                f"mori_http_request_duration_seconds_count{{{base}}} {latency_count[key]}"
            )
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


class RequestContextMiddleware:
    """Adds request ID, security headers, structured logs and metrics."""

    def __init__(self, app, registry: MetricsRegistry = metrics) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = ""
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                request_id = value.decode("latin1")[:64]
                break
        request_id = request_id or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin1")))
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            method = scope.get("method", "GET")
            path = normalize_path(scope.get("path", "/"))
            self.registry.observe_request(method, path, status_code, duration)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": round(duration * 1000, 2),
                    },
                    ensure_ascii=False,
                )
            )


class TokenBucket:
    def __init__(self, limit_per_minute: int, capacity: int | None = None) -> None:
        self.rate = max(0.1, limit_per_minute / 60.0)
        self.capacity = float(capacity or max(1, limit_per_minute))
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def allow(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        self.tokens = min(
            self.capacity,
            self.tokens + max(0.0, current - self.updated) * self.rate,
        )
        self.updated = current
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware:
    """Small in-process token bucket. Production should use Redis or an edge limiter."""

    def __init__(self, app, limit_per_minute: int = 240) -> None:
        self.app = app
        self.limit = limit_per_minute
        self._lock = threading.Lock()
        self._buckets: dict[str, TokenBucket] = {}

    def _bucket(self, key: str) -> TokenBucket:
        with self._lock:
            if len(self._buckets) > 10000:
                self._buckets.clear()
            return self._buckets.setdefault(key, TokenBucket(self.limit))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "/")
        if path in SKIP_RATE_LIMIT or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or ("unknown", 0)
        key = str(client[0] or "unknown")
        if not self._bucket(key).allow():
            body = '{"detail":"请求过于频繁，请稍后再试。"}'.encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"retry-after", b"60"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
