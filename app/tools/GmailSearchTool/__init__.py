"""Gmail email search tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.gmail import make_gmail_client
from app.tools.base import BaseTool


class GmailSearchTool(BaseTool):
    """Search a Gmail mailbox for emails relevant to an HR or legal investigation.

    Supports Gmail query syntax, including sender/recipient filters, date ranges,
    subject keywords, and label filters.  The tool reads message metadata and
    snippets only — no attachment content is fetched.
    """

    name = "search_gmail_emails"
    source = "email"
    description = (
        "Search a Gmail or Google Workspace mailbox for emails matching HR/legal investigation "
        "criteria. Supports Gmail query syntax: sender, recipient, date ranges, keywords, and "
        "label filters. Returns subject, participants, timestamps, and message snippets."
    )
    use_cases = [
        "Finding emails between a complainant and the accused during a harassment investigation",
        "Locating emails referencing a specific incident, date, or project",
        "Identifying whether a custodian was aware of a policy or received specific communication",
        "Tracing escalation chains by searching for forwarded or CC'd emails",
        "Establishing a timeline of events by retrieving emails in date order",
        "Verifying whether a terminated employee was notified of legal hold obligations",
    ]
    requires = ["access_token|service_account_json"]
    input_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "description": "OAuth2 access token with gmail.readonly scope",
            },
            "service_account_json": {
                "type": "string",
                "description": "Service account key JSON (string) with domain-wide delegation",
            },
            "delegated_email": {
                "type": "string",
                "description": "Email address of the mailbox to search (required for service account auth)",
            },
            "query": {
                "type": "string",
                "description": (
                    "Gmail search query. Examples: "
                    "'from:alice@corp.com after:2024/01/01', "
                    "'subject:harassment', "
                    "'to:hr@corp.com label:inbox'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum emails to return (1–100)",
                "default": 20,
            },
        },
        "required": ["query"],
    }
    outputs = {
        "messages": "List of email summaries: subject, from, to, cc, received_at, snippet",
        "total_estimate": "Estimated total matching messages in the mailbox",
        "query": "The search query used",
    }

    def is_available(self, sources: dict) -> bool:
        email_cfg = sources.get("gmail", sources.get("email", {}))
        return bool(
            email_cfg.get("access_token")
            or (email_cfg.get("service_account_json") and email_cfg.get("delegated_email"))
        )

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("gmail", sources.get("email", {}))
        return {
            "access_token": cfg.get("access_token", ""),
            "service_account_json": cfg.get("service_account_json", ""),
            "delegated_email": cfg.get("delegated_email", ""),
            "query": "",
            "max_results": 20,
        }

    def run(
        self,
        query: str,
        access_token: str = "",
        service_account_json: str = "",
        delegated_email: str = "",
        max_results: int = 20,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not query:
            return {"source": "email", "available": False, "error": "query is required."}

        client = make_gmail_client(
            access_token=access_token or None,
            service_account_json=service_account_json or None,
            delegated_email=delegated_email or None,
        )
        if client is None:
            return {
                "source": "email",
                "available": False,
                "error": (
                    "Gmail credentials not configured. "
                    "Provide access_token or service_account_json + delegated_email."
                ),
            }

        try:
            with client:
                result = client.search_messages(
                    query=query,
                    max_results=max_results,
                    include_body=True,
                )
        except Exception as exc:
            return {"source": "email", "available": False, "error": str(exc)}

        return {
            "source": "email",
            "available": True,
            "mailbox": delegated_email or "me",
            "query": result.get("query", query),
            "messages": result.get("messages", []),
            "total_estimate": result.get("total_estimate", 0),
            "returned_count": len(result.get("messages", [])),
        }


search_gmail_emails = GmailSearchTool()
