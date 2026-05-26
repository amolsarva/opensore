"""HTTP endpoint probe tool — health check any URL for status, latency, and TLS cert expiry."""

from __future__ import annotations

import socket
import ssl
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.tools.base import BaseTool


class HttpProbeTool(BaseTool):
    """Probe any HTTP/HTTPS endpoint for availability, latency, and certificate health."""

    name = "http_probe"
    source = "http_probe"
    description = (
        "Probe any HTTP/HTTPS endpoint to check its availability, response latency, "
        "status code, and TLS certificate validity. Use during investigation to verify "
        "downstream service reachability or detect certificate expiry issues."
    )
    use_cases = [
        "Checking if a downstream API endpoint is reachable during an outage",
        "Measuring response latency to confirm a slowness hypothesis",
        "Verifying SSL/TLS certificate expiry for security or reliability incidents",
        "Confirming a service health-check URL returns the expected status code",
        "Detecting redirect chains that might indicate misconfiguration",
    ]
    requires = ["url"]
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to probe (http:// or https://)",
            },
            "method": {
                "type": "string",
                "default": "GET",
                "description": "HTTP method (GET, POST, HEAD, etc.)",
            },
            "expected_status": {
                "type": "integer",
                "default": 200,
                "description": "Expected HTTP status code for ok=True",
            },
            "timeout_seconds": {
                "type": "number",
                "default": 10.0,
                "description": "Request timeout in seconds",
            },
            "headers": {
                "type": "object",
                "default": {},
                "description": "Additional request headers",
            },
            "follow_redirects": {
                "type": "boolean",
                "default": True,
                "description": "Follow HTTP redirects",
            },
        },
        "required": ["url"],
    }
    outputs = {
        "status_code": "HTTP response status code",
        "ok": "True if status_code matches expected_status",
        "latency_ms": "Round-trip latency in milliseconds",
        "ssl_expiry_days": "Days until TLS cert expires (HTTPS only)",
        "body_excerpt": "First 500 chars of the response body",
        "redirect_count": "Number of redirects followed",
    }

    def is_available(self, sources: dict) -> bool:  # noqa: ARG002
        return True

    def extract_params(self, sources: dict) -> dict[str, Any]:  # noqa: ARG002
        return {
            "url": "",
            "method": "GET",
            "expected_status": 200,
            "timeout_seconds": 10.0,
            "follow_redirects": True,
        }

    def run(
        self,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        timeout_seconds: float = 10.0,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not url:
            return {"source": "http_probe", "available": False, "error": "url is required."}

        ssl_expiry_days: float | None = None

        if url.lower().startswith("https://"):
            ssl_expiry_days = self._check_ssl_expiry(url, timeout_seconds)

        t0 = time.perf_counter()
        try:
            resp = httpx.request(
                method.upper(),
                url,
                headers=headers or {},
                timeout=timeout_seconds,
                follow_redirects=follow_redirects,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            body_excerpt = resp.text[:500] if resp.text else ""
            redirect_count = len(resp.history)
            return {
                "source": "http_probe",
                "available": True,
                "url": url,
                "status_code": resp.status_code,
                "ok": resp.status_code == expected_status,
                "latency_ms": round(latency_ms, 2),
                "ssl_expiry_days": (
                    round(ssl_expiry_days, 1) if ssl_expiry_days is not None else None
                ),
                "body_excerpt": body_excerpt,
                "redirect_count": redirect_count,
                "content_type": resp.headers.get("content-type", ""),
            }
        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "source": "http_probe",
                "available": True,
                "url": url,
                "ok": False,
                "error": f"Request timed out after {timeout_seconds}s",
                "latency_ms": round(latency_ms, 2),
                "ssl_expiry_days": ssl_expiry_days,
                "body_excerpt": "",
                "redirect_count": 0,
            }
        except Exception as exc:
            return {
                "source": "http_probe",
                "available": True,
                "url": url,
                "ok": False,
                "error": str(exc),
                "latency_ms": None,
                "ssl_expiry_days": ssl_expiry_days,
                "body_excerpt": "",
                "redirect_count": 0,
            }

    @staticmethod
    def _check_ssl_expiry(url: str, timeout: float) -> float | None:
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            port = parsed.port or 443
            ctx = ssl.create_default_context()
            with (
                socket.create_connection((hostname, port), timeout=timeout) as sock,
                ctx.wrap_socket(sock, server_hostname=hostname) as ssock,
            ):
                    cert = ssock.getpeercert() or {}
                    expire_raw = cert.get("notAfter")
                    expire_str = str(expire_raw) if expire_raw else ""
                    if expire_str:
                        expire_dt = datetime.strptime(
                            expire_str, "%b %d %H:%M:%S %Y %Z"
                        ).replace(tzinfo=UTC)
                        return (expire_dt - datetime.now(UTC)).total_seconds() / 86400
        except Exception:
            pass
        return None


http_probe = HttpProbeTool()
