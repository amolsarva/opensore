"""Central registry for integration metadata and verification dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.integrations._verification_adapters import (
    VerifierFn,
    _verify_bitbucket,
    _verify_discord,
    _verify_github,
    _verify_google_docs,
    _verify_openclaw,
    _verify_slack_without_test,
    _verify_telegram,
    _verify_tracer,
    _verify_twilio,
    _verify_whatsapp,
)


@dataclass(frozen=True)
class IntegrationSpec:
    """Canonical metadata for one integration service."""

    service: str
    aliases: tuple[str, ...] = ()
    family_members: tuple[str, ...] = ()
    classifier: Any | None = None
    env_loader: Any | None = None
    effective_resolver: Any | None = None
    verifier: VerifierFn | None = None
    direct_effective: bool = False
    skip_classification: bool = False
    core_verify: bool = False
    setup_order: int | None = None
    verify_order: int | None = None


INTEGRATION_SPECS: tuple[IntegrationSpec, ...] = (
    IntegrationSpec(
        service="github",
        aliases=("github_mcp",),
        verifier=_verify_github,
        direct_effective=True,
        setup_order=1,
        verify_order=1,
    ),
    IntegrationSpec(
        service="gitlab",
        verifier=None,
        direct_effective=True,
        setup_order=2,
        verify_order=None,
    ),
    IntegrationSpec(
        service="bitbucket",
        verifier=_verify_bitbucket,
        verify_order=3,
    ),
    IntegrationSpec(
        service="slack",
        verifier=_verify_slack_without_test,
        skip_classification=True,
        setup_order=3,
        verify_order=4,
    ),
    IntegrationSpec(
        service="linear",
        verifier=None,
        direct_effective=True,
        setup_order=4,
        verify_order=None,
    ),
    IntegrationSpec(
        service="jira",
        verifier=None,
        direct_effective=True,
        setup_order=5,
        verify_order=None,
    ),
    IntegrationSpec(
        service="google_docs",
        verifier=_verify_google_docs,
        setup_order=6,
        verify_order=5,
    ),
    IntegrationSpec(
        service="openclaw",
        verifier=_verify_openclaw,
        direct_effective=True,
        setup_order=7,
        verify_order=6,
    ),
    IntegrationSpec(
        service="twilio",
        verifier=_verify_twilio,
        direct_effective=True,
        setup_order=8,
        verify_order=7,
    ),
    IntegrationSpec(
        service="discord",
        verifier=_verify_discord,
        direct_effective=True,
        setup_order=9,
        verify_order=8,
    ),
    IntegrationSpec(
        service="telegram",
        verifier=_verify_telegram,
        direct_effective=True,
        setup_order=10,
        verify_order=9,
    ),
    IntegrationSpec(
        service="whatsapp",
        verifier=_verify_whatsapp,
        direct_effective=True,
        setup_order=11,
        verify_order=10,
    ),
    IntegrationSpec(
        service="tracer",
        verifier=_verify_tracer,
        setup_order=12,
        verify_order=11,
    ),
    IntegrationSpec(service="notion"),
)

INTEGRATION_SPECS_BY_SERVICE = {spec.service: spec for spec in INTEGRATION_SPECS}

SERVICE_KEY_MAP: dict[str, str] = {spec.service: spec.service for spec in INTEGRATION_SPECS}
for _spec in INTEGRATION_SPECS:
    for _alias in _spec.aliases:
        SERVICE_KEY_MAP[_alias] = _spec.service

SKIP_CLASSIFIED_SERVICES: frozenset[str] = frozenset(
    spec.service for spec in INTEGRATION_SPECS if spec.skip_classification
)

SERVICE_FAMILY_MAP: dict[str, str] = {spec.service: spec.service for spec in INTEGRATION_SPECS}
for _spec in INTEGRATION_SPECS:
    for _member in _spec.family_members:
        SERVICE_FAMILY_MAP[_member] = _spec.service

DIRECT_CLASSIFIED_EFFECTIVE_SERVICES = tuple(
    spec.service for spec in INTEGRATION_SPECS if spec.direct_effective
)

SUPPORTED_VERIFY_SERVICES = tuple(
    spec.service
    for spec in sorted(
        (candidate for candidate in INTEGRATION_SPECS if candidate.verifier is not None),
        key=lambda candidate: (
            candidate.verify_order if candidate.verify_order is not None else 10_000
        ),
    )
)

SUPPORTED_SETUP_SERVICES = tuple(
    spec.service
    for spec in sorted(
        (candidate for candidate in INTEGRATION_SPECS if candidate.setup_order is not None),
        key=lambda candidate: (
            candidate.setup_order if candidate.setup_order is not None else 10_000
        ),
    )
)

CORE_VERIFY_SERVICES = frozenset(spec.service for spec in INTEGRATION_SPECS if spec.core_verify)


def family_key(service_key: str) -> str:
    """Return the family key used for multi-instance sibling buckets."""
    return SERVICE_FAMILY_MAP.get(service_key, service_key)


def service_key(service_name: str) -> str:
    """Normalize an incoming service label to its canonical registry key."""
    lowered = service_name.strip().lower()
    return SERVICE_KEY_MAP.get(lowered, lowered)
