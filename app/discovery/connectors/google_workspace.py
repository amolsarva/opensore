"""Google Workspace source connector for discovery — Gmail, Drive, and Calendar.

OAuth client credentials are read from environment variables:
    OPENSORE_GOOGLE_CLIENT_ID
    OPENSORE_GOOGLE_CLIENT_SECRET

Create a GCP OAuth 2.0 Desktop-app client ID at:
https://console.cloud.google.com/apis/credentials
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from app.discovery.connectors.base import DiscoveryEstimate, DiscoverySearchHit
from app.discovery.credentials import new_source_id, utc_now
from app.discovery.models import DiscoveryInvestigationRequest

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "email",
    "profile",
]

_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_ENV_CLIENT_ID = "OPENSORE_GOOGLE_CLIENT_ID"
_ENV_CLIENT_SECRET = "OPENSORE_GOOGLE_CLIENT_SECRET"


def _require_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env or raise with instructions."""
    client_id = os.environ.get(_ENV_CLIENT_ID, "").strip()
    client_secret = os.environ.get(_ENV_CLIENT_SECRET, "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Google Workspace OAuth credentials are not configured.\n"
            f"Set {_ENV_CLIENT_ID} and {_ENV_CLIENT_SECRET} in your environment.\n"
            "Create an OAuth 2.0 Desktop-app client ID at:\n"
            "  https://console.cloud.google.com/apis/credentials"
        )
    return client_id, client_secret


def run_google_oauth() -> dict[str, Any]:
    """Run the Google OAuth flow and return a credential store record.

    Opens the browser for the user to authorize, then fetches the user's
    email address from the Google userinfo endpoint.
    """
    client_id, client_secret = _require_client_credentials()
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True)

    with httpx.Client() as client:
        response = client.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10.0,
        )
    response.raise_for_status()
    user_info = response.json()
    email: str = user_info.get("email", "")

    import json

    return {
        "id": new_source_id("gs"),
        "kind": "google_workspace",
        "label": email,
        "email": email,
        "scopes": list(SCOPES),
        "token": json.loads(credentials.to_json()),
        "connected_at": utc_now(),
    }


def _build_credentials(record: dict[str, Any]) -> Credentials:
    """Build and refresh Google credentials from a stored token record."""
    client_id, client_secret = _require_client_credentials()
    token_data: dict[str, Any] = record.get("token", {})
    expiry_str: str | None = token_data.get("expiry")
    expiry: datetime | None = None
    if expiry_str:
        normalized = expiry_str.rstrip("Z")
        try:
            expiry = datetime.fromisoformat(normalized).replace(tzinfo=UTC)
        except ValueError:
            expiry = None

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=record.get("scopes", SCOPES),
        expiry=expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _date_to_yyyymmdd(date_str: str | None) -> str | None:
    """Convert an ISO date string to YYYYMMDD format for Gmail queries."""
    if not date_str:
        return None
    normalized = date_str.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return None


def _custodian_identifiers(request: DiscoveryInvestigationRequest) -> set[str]:
    """Return a flat set of lowercase custodian email/name/alias strings."""
    identifiers: set[str] = set()
    for custodian in request.custodians:
        for term in custodian.search_terms():
            identifiers.add(term.lower())
    return identifiers


def _matches_custodian(field_value: str, identifiers: set[str]) -> bool:
    if not identifiers:
        return True
    lowered = field_value.lower()
    return any(ident in lowered for ident in identifiers)


def _header_value(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


class GoogleWorkspaceConnector:
    """Discovery connector that searches Gmail and Drive using OAuth credentials."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    @property
    def source_id(self) -> str:
        return str(self._record.get("id", ""))

    @property
    def kind(self) -> str:
        return "google_workspace"

    @property
    def label(self) -> str:
        return str(self._record.get("label", ""))

    def verify(self) -> bool:
        """Return True if the stored credentials can reach the userinfo endpoint."""
        try:
            creds = _build_credentials(self._record)
            with httpx.Client() as client:
                response = client.get(
                    _USERINFO_URL,
                    headers={"Authorization": f"Bearer {creds.token}"},
                    timeout=10.0,
                )
            return response.status_code == 200
        except Exception:
            return False

    def estimate(self, request: DiscoveryInvestigationRequest) -> DiscoveryEstimate:
        """Return a query count estimate: each keyword term generates 3 queries (Gmail, Drive, Calendar)."""
        term_count = sum(len(ks.terms) for ks in request.keyword_sets)
        return DiscoveryEstimate(
            source_kind=self.kind,
            label=self.label,
            query_count=term_count * 3,
        )

    def search(self, request: DiscoveryInvestigationRequest) -> Iterator[DiscoverySearchHit]:
        """Search Gmail and Drive for each keyword set and term, yielding hits."""
        creds = _build_credentials(self._record)
        date_start = _date_to_yyyymmdd(request.date_start)
        date_end = _date_to_yyyymmdd(request.date_end)
        custodian_ids = _custodian_identifiers(request)

        yield from self._search_gmail(
            creds=creds,
            request=request,
            date_start=date_start,
            date_end=date_end,
            custodian_ids=custodian_ids,
        )
        yield from self._search_drive(
            creds=creds,
            request=request,
            custodian_ids=custodian_ids,
        )

    def _search_gmail(
        self,
        *,
        creds: Credentials,
        request: DiscoveryInvestigationRequest,
        date_start: str | None,
        date_end: str | None,
        custodian_ids: set[str],
    ) -> Iterator[DiscoverySearchHit]:
        gmail = build("gmail", "v1", credentials=creds)
        for keyword_set in request.keyword_sets:
            for term in keyword_set.terms:
                query_parts = [f"({term})"]
                if date_start:
                    query_parts.append(f"after:{date_start}")
                if date_end:
                    query_parts.append(f"before:{date_end}")
                query = " ".join(query_parts)

                result = (
                    gmail.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=100)
                    .execute()
                )
                messages = result.get("messages", [])
                for msg_ref in messages:
                    msg_id: str = msg_ref.get("id", "")
                    try:
                        msg = (
                            gmail.users()
                            .messages()
                            .get(
                                userId="me",
                                id=msg_id,
                                format="metadata",
                                metadataHeaders=["From", "To", "Subject", "Date"],
                            )
                            .execute()
                        )
                    except Exception:
                        continue

                    payload = msg.get("payload", {})
                    headers: list[dict[str, str]] = payload.get("headers", [])
                    sender = _header_value(headers, "From")
                    recipients = _header_value(headers, "To")
                    subject = _header_value(headers, "Subject")
                    date_header = _header_value(headers, "Date")
                    thread_id: str = msg.get("threadId", "")
                    snippet: str = msg.get("snippet", "")

                    if custodian_ids and not (
                        _matches_custodian(sender, custodian_ids)
                        or _matches_custodian(recipients, custodian_ids)
                    ):
                        continue

                    custodian_label = _resolve_custodian_label(
                        sender=sender,
                        recipients=recipients,
                        custodians=request.custodians,
                    )

                    yield DiscoverySearchHit(
                        source_kind=self.kind,
                        source_label=self.label,
                        message_id=msg_id,
                        timestamp=date_header,
                        sender=sender,
                        recipients=recipients,
                        subject=subject,
                        excerpt=snippet,
                        source_url=f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
                        custodian=custodian_label,
                        matched_keyword=term,
                        matched_keyword_set=keyword_set.name,
                        thread_id=thread_id,
                    )

    def _search_drive(
        self,
        *,
        creds: Credentials,
        request: DiscoveryInvestigationRequest,
        custodian_ids: set[str],
    ) -> Iterator[DiscoverySearchHit]:
        drive = build("drive", "v3", credentials=creds)
        for keyword_set in request.keyword_sets:
            for term in keyword_set.terms:
                query = f"fullText contains '{term}'"
                result = (
                    drive.files()
                    .list(
                        q=query,
                        fields="files(id,name,webViewLink,modifiedTime,owners)",
                    )
                    .execute()
                )
                files: list[dict[str, Any]] = result.get("files", [])
                for file_record in files:
                    owners: list[dict[str, Any]] = file_record.get("owners", [])
                    owner_email = owners[0].get("emailAddress", "") if owners else ""
                    owner_name = owners[0].get("displayName", "") if owners else ""
                    modified_time: str = file_record.get("modifiedTime", "")

                    if custodian_ids and not _matches_custodian(
                        f"{owner_email} {owner_name}", custodian_ids
                    ):
                        continue

                    file_id: str = file_record.get("id", "")
                    file_name: str = file_record.get("name", "")
                    web_link: str = file_record.get("webViewLink", f"https://drive.google.com/file/d/{file_id}")

                    yield DiscoverySearchHit(
                        source_kind=self.kind,
                        source_label=self.label,
                        message_id=file_id,
                        timestamp=modified_time,
                        sender=owner_email,
                        recipients="",
                        subject=file_name,
                        excerpt=f"Drive file: {file_name}",
                        source_url=web_link,
                        custodian=owner_email or owner_name,
                        matched_keyword=term,
                        matched_keyword_set=keyword_set.name,
                        file_name=file_name,
                    )


def _resolve_custodian_label(
    *,
    sender: str,
    recipients: str,
    custodians: list[Any],
) -> str:
    """Return the primary label of the matching custodian, or the sender as fallback."""
    combined = f"{sender} {recipients}".lower()
    for custodian in custodians:
        for term in custodian.search_terms():
            if term.lower() in combined:
                return custodian.primary_label
    return sender
