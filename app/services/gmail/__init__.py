"""Gmail API service client for email search and retrieval."""

from __future__ import annotations

from app.services.gmail.client import GmailClient, make_gmail_client

__all__ = ["GmailClient", "make_gmail_client"]
