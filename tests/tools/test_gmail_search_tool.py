"""Tests for the Gmail email search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tools.GmailSearchTool import GmailSearchTool, search_gmail_emails
from app.tools.registry import get_registered_tool_map


class TestGmailSearchToolMetadata:
    def test_tool_is_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "search_gmail_emails" in tool_map

    def test_tool_source_is_email(self) -> None:
        assert search_gmail_emails.source == "email"

    def test_tool_name(self) -> None:
        assert search_gmail_emails.name == "search_gmail_emails"

    def test_input_schema_has_required_query(self) -> None:
        schema = search_gmail_emails.input_schema
        assert "query" in schema.get("required", [])

    def test_input_schema_has_auth_fields(self) -> None:
        props = search_gmail_emails.input_schema.get("properties", {})
        assert "access_token" in props
        assert "service_account_json" in props
        assert "delegated_email" in props


class TestGmailSearchToolAvailability:
    def test_available_with_access_token(self) -> None:
        tool = GmailSearchTool()
        assert tool.is_available({"email": {"access_token": "ya29.abc"}})

    def test_available_with_service_account(self) -> None:
        tool = GmailSearchTool()
        sources = {
            "gmail": {
                "service_account_json": '{"type":"service_account"}',
                "delegated_email": "user@corp.com",
            }
        }
        assert tool.is_available(sources)

    def test_not_available_when_no_credentials(self) -> None:
        tool = GmailSearchTool()
        assert not tool.is_available({})
        assert not tool.is_available({"email": {}})

    def test_not_available_with_partial_service_account(self) -> None:
        tool = GmailSearchTool()
        # service_account_json present but no delegated_email
        assert not tool.is_available({"gmail": {"service_account_json": "{}"}})


class TestGmailSearchToolRun:
    def test_returns_error_when_no_query(self) -> None:
        tool = GmailSearchTool()
        result = tool.run(query="", access_token="ya29.abc")
        assert result["available"] is False
        assert "query" in result["error"]

    def test_returns_error_when_no_credentials(self) -> None:
        tool = GmailSearchTool()
        result = tool.run(query="from:alice@corp.com")
        assert result["available"] is False
        assert "credentials" in result["error"].lower()

    def test_successful_search_with_mock_client(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_messages.return_value = {
            "messages": [
                {
                    "id": "msg1",
                    "thread_id": "thread1",
                    "subject": "Re: HR complaint follow-up",
                    "from": "manager@corp.com",
                    "to": "hr@corp.com",
                    "received_at": "2024-03-15T10:30:00Z",
                    "snippet": "I wanted to follow up on the complaint filed last week...",
                }
            ],
            "total_estimate": 5,
            "query": "from:manager@corp.com subject:complaint",
        }

        with patch("app.tools.GmailSearchTool.make_gmail_client", return_value=mock_client):
            tool = GmailSearchTool()
            result = tool.run(
                query="from:manager@corp.com subject:complaint",
                access_token="ya29.test",
            )

        assert result["available"] is True
        assert result["returned_count"] == 1
        assert len(result["messages"]) == 1
        assert result["messages"][0]["subject"] == "Re: HR complaint follow-up"
        assert result["total_estimate"] == 5

    def test_handles_client_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_messages.side_effect = ConnectionError("network error")

        with patch("app.tools.GmailSearchTool.make_gmail_client", return_value=mock_client):
            tool = GmailSearchTool()
            result = tool.run(query="subject:test", access_token="ya29.test")

        assert result["available"] is False
        assert "network error" in result["error"]

    def test_returns_mailbox_in_result(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_messages.return_value = {
            "messages": [],
            "total_estimate": 0,
            "query": "subject:test",
        }

        with patch("app.tools.GmailSearchTool.make_gmail_client", return_value=mock_client):
            tool = GmailSearchTool()
            result = tool.run(
                query="subject:test",
                access_token="ya29.test",
                delegated_email="alice@corp.com",
            )

        assert result["mailbox"] == "alice@corp.com"


class TestGmailClientParsing:
    def test_parse_message_extracts_headers(self) -> None:
        from app.services.gmail.client import GmailClient

        raw = {
            "id": "abc123",
            "threadId": "thread_abc",
            "internalDate": "1710497400000",  # 2024-03-15T11:30:00Z approx
            "snippet": "Please review the attached &amp; sign",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Review request"},
                    {"name": "From", "value": "alice@corp.com"},
                    {"name": "To", "value": "bob@corp.com"},
                    {"name": "Date", "value": "Fri, 15 Mar 2024 11:30:00 +0000"},
                ]
            },
        }
        parsed = GmailClient._parse_message(raw)

        assert parsed["id"] == "abc123"
        assert parsed["subject"] == "Review request"
        assert parsed["from"] == "alice@corp.com"
        assert parsed["to"] == "bob@corp.com"
        assert parsed["snippet"] == "Please review the attached & sign"
        assert parsed["received_at"] is not None
        assert parsed["label_ids"] == ["INBOX", "UNREAD"]

    def test_parse_message_handles_missing_headers(self) -> None:
        from app.services.gmail.client import GmailClient

        raw = {
            "id": "xyz",
            "threadId": "t1",
            "snippet": "",
            "payload": {"headers": []},
        }
        parsed = GmailClient._parse_message(raw)

        assert parsed["subject"] == "(no subject)"
        assert parsed["from"] == ""
        assert parsed["received_at"] is None
