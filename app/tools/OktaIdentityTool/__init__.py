"""Okta identity lookup tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.okta import make_okta_client
from app.tools.base import BaseTool


class OktaIdentityTool(BaseTool):
    """Look up employee identity, group memberships, app access, and auth events in Okta.

    Supports searching by name or email, resolving group memberships and
    application assignments, and retrieving authentication event logs for
    a specified date range.
    """

    name = "lookup_okta_identity"
    source = "okta"
    description = (
        "Look up an employee's identity profile, group memberships, application access, "
        "and authentication activity in Okta. Use to establish whether a subject had "
        "access to specific systems, identify unusual login patterns, or confirm "
        "employment and role at a given time during an HR/legal investigation."
    )
    use_cases = [
        "Verifying an employee's identity, title, and department at the time of an incident",
        "Determining which applications and systems an employee could access",
        "Checking whether a subject's account was active or deprovisioned at a key date",
        "Reviewing login history to establish presence or identify anomalous access",
        "Identifying group memberships that granted elevated privileges",
        "Checking for after-hours or unusual login patterns during a misconduct window",
    ]
    requires = ["domain", "api_token"]
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Okta domain (e.g. 'acmecorp.okta.com')",
            },
            "api_token": {
                "type": "string",
                "description": "Okta API token (SSWS token)",
            },
            "user_id": {
                "type": "string",
                "description": "Okta user ID, login email, or UPN (use if known)",
            },
            "search_query": {
                "type": "string",
                "description": "Name or email to search for (used when user_id is not known)",
            },
            "include_groups": {
                "type": "boolean",
                "description": "Include group memberships in the result",
                "default": True,
            },
            "include_apps": {
                "type": "boolean",
                "description": "Include application assignments in the result",
                "default": False,
            },
            "include_auth_events": {
                "type": "boolean",
                "description": "Include recent authentication events from the system log",
                "default": False,
            },
            "auth_since": {
                "type": "string",
                "description": "ISO-8601 start date for auth event filter (e.g. '2024-01-01T00:00:00Z')",
            },
            "auth_until": {
                "type": "string",
                "description": "ISO-8601 end date for auth event filter",
            },
            "auth_limit": {
                "type": "integer",
                "description": "Maximum auth events to return (default: 50)",
                "default": 50,
            },
        },
        "required": ["domain", "api_token"],
    }
    outputs = {
        "user": "User profile: id, login, email, name, title, department, status, last_login",
        "groups": "Group memberships with name and description",
        "apps": "Application assignments with label and URL",
        "auth_events": "Authentication events: type, timestamp, outcome, IP address",
        "search_results": "Matching users when search_query is used",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("okta", {})
        return bool(cfg.get("domain") and cfg.get("api_token"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("okta", {})
        return {
            "domain": cfg.get("domain", ""),
            "api_token": cfg.get("api_token", ""),
            "user_id": "",
            "search_query": "",
            "include_groups": True,
            "include_apps": False,
            "include_auth_events": False,
            "auth_since": "",
            "auth_until": "",
            "auth_limit": 50,
        }

    def run(
        self,
        domain: str = "",
        api_token: str = "",
        user_id: str = "",
        search_query: str = "",
        include_groups: bool = True,
        include_apps: bool = False,
        include_auth_events: bool = False,
        auth_since: str = "",
        auth_until: str = "",
        auth_limit: int = 50,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not domain or not api_token:
            return {
                "source": "okta",
                "available": False,
                "error": "domain and api_token are required.",
            }

        if not user_id and not search_query:
            return {
                "source": "okta",
                "available": False,
                "error": "Provide user_id or search_query.",
            }

        client = make_okta_client(domain=domain, api_token=api_token)
        if client is None:
            return {"source": "okta", "available": False, "error": "Could not create client."}

        try:
            with client:
                return self._run_with_client(
                    client,
                    user_id=user_id,
                    search_query=search_query,
                    include_groups=include_groups,
                    include_apps=include_apps,
                    include_auth_events=include_auth_events,
                    auth_since=auth_since or None,
                    auth_until=auth_until or None,
                    auth_limit=auth_limit,
                )
        except Exception as exc:
            return {"source": "okta", "available": False, "error": str(exc)}

    def _run_with_client(
        self,
        client: Any,
        *,
        user_id: str,
        search_query: str,
        include_groups: bool,
        include_apps: bool,
        include_auth_events: bool,
        auth_since: str | None,
        auth_until: str | None,
        auth_limit: int,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"source": "okta", "available": True}

        if search_query and not user_id:
            matches = client.search_users(search_query)
            if not matches:
                return {
                    "source": "okta",
                    "available": True,
                    "search_query": search_query,
                    "search_results": [],
                    "message": f"No users found matching '{search_query}'.",
                }
            if len(matches) > 1:
                return {
                    "source": "okta",
                    "available": True,
                    "search_query": search_query,
                    "search_results": matches,
                    "message": f"Found {len(matches)} users. Refine search or provide user_id.",
                }
            user_id = matches[0]["id"]
            result["search_results"] = matches

        user = client.get_user(user_id)
        result["user"] = user
        result["user_id"] = user_id

        if include_groups:
            result["groups"] = client.get_user_groups(user_id)

        if include_apps:
            result["apps"] = client.get_user_app_assignments(user_id)

        if include_auth_events:
            result["auth_events"] = client.get_user_auth_events(
                user_id,
                since=auth_since,
                until=auth_until,
                limit=auth_limit,
            )

        return result


lookup_okta_identity = OktaIdentityTool()
