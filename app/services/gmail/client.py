"""Gmail API client using service account delegation or OAuth bearer tokens.

Supports two authentication modes:
- ``service_account``: JSON service account key with domain-wide delegation.
  The ``delegated_email`` field specifies which mailbox to impersonate.
- ``bearer``: A raw OAuth2 access token (useful for testing or short-lived sessions).
"""

from __future__ import annotations

import base64
import json
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import requests


class GmailClient:
    """Thin HTTP wrapper around the Gmail REST API."""

    _BASE = "https://gmail.googleapis.com/gmail/v1/users"

    def __init__(self, access_token: str, user_id: str = "me") -> None:
        self._token = access_token
        self._user_id = user_id
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {access_token}"})

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_messages(
        self,
        query: str,
        max_results: int = 20,
        include_body: bool = True,
    ) -> dict[str, Any]:
        """Search mailbox and return message summaries.

        Args:
            query: Gmail query string (e.g. "from:alice@corp.com after:2024/01/01")
            max_results: Maximum number of messages to return (1–100)
            include_body: Whether to fetch message snippets/bodies

        Returns:
            dict with ``messages`` list and ``total_estimate``
        """
        max_results = max(1, min(max_results, 100))
        list_url = f"{self._BASE}/{self._user_id}/messages"
        list_resp = self._session.get(
            list_url,
            params={"q": query, "maxResults": max_results},
            timeout=15,
        )
        list_resp.raise_for_status()
        data = list_resp.json()

        raw_messages = data.get("messages", [])
        total = data.get("resultSizeEstimate", len(raw_messages))
        messages: list[dict[str, Any]] = []

        for msg_stub in raw_messages:
            msg_id = msg_stub.get("id", "")
            if not msg_id:
                continue
            if include_body:
                detail = self._get_message(msg_id)
                if detail:
                    messages.append(detail)
            else:
                messages.append({"id": msg_id, "thread_id": msg_stub.get("threadId", "")})

        return {"messages": messages, "total_estimate": total, "query": query}

    # ------------------------------------------------------------------
    # Thread retrieval
    # ------------------------------------------------------------------

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Return all messages in a Gmail thread."""
        url = f"{self._BASE}/{self._user_id}/threads/{thread_id}"
        resp = self._session.get(url, params={"format": "metadata"}, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        messages = [self._parse_message(m) for m in raw.get("messages", [])]
        return {"thread_id": thread_id, "messages": messages, "message_count": len(messages)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_message(self, msg_id: str) -> dict[str, Any] | None:
        url = f"{self._BASE}/{self._user_id}/messages/{msg_id}"
        try:
            resp = self._session.get(url, params={"format": "metadata"}, timeout=15)
            resp.raise_for_status()
            return self._parse_message(resp.json())
        except requests.HTTPError:
            return None

    @staticmethod
    def _parse_message(raw: dict[str, Any]) -> dict[str, Any]:
        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        received_ts = raw.get("internalDate")
        received_iso: str | None = None
        if received_ts:
            try:
                received_iso = datetime.utcfromtimestamp(
                    int(received_ts) / 1000
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OverflowError):
                pass

        snippet = raw.get("snippet", "")
        # Gmail HTML-escapes snippets; do a minimal decode
        snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

        return {
            "id": raw.get("id", ""),
            "thread_id": raw.get("threadId", ""),
            "subject": headers.get("subject", "(no subject)"),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "date": headers.get("date", ""),
            "received_at": received_iso,
            "snippet": snippet,
            "label_ids": raw.get("labelIds", []),
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> GmailClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Service-account OAuth token exchange
# ---------------------------------------------------------------------------

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _get_service_account_token(
    service_account_json: str,
    delegated_email: str,
) -> str:
    """Obtain a short-lived access token via service account JWT assertion."""
    try:
        import time

        key_data: dict[str, Any] = json.loads(service_account_json)
        client_email = key_data["client_email"]
        private_key_id = key_data["private_key_id"]
        private_key_pem = key_data["private_key"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ValueError(f"Invalid service account JSON: {exc}") from exc

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
    except ImportError as exc:
        raise ImportError(
            "cryptography package required for service account auth: pip install cryptography"
        ) from exc

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": private_key_id}
    payload = {
        "iss": client_email,
        "sub": delegated_email,
        "scope": _GMAIL_SCOPE,
        "aud": _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    def _b64url(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    header_b64 = _b64url(json.dumps(header).encode())
    payload_b64 = _b64url(json.dumps(payload).encode())
    signing_input = header_b64 + b"." + payload_b64
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt = signing_input + b"." + _b64url(signature)

    resp = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt.decode(),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def make_gmail_client(
    *,
    access_token: str | None = None,
    service_account_json: str | None = None,
    delegated_email: str | None = None,
) -> GmailClient | None:
    """Create a GmailClient from credentials.

    Pass exactly one of:
    - ``access_token``: a ready OAuth2 bearer token
    - ``service_account_json`` + ``delegated_email``: service-account delegation
    """
    if access_token:
        user_id = delegated_email or "me"
        return GmailClient(access_token=access_token, user_id=user_id)

    if service_account_json and delegated_email:
        try:
            token = _get_service_account_token(service_account_json, delegated_email)
            return GmailClient(access_token=token, user_id=delegated_email)
        except Exception:
            return None

    return None
