"""Backward-compatible re-exports for integration models.

Import directly from config_models or effective_models in new code.
This shim exists only so existing callers don't need a mass update.
"""

from app.integrations.config_models import (
    DiscordBotConfig,
    GitHubActionsIntegrationConfig,
    GitLabIntegrationConfig,
    GoogleDocsIntegrationConfig,
    JiraIntegrationConfig,
    LinearIntegrationConfig,
    NotionIntegrationConfig,
    PagerDutyIntegrationConfig,
    SlackBotConfig,
    SlackSearchIntegrationConfig,
    SlackWebhookConfig,
    TelegramBotConfig,
    TracerIntegrationConfig,
    TwilioIntegrationConfig,
    TwilioSMSChannelConfig,
    WhatsAppConfig,
)
from app.integrations.effective_models import (
    EffectiveIntegrationEntry,
    EffectiveIntegrations,
    IntegrationInstance,
)

__all__ = [
    "DiscordBotConfig",
    "EffectiveIntegrationEntry",
    "EffectiveIntegrations",
    "GitHubActionsIntegrationConfig",
    "GitLabIntegrationConfig",
    "GoogleDocsIntegrationConfig",
    "IntegrationInstance",
    "JiraIntegrationConfig",
    "LinearIntegrationConfig",
    "NotionIntegrationConfig",
    "PagerDutyIntegrationConfig",
    "SlackBotConfig",
    "SlackSearchIntegrationConfig",
    "SlackWebhookConfig",
    "TelegramBotConfig",
    "TracerIntegrationConfig",
    "TwilioIntegrationConfig",
    "TwilioSMSChannelConfig",
    "WhatsAppConfig",
]
