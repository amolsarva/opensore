"""Unit tests for GitHub Actions tools — mocked HTTP, no live credentials."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.github.client import GitHubClient, make_github_client
from app.tools.GitHubActionsJobsTool import GitHubActionsJobsTool
from app.tools.GitHubActionsRunsTool import GitHubActionsRunsTool

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def test_make_github_client_always_returns_client() -> None:
    client = make_github_client()
    assert isinstance(client, GitHubClient)
    assert client.is_configured  # always True


def test_make_github_client_with_token() -> None:
    client = make_github_client(token="ghp_abc123")
    assert isinstance(client, GitHubClient)


# ---------------------------------------------------------------------------
# GitHubActionsRunsTool
# ---------------------------------------------------------------------------


def test_runs_tool_metadata() -> None:
    tool = GitHubActionsRunsTool()
    assert tool.name == "github_actions_runs"
    assert tool.source == "github_actions"
    assert "owner" in tool.input_schema["properties"]
    assert "repo" in tool.input_schema["properties"]
    assert "status" in tool.input_schema["properties"]


def test_runs_tool_requires_owner_and_repo() -> None:
    tool = GitHubActionsRunsTool()
    result = tool.run(owner="", repo="myrepo")
    assert result["available"] is False

    result = tool.run(owner="myorg", repo="")
    assert result["available"] is False


def test_runs_tool_available_when_owner_repo_present() -> None:
    tool = GitHubActionsRunsTool()
    assert tool.is_available({"github": {"owner": "myorg", "repo": "myrepo"}})
    assert not tool.is_available({"github": {}})
    assert not tool.is_available({})


def test_runs_tool_success() -> None:
    tool = GitHubActionsRunsTool()
    mock_result = {
        "success": True,
        "runs": [
            {
                "id": 12345,
                "name": "Deploy to Production",
                "workflow_id": 678,
                "head_branch": "main",
                "head_sha": "abc123def456",
                "status": "completed",
                "conclusion": "failure",
                "event": "push",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:15:00Z",
                "html_url": "https://github.com/org/repo/actions/runs/12345",
                "actor": "alice",
            }
        ],
        "total_count": 1,
    }
    with patch("app.tools.GitHubActionsRunsTool.make_github_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_workflow_runs.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(owner="myorg", repo="myrepo", status="failure", per_page=10)

    assert result["available"] is True
    assert len(result["runs"]) == 1
    assert result["runs"][0]["conclusion"] == "failure"
    assert result["runs"][0]["actor"] == "alice"


def test_runs_tool_failure_propagated() -> None:
    tool = GitHubActionsRunsTool()
    mock_result = {"success": False, "error": "HTTP 404: Not Found", "runs": []}
    with patch("app.tools.GitHubActionsRunsTool.make_github_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_workflow_runs.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(owner="org", repo="repo")

    assert result["available"] is False
    assert "404" in result["error"]


# ---------------------------------------------------------------------------
# GitHubActionsJobsTool
# ---------------------------------------------------------------------------


def test_jobs_tool_metadata() -> None:
    tool = GitHubActionsJobsTool()
    assert tool.name == "github_actions_jobs"
    assert tool.source == "github_actions"
    assert "run_id" in tool.input_schema["properties"]
    assert "fetch_logs_for_job_id" in tool.input_schema["properties"]


def test_jobs_tool_requires_run_id() -> None:
    tool = GitHubActionsJobsTool()
    result = tool.run(owner="org", repo="repo", run_id=0)
    assert result["available"] is False
    assert "run_id" in result["error"]


def test_jobs_tool_success_with_failed_jobs() -> None:
    tool = GitHubActionsJobsTool()
    mock_jobs = {
        "success": True,
        "total_count": 2,
        "jobs": [
            {
                "id": 1001,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": "2024-01-15T10:05:00Z",
                "html_url": "https://github.com/org/repo/actions/jobs/1001",
                "steps": [],
                "failed_steps": [],
            },
            {
                "id": 1002,
                "name": "deploy",
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2024-01-15T10:05:00Z",
                "completed_at": "2024-01-15T10:10:00Z",
                "html_url": "https://github.com/org/repo/actions/jobs/1002",
                "steps": [
                    {
                        "name": "kubectl apply",
                        "status": "completed",
                        "conclusion": "failure",
                        "number": 3,
                    }
                ],
                "failed_steps": ["kubectl apply"],
            },
        ],
    }
    with patch("app.tools.GitHubActionsJobsTool.make_github_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_jobs.return_value = mock_jobs
        mock_factory.return_value = mock_client

        result = tool.run(owner="org", repo="repo", run_id=12345)

    assert result["available"] is True
    assert result["total_count"] == 2
    assert "deploy" in result["failed_jobs"]
    assert "build" not in result["failed_jobs"]


def test_jobs_tool_fetches_logs_when_requested() -> None:
    tool = GitHubActionsJobsTool()
    mock_jobs = {"success": True, "total_count": 1, "jobs": []}
    mock_logs = {
        "success": True,
        "job_id": 999,
        "logs": "Error: kubectl apply failed\nTimeout exceeded",
    }
    with patch("app.tools.GitHubActionsJobsTool.make_github_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_jobs.return_value = mock_jobs
        mock_client.get_job_logs.return_value = mock_logs
        mock_factory.return_value = mock_client

        result = tool.run(owner="org", repo="repo", run_id=12345, fetch_logs_for_job_id=999)

    assert result["available"] is True
    assert "kubectl apply failed" in result.get("logs", "")
