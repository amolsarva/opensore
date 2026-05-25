"""GitHub Actions workflow runs tool — find recent CI/CD failures during incident investigation."""

from __future__ import annotations

from typing import Any

from app.services.github import make_github_client
from app.tools.base import BaseTool


class GitHubActionsRunsTool(BaseTool):
    """List recent GitHub Actions workflow runs to correlate deployments with incidents."""

    name = "github_actions_runs"
    source = "github_actions"
    description = (
        "List recent GitHub Actions workflow runs for a repository. Use this to find failed "
        "deployments, broken CI pipelines, or recent pushes that may have triggered the incident."
    )
    use_cases = [
        "Checking whether a recent deployment triggered the alert",
        "Finding failed CI/CD pipelines in the incident time window",
        "Listing all recent workflow runs for a specific branch",
        "Filtering for only failed or cancelled runs to quickly find the culprit",
        "Correlating a production incident with a specific commit or workflow event",
    ]
    requires = ["owner", "repo"]
    input_schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "GitHub repository owner or org"},
            "repo": {"type": "string", "description": "Repository name"},
            "github_token": {
                "type": "string",
                "description": "GitHub personal access token (optional for public repos)",
                "default": "",
            },
            "github_url": {
                "type": "string",
                "description": "GitHub Enterprise base URL (leave empty for github.com)",
                "default": "",
            },
            "workflow_id": {
                "type": "string",
                "description": "Filter to a specific workflow file name (e.g. 'deploy.yml') or numeric ID",
                "default": "",
            },
            "branch": {
                "type": "string",
                "description": "Filter runs to a specific branch (e.g. 'main')",
                "default": "",
            },
            "status": {
                "type": "string",
                "description": "Filter by status: completed, in_progress, queued, failure, success",
                "default": "",
            },
            "event": {
                "type": "string",
                "description": "Filter by triggering event: push, pull_request, schedule, workflow_dispatch",
                "default": "",
            },
            "per_page": {
                "type": "integer",
                "description": "Number of runs to return",
                "default": 20,
            },
        },
        "required": ["owner", "repo"],
    }
    outputs = {
        "runs": "List of workflow runs with id, name, branch, sha, status, conclusion, event, created_at, html_url",
        "total_count": "Total matching workflow runs in the repository",
    }

    def is_available(self, sources: dict) -> bool:
        gh = sources.get("github", {})
        return bool(gh.get("owner") and gh.get("repo"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        gh = sources.get("github", {})
        return {
            "owner": gh.get("owner", ""),
            "repo": gh.get("repo", ""),
            "github_token": gh.get("auth_token") or gh.get("github_token", ""),
            "github_url": gh.get("url", ""),
            "workflow_id": "",
            "branch": gh.get("ref", ""),
            "status": "failure",
            "event": "",
            "per_page": 20,
        }

    def run(
        self,
        owner: str,
        repo: str,
        github_token: str = "",
        github_url: str = "",
        workflow_id: str = "",
        branch: str = "",
        status: str = "",
        event: str = "",
        per_page: int = 20,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not owner or not repo:
            return {"source": "github", "available": False, "error": "owner and repo are required."}

        from app.services.github.client import _BASE_URL

        base_url = github_url.rstrip("/") + "/api/v3" if github_url else _BASE_URL
        client = make_github_client(token=github_token or None, base_url=base_url)

        with client:
            result = client.list_workflow_runs(
                owner=owner,
                repo=repo,
                workflow_id=workflow_id,
                branch=branch,
                status=status,
                per_page=per_page,
                event=event,
            )

        if not result.get("success"):
            return {"source": "github", "available": False, "error": result.get("error", "unknown")}
        return {
            "source": "github",
            "available": True,
            "owner": owner,
            "repo": repo,
            "runs": result.get("runs", []),
            "total_count": result.get("total_count", 0),
        }


github_actions_runs = GitHubActionsRunsTool()
