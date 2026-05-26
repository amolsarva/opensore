"""Grafana annotation writeback — mark the investigation window on dashboards."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.tools.base import BaseTool


class GrafanaAnnotateTool(BaseTool):
    """Write a Grafana annotation to correlate investigation findings with dashboard timelines."""

    name = "grafana_annotate"
    source = "grafana"
    description = (
        "Write a Grafana annotation to mark the incident window on dashboards. "
        "Use at the end of an investigation to overlay the root cause summary "
        "directly on metric and log panels for future reference."
    )
    use_cases = [
        "Marking incident start and end time directly on Grafana dashboards",
        "Adding root cause summary as a Grafana annotation for audit trails",
        "Tagging a deployment or config change found during investigation",
        "Correlating investigation findings with visible Grafana time windows",
    ]
    requires = ["grafana_url", "api_key", "text"]
    input_schema = {
        "type": "object",
        "properties": {
            "grafana_url": {
                "type": "string",
                "description": "Grafana base URL (e.g. https://grafana.example.com)",
            },
            "api_key": {
                "type": "string",
                "description": "Grafana service account token or legacy API key",
            },
            "text": {
                "type": "string",
                "description": "Annotation body — paste root cause summary here",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["opensore", "rca"],
                "description": "Tags for filtering annotations in Grafana",
            },
            "time_ms": {
                "type": "integer",
                "description": "Annotation epoch timestamp in milliseconds (defaults to now)",
            },
            "time_end_ms": {
                "type": "integer",
                "description": "End timestamp for a region annotation (optional)",
            },
            "dashboard_uid": {
                "type": "string",
                "description": "Scope annotation to a specific dashboard UID (optional)",
            },
            "panel_id": {
                "type": "integer",
                "description": "Scope annotation to a specific panel ID (optional)",
            },
        },
        "required": ["grafana_url", "api_key", "text"],
    }
    outputs = {
        "annotation_id": "ID of the created Grafana annotation",
        "url": "URL to view the annotation in Grafana",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("grafana", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        g = sources.get("grafana", {})
        return {
            "grafana_url": g.get("endpoint", ""),
            "api_key": g.get("api_key", ""),
            "text": "",
            "tags": ["opensore", "rca"],
        }

    def run(
        self,
        grafana_url: str,
        api_key: str,
        text: str,
        tags: list[str] | None = None,
        time_ms: int | None = None,
        time_end_ms: int | None = None,
        dashboard_uid: str | None = None,
        panel_id: int | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not grafana_url or not api_key:
            return {
                "source": "grafana",
                "available": False,
                "error": "grafana_url and api_key are required.",
            }
        if not text:
            return {"source": "grafana", "available": False, "error": "text is required."}

        now_ms = int(time.time() * 1000)
        payload: dict[str, Any] = {
            "text": text[:5000],
            "tags": tags or ["opensore", "rca"],
            "time": time_ms or now_ms,
        }
        if time_end_ms:
            payload["timeEnd"] = time_end_ms
        if dashboard_uid:
            payload["dashboardUID"] = dashboard_uid
        if panel_id is not None:
            payload["panelId"] = panel_id

        base = grafana_url.rstrip("/")
        try:
            resp = httpx.post(
                f"{base}/api/annotations",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            ann_id = data.get("id", "")
            return {
                "source": "grafana",
                "available": True,
                "annotation_id": ann_id,
                "url": f"{base}/dashboard/annotations?annotationId={ann_id}",
                "message": data.get("message", "Annotation created."),
            }
        except httpx.HTTPStatusError as exc:
            return {
                "source": "grafana",
                "available": False,
                "error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            }
        except Exception as exc:
            return {"source": "grafana", "available": False, "error": str(exc)}


grafana_annotate = GrafanaAnnotateTool()
