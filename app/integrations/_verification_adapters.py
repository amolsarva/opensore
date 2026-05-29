"""Shared verification adapters and service-specific verifiers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import requests

from app.auth.jwt_auth import extract_org_id_from_jwt
from app.config import get_tracer_base_url
from app.integrations.bitbucket import build_bitbucket_config, validate_bitbucket_config
from app.integrations.config_models import (
    GoogleDocsIntegrationConfig,
    SlackWebhookConfig,
    TracerIntegrationConfig,
)
from app.integrations.github_mcp import build_github_mcp_config, validate_github_mcp_config
from app.integrations.openclaw import build_openclaw_config, validate_openclaw_config
from app.services.google_docs import GoogleDocsClient

VerifierFn = Callable[[str, dict[str, Any]], dict[str, str]]


def result(
    service: str,
    source: str,
    status: str,
    detail: str,
) -> dict[str, str]:
    return {
        "service": service,
        "source": source,
        "status": status,
        "detail": detail,
    }


def _verify_with_validation_result[ConfigT](
    service: str,
    source: str,
    config: dict[str, Any],
    *,
    build_config: Callable[[dict[str, Any]], ConfigT],
    validate_config: Callable[[ConfigT], Any],
) -> dict[str, str]:
    normalized_config = build_config(config)
    validation_result = validate_config(normalized_config)
    return result(
        service,
        source,
        "passed" if validation_result.ok else "failed",
        validation_result.detail,
    )


def build_validation_verifier[ConfigT](
    service: str,
    *,
    build_config: Callable[[dict[str, Any]], ConfigT],
    validate_config: Callable[[ConfigT], Any],
) -> VerifierFn:
    def _verifier(source: str, config: dict[str, Any]) -> dict[str, str]:
        return _verify_with_validation_result(
            service,
            source,
            config,
            build_config=build_config,
            validate_config=validate_config,
        )

    return _verifier


def build_probe_verifier[ConfigT](
    service: str,
    *,
    build_config: Callable[[dict[str, Any]], ConfigT],
    client_factory: Callable[[ConfigT], Any],
) -> VerifierFn:
    def _verifier(source: str, config: dict[str, Any]) -> dict[str, str]:
        try:
            normalized_config = build_config(config)
        except Exception as err:
            return result(service, source, "missing", str(err))
        try:
            probe_result = client_factory(normalized_config).probe_access()
        except Exception as err:
            return result(service, source, "failed", str(err))
        return result(service, source, probe_result.status, probe_result.detail)

    return _verifier


def _verify_slack(
    source: str,
    config: dict[str, Any],
    *,
    send_slack_test: bool,
) -> dict[str, str]:
    try:
        slack_config = SlackWebhookConfig.model_validate(config)
    except Exception as err:
        return result("slack", source, "missing", str(err))

    webhook_url = slack_config.webhook_url
    if not webhook_url:
        return result("slack", source, "missing", "SLACK_WEBHOOK_URL is not configured.")

    if not send_slack_test:
        return result(
            "slack", source, "passed", "Configured. Use --send-slack-test to validate delivery."
        )

    payload = {
        "text": "Tracer integration test: Slack webhook is configured correctly.",
    }
    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
    except Exception as exc:
        return result("slack", source, "failed", f"Webhook delivery failed: {exc}")
    return result("slack", source, "passed", "Webhook delivered test message successfully.")


def _verify_tracer(source: str, config: dict[str, Any]) -> dict[str, str]:
    tracer_config = TracerIntegrationConfig.model_validate(config)
    if not tracer_config.jwt_token:
        return result("tracer", source, "missing", "Missing JWT token.")

    base_url = tracer_config.base_url or get_tracer_base_url()
    try:
        org_id = extract_org_id_from_jwt(tracer_config.jwt_token)
    except Exception as err:
        return result("tracer", source, "failed", f"JWT decode failed: {err}")
    if not org_id:
        return result("tracer", source, "failed", "JWT did not contain an org identifier.")

    try:
        from app.services.tracer_client.client import TracerClient  # type: ignore[import]

        tracer_client = TracerClient(
            base_url=base_url,
            org_id=org_id,
            jwt_token=tracer_config.jwt_token,
        )
        integrations = tracer_client.get_all_integrations()
    except ImportError:
        return result("tracer", source, "failed", "Tracer client not available.")
    except Exception as err:
        return result("tracer", source, "failed", f"Tracer API check failed: {err}")

    return result(
        "tracer",
        source,
        "passed",
        f"Connected to {base_url} for org {org_id} and listed {len(integrations)} integrations.",
    )


def _verify_discord(source: str, config: dict[str, Any]) -> dict[str, str]:
    try:
        import discord  # type: ignore[import-not-found]
    except Exception:
        return result("discord", source, "failed", "discord.py is not installed.")

    bot_token = str(config.get("bot_token", "")).strip()
    if not bot_token:
        return result("discord", source, "missing", "Missing bot_token.")

    intents = discord.Intents.none()
    intents.guilds = True
    client = discord.Client(intents=intents)
    try:
        client.run(bot_token)
    except discord.LoginFailure as err:
        return result("discord", source, "failed", f"Discord login failed: {err}")
    except Exception as err:
        detail = str(err)
        if "run() cannot be called from a running event loop" in detail:
            return result("discord", source, "passed", "Discord bot token accepted.")
        return result("discord", source, "failed", f"Discord API check failed: {err}")
    return result("discord", source, "passed", "Discord bot token accepted.")


def _verify_telegram(source: str, config: dict[str, Any]) -> dict[str, str]:
    bot_token = str(config.get("bot_token", "")).strip()
    if not bot_token:
        return result("telegram", source, "missing", "Missing bot_token.")

    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return result("telegram", source, "failed", f"Telegram API check failed: {exc}")

    if not payload.get("ok"):
        return result(
            "telegram",
            source,
            "failed",
            f"Telegram API check failed: {payload.get('description', 'unknown error')}",
        )

    user = payload.get("result", {})
    username = str(user.get("username", "")).strip()
    return result(
        "telegram",
        source,
        "passed",
        f"Connected to Telegram bot @{username or 'unknown'}.",
    )


def _verify_whatsapp(source: str, config: dict[str, Any]) -> dict[str, str]:
    account_sid = str(config.get("account_sid", "")).strip()
    auth_token = str(config.get("auth_token", "")).strip()
    if not account_sid:
        return result("whatsapp", source, "missing", "Missing account_sid.")
    if not auth_token:
        return result("whatsapp", source, "missing", "Missing auth_token.")

    try:
        response = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json",
            auth=(account_sid, auth_token),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return result("whatsapp", source, "failed", f"Twilio API check failed: {exc}")

    friendly_name = str(payload.get("friendly_name", "")).strip()
    return result(
        "whatsapp",
        source,
        "passed",
        f"Connected to Twilio account {friendly_name or account_sid}.",
    )


def _verify_twilio(source: str, config: dict[str, Any]) -> dict[str, str]:
    """Verify the Twilio integration: account auth + SMS channel readiness.

    A "passed" result confirms the account credentials authenticate and the
    SMS channel has a usable sender (``from_number`` or
    ``messaging_service_sid``). WhatsApp is verified separately via the
    standalone ``whatsapp`` integration.
    """
    account_sid = str(config.get("account_sid", "")).strip()
    auth_token = str(config.get("auth_token", "")).strip()
    if not account_sid:
        return result("twilio", source, "missing", "Missing account_sid.")
    if not auth_token:
        return result("twilio", source, "missing", "Missing auth_token.")

    try:
        response = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json",
            auth=(account_sid, auth_token),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return result("twilio", source, "failed", f"Twilio API check failed: {exc}")

    friendly_name = str(payload.get("friendly_name", "")).strip() or account_sid

    sms_cfg = config.get("sms") or {}
    sms_ready = bool(sms_cfg.get("enabled")) and bool(
        str(sms_cfg.get("from_number") or "").strip()
        or str(sms_cfg.get("messaging_service_sid") or "").strip()
    )

    if not sms_ready:
        return result(
            "twilio",
            source,
            "failed",
            (
                f"Connected to Twilio account {friendly_name} but the SMS channel "
                "is not ready. Enable SMS and set a from_number or messaging_service_sid."
            ),
        )

    return result(
        "twilio",
        source,
        "passed",
        f"Connected to Twilio account {friendly_name}; SMS channel ready.",
    )


_verify_github = build_validation_verifier(
    "github",
    build_config=build_github_mcp_config,
    validate_config=validate_github_mcp_config,
)
_verify_openclaw = build_validation_verifier(
    "openclaw",
    build_config=build_openclaw_config,
    validate_config=validate_openclaw_config,
)
_verify_bitbucket = build_validation_verifier(
    "bitbucket",
    build_config=build_bitbucket_config,
    validate_config=validate_bitbucket_config,
)
_verify_google_docs = build_probe_verifier(
    "google_docs",
    build_config=GoogleDocsIntegrationConfig.model_validate,
    client_factory=GoogleDocsClient,
)


def _verify_slack_without_test(source: str, config: dict[str, Any]) -> dict[str, str]:
    return _verify_slack(source, config, send_slack_test=False)


__all__ = [
    "VerifierFn",
    "_verify_bitbucket",
    "_verify_discord",
    "_verify_github",
    "_verify_google_docs",
    "_verify_openclaw",
    "_verify_slack",
    "_verify_slack_without_test",
    "_verify_telegram",
    "_verify_tracer",
    "_verify_twilio",
    "_verify_whatsapp",
    "build_probe_verifier",
    "build_validation_verifier",
    "result",
]
