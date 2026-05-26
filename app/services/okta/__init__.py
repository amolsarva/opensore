"""Okta identity and access management client."""

from __future__ import annotations

from app.services.okta.client import OktaClient, make_okta_client

__all__ = ["OktaClient", "make_okta_client"]
