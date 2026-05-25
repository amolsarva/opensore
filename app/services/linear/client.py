"""Linear GraphQL API client.

Covers issue search, team lookup, and issue creation for RCA writeback.
Linear's API is GraphQL-only; this client wraps the most useful mutations
and queries for incident investigation workflows.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.probes import ProbeResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.linear.app/graphql"
_DEFAULT_TIMEOUT = 20

_VIEWER_QUERY = """
query { viewer { id name email } }
"""

_SEARCH_ISSUES_QUERY = """
query SearchIssues($query: String!, $first: Int!) {
  issueSearch(query: $query, first: $first) {
    nodes {
      id
      identifier
      title
      state { name type }
      priority
      createdAt
      updatedAt
      url
      team { name key }
      assignee { name email }
      description
    }
  }
}
"""

_CREATE_ISSUE_MUTATION = """
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      title
      url
    }
  }
}
"""

_TEAMS_QUERY = """
query { teams { nodes { id name key } } }
"""


class LinearClient:
    """Synchronous Linear GraphQL API client."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.strip()
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def probe_access(self) -> ProbeResult:
        if not self.is_configured:
            return ProbeResult.missing("Missing Linear API key.")
        with self:
            result = self._gql(_VIEWER_QUERY)
        if "errors" in result:
            return ProbeResult.failed(f"Linear auth failed: {result['errors']}")
        viewer = result.get("data", {}).get("viewer", {})
        name = viewer.get("name", "unknown")
        return ProbeResult.passed(f"Connected to Linear as {name}.")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> LinearClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _gql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = self._get_client().post(_API_URL, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            return {
                "errors": [
                    {"message": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}
                ]
            }
        except Exception as exc:
            return {"errors": [{"message": str(exc)}]}

    def search_issues(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Full-text search across Linear issues."""
        result = self._gql(_SEARCH_ISSUES_QUERY, {"query": query, "first": min(limit, 50)})
        if "errors" in result:
            return {"success": False, "error": str(result["errors"]), "issues": []}
        nodes = result.get("data", {}).get("issueSearch", {}).get("nodes", [])
        issues = [
            {
                "id": i.get("id", ""),
                "identifier": i.get("identifier", ""),
                "title": i.get("title", ""),
                "state": i.get("state", {}).get("name", ""),
                "state_type": i.get("state", {}).get("type", ""),
                "priority": i.get("priority", 0),
                "team": i.get("team", {}).get("name", ""),
                "team_key": i.get("team", {}).get("key", ""),
                "assignee": i.get("assignee", {}).get("name", "") if i.get("assignee") else "",
                "url": i.get("url", ""),
                "created_at": i.get("createdAt", ""),
                "updated_at": i.get("updatedAt", ""),
                "description": (i.get("description") or "")[:300],
            }
            for i in nodes
        ]
        return {"success": True, "issues": issues, "total": len(issues)}

    def create_issue(
        self,
        title: str,
        description: str,
        team_id: str,
        priority: int = 2,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Linear issue — used for RCA writeback."""
        inp: dict[str, Any] = {
            "title": title,
            "teamId": team_id,
            "priority": priority,
        }
        if description:
            inp["description"] = description[:65535]
        if label_ids:
            inp["labelIds"] = label_ids

        result = self._gql(_CREATE_ISSUE_MUTATION, {"input": inp})
        if "errors" in result:
            return {"success": False, "error": str(result["errors"])}
        create_result = result.get("data", {}).get("issueCreate", {})
        if not create_result.get("success"):
            return {"success": False, "error": "issueCreate returned success=false"}
        issue = create_result.get("issue", {})
        return {
            "success": True,
            "id": issue.get("id", ""),
            "identifier": issue.get("identifier", ""),
            "title": issue.get("title", ""),
            "url": issue.get("url", ""),
        }

    def list_teams(self) -> dict[str, Any]:
        """List all Linear teams to find the right team_id for issue creation."""
        result = self._gql(_TEAMS_QUERY)
        if "errors" in result:
            return {"success": False, "error": str(result["errors"]), "teams": []}
        teams = [
            {"id": t.get("id", ""), "name": t.get("name", ""), "key": t.get("key", "")}
            for t in result.get("data", {}).get("teams", {}).get("nodes", [])
        ]
        return {"success": True, "teams": teams}


def make_linear_client(api_key: str | None) -> LinearClient | None:
    key = (api_key or "").strip()
    if not key:
        return None
    return LinearClient(api_key=key)
