"""Shared integration catalog for normalization and resolution."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.config import get_tracer_base_url
from app.integrations.config_models import (
    DiscordBotConfig,
    JiraIntegrationConfig,
    SlackWebhookConfig,
    TelegramBotConfig,
    TwilioIntegrationConfig,
    WhatsAppConfig,
)
from app.integrations.effective_models import EffectiveIntegrations
from app.integrations.github_mcp import build_github_mcp_config
from app.integrations.gitlab import DEFAULT_GITLAB_BASE_URL, build_gitlab_config
from app.integrations.openclaw import build_openclaw_config
from app.integrations.registry import (
    DIRECT_CLASSIFIED_EFFECTIVE_SERVICES,
    SKIP_CLASSIFIED_SERVICES,
    family_key,
    service_key,
)
from app.integrations.store import _STRUCTURAL_RECORD_FIELDS, load_integrations
from app.llm_credentials import resolve_env_credential
from app.utils.coercion import safe_int
from app.utils.errors import report_exception

logger = logging.getLogger(__name__)


def _report_classify_failure(exc: BaseException, *, integration: str, record_id: str) -> None:
    """Route a per-instance classify failure to Sentry + warning log.

    Replaces the historic ``except Exception: return None, None`` pattern in
    ``_classify_service_instance``: the caller still gets ``(None, None)``
    and skips the integration, but the failure is now visible to operators
    instead of being silently swallowed (#1468).
    """
    report_exception(
        exc,
        logger=logger,
        message=f"classify_failed: integration={integration} record_id={record_id}",
        severity="warning",
        tags={
            "surface": "integration",
            "component": "app.integrations._catalog_impl",
            "integration": integration,
            "event": "classify_failed",
        },
        extras={"record_id": record_id},
    )


def _report_env_loader_failure(exc: BaseException, *, integration: str) -> None:
    """Route a per-vendor env-loader failure to Sentry + warning log.

    Replaces ``except Exception: pass`` and ``logger.debug(..., exc_info=True)``
    paths in ``load_env_integrations``: integration is still skipped, but the
    misconfiguration reaches Sentry rather than being lost to debug output
    (#1468).
    """
    report_exception(
        exc,
        logger=logger,
        message=f"env_loader_failed: integration={integration}",
        severity="warning",
        tags={
            "surface": "integration",
            "component": "app.integrations._catalog_impl",
            "integration": integration,
            "event": "env_loader_failed",
        },
    )


def _should_publish_instance_siblings(instances: object) -> bool:
    """Return whether an effective integration should expose its ``instances`` list."""
    if not isinstance(instances, list) or not instances:
        return False
    if len(instances) > 1:
        return True
    return str(instances[0].get("name", "default")) != "default"


def _record_instances(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a record (v1 or v2 shape) into a list of instance dicts.

    v2 records return their ``instances`` list directly. v1 records are
    migrated on the fly: ``credentials`` plus every non-structural top-level
    field (e.g. AWS ``role_arn``) become the single ``default`` instance's
    credentials. This matches the v1→v2 store migration so downstream
    classification logic reads ONE uniform shape.
    """
    if isinstance(record.get("instances"), list):
        return [inst if isinstance(inst, dict) else {} for inst in record["instances"]]
    credentials = dict(record.get("credentials", {}))
    for key, value in record.items():
        if key in _STRUCTURAL_RECORD_FIELDS or key == "credentials":
            continue
        credentials.setdefault(key, value)
    return [{"name": "default", "tags": {}, "credentials": credentials}]


def classify_integrations(integrations: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify active integrations by service into normalized runtime configs.

    Backward compat: for each ``service``, ``resolved[service]`` is the flat
    config dict of the DEFAULT (first) instance, matching the pre-multi-instance
    contract. When multiple instances exist (or an instance has an explicit
    non-``default`` name), a sibling key ``_all_{service}_instances`` carries
    all of them as ``[{name, tags, config, integration_id}, ...]``. See
    ``app/integrations/selectors.py`` for consumers.
    """
    resolved: dict[str, Any] = {}
    all_instances: dict[str, list[dict[str, Any]]] = {}

    active = [integration for integration in integrations if integration.get("status") == "active"]

    for integration in active:
        service = str(integration.get("service") or "").strip()
        if not service:
            continue

        service_lower = service.lower()
        if service_lower in SKIP_CLASSIFIED_SERVICES:
            continue

        key = service_key(service_lower)
        record_id = str(integration.get("id", "")).strip()

        for instance in _record_instances(integration):
            credentials = instance.get("credentials", {}) or {}
            instance_name = str(instance.get("name", "default")).strip().lower() or "default"
            instance_tags = instance.get("tags", {}) or {}
            flat_view, flat_key = _classify_service_instance(key, credentials, record_id=record_id)
            if flat_view is None or flat_key is None:
                continue
            resolved.setdefault(flat_key, flat_view)
            # Bucket under the family key so related classifier outputs share
            # one _all_<family>_instances list.
            all_instances.setdefault(family_key(flat_key), []).append(
                {
                    "name": instance_name,
                    "tags": instance_tags,
                    "config": flat_view,
                    "integration_id": record_id,
                }
            )

    for service, instances in all_instances.items():
        if len(instances) > 1 or (instances and instances[0]["name"] != "default"):
            resolved[f"_all_{service}_instances"] = instances

    resolved["_all"] = active
    return resolved


def _classify_service_instance(
    key: str, credentials: dict[str, Any], *, record_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Classify one instance into (flat_view, resolved_key).

    Returns ``(None, None)`` when the instance is invalid or should be skipped
    (e.g. required field missing).
    """
    if key == "github":
        try:
            github_config = build_github_mcp_config(
                {
                    "url": credentials.get("url", ""),
                    "mode": credentials.get("mode", "streamable-http"),
                    "command": credentials.get("command", ""),
                    "args": credentials.get("args", []),
                    "auth_token": credentials.get("auth_token", ""),
                    "toolsets": credentials.get("toolsets", []),
                    "integration_id": record_id,
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        return github_config.model_dump(), "github"

    if key == "gitlab":
        try:
            gitlab_config = build_gitlab_config(
                {
                    "base_url": credentials.get("base_url", ""),
                    "auth_token": credentials.get("auth_token", ""),
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        return gitlab_config.model_dump(), "gitlab"

    if key == "bitbucket":
        workspace = str(credentials.get("workspace", "")).strip()
        if not workspace:
            return None, None
        base_url = (
            str(credentials.get("base_url", "https://api.bitbucket.org/2.0")).strip()
            or "https://api.bitbucket.org/2.0"
        )
        return {
            "workspace": workspace,
            "username": str(credentials.get("username", "")).strip(),
            "app_password": str(credentials.get("app_password", "")).strip(),
            "base_url": base_url,
            "max_results": max(1, min(safe_int(credentials.get("max_results", 25), 25), 100)),
            "integration_id": record_id,
        }, "bitbucket"

    if key == "jira":
        try:
            jira_config = JiraIntegrationConfig.model_validate(
                {
                    "base_url": credentials.get("base_url", ""),
                    "email": credentials.get("email", ""),
                    "api_token": credentials.get("api_token", ""),
                    "project_key": credentials.get("project_key", ""),
                    "integration_id": record_id,
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        if jira_config.base_url and jira_config.email and jira_config.api_token:
            return jira_config.model_dump(), "jira"
        return None, None

    if key == "discord":
        try:
            discord_config = DiscordBotConfig.model_validate(
                {
                    "bot_token": credentials.get("bot_token", ""),
                    "application_id": credentials.get("application_id", ""),
                    "public_key": credentials.get("public_key", ""),
                    "default_channel_id": credentials.get("default_channel_id"),
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        if discord_config.bot_token:
            return discord_config.model_dump(), "discord"
        return None, None

    if key == "telegram":
        try:
            tg_config = TelegramBotConfig.model_validate(
                {
                    "bot_token": credentials.get("bot_token", ""),
                    "default_chat_id": credentials.get("default_chat_id"),
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        if tg_config.bot_token:
            return tg_config.model_dump(), "telegram"
        return None, None

    if key == "whatsapp":
        try:
            wa_config = WhatsAppConfig.model_validate(
                {
                    "account_sid": credentials.get("account_sid", ""),
                    "auth_token": credentials.get("auth_token", ""),
                    "from_number": credentials.get("from_number", ""),
                    "default_to": credentials.get("default_to"),
                }
            )
        except Exception:
            return None, None
        return wa_config.model_dump(), "whatsapp"

    if key == "twilio":
        try:
            twilio_config = TwilioIntegrationConfig.model_validate(
                {
                    "account_sid": credentials.get("account_sid", ""),
                    "auth_token": credentials.get("auth_token", ""),
                    "sms": credentials.get("sms", {}),
                    "integration_id": record_id,
                }
            )
        except Exception:
            return None, None
        return twilio_config.model_dump(), "twilio"

    if key == "openclaw":
        try:
            openclaw_config = build_openclaw_config(
                {
                    "url": credentials.get("url", ""),
                    "mode": credentials.get("mode", "streamable-http"),
                    "command": credentials.get("command", ""),
                    "args": credentials.get("args", []),
                    "auth_token": credentials.get("auth_token", ""),
                    "integration_id": record_id,
                }
            )
        except Exception as exc:
            _report_classify_failure(exc, integration=key, record_id=record_id)
            return None, None
        if openclaw_config.is_configured:
            config_dict = openclaw_config.model_dump()
            config_dict["connection_verified"] = True
            return config_dict, "openclaw"
        return None, None

    # Fallback for unknown services: pass through credentials + record id.
    return {"credentials": credentials, "integration_id": record_id}, key


def _parse_instances_env(env_name: str, service: str) -> dict[str, Any] | None:
    """Parse ``<SERVICE>_INSTANCES`` env var into a v2 integration record.

    Accepts a JSON array of instance entries. Each entry may be either
    ``{"name": ..., "tags": {...}, "credentials": {...}}`` or a flat
    ``{"name": ..., "tags": {...}, <field>: <value>, ...}`` — we accept
    both shapes and normalize to ``credentials``. Returns None if the env
    var is unset, empty, invalid JSON, or not a non-empty list (logs a
    warning on parse failure so callers can fall through to legacy vars).

    Critical: always returns a SINGLE record with multiple instances inside,
    never multiple records — otherwise ``merge_integrations_by_service``
    would drop all but one (PR #527 bug #2).
    """
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Do NOT include exc.msg or the raw value — JSONDecodeError messages
        # embed a slice of the offending input, which could leak a fragment
        # of an API key if the env var was accidentally populated with a
        # credential instead of a JSON array. Log only position + line/col.
        logger.warning(
            "%s is not valid JSON (parse failed at line %d col %d); falling back to legacy vars",
            env_name,
            exc.lineno,
            exc.colno,
        )
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    instances: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        nested_creds = entry.get("credentials")
        if isinstance(nested_creds, dict):
            credentials = dict(nested_creds)
        else:
            credentials = {k: v for k, v in entry.items() if k not in {"name", "tags"}}
        name = str(entry.get("name", "default")).strip().lower() or "default"
        tags = entry.get("tags") if isinstance(entry.get("tags"), dict) else {}
        instances.append({"name": name, "tags": tags, "credentials": credentials})
    if not instances:
        return None
    return {
        "id": f"env-{service}",
        "service": service,
        "status": "active",
        "instances": instances,
    }


def _active_env_record(
    service: str,
    credentials: dict[str, Any],
    *,
    record_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": record_id or f"env-{service.replace('_', '-')}",
        "service": service,
        "status": "active",
        **extra,
        "credentials": credentials,
    }


def load_env_integrations() -> list[dict[str, Any]]:
    """Build integration records from local environment variables."""
    integrations: list[dict[str, Any]] = []

    github_mode = os.getenv("GITHUB_MCP_MODE", "streamable-http").strip() or "streamable-http"
    github_url = os.getenv("GITHUB_MCP_URL", "").strip()
    github_command = os.getenv("GITHUB_MCP_COMMAND", "").strip()
    github_args = os.getenv("GITHUB_MCP_ARGS", "").strip()
    github_auth_token = os.getenv("GITHUB_MCP_AUTH_TOKEN", "").strip()
    github_toolsets = os.getenv("GITHUB_MCP_TOOLSETS", "").strip()
    if (github_mode == "stdio" and github_command) or (github_mode != "stdio" and github_url):
        github_config = build_github_mcp_config(
            {
                "url": github_url,
                "mode": github_mode,
                "command": github_command,
                "args": [part for part in github_args.split() if part],
                "auth_token": github_auth_token,
                "toolsets": [part.strip() for part in github_toolsets.split(",") if part.strip()],
            }
        )
        integrations.append(
            _active_env_record(
                "github",
                github_config.model_dump(exclude={"integration_id"}),
            )
        )

    gitlab_access_token = resolve_env_credential("GITLAB_ACCESS_TOKEN")
    if gitlab_access_token:
        gitlab_config = build_gitlab_config(
            {
                "base_url": os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL).strip()
                or DEFAULT_GITLAB_BASE_URL,
                "auth_token": gitlab_access_token,
            }
        )
        integrations.append(_active_env_record("gitlab", gitlab_config.model_dump()))

    bitbucket_workspace = os.getenv("BITBUCKET_WORKSPACE", "").strip()
    if bitbucket_workspace:
        integrations.append(
            _active_env_record(
                "bitbucket",
                {
                    "workspace": bitbucket_workspace,
                    "username": os.getenv("BITBUCKET_USERNAME", "").strip(),
                    "app_password": os.getenv("BITBUCKET_APP_PASSWORD", "").strip(),
                    "base_url": os.getenv(
                        "BITBUCKET_BASE_URL", "https://api.bitbucket.org/2.0"
                    ).strip()
                    or "https://api.bitbucket.org/2.0",
                    "max_results": safe_int(os.getenv("BITBUCKET_MAX_RESULTS", "25"), 25),
                },
            )
        )

    jira_base_url = os.getenv("JIRA_BASE_URL", "").strip()
    jira_email = os.getenv("JIRA_EMAIL", "").strip()
    jira_api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "").strip()
    if jira_base_url and jira_email and jira_api_token:
        try:
            jira_config = JiraIntegrationConfig.model_validate(
                {
                    "base_url": jira_base_url,
                    "email": jira_email,
                    "api_token": jira_api_token,
                    "project_key": jira_project_key,
                }
            )
        except Exception as exc:
            _report_env_loader_failure(exc, integration="jira")
        else:
            integrations.append(
                _active_env_record(
                    "jira",
                    jira_config.model_dump(exclude={"integration_id"}),
                )
            )

    discord_bot_token = resolve_env_credential("DISCORD_BOT_TOKEN")
    if discord_bot_token:
        try:
            discord_config = DiscordBotConfig.model_validate(
                {
                    "bot_token": discord_bot_token,
                    "application_id": os.getenv("DISCORD_APPLICATION_ID", "").strip(),
                    "public_key": os.getenv("DISCORD_PUBLIC_KEY", "").strip(),
                    "default_channel_id": os.getenv("DISCORD_DEFAULT_CHANNEL_ID", "").strip()
                    or None,
                }
            )
        except Exception as exc:
            _report_env_loader_failure(exc, integration="discord")
        else:
            integrations.append(_active_env_record("discord", discord_config.model_dump()))

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if telegram_bot_token:
        try:
            tg_config = TelegramBotConfig.model_validate(
                {
                    "bot_token": telegram_bot_token,
                    "default_chat_id": os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "").strip() or None,
                }
            )
        except Exception as exc:
            _report_env_loader_failure(exc, integration="telegram")
        else:
            integrations.append(_active_env_record("telegram", tg_config.model_dump()))

    # Shared Twilio account credentials — consumed by both the WhatsApp and
    # the SMS env-bootstrap blocks below.
    twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

    whatsapp_from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    if twilio_account_sid and twilio_auth_token and whatsapp_from_number:
        wa_config = WhatsAppConfig.model_validate(
            {
                "account_sid": twilio_account_sid,
                "auth_token": twilio_auth_token,
                "from_number": whatsapp_from_number,
                "default_to": os.getenv("WHATSAPP_DEFAULT_TO", "").strip() or None,
            }
        )
        integrations.append(_active_env_record("whatsapp", wa_config.model_dump()))

    # Twilio SMS integration — independent of the legacy WhatsApp record.
    # Hydrated when account+token are present AND an SMS sender is set
    # (a from_number or a Messaging Service SID).
    twilio_sms_from = os.getenv("TWILIO_SMS_FROM", "").strip()
    twilio_sms_messaging_service = os.getenv("TWILIO_SMS_MESSAGING_SERVICE_SID", "").strip()
    if (
        twilio_account_sid
        and twilio_auth_token
        and (twilio_sms_from or twilio_sms_messaging_service)
    ):
        twilio_payload: dict[str, Any] = {
            "account_sid": twilio_account_sid,
            "auth_token": twilio_auth_token,
            "sms": {
                "enabled": True,
                "from_number": twilio_sms_from,
                "messaging_service_sid": twilio_sms_messaging_service,
                "default_to": os.getenv("TWILIO_SMS_DEFAULT_TO", "").strip() or None,
            },
        }
        try:
            twilio_config = TwilioIntegrationConfig.model_validate(twilio_payload)
        except Exception:
            twilio_config = None
        if twilio_config is not None:
            integrations.append(
                _active_env_record(
                    "twilio",
                    twilio_config.model_dump(exclude={"integration_id"}),
                )
            )

    openclaw_url = os.getenv("OPENCLAW_MCP_URL", "").strip()
    openclaw_command = os.getenv("OPENCLAW_MCP_COMMAND", "").strip()
    openclaw_mode = os.getenv("OPENCLAW_MCP_MODE", "streamable-http").strip().lower()
    openclaw_mode = openclaw_mode or "streamable-http"
    if (openclaw_mode == "stdio" and openclaw_command) or (
        openclaw_mode != "stdio" and openclaw_url
    ):
        try:
            openclaw_config = build_openclaw_config(
                {
                    "url": openclaw_url,
                    "mode": openclaw_mode,
                    "command": openclaw_command,
                    "args": [
                        part for part in os.getenv("OPENCLAW_MCP_ARGS", "").strip().split() if part
                    ],
                    "auth_token": resolve_env_credential("OPENCLAW_MCP_AUTH_TOKEN"),
                }
            )
            integrations.append(
                _active_env_record(
                    "openclaw",
                    {
                        **openclaw_config.model_dump(exclude={"integration_id"}),
                        "connection_verified": True,
                    },
                )
            )
        except Exception as exc:
            _report_env_loader_failure(exc, integration="openclaw")

    return integrations


def merge_local_integrations(
    store_integrations: list[dict[str, Any]],
    env_integrations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge local store and env integrations, preferring store entries by service."""
    return merge_integrations_by_service(env_integrations, store_integrations)


def merge_integrations_by_service(
    *integration_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge integration records by service, letting later groups override earlier ones."""
    merged_by_service: dict[str, dict[str, Any]] = {}
    for integration_group in integration_groups:
        for integration in integration_group:
            service = str(integration.get("service", "")).strip()
            if service:
                merged_by_service[service] = integration
    return list(merged_by_service.values())


def _effective_entry(source: str, config: dict[str, Any]) -> dict[str, Any]:
    return {"source": source, "config": config}


def _publish_classified_effective_service(
    effective: dict[str, dict[str, Any]],
    classified_integrations: dict[str, Any],
    source_by_service: dict[str, str],
    service: str,
) -> None:
    """Copy a directly classified service into the effective view."""
    resolved_integration = classified_integrations.get(service)
    if not isinstance(resolved_integration, dict):
        return

    effective[service] = _effective_entry(
        source_by_service.get(service, "local env"),
        resolved_integration,
    )
    all_instances = classified_integrations.get(f"_all_{service}_instances")
    if _should_publish_instance_siblings(all_instances):
        effective[service]["instances"] = all_instances


def _service_metadata(
    store_integrations: list[dict[str, Any]],
    env_integrations: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    source_by_service: dict[str, str] = {}
    store_integration_by_service: dict[str, dict[str, Any]] = {}

    for integration in env_integrations:
        service = str(integration.get("service", "")).strip().lower()
        if service:
            source_by_service[service] = "local env"

    for integration in store_integrations:
        service = str(integration.get("service", "")).strip().lower()
        if service:
            source_by_service[service] = "local store"
            store_integration_by_service.setdefault(service, integration)

    return source_by_service, store_integration_by_service


def _raw_credentials(config: dict[str, Any]) -> dict[str, Any]:
    credentials = config.get("credentials")
    if isinstance(credentials, dict):
        return credentials

    instances = config.get("instances")
    if isinstance(instances, list):
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            instance_credentials = instance.get("credentials")
            if isinstance(instance_credentials, dict):
                return instance_credentials

    return config


def resolve_effective_integrations(
    *,
    store_integrations: list[dict[str, Any]] | None = None,
    env_integrations: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve effective local integrations from ~/.config/opensore and environment variables."""
    store_records = (
        list(store_integrations) if store_integrations is not None else load_integrations()
    )
    env_records = (
        list(env_integrations) if env_integrations is not None else load_env_integrations()
    )
    merged_integrations = merge_local_integrations(store_records, env_records)
    classified_integrations = classify_integrations(merged_integrations)
    source_by_service, store_integration_by_service = _service_metadata(store_records, env_records)

    effective: dict[str, dict[str, Any]] = {}

    for service in DIRECT_CLASSIFIED_EFFECTIVE_SERVICES:
        _publish_classified_effective_service(
            effective,
            classified_integrations,
            source_by_service,
            service,
        )

    tracer_integration = classified_integrations.get("tracer")
    if isinstance(tracer_integration, dict):
        tracer_credentials = _raw_credentials(tracer_integration)
        effective["tracer"] = _effective_entry(
            source_by_service.get("tracer", "local store"),
            {
                "base_url": str(tracer_credentials.get("base_url", "")).strip(),
                "jwt_token": str(tracer_credentials.get("jwt_token", "")).strip(),
            },
        )
    else:
        jwt_token = os.getenv("JWT_TOKEN", "").strip()
        if jwt_token:
            effective["tracer"] = _effective_entry(
                "local env",
                {
                    "base_url": os.getenv("TRACER_API_URL", "").strip() or get_tracer_base_url(),
                    "jwt_token": jwt_token,
                },
            )

    slack_store_integration = store_integration_by_service.get("slack")
    if isinstance(slack_store_integration, dict):
        slack_credentials = _raw_credentials(slack_store_integration)
        webhook_url = str(slack_credentials.get("webhook_url", "")).strip()
        if webhook_url:
            try:
                slack_config = SlackWebhookConfig.model_validate({"webhook_url": webhook_url})
                effective["slack"] = _effective_entry("local store", slack_config.model_dump())
            except Exception:
                # Do NOT include the exception value — Pydantic v2 ValidationError
                # embeds the input_value (here a SlackWebhookConfig containing the
                # webhook_url) in its string representation, and Slack webhook URLs
                # carry a secret token in the path. Log only a static message.
                logger.warning("Slack webhook URL from store is invalid; skipping Slack")
    elif slack_webhook_url := os.getenv("SLACK_WEBHOOK_URL", "").strip():
        try:
            slack_config = SlackWebhookConfig.model_validate({"webhook_url": slack_webhook_url})
            effective["slack"] = _effective_entry("local env", slack_config.model_dump())
        except Exception:
            # See note above: avoid logging the ValidationError which embeds the
            # raw webhook_url (and its secret token).
            logger.warning("SLACK_WEBHOOK_URL is invalid; skipping Slack")

    google_docs_integration = classified_integrations.get("google_docs")
    if isinstance(google_docs_integration, dict):
        google_docs_credentials = _raw_credentials(google_docs_integration)
        effective["google_docs"] = _effective_entry(
            source_by_service.get("google_docs", "local env"),
            {
                "credentials_file": str(
                    google_docs_credentials.get("credentials_file", "")
                ).strip(),
                "folder_id": str(google_docs_credentials.get("folder_id", "")).strip(),
            },
        )
    else:
        credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "").strip()
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if credentials_file and folder_id:
            effective["google_docs"] = _effective_entry(
                "local env",
                {
                    "credentials_file": credentials_file,
                    "folder_id": folder_id,
                },
            )

    known_keys = set(EffectiveIntegrations.model_fields)
    unknown_keys = set(effective) - known_keys
    if unknown_keys:
        logger.warning(
            "resolve_effective_integrations: dropping unrecognised integration key(s): %s",
            sorted(unknown_keys),
        )
    filtered_effective = {k: v for k, v in effective.items() if k in known_keys}
    return EffectiveIntegrations.model_validate(filtered_effective).model_dump(exclude_none=True)
