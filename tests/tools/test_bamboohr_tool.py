"""Tests for the BambooHR employee directory tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.BambooHRTool import BambooHREmployeeLookupTool, lookup_bamboohr_employee
from app.tools.registry import get_registered_tool_map


class TestBambooHRToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "lookup_bamboohr_employee" in tool_map

    def test_source_is_bamboohr(self) -> None:
        assert lookup_bamboohr_employee.source == "bamboohr"

    def test_input_schema_required_fields(self) -> None:
        schema = lookup_bamboohr_employee.input_schema
        assert "subdomain" in schema.get("required", [])
        assert "api_key" in schema.get("required", [])

    def test_use_cases_are_hr_focused(self) -> None:
        assert any("supervisor" in uc.lower() or "reporting" in uc.lower()
                   for uc in lookup_bamboohr_employee.use_cases)


class TestBambooHRToolAvailability:
    def test_available_when_configured(self) -> None:
        tool = BambooHREmployeeLookupTool()
        assert tool.is_available({"bamboohr": {"subdomain": "acme", "api_key": "bhr_key"}})

    def test_not_available_missing_api_key(self) -> None:
        tool = BambooHREmployeeLookupTool()
        assert not tool.is_available({"bamboohr": {"subdomain": "acme"}})

    def test_not_available_empty(self) -> None:
        tool = BambooHREmployeeLookupTool()
        assert not tool.is_available({})


class TestBambooHRToolRun:
    def test_error_without_credentials(self) -> None:
        tool = BambooHREmployeeLookupTool()
        result = tool.run(subdomain="", api_key="", employee_id="42")
        assert result["available"] is False

    def test_error_without_id_or_search(self) -> None:
        tool = BambooHREmployeeLookupTool()
        result = tool.run(subdomain="acme", api_key="key")
        assert result["available"] is False
        assert "search_term" in result["error"]

    def test_employee_lookup_by_id(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_employee.return_value = {
            "id": "42",
            "displayName": "Alice Johnson",
            "jobTitle": "Software Engineer",
            "department": "Engineering",
            "workEmail": "alice@corp.com",
            "supervisorId": "10",
            "status": "Active",
        }
        mock_client.get_reporting_chain.return_value = [
            {"id": "42", "displayName": "Alice Johnson"},
            {"id": "10", "displayName": "Bob Smith", "jobTitle": "Engineering Manager"},
        ]

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(
                subdomain="acme",
                api_key="key",
                employee_id="42",
                include_reporting_chain=True,
            )

        assert result["available"] is True
        assert result["employee"]["displayName"] == "Alice Johnson"
        # reporting_chain excludes self (first element)
        assert len(result["reporting_chain"]) == 1
        assert result["reporting_chain"][0]["displayName"] == "Bob Smith"

    def test_search_by_name_multiple_results(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_employees.return_value = [
            {"id": "1", "displayName": "Alice Johnson"},
            {"id": "2", "displayName": "Alice Williams"},
        ]

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(subdomain="acme", api_key="key", search_term="Alice")

        assert result["available"] is True
        assert len(result["search_results"]) == 2
        assert "Refine search" in result["message"]

    def test_search_by_name_single_result_fetches_profile(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_employees.return_value = [
            {"id": "5", "displayName": "Charlie Brown"}
        ]
        mock_client.get_employee.return_value = {
            "id": "5",
            "displayName": "Charlie Brown",
            "jobTitle": "HR Manager",
            "department": "Human Resources",
        }
        mock_client.get_reporting_chain.return_value = [
            {"id": "5", "displayName": "Charlie Brown"},
        ]

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(subdomain="acme", api_key="key", search_term="Charlie")

        assert result["available"] is True
        assert result["employee"]["jobTitle"] == "HR Manager"

    def test_search_no_match(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_employees.return_value = []

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(subdomain="acme", api_key="key", search_term="NoOne")

        assert result["available"] is True
        assert result["search_results"] == []
        assert "No employees found" in result["message"]

    def test_include_direct_reports(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_employee.return_value = {"id": "10", "displayName": "Manager Bob"}
        mock_client.get_reporting_chain.return_value = [{"id": "10"}]
        mock_client.get_direct_reports.return_value = [
            {"id": "11", "displayName": "Report 1"},
            {"id": "12", "displayName": "Report 2"},
        ]

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(
                subdomain="acme",
                api_key="key",
                employee_id="10",
                include_direct_reports=True,
            )

        assert result["available"] is True
        assert len(result["direct_reports"]) == 2

    def test_handles_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_employee.side_effect = Exception("401 Unauthorized")

        with patch("app.tools.BambooHRTool.make_bamboohr_client", return_value=mock_client):
            tool = BambooHREmployeeLookupTool()
            result = tool.run(subdomain="acme", api_key="key", employee_id="99")

        assert result["available"] is False
        assert "401 Unauthorized" in result["error"]
