from __future__ import annotations

from app.tools.registry import get_registered_tool_map


def test_jira_tool_family_uses_correct_source_and_required_fields() -> None:
    tool_map = get_registered_tool_map("investigation")

    search_tool = tool_map["jira_search_issues"]
    detail_tool = tool_map["jira_issue_detail"]

    assert search_tool.source == "jira"
    assert {"base_url", "email", "api_token"} <= set(
        search_tool.public_input_schema.get("required", [])
    )

    assert detail_tool.source == "jira"
    assert "issue_key" in set(detail_tool.public_input_schema.get("required", []))


def test_slack_tool_requires_channel_and_token_filters() -> None:
    tool_map = get_registered_tool_map("investigation")
    slack_tool = tool_map["slack_channel_history"]
    required = set(slack_tool.public_input_schema.get("required", []))
    assert {"bot_token", "channel_id"} <= required


def test_github_search_tool_requires_owner_repo_query() -> None:
    tool_map = get_registered_tool_map("investigation")
    github = tool_map["search_github_code"]
    bitbucket = tool_map["get_bitbucket_file_contents"]

    github_props = set(github.public_input_schema.get("properties", {}).keys())
    bitbucket_props = set(bitbucket.public_input_schema.get("properties", {}).keys())

    assert {"owner", "repo", "query"} <= github_props
    assert {"repo_slug", "path"} <= bitbucket_props
