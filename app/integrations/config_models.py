"""Canonical strict models for normalized integration configuration."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from app.config import get_tracer_base_url
from app.integrations._validators import (
    normalize_bearer,
    normalize_bool_str,
    normalize_str,
    normalize_url,
)
from app.strict_config import StrictConfigModel

# ---------------------------------------------------------------------------
# Alerting & Incident Management
# ---------------------------------------------------------------------------


class SlackWebhookConfig(StrictConfigModel):
    """Slack webhook runtime config."""

    webhook_url: str

    @model_validator(mode="after")
    def _require_https_slack_url(self) -> SlackWebhookConfig:
        parsed = urlparse(self.webhook_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Slack webhook must be a valid HTTPS URL.")
        hostname = (parsed.hostname or "").lower()
        if hostname != "slack.com" and not hostname.endswith(".slack.com"):
            raise ValueError("Slack webhook host must be a Slack domain.")
        return self


# ---------------------------------------------------------------------------
# Source Control & CI/CD
# ---------------------------------------------------------------------------


class GitLabIntegrationConfig(StrictConfigModel):
    """Normalized GitLab credentials used by resolution and verification flows."""

    url: str
    access_token: str
    integration_id: str = ""


# ---------------------------------------------------------------------------
# Productivity & Collaboration
# ---------------------------------------------------------------------------


class JiraIntegrationConfig(StrictConfigModel):
    """Normalized Jira credentials used by resolution and verification flows."""

    base_url: str
    email: str
    api_token: str
    project_key: str
    integration_id: str = ""

    _normalize_base_url = field_validator("base_url", mode="before")(normalize_url())
    _normalize_strs = field_validator("email", "api_token", "project_key", mode="before")(
        normalize_str()
    )

    @property
    def auth(self) -> tuple[str, str]:
        return (self.email, self.api_token)

    @property
    def api_base(self) -> str:
        return f"{self.base_url}/rest/api/3"


class NotionIntegrationConfig(StrictConfigModel):
    """Normalized Notion credentials used by resolution and verification flows."""

    api_key: str
    database_id: str
    integration_id: str = ""

    _normalize_strs = field_validator("api_key", "database_id", mode="before")(normalize_str())


class GoogleDocsIntegrationConfig(StrictConfigModel):
    """Normalized Google Docs (Drive API) credentials for incident report generation."""

    credentials_file: str
    folder_id: str
    integration_id: str = ""
    timeout_seconds: int = 30

    _normalize_credentials_file = field_validator("credentials_file", mode="before")(
        normalize_str()
    )

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout(cls, value: object) -> int:
        if isinstance(value, str):
            try:
                timeout = int(value)
            except ValueError:
                return 30
        elif isinstance(value, int | float):
            timeout = int(value)
        else:
            return 30
        return max(5, min(timeout, 300))


# ---------------------------------------------------------------------------
# Messaging Bots
# ---------------------------------------------------------------------------


class DiscordBotConfig(StrictConfigModel):
    """Discord runtime config."""

    bot_token: str
    application_id: str = ""
    public_key: str = ""
    default_channel_id: str | None = None
    identity_policy: dict[str, object] | None = Field(
        default=None,
        description="Messaging identity policy for inbound security (MessagingIdentityPolicy shape)",
    )

    @field_validator("bot_token", mode="before")
    @classmethod
    def _validate_bot_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("bot_token cannot be empty or just whitespace")
        return stripped

    @field_validator("public_key", mode="before")
    @classmethod
    def _validate_public_key(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if stripped and not re.fullmatch(r"[0-9a-fA-F]+", stripped):
            raise ValueError("public_key must be a valid hexadecimal string")
        return stripped


class TelegramBotConfig(StrictConfigModel):
    """Telegram Bot runtime config."""

    bot_token: str
    default_chat_id: str | None = None
    identity_policy: dict[str, object] | None = Field(
        default=None,
        description="Messaging identity policy for inbound security (MessagingIdentityPolicy shape)",
    )

    @field_validator("bot_token", mode="before")
    @classmethod
    def _validate_bot_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("bot_token cannot be empty or just whitespace")
        return stripped


class WhatsAppConfig(StrictConfigModel):
    """Twilio WhatsApp runtime config.

    WhatsApp delivery is owned entirely by the standalone ``whatsapp``
    integration. The unified :class:`TwilioIntegrationConfig` adds SMS as a
    separate channel and intentionally does NOT duplicate WhatsApp.
    """

    account_sid: str
    auth_token: str
    from_number: str
    default_to: str | None = None
    identity_policy: dict[str, object] | None = Field(
        default=None,
        description="Messaging identity policy for inbound security (MessagingIdentityPolicy shape)",
    )

    @field_validator("account_sid", mode="before")
    @classmethod
    def _validate_account_sid(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("account_sid cannot be empty or just whitespace")
        return stripped

    @field_validator("auth_token", mode="before")
    @classmethod
    def _validate_auth_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("auth_token cannot be empty or just whitespace")
        return stripped

    @field_validator("from_number", mode="before")
    @classmethod
    def _validate_from_number(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("from_number cannot be empty or just whitespace")
        return stripped


class TwilioSMSChannelConfig(StrictConfigModel):
    """SMS channel sub-config inside a unified Twilio integration.

    Either ``from_number`` (a Twilio-provisioned phone number) OR
    ``messaging_service_sid`` (a Twilio Messaging Service) must be set
    for the channel to be considered configured.
    """

    enabled: bool = False
    from_number: str = ""
    default_to: str | None = None
    messaging_service_sid: str = ""

    _normalize_strs = field_validator("from_number", "messaging_service_sid", mode="before")(
        normalize_str()
    )
    _normalize_enabled = field_validator("enabled", mode="before")(normalize_bool_str())

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and (self.from_number or self.messaging_service_sid))


class TwilioIntegrationConfig(StrictConfigModel):
    """Unified Twilio runtime config.

    Adds SMS as a Twilio-backed outbound channel. WhatsApp is owned by the
    standalone ``whatsapp`` integration and is intentionally not duplicated
    here. Both can share the same Twilio account credentials.
    """

    account_sid: str
    auth_token: str
    sms: TwilioSMSChannelConfig = Field(default_factory=TwilioSMSChannelConfig)
    integration_id: str = ""

    @field_validator("account_sid", mode="before")
    @classmethod
    def _validate_account_sid(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("account_sid cannot be empty or just whitespace")
        return stripped

    @field_validator("auth_token", mode="before")
    @classmethod
    def _validate_auth_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("auth_token cannot be empty or just whitespace")
        return stripped

    @model_validator(mode="after")
    def _require_sms_channel(self) -> TwilioIntegrationConfig:
        if not self.sms.is_configured:
            raise ValueError(
                "Twilio integration requires the SMS channel configured "
                "(enabled=true with a from_number or messaging_service_sid)."
            )
        return self

    @property
    def configured_channels(self) -> list[str]:
        return ["sms"] if self.sms.is_configured else []


class SlackBotConfig(StrictConfigModel):
    """Slack Bot (Events API) runtime config for inbound messaging.

    NOTE: ``signing_secret`` defaults to empty for backward compatibility,
    but MUST be set in production when inbound messaging is enabled.
    Without it, the Slack Events API webhook handler cannot verify request
    authenticity and will accept forged requests from any source.
    """

    bot_token: str
    signing_secret: str = Field(
        default="",
        description="Slack signing secret for webhook HMAC verification. MUST be set for inbound.",
    )
    app_id: str = ""
    identity_policy: dict[str, object] | None = Field(
        default=None,
        description="Messaging identity policy for inbound security (MessagingIdentityPolicy shape)",
    )

    @field_validator("bot_token", mode="before")
    @classmethod
    def _validate_bot_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("bot_token cannot be empty or just whitespace")
        return stripped


# ---------------------------------------------------------------------------
# Tracer internal
# ---------------------------------------------------------------------------


class TracerIntegrationConfig(StrictConfigModel):
    """Tracer API access config."""

    base_url: str = Field(default_factory=get_tracer_base_url)
    jwt_token: str

    @field_validator("base_url", mode="before")
    @classmethod
    def _normalize_base_url(cls, value: object) -> str:
        return str(value or get_tracer_base_url()).strip() or get_tracer_base_url()

    _normalize_token = field_validator("jwt_token", mode="before")(normalize_bearer())


# ---------------------------------------------------------------------------
# SaaS / workflow integrations
# ---------------------------------------------------------------------------


class PagerDutyIntegrationConfig(StrictConfigModel):
    """Normalized PagerDuty credentials for incident lookup, on-call, and writeback."""

    api_token: str
    from_email: str = ""
    integration_id: str = ""

    _normalize_strs = field_validator("api_token", "from_email", mode="before")(normalize_str())

    @field_validator("api_token", mode="before")
    @classmethod
    def _require_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("api_token cannot be empty")
        return stripped


class SlackSearchIntegrationConfig(StrictConfigModel):
    """Slack credentials for searching messages during investigations.

    Requires a bot token with search:read, channels:history, and channels:read scopes.
    """

    bot_token: str
    default_channel: str = ""
    integration_id: str = ""

    _normalize_strs = field_validator("bot_token", "default_channel", mode="before")(
        normalize_str()
    )

    @field_validator("bot_token", mode="before")
    @classmethod
    def _require_token(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("bot_token cannot be empty")
        return stripped


class LinearIntegrationConfig(StrictConfigModel):
    """Linear GraphQL API credentials for issue search and creation."""

    api_key: str
    default_team_id: str = ""
    integration_id: str = ""

    _normalize_strs = field_validator("api_key", "default_team_id", mode="before")(normalize_str())

    @field_validator("api_key", mode="before")
    @classmethod
    def _require_api_key(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("api_key cannot be empty")
        return stripped


class GitHubActionsIntegrationConfig(StrictConfigModel):
    """GitHub credentials for Actions/Workflows REST API access during investigations."""

    owner: str
    repo: str
    auth_token: str = ""
    url: str = ""
    integration_id: str = ""

    _normalize_strs = field_validator("owner", "repo", "auth_token", "url", mode="before")(
        normalize_str()
    )

    @field_validator("owner", "repo", mode="before")
    @classmethod
    def _require_non_empty(cls, value: object) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            raise ValueError("owner and repo cannot be empty")
        return stripped
