"""BambooHR REST API client.

Authentication uses HTTP Basic Auth with an API key:
    username = api_key, password = "x"
    Base URL: https://{subdomain}.bamboohr.com/api/gateway.php/{subdomain}/v1

Reference: https://documentation.bamboohr.com/reference
"""

from __future__ import annotations

from typing import Any

import requests


class BambooHRClient:
    """HTTP client for the BambooHR API."""

    def __init__(self, subdomain: str, api_key: str) -> None:
        self._base = f"https://api.bamboohr.com/api/gateway.php/{subdomain}/v1"
        self._session = requests.Session()
        self._session.auth = (api_key, "x")
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Employee lookup
    # ------------------------------------------------------------------

    def get_employee(
        self,
        employee_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retrieve a single employee record by ID."""
        default_fields = [
            "id", "firstName", "lastName", "displayName", "jobTitle",
            "department", "location", "workEmail", "workPhone",
            "supervisorId", "supervisorEId", "supervisor",
            "hireDate", "employmentHistoryStatus", "status",
            "division", "costCenter",
        ]
        requested_fields = fields or default_fields
        params = {"fields": ",".join(requested_fields)}
        resp = self._session.get(
            f"{self._base}/employees/{employee_id}", params=params, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def search_employees(self, search_term: str) -> list[dict[str, Any]]:
        """Search the employee directory by name or email."""
        resp = self._session.get(
            f"{self._base}/employees/directory",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        employees: list[dict[str, Any]] = data.get("employees", [])

        if not search_term:
            return employees

        term_lower = search_term.lower()
        return [
            emp
            for emp in employees
            if term_lower in (emp.get("displayName") or "").lower()
            or term_lower in (emp.get("workEmail") or "").lower()
            or term_lower in (emp.get("lastName") or "").lower()
        ]

    def get_directory(self) -> list[dict[str, Any]]:
        """Return all active employees from the company directory."""
        resp = self._session.get(f"{self._base}/employees/directory", timeout=15)
        resp.raise_for_status()
        return resp.json().get("employees", [])

    def get_reporting_chain(self, employee_id: str, max_depth: int = 6) -> list[dict[str, Any]]:
        """Walk the supervisor chain upward from an employee.

        Returns a list of employee records ordered from the employee upward
        to the root (CEO), stopping at ``max_depth`` levels.
        """
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current_id: str | None = str(employee_id)

        for _ in range(max_depth):
            if not current_id or current_id in seen:
                break
            seen.add(current_id)
            try:
                emp = self.get_employee(current_id)
            except requests.HTTPError:
                break
            chain.append(emp)
            current_id = emp.get("supervisorId") or emp.get("supervisorEId")

        return chain

    def get_direct_reports(self, employee_id: str) -> list[dict[str, Any]]:
        """Return all employees who directly report to a given employee."""
        directory = self.get_directory()
        str_id = str(employee_id)
        return [
            emp
            for emp in directory
            if str(emp.get("supervisorEId", "")) == str_id
            or str(emp.get("supervisorId", "")) == str_id
        ]

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> BambooHRClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def make_bamboohr_client(
    subdomain: str,
    api_key: str,
) -> BambooHRClient | None:
    """Create a BambooHRClient, or None if credentials are missing."""
    if not subdomain or not api_key:
        return None
    return BambooHRClient(subdomain=subdomain, api_key=api_key)
