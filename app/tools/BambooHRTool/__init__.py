"""BambooHR employee directory and org chart tools for HR investigations."""

from __future__ import annotations

from typing import Any

from app.services.bamboohr import make_bamboohr_client
from app.tools.base import BaseTool


class BambooHREmployeeLookupTool(BaseTool):
    """Look up an employee profile, reporting chain, and direct reports from BambooHR.

    Supports search by name/email and retrieval of the full reporting hierarchy,
    enabling investigators to understand the organizational relationships between
    parties involved in a complaint.
    """

    name = "lookup_bamboohr_employee"
    source = "bamboohr"
    description = (
        "Look up employee profiles, org chart position, and reporting relationships in BambooHR. "
        "Returns job title, department, location, supervisor chain, and direct reports. "
        "Use to understand the organizational context of parties in an HR investigation."
    )
    use_cases = [
        "Finding an employee's current job title, department, and location",
        "Identifying who a complainant or accused person reports to",
        "Mapping the full management chain between two employees",
        "Listing all direct reports of a manager during an investigation of leadership conduct",
        "Verifying employment status, hire date, and division of key parties",
        "Identifying whether two parties share a reporting chain that creates a power dynamic",
    ]
    requires = ["subdomain", "api_key"]
    input_schema = {
        "type": "object",
        "properties": {
            "subdomain": {
                "type": "string",
                "description": "BambooHR company subdomain (e.g. 'acmecorp' for acmecorp.bamboohr.com)",
            },
            "api_key": {
                "type": "string",
                "description": "BambooHR API key",
            },
            "employee_id": {
                "type": "string",
                "description": "Employee ID to look up directly (use if known)",
            },
            "search_term": {
                "type": "string",
                "description": "Name or email to search for (used when employee_id is not known)",
            },
            "include_reporting_chain": {
                "type": "boolean",
                "description": "Whether to include the full supervisor chain above the employee",
                "default": True,
            },
            "include_direct_reports": {
                "type": "boolean",
                "description": "Whether to include employees who directly report to this employee",
                "default": False,
            },
        },
        "required": ["subdomain", "api_key"],
    }
    outputs = {
        "employee": "Employee profile: name, title, department, hire date, status",
        "reporting_chain": "Ordered list of supervisors from this employee up to root",
        "direct_reports": "List of employees who report to this employee",
        "search_results": "Matching employees when search_term is used",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("bamboohr", {})
        return bool(cfg.get("subdomain") and cfg.get("api_key"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("bamboohr", {})
        return {
            "subdomain": cfg.get("subdomain", ""),
            "api_key": cfg.get("api_key", ""),
            "employee_id": "",
            "search_term": "",
            "include_reporting_chain": True,
            "include_direct_reports": False,
        }

    def run(
        self,
        subdomain: str,
        api_key: str,
        employee_id: str = "",
        search_term: str = "",
        include_reporting_chain: bool = True,
        include_direct_reports: bool = False,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not subdomain or not api_key:
            return {
                "source": "bamboohr",
                "available": False,
                "error": "subdomain and api_key are required.",
            }

        if not employee_id and not search_term:
            return {
                "source": "bamboohr",
                "available": False,
                "error": "Provide employee_id or search_term.",
            }

        client = make_bamboohr_client(subdomain=subdomain, api_key=api_key)
        if client is None:
            return {"source": "bamboohr", "available": False, "error": "Could not create client."}

        try:
            with client:
                return self._run_with_client(
                    client,
                    employee_id=employee_id,
                    search_term=search_term,
                    include_reporting_chain=include_reporting_chain,
                    include_direct_reports=include_direct_reports,
                )
        except Exception as exc:
            return {"source": "bamboohr", "available": False, "error": str(exc)}

    def _run_with_client(
        self,
        client: Any,
        *,
        employee_id: str,
        search_term: str,
        include_reporting_chain: bool,
        include_direct_reports: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"source": "bamboohr", "available": True}

        # Search mode — find matching employees first
        if search_term and not employee_id:
            matches = client.search_employees(search_term)
            if not matches:
                return {
                    "source": "bamboohr",
                    "available": True,
                    "search_term": search_term,
                    "search_results": [],
                    "message": f"No employees found matching '{search_term}'.",
                }
            # If exactly one match, continue to full profile; otherwise return list
            if len(matches) > 1:
                return {
                    "source": "bamboohr",
                    "available": True,
                    "search_term": search_term,
                    "search_results": matches,
                    "message": f"Found {len(matches)} employees. Refine search or use employee_id.",
                }
            employee_id = str(matches[0].get("id", ""))
            result["search_results"] = matches

        # Profile lookup
        employee = client.get_employee(employee_id)
        result["employee"] = employee
        result["employee_id"] = employee_id

        if include_reporting_chain:
            chain = client.get_reporting_chain(employee_id)
            result["reporting_chain"] = chain[1:]  # exclude self

        if include_direct_reports:
            reports = client.get_direct_reports(employee_id)
            result["direct_reports"] = reports

        return result


lookup_bamboohr_employee = BambooHREmployeeLookupTool()
