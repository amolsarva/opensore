from __future__ import annotations

from app.agent.prompt import build_system_prompt, format_alert_context


def test_build_system_prompt_returns_non_empty_string() -> None:
    prompt = build_system_prompt({"alert_source": "jira"})
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_alert_context_returns_non_empty_string() -> None:
    context = format_alert_context(
        {
            "alert_name": "Policy violation",
            "alert_source": "jira",
            "pipeline_name": "hr",
            "severity": "high",
            "resolved_integrations": {
                "jira": {"base_url": "https://example.atlassian.net"},
            },
        }
    )
    assert isinstance(context, str)
