"""GitHub Actions jobs tool — drill into a specific workflow run and get failed step logs."""

from __future__ import annotations

from typing import Any

from app.services.github import make_github_client
from app.tools.base import BaseTool


class GitHubActionsJobsTool(BaseTool):
    """Fetch jobs and step-level failures for a specific GitHub Actions workflow run."""

    name = "github_actions_jobs"
    source = "github_actions"
    description = (
        "Fetch the jobs and failed steps for a specific GitHub Actions workflow run. "
        "Optionally fetch raw logs for a specific failing job. Use after github_actions_runs "
        "to drill into why a deployment or CI run failed."
    )
    use_cases = [
        "Getting the specific failed test or build step from a CI run",
        "Fetching logs from a failed deployment job to identify the root error",
        "Listing all steps in a workflow run to find the first failure point",
        "Correlating a deployment pipeline failure with the production incident",
    ]
    requires = ["owner", "repo", "run_id"]
    input_schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "GitHub repo owner"},
            "repo": {"type": "string", "description": "Repository name"},
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID from github_actions_runs",
            },
            "github_token": {"type": "string", "description": "GitHub token", "default": ""},
            "github_url": {
                "type": "string",
                "description": "GitHub Enterprise base URL",
                "default": "",
            },
            "fetch_logs_for_job_id": {
                "type": "integer",
                "description": "If set, also fetch raw logs for this job ID",
                "default": 0,
            },
        },
        "required": ["owner", "repo", "run_id"],
    }
    outputs = {
        "jobs": "List of jobs with name, status, conclusion, failed_steps, and html_url",
        "logs": "Raw log text for the requested job (if fetch_logs_for_job_id provided)",
    }

    def is_available(self, sources: dict) -> bool:
        gh = sources.get("github", {})
        return bool(gh.get("owner") and gh.get("repo"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        gh = sources.get("github", {})
        return {
            "owner": gh.get("owner", ""),
            "repo": gh.get("repo", ""),
            "run_id": 0,
            "github_token": gh.get("auth_token") or gh.get("github_token", ""),
            "github_url": gh.get("url", ""),
            "fetch_logs_for_job_id": 0,
        }

    def run(
        self,
        owner: str,
        repo: str,
        run_id: int,
        github_token: str = "",
        github_url: str = "",
        fetch_logs_for_job_id: int = 0,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not owner or not repo:
            return {"source": "github", "available": False, "error": "owner and repo are required."}
        if not run_id:
            return {"source": "github", "available": False, "error": "run_id is required."}

        from app.services.github.client import _BASE_URL

        base_url = github_url.rstrip("/") + "/api/v3" if github_url else _BASE_URL
        client = make_github_client(token=github_token or None, base_url=base_url)

        with client:
            jobs_result = client.list_jobs(owner=owner, repo=repo, run_id=run_id)
            logs: str = ""
            if fetch_logs_for_job_id and jobs_result.get("success"):
                logs_result = client.get_job_logs(
                    owner=owner, repo=repo, job_id=fetch_logs_for_job_id
                )
                logs = (
                    logs_result.get("logs", "")
                    if logs_result.get("success")
                    else logs_result.get("error", "")
                )

        if not jobs_result.get("success"):
            return {
                "source": "github",
                "available": False,
                "error": jobs_result.get("error", "unknown"),
            }

        out: dict[str, Any] = {
            "source": "github",
            "available": True,
            "run_id": run_id,
            "jobs": jobs_result.get("jobs", []),
            "total_count": jobs_result.get("total_count", 0),
            "failed_jobs": [
                j["name"] for j in jobs_result.get("jobs", []) if j.get("conclusion") == "failure"
            ],
        }
        if logs:
            out["logs"] = logs
        return out


github_actions_jobs = GitHubActionsJobsTool()
