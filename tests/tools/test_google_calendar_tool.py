"""Tests for the Google Calendar meeting history tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.GoogleCalendarTool import GoogleCalendarTool, search_google_calendar
from app.tools.registry import get_registered_tool_map

SAMPLE_EVENT = {
    "id": "event-abc",
    "summary": "1:1 Alice / Bob",
    "description": "Weekly sync",
    "start": "2024-03-15T10:00:00Z",
    "end": "2024-03-15T10:30:00Z",
    "organizer_email": "bob@corp.com",
    "organizer_name": "Bob Manager",
    "attendees": [
        {"email": "bob@corp.com", "display_name": "Bob Manager", "response": "accepted", "optional": False},
        {"email": "alice@corp.com", "display_name": "Alice", "response": "accepted", "optional": False},
    ],
    "location": "",
    "status": "confirmed",
    "html_link": "https://calendar.google.com/event?id=event-abc",
    "recurring_event_id": "recurring-xyz",
    "created": "2024-01-01T00:00:00Z",
    "updated": "2024-03-14T09:00:00Z",
}


class TestCalendarToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "search_google_calendar" in tool_map

    def test_source_is_google_calendar(self) -> None:
        assert search_google_calendar.source == "google_calendar"

    def test_input_schema_required(self) -> None:
        assert "access_token" in search_google_calendar.input_schema.get("required", [])

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any("meeting" in uc.lower() for uc in search_google_calendar.use_cases)


class TestCalendarToolAvailability:
    def test_available_with_token(self) -> None:
        tool = GoogleCalendarTool()
        assert tool.is_available({"google_calendar": {"access_token": "tok"}})

    def test_available_via_google_key(self) -> None:
        tool = GoogleCalendarTool()
        assert tool.is_available({"google": {"access_token": "tok"}})

    def test_not_available_empty(self) -> None:
        tool = GoogleCalendarTool()
        assert not tool.is_available({})

    def test_extract_params(self) -> None:
        tool = GoogleCalendarTool()
        params = tool.extract_params({"google_calendar": {"access_token": "tok"}})
        assert params["access_token"] == "tok"
        assert params["calendar_id"] == "primary"


class TestCalendarToolRun:
    def test_error_without_token(self) -> None:
        tool = GoogleCalendarTool()
        result = tool.run(access_token="")
        assert result["available"] is False
        assert "access_token" in result["error"]

    def test_list_events(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_events.return_value = {
            "events": [SAMPLE_EVENT],
            "calendar_id": "primary",
            "next_page_token": None,
        }

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(
                access_token="tok",
                time_min="2024-03-01T00:00:00Z",
                time_max="2024-03-31T23:59:59Z",
            )

        assert result["available"] is True
        assert result["calendar_id"] == "primary"
        assert len(result["events"]) == 1
        assert result["events"][0]["summary"] == "1:1 Alice / Bob"
        assert result["returned_count"] == 1

    def test_filter_by_attendee(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.find_meetings_between.return_value = [SAMPLE_EVENT]

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(
                access_token="tok",
                attendee_email="alice@corp.com",
                time_min="2024-03-01T00:00:00Z",
            )

        assert result["available"] is True
        assert result["attendee_filter"] == "alice@corp.com"
        assert result["returned_count"] == 1
        mock_client.find_meetings_between.assert_called_once_with(
            calendar_id="primary",
            attendee_email="alice@corp.com",
            time_min="2024-03-01T00:00:00Z",
            time_max=None,
            max_results=50,
        )

    def test_attendee_filter_takes_priority_over_query(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.find_meetings_between.return_value = []

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(
                access_token="tok",
                attendee_email="alice@corp.com",
                query="1:1",
            )

        assert result["available"] is True
        mock_client.find_meetings_between.assert_called_once()
        mock_client.list_events.assert_not_called()

    def test_keyword_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_events.return_value = {
            "events": [],
            "calendar_id": "primary",
            "next_page_token": None,
        }

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(access_token="tok", query="confidential meeting")

        assert result["available"] is True
        mock_client.list_events.assert_called_once_with(
            calendar_id="primary",
            time_min=None,
            time_max=None,
            query="confidential meeting",
            max_results=50,
        )

    def test_empty_results(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_events.return_value = {
            "events": [],
            "calendar_id": "hr-calendar",
            "next_page_token": None,
        }

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(access_token="tok", calendar_id="hr-calendar")

        assert result["available"] is True
        assert result["events"] == []
        assert result["returned_count"] == 0

    def test_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_events.side_effect = Exception("403 Forbidden")

        with patch("app.tools.GoogleCalendarTool.make_google_calendar_client", return_value=mock_client):
            tool = GoogleCalendarTool()
            result = tool.run(access_token="tok")

        assert result["available"] is False
        assert "403 Forbidden" in result["error"]
