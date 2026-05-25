"""Slack source connector for discovery — searches workspace messages via user token.

OAuth client credentials are read from environment variables:
    OPENSORE_SLACK_CLIENT_ID
    OPENSORE_SLACK_CLIENT_SECRET

Create a Slack app with ``search:read`` and ``users:read`` user scopes at:
https://api.slack.com/apps
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from typing import Any

import httpx
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.discovery.connectors.base import DiscoveryEstimate, DiscoverySearchHit
from app.discovery.connectors.oauth import run_loopback_oauth
from app.discovery.credentials import new_source_id, utc_now
from app.discovery.models import DiscoveryCustodian, DiscoveryInvestigationRequest

_ENV_CLIENT_ID = "OPENSORE_SLACK_CLIENT_ID"
_ENV_CLIENT_SECRET = "OPENSORE_SLACK_CLIENT_SECRET"
_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
_USERS_INFO_URL = "https://slack.com/api/users.info"


def _require_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env or raise with instructions."""
    client_id = os.environ.get(_ENV_CLIENT_ID, "").strip()
    client_secret = os.environ.get(_ENV_CLIENT_SECRET, "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Slack OAuth credentials are not configured.\n"
            f"Set {_ENV_CLIENT_ID} and {_ENV_CLIENT_SECRET} in your environment.\n"
            "Create a Slack app with 'search:read' and 'users:read' user scopes at:\n"
            "  https://api.slack.com/apps"
        )
    return client_id, client_secret


def run_slack_oauth() -> dict[str, Any]:
    """Run the Slack OAuth flow and return a credential store record.

    Opens the browser for the user to authorize via Slack's OAuth v2 flow,
    then exchanges the code for an access token and fetches user info.
    """
    client_id, client_secret = _require_client_credentials()
    state = secrets.token_urlsafe(16)

    def build_url(redirect_uri: str) -> str:
        return (
            f"https://slack.com/oauth/v2/authorize"
            f"?client_id={client_id}"
            f"&user_scope=search:read,users:read"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )

    code, redirect_uri = run_loopback_oauth(build_url)

    with httpx.Client() as client:
        response = client.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=15.0,
        )
    response.raise_for_status()
    token_data = response.json()

    if not token_data.get("ok"):
        raise RuntimeError(
            f"Slack OAuth token exchange failed: {token_data.get('error', 'unknown error')}"
        )

    authed_user: dict[str, Any] = token_data.get("authed_user", {})
    authed_user_token: str = authed_user.get("access_token", "")
    authed_user_id: str = authed_user.get("id", "")
    team: dict[str, Any] = token_data.get("team", {})
    team_id: str = team.get("id", "")
    team_name: str = team.get("name", "")

    with httpx.Client() as client:
        info_response = client.get(
            _USERS_INFO_URL,
            headers={"Authorization": f"Bearer {authed_user_token}"},
            params={"user": authed_user_id},
            timeout=10.0,
        )
    info_response.raise_for_status()
    user_info_data = info_response.json()
    user_profile: dict[str, Any] = user_info_data.get("user", {}).get("profile", {})
    user_display_name: str = (
        user_profile.get("display_name") or user_profile.get("real_name") or authed_user_id
    )

    label = f"{team_name} ({user_display_name})"
    return {
        "id": new_source_id("sl"),
        "kind": "slack",
        "label": label,
        "team_id": team_id,
        "team_name": team_name,
        "user_id": authed_user_id,
        "authed_user_token": authed_user_token,
        "connected_at": utc_now(),
    }


def _date_to_slack_format(date_str: str | None) -> str | None:
    """Convert an ISO date string to YYYY-MM-DD for Slack search modifiers."""
    if not date_str:
        return None
    normalized = date_str.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _custodian_identifiers(request: DiscoveryInvestigationRequest) -> set[str]:
    """Return a flat set of lowercase custodian identity strings."""
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


class SlackConnector:
    """Discovery connector that searches Slack messages using a user OAuth token."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record
        self._client = WebClient(token=record.get("authed_user_token", ""))

    @property
    def source_id(self) -> str:
        return str(self._record.get("id", ""))

    @property
    def kind(self) -> str:
        return "slack"

    @property
    def label(self) -> str:
        return str(self._record.get("label", ""))

    def verify(self) -> bool:
        """Return True if the stored token can authenticate with Slack."""
        try:
            result = self._client.auth_test()
            return bool(result.get("ok"))
        except (SlackApiError, Exception):
            return False

    def estimate(self, request: DiscoveryInvestigationRequest) -> DiscoveryEstimate:
        """Return one query per keyword group (Slack search covers entire message body)."""
        return DiscoveryEstimate(
            source_kind=self.kind,
            label=self.label,
            query_count=len(request.keyword_sets),
        )

    def search(self, request: DiscoveryInvestigationRequest) -> Iterator[DiscoverySearchHit]:
        """Search Slack for each keyword set, yielding hits with custodian filtering."""
        date_start = _date_to_slack_format(request.date_start)
        date_end = _date_to_slack_format(request.date_end)
        custodian_ids = _custodian_identifiers(request)

        for keyword_set in request.keyword_sets:
            terms = keyword_set.terms
            query_parts = [" ".join(terms)]
            if date_start:
                query_parts.append(f"after:{date_start}")
            if date_end:
                query_parts.append(f"before:{date_end}")
            query = " ".join(query_parts)

            page = 1
            while True:
                try:
                    result = self._client.search_messages(
                        query=query,
                        count=100,
                        page=page,
                    )
                except (SlackApiError, Exception):
                    break

                messages_data: dict[str, Any] = result.get("messages", {})  # type: ignore[union-attr]
                matches: list[dict[str, Any]] = messages_data.get("matches", [])
                paging: dict[str, Any] = messages_data.get("paging", {})

                for match in matches:
                    username: str = match.get("username", "")
                    user_id: str = match.get("user", "")
                    sender_field = username or user_id

                    if custodian_ids and not _matches_custodian(sender_field, custodian_ids):
                        continue

                    custodian_label = _resolve_custodian_label(
                        sender=sender_field,
                        custodians=request.custodians,
                    )

                    channel_info: dict[str, Any] = match.get("channel", {})
                    channel_name: str = channel_info.get("name", "")
                    permalink: str = match.get("permalink", "")
                    ts: str = match.get("ts", "")
                    text: str = match.get("text", "")
                    msg_ts = ts.replace(".", "")

                    matched_term = _first_matching_term(text, terms)

                    yield DiscoverySearchHit(
                        source_kind=self.kind,
                        source_label=self.label,
                        message_id=msg_ts or ts,
                        timestamp=ts,
                        sender=sender_field,
                        recipients="",
                        subject="",
                        excerpt=text[:280],
                        source_url=permalink,
                        custodian=custodian_label,
                        matched_keyword=matched_term,
                        matched_keyword_set=keyword_set.name,
                        channel=channel_name,
                        thread_id=match.get("thread_ts", ""),
                    )

                total_pages = paging.get("pages", 1)
                if page >= total_pages:
                    break
                page += 1


def _first_matching_term(text: str, terms: list[str]) -> str:
    """Return the first term that appears (case-insensitively) in text."""
    lowered = text.lower()
    for term in terms:
        if term.lower() in lowered:
            return term
    return terms[0] if terms else ""


def _resolve_custodian_label(
    *,
    sender: str,
    custodians: list[DiscoveryCustodian],
) -> str:
    """Return the primary label of the matching custodian, or the sender as fallback."""
    lowered_sender = sender.lower()
    for custodian in custodians:
        for term in custodian.search_terms():
            if term.lower() in lowered_sender:
                return custodian.primary_label
    return sender
