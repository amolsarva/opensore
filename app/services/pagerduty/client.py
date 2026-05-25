"""PagerDuty REST API v2 client.

Covers incident listing/detail, on-call schedules, escalation policies,
and adding notes to incidents for post-RCA writeback.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.probes import ProbeResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_BASE_URL = "https://api.pagerduty.com"


class PagerDutyConfig:
    """Minimal config container — wraps the API token."""

    def __init__(self, api_token: str, from_email: str = "") -> None:
        self.api_token = api_token.strip()
        self.from_email = from_email.strip()

    @property
    def headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Token token={self.api_token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        }
        if self.from_email:
            h["From"] = self.from_email
        return h


class PagerDutyClient:
    """Synchronous client for the PagerDuty REST API v2."""

    def __init__(self, config: PagerDutyConfig) -> None:
        self.config = config
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=_BASE_URL,
                headers=self.config.headers,
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_token)

    def probe_access(self) -> ProbeResult:
        if not self.is_configured:
            return ProbeResult.missing("Missing PagerDuty API token.")
        with self:
            result = self.list_incidents(limit=1)
        if not result.get("success"):
            return ProbeResult.failed(f"PagerDuty probe failed: {result.get('error', 'unknown')}")
        return ProbeResult.passed("Connected to PagerDuty API; token accepted.")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> PagerDutyClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_incidents(
        self,
        statuses: list[str] | None = None,
        limit: int = 25,
        service_ids: list[str] | None = None,
        urgency: str | None = None,
    ) -> dict[str, Any]:
        """List incidents filtered by status, service, and urgency."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if statuses:
            params["statuses[]"] = statuses
        else:
            params["statuses[]"] = ["triggered", "acknowledged"]
        if service_ids:
            params["service_ids[]"] = service_ids
        if urgency:
            params["urgencies[]"] = [urgency]

        try:
            resp = self._get_client().get("/incidents", params=params)
            resp.raise_for_status()
            data = resp.json()
            incidents = [
                {
                    "id": i.get("id", ""),
                    "incident_number": i.get("incident_number", ""),
                    "title": i.get("title", ""),
                    "status": i.get("status", ""),
                    "urgency": i.get("urgency", ""),
                    "created_at": i.get("created_at", ""),
                    "html_url": i.get("html_url", ""),
                    "service": i.get("service", {}).get("summary", ""),
                    "assigned_to": [
                        a.get("assignee", {}).get("summary", "") for a in i.get("assignments", [])
                    ],
                    "escalation_policy": i.get("escalation_policy", {}).get("summary", ""),
                }
                for i in data.get("incidents", [])
            ]
            return {"success": True, "incidents": incidents, "total": len(incidents)}
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[pagerduty] list_incidents error: %s", error)
            return {"success": False, "error": error, "incidents": []}
        except Exception as exc:
            logger.warning("[pagerduty] list_incidents exception: %s", exc)
            return {"success": False, "error": str(exc), "incidents": []}

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        """Fetch full details for a single incident."""
        try:
            resp = self._get_client().get(f"/incidents/{incident_id}")
            resp.raise_for_status()
            i = resp.json().get("incident", {})
            return {
                "success": True,
                "incident": {
                    "id": i.get("id", ""),
                    "incident_number": i.get("incident_number", ""),
                    "title": i.get("title", ""),
                    "status": i.get("status", ""),
                    "urgency": i.get("urgency", ""),
                    "created_at": i.get("created_at", ""),
                    "resolved_at": i.get("resolved_at", ""),
                    "html_url": i.get("html_url", ""),
                    "service": i.get("service", {}).get("summary", ""),
                    "body": i.get("body", {}).get("details", ""),
                    "assigned_to": [
                        a.get("assignee", {}).get("summary", "") for a in i.get("assignments", [])
                    ],
                    "alert_counts": i.get("alert_counts", {}),
                },
            }
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[pagerduty] get_incident error: %s", error)
            return {"success": False, "error": error}
        except Exception as exc:
            logger.warning("[pagerduty] get_incident exception: %s", exc)
            return {"success": False, "error": str(exc)}

    def add_note(self, incident_id: str, content: str) -> dict[str, Any]:
        """Add a note to an incident (for RCA writeback)."""
        payload = {"note": {"content": content[:25000]}}
        try:
            resp = self._get_client().post(f"/incidents/{incident_id}/notes", json=payload)
            resp.raise_for_status()
            note = resp.json().get("note", {})
            return {
                "success": True,
                "note_id": note.get("id", ""),
                "created_at": note.get("created_at", ""),
            }
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[pagerduty] add_note error: %s", error)
            return {"success": False, "error": error}
        except Exception as exc:
            logger.warning("[pagerduty] add_note exception: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_oncall(self, schedule_ids: list[str] | None = None, limit: int = 20) -> dict[str, Any]:
        """List current on-call entries across all or specific schedules."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if schedule_ids:
            params["schedule_ids[]"] = schedule_ids

        try:
            resp = self._get_client().get("/oncalls", params=params)
            resp.raise_for_status()
            data = resp.json()
            oncalls = [
                {
                    "user": o.get("user", {}).get("summary", ""),
                    "user_email": o.get("user", {}).get("email", ""),
                    "schedule": o.get("schedule", {}).get("summary", ""),
                    "escalation_policy": o.get("escalation_policy", {}).get("summary", ""),
                    "escalation_level": o.get("escalation_level", 1),
                    "start": o.get("start", ""),
                    "end": o.get("end", ""),
                }
                for o in data.get("oncalls", [])
            ]
            return {"success": True, "oncalls": oncalls}
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[pagerduty] get_oncall error: %s", error)
            return {"success": False, "error": error, "oncalls": []}
        except Exception as exc:
            logger.warning("[pagerduty] get_oncall exception: %s", exc)
            return {"success": False, "error": str(exc), "oncalls": []}

    def list_services(self, limit: int = 50) -> dict[str, Any]:
        """List PagerDuty services for service-to-tool correlation."""
        try:
            resp = self._get_client().get("/services", params={"limit": min(limit, 100)})
            resp.raise_for_status()
            services = [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "status": s.get("status", ""),
                    "html_url": s.get("html_url", ""),
                    "escalation_policy": s.get("escalation_policy", {}).get("summary", ""),
                }
                for s in resp.json().get("services", [])
            ]
            return {"success": True, "services": services}
        except Exception as exc:
            logger.warning("[pagerduty] list_services exception: %s", exc)
            return {"success": False, "error": str(exc), "services": []}


def make_pagerduty_client(
    api_token: str | None,
    from_email: str | None = None,
) -> PagerDutyClient | None:
    token = (api_token or "").strip()
    if not token:
        return None
    config = PagerDutyConfig(api_token=token, from_email=from_email or "")
    return PagerDutyClient(config)
