"""GitHub REST API v3 client — focused on Actions/Workflows for incident correlation.

This client is intentionally scoped to the data most useful during an investigation:
workflow runs, failed jobs, and step logs. It uses the REST API directly rather
than the MCP server, making it self-contained and network-call-predictable.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.probes import ProbeResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.github.com"
_DEFAULT_TIMEOUT = 20


class GitHubClient:
    """Synchronous GitHub REST API v3 client."""

    def __init__(self, token: str, base_url: str = _BASE_URL) -> None:
        self._token = token.strip()
        self._base_url = base_url.rstrip("/")
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers: dict[str, str] = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return True  # token is optional for public repos

    def probe_access(self) -> ProbeResult:
        try:
            with self:
                resp = self._get_client().get("/rate_limit")
                resp.raise_for_status()
                data = resp.json()
                remaining = data.get("rate", {}).get("remaining", 0)
                return ProbeResult.passed(f"GitHub API reachable; {remaining} requests remaining.")
        except Exception as exc:
            return ProbeResult.failed(f"GitHub probe failed: {exc}")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: str = "",
        branch: str = "",
        status: str = "",
        per_page: int = 20,
        event: str = "",
    ) -> dict[str, Any]:
        """List workflow runs for a repo, optionally scoped to a specific workflow, branch, or status."""
        path = f"/repos/{owner}/{repo}/actions/runs"
        if workflow_id:
            path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"

        params: dict[str, Any] = {"per_page": min(per_page, 100)}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        if event:
            params["event"] = event

        try:
            resp = self._get_client().get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
            runs = [
                {
                    "id": r.get("id"),
                    "name": r.get("name", ""),
                    "workflow_id": r.get("workflow_id"),
                    "head_branch": r.get("head_branch", ""),
                    "head_sha": r.get("head_sha", "")[:12],
                    "status": r.get("status", ""),
                    "conclusion": r.get("conclusion", ""),
                    "event": r.get("event", ""),
                    "created_at": r.get("created_at", ""),
                    "updated_at": r.get("updated_at", ""),
                    "html_url": r.get("html_url", ""),
                    "actor": r.get("actor", {}).get("login", ""),
                }
                for r in data.get("workflow_runs", [])
            ]
            return {
                "success": True,
                "runs": runs,
                "total_count": data.get("total_count", len(runs)),
            }
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[github] list_workflow_runs error: %s", error)
            return {"success": False, "error": error, "runs": []}
        except Exception as exc:
            logger.warning("[github] list_workflow_runs exception: %s", exc)
            return {"success": False, "error": str(exc), "runs": []}

    def list_jobs(self, owner: str, repo: str, run_id: int) -> dict[str, Any]:
        """List jobs for a specific workflow run — includes per-step pass/fail."""
        try:
            resp = self._get_client().get(
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
                params={"per_page": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            jobs = [
                {
                    "id": j.get("id"),
                    "name": j.get("name", ""),
                    "status": j.get("status", ""),
                    "conclusion": j.get("conclusion", ""),
                    "started_at": j.get("started_at", ""),
                    "completed_at": j.get("completed_at", ""),
                    "html_url": j.get("html_url", ""),
                    "steps": [
                        {
                            "name": s.get("name", ""),
                            "status": s.get("status", ""),
                            "conclusion": s.get("conclusion", ""),
                            "number": s.get("number"),
                        }
                        for s in j.get("steps", [])
                        if s.get("conclusion") in ("failure", "cancelled", None)
                        or s.get("status") != "completed"
                    ],
                    "failed_steps": [
                        s.get("name", "")
                        for s in j.get("steps", [])
                        if s.get("conclusion") == "failure"
                    ],
                }
                for j in data.get("jobs", [])
            ]
            return {
                "success": True,
                "jobs": jobs,
                "total_count": data.get("total_count", len(jobs)),
            }
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}"
            logger.warning("[github] list_jobs error: %s", error)
            return {"success": False, "error": error, "jobs": []}
        except Exception as exc:
            logger.warning("[github] list_jobs exception: %s", exc)
            return {"success": False, "error": str(exc), "jobs": []}

    def get_job_logs(
        self, owner: str, repo: str, job_id: int, max_bytes: int = 8000
    ) -> dict[str, Any]:
        """Fetch raw logs for a specific job — truncated to stay within context limits."""
        try:
            resp = self._get_client().get(
                f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
                follow_redirects=True,
            )
            if resp.status_code == 404:
                return {
                    "success": False,
                    "error": "Logs not available (job may still be running or logs expired)",
                }
            resp.raise_for_status()
            log_text = resp.text
            if len(log_text) > max_bytes:
                log_text = "...[truncated]...\n" + log_text[-max_bytes:]
            return {"success": True, "job_id": job_id, "logs": log_text}
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}"
            logger.warning("[github] get_job_logs error: %s", error)
            return {"success": False, "error": error}
        except Exception as exc:
            logger.warning("[github] get_job_logs exception: %s", exc)
            return {"success": False, "error": str(exc)}

    def list_workflows(self, owner: str, repo: str) -> dict[str, Any]:
        """List all workflows defined in a repo."""
        try:
            resp = self._get_client().get(f"/repos/{owner}/{repo}/actions/workflows")
            resp.raise_for_status()
            workflows = [
                {
                    "id": w.get("id"),
                    "name": w.get("name", ""),
                    "path": w.get("path", ""),
                    "state": w.get("state", ""),
                    "html_url": w.get("html_url", ""),
                }
                for w in resp.json().get("workflows", [])
            ]
            return {"success": True, "workflows": workflows}
        except Exception as exc:
            logger.warning("[github] list_workflows exception: %s", exc)
            return {"success": False, "error": str(exc), "workflows": []}


def make_github_client(token: str | None = None, base_url: str = _BASE_URL) -> GitHubClient:
    return GitHubClient(token=token or "", base_url=base_url)
