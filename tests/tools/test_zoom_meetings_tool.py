"""Tests for the Zoom meeting records tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.registry import get_registered_tool_map
from app.tools.ZoomMeetingsTool import ZoomMeetingsTool, search_zoom_meetings

MEETING = {
    "id": "12345678",
    "uuid": "abc/def==",
    "topic": "1:1 Alice and Bob",
    "host_id": "host-001",
    "host_email": "bob@corp.com",
    "type": 2,
    "start_time": "2024-03-15T10:00:00Z",
    "duration_minutes": 30,
    "timezone": "America/New_York",
    "join_url": "https://zoom.us/j/12345678",
}

DETAIL = {**MEETING, "agenda": "", "recording_enabled": False, "waiting_room": False, "status": "ended"}

PARTICIPANT = {
    "id": "part-1",
    "user_id": "okta-001",
    "name": "Alice Johnson",
    "email": "alice@corp.com",
    "join_time": "2024-03-15T10:01:00Z",
    "leave_time": "2024-03-15T10:30:00Z",
    "duration_seconds": 1740,
    "ip_address": "10.0.0.1",
    "device": "Mac",
}


class TestZoomToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "search_zoom_meetings" in tool_map

    def test_source_is_zoom(self) -> None:
        assert search_zoom_meetings.source == "zoom"

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any("participant" in uc.lower() or "meeting" in uc.lower() for uc in search_zoom_meetings.use_cases)


class TestZoomToolAvailability:
    def test_available_with_access_token(self) -> None:
        tool = ZoomMeetingsTool()
        assert tool.is_available({"zoom": {"access_token": "tok"}})

    def test_available_with_server_to_server_creds(self) -> None:
        tool = ZoomMeetingsTool()
        assert tool.is_available({"zoom": {"account_id": "a", "client_id": "c", "client_secret": "s"}})

    def test_not_available_empty(self) -> None:
        tool = ZoomMeetingsTool()
        assert not tool.is_available({})

    def test_not_available_partial_creds(self) -> None:
        tool = ZoomMeetingsTool()
        assert not tool.is_available({"zoom": {"account_id": "only-account"}})


class TestZoomToolRun:
    def test_error_without_target(self) -> None:
        tool = ZoomMeetingsTool()
        result = tool.run(access_token="tok")
        assert result["available"] is False
        assert "user_id" in result["error"]

    def test_error_without_credentials(self) -> None:
        tool = ZoomMeetingsTool()
        result = tool.run(user_id="alice@corp.com")
        assert result["available"] is False
        assert "credentials" in result["error"].lower()

    def test_list_user_meetings(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_user_meetings.return_value = {
            "meetings": [MEETING],
            "user_id": "alice@corp.com",
            "total_records": 1,
        }

        with patch("app.tools.ZoomMeetingsTool.make_zoom_client", return_value=mock_client):
            tool = ZoomMeetingsTool()
            result = tool.run(
                access_token="tok",
                user_id="alice@corp.com",
                from_date="2024-03-01",
                to_date="2024-03-31",
            )

        assert result["available"] is True
        assert result["user_id"] == "alice@corp.com"
        assert result["returned_count"] == 1
        assert result["meetings"][0]["topic"] == "1:1 Alice and Bob"

    def test_get_meeting_by_id(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_meeting.return_value = DETAIL
        mock_client.get_meeting_participants.return_value = {
            "meeting_id": "12345678",
            "participants": [PARTICIPANT],
            "total_records": 1,
        }

        with patch("app.tools.ZoomMeetingsTool.make_zoom_client", return_value=mock_client):
            tool = ZoomMeetingsTool()
            result = tool.run(access_token="tok", meeting_id="12345678")

        assert result["available"] is True
        assert result["meeting_detail"]["topic"] == "1:1 Alice and Bob"
        assert len(result["participants"]) == 1
        assert result["participants"][0]["email"] == "alice@corp.com"
        assert result["participant_count"] == 1

    def test_include_participants_for_user_meetings(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_user_meetings.return_value = {
            "meetings": [dict(MEETING)],
            "user_id": "alice@corp.com",
            "total_records": 1,
        }
        mock_client.get_meeting_participants.return_value = {
            "meeting_id": "12345678",
            "participants": [PARTICIPANT],
            "total_records": 1,
        }

        with patch("app.tools.ZoomMeetingsTool.make_zoom_client", return_value=mock_client):
            tool = ZoomMeetingsTool()
            result = tool.run(
                access_token="tok",
                user_id="alice@corp.com",
                include_participants=True,
            )

        assert result["available"] is True
        assert result["meetings"][0]["participants"][0]["name"] == "Alice Johnson"

    def test_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_user_meetings.side_effect = Exception("404 Not Found")

        with patch("app.tools.ZoomMeetingsTool.make_zoom_client", return_value=mock_client):
            tool = ZoomMeetingsTool()
            result = tool.run(access_token="tok", user_id="alice@corp.com")

        assert result["available"] is False
        assert "404 Not Found" in result["error"]

    def test_empty_meeting_list(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_user_meetings.return_value = {
            "meetings": [],
            "user_id": "alice@corp.com",
            "total_records": 0,
        }

        with patch("app.tools.ZoomMeetingsTool.make_zoom_client", return_value=mock_client):
            tool = ZoomMeetingsTool()
            result = tool.run(access_token="tok", user_id="alice@corp.com")

        assert result["available"] is True
        assert result["returned_count"] == 0
        assert result["meetings"] == []
