"""Broadcast investigation findings to all configured output channels simultaneously."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.tools.base import BaseTool


class BroadcastFindingsTool(BaseTool):
    """Dispatch RCA summary to PagerDuty, Linear, and Jira in parallel."""

    name = "broadcast_findings"
    source = "broadcast"
    description = (
        "Broadcast investigation findings to all configured output channels simultaneously: "
        "PagerDuty incident note, Linear issue, and Jira ticket. "
        "Use as the final step after completing root cause analysis so every stakeholder "
        "system receives the findings without multiple separate tool calls."
    )
    use_cases = [
        "Dispatching a complete RCA summary to all tracking systems at once",
        "Creating a Linear and Jira ticket while adding a PagerDuty note in one step",
        "Notifying all configured delivery channels after identifying the root cause",
        "Reducing post-incident documentation time by broadcasting in parallel",
    ]
    requires = ["summary"]
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Investigation summary to broadcast (Markdown supported)",
            },
            "alert_name": {
                "type": "string",
                "default": "",
                "description": "Alert name used as the ticket/issue title",
            },
            "pagerduty_incident_id": {
                "type": "string",
                "default": "",
                "description": "PagerDuty incident ID to attach a note to",
            },
            "linear_team_id": {
                "type": "string",
                "default": "",
                "description": "Linear team ID to create a follow-up issue in",
            },
            "jira_project_key": {
                "type": "string",
                "default": "",
                "description": "Jira project key to create an incident issue in",
            },
        },
        "required": ["summary"],
    }
    outputs = {
        "dispatched": "Number of channels that received the findings successfully",
        "total_channels": "Number of channels attempted",
        "results": "Per-channel dispatch outcome dict",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(
            sources.get("pagerduty", {}).get("connection_verified")
            or sources.get("linear", {}).get("connection_verified")
            or sources.get("jira", {}).get("connection_verified")
        )

    def extract_params(self, sources: dict) -> dict[str, Any]:
        pd = sources.get("pagerduty", {})
        lin = sources.get("linear", {})
        return {
            "summary": "",
            "alert_name": "",
            "pagerduty_incident_id": pd.get("default_incident_id", ""),
            "linear_team_id": lin.get("default_team_id", ""),
            "jira_project_key": "",
        }

    def run(
        self,
        summary: str,
        alert_name: str = "",
        pagerduty_incident_id: str = "",
        linear_team_id: str = "",
        jira_project_key: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not summary:
            return {"source": "broadcast", "available": False, "error": "summary is required."}

        title = (alert_name or "Incident Investigation").strip()
        tasks: dict[str, Any] = {}

        if pagerduty_incident_id and kwargs.get("pagerduty_api_token"):
            tasks["pagerduty"] = lambda: self._dispatch_pagerduty(
                pagerduty_incident_id,
                f"**{title}**\n\n{summary}",
                str(kwargs.get("pagerduty_api_token", "")),
            )
        if linear_team_id and kwargs.get("linear_api_key"):
            tasks["linear"] = lambda tid=linear_team_id: self._dispatch_linear(
                title,
                summary,
                tid,
                str(kwargs.get("linear_api_key", "")),
            )
        if (
            jira_project_key
            and kwargs.get("jira_base_url")
            and kwargs.get("jira_email")
            and kwargs.get("jira_api_token")
        ):
            tasks["jira"] = lambda pkey=jira_project_key: self._dispatch_jira(
                title,
                summary,
                pkey,
                str(kwargs.get("jira_base_url", "")),
                str(kwargs.get("jira_email", "")),
                str(kwargs.get("jira_api_token", "")),
            )

        if not tasks:
            return {
                "source": "broadcast",
                "available": True,
                "dispatched": 0,
                "total_channels": 0,
                "results": {},
                "message": (
                    "No output channels triggered. Provide pagerduty_incident_id, "
                    "linear_team_id, or jira_project_key with matching credentials."
                ),
            }

        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): channel for channel, fn in tasks.items()}
            for future in as_completed(futures):
                channel = futures[future]
                try:
                    results[channel] = future.result()
                except Exception as exc:
                    results[channel] = {"ok": False, "error": str(exc)}

        dispatched = sum(1 for r in results.values() if r.get("ok") or r.get("success"))
        return {
            "source": "broadcast",
            "available": True,
            "dispatched": dispatched,
            "total_channels": len(tasks),
            "results": results,
        }

    @staticmethod
    def _dispatch_pagerduty(incident_id: str, content: str, api_token: str) -> dict[str, Any]:
        from app.services.pagerduty import make_pagerduty_client

        client = make_pagerduty_client(api_token, "")
        if client is None:
            return {"ok": False, "error": "PagerDuty not configured."}
        with client:
            r = client.add_note(incident_id=incident_id, content=content)
        return {"ok": r.get("success", False), **r}

    @staticmethod
    def _dispatch_linear(
        title: str, description: str, team_id: str, api_key: str
    ) -> dict[str, Any]:
        from app.services.linear import make_linear_client

        client = make_linear_client(api_key)
        if client is None:
            return {"ok": False, "error": "Linear not configured."}
        with client:
            r = client.create_issue(
                title=title, description=description, team_id=team_id, priority=2
            )
        return {"ok": r.get("success", False), **r}

    @staticmethod
    def _dispatch_jira(
        title: str,
        description: str,
        project_key: str,
        base_url: str,
        email: str,
        api_token: str,
    ) -> dict[str, Any]:
        from app.services.jira import make_jira_client

        client = make_jira_client(
            base_url=base_url,
            email=email,
            api_token=api_token,
            project_key=project_key,
        )
        if client is None:
            return {"ok": False, "error": "Jira not configured."}
        r = client.create_issue(
            summary=title,
            description=description,
            issue_type="Incident",
            priority="High",
        )
        return {"ok": r.get("success", False), **r}


broadcast_findings = BroadcastFindingsTool()
