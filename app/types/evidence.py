"""Evidence source type — the canonical set of data source identifiers."""

from __future__ import annotations

from typing import Literal

EvidenceSource = Literal[
    "storage",
    "knowledge",
    "github",
    "github_actions",
    "gitlab",
    "bitbucket",
    "google_docs",
    "jira",
    "openclaw",
    "slack",
    "linear",
    "twilio",
    "http_probe",
    "broadcast",
    "email",
    "bamboohr",
    "teams",
    "sharepoint",
]
