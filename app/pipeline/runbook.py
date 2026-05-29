"""Auto-runbook generator — converts a completed investigation into a reusable runbook.

After RCA completes, this module produces a structured Markdown runbook that documents
the failure pattern, detection signals, investigation playbook, and remediation steps.
Runbooks are stored in ~/.opensore/runbooks/ and indexed by root_cause_category + alert name.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_RUNBOOK_DIR = Path.home() / ".opensore" / "runbooks"


def _runbook_dir() -> Path:
    _RUNBOOK_DIR.mkdir(parents=True, exist_ok=True)
    return _RUNBOOK_DIR


def _slugify(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def generate_runbook(state: dict[str, Any]) -> dict[str, Any]:
    """Generate and persist a runbook from a completed investigation state.

    Returns a dict with 'runbook_path', 'runbook_md', and 'runbook_id'.
    """
    alert_name = str(state.get("alert_name") or state.get("name") or "unknown-alert")
    root_cause = str(state.get("root_cause") or "")
    root_cause_category = str(state.get("root_cause_category") or "unknown")
    causal_chain: list[str] = state.get("causal_chain") or []
    remediation_steps: list[str] = state.get("remediation_steps") or []
    validated_claims: list[dict] = state.get("validated_claims") or []
    non_validated_claims: list[dict] = state.get("non_validated_claims") or []
    validity_score: float = float(state.get("validity_score") or 0.0)
    raw_alert: dict[str, Any] = state.get("raw_alert") or {}
    evidence_entries: list[dict] = state.get("evidence_entries") or []

    now = datetime.now(tz=UTC)
    runbook_id = hashlib.sha1(
        f"{alert_name}:{root_cause_category}:{now.isoformat()}".encode()
    ).hexdigest()[:12]

    slug = _slugify(f"{root_cause_category}-{alert_name}")
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{slug}-{runbook_id}.md"

    runbook_md = _render_runbook(
        alert_name=alert_name,
        root_cause=root_cause,
        root_cause_category=root_cause_category,
        causal_chain=causal_chain,
        remediation_steps=remediation_steps,
        validated_claims=validated_claims,
        non_validated_claims=non_validated_claims,
        validity_score=validity_score,
        raw_alert=raw_alert,
        evidence_entries=evidence_entries,
        runbook_id=runbook_id,
        generated_at=now,
    )

    runbook_path = _runbook_dir() / filename
    runbook_path.write_text(runbook_md, encoding="utf-8")

    _update_index(
        runbook_id=runbook_id,
        filename=filename,
        alert_name=alert_name,
        root_cause_category=root_cause_category,
        generated_at=now,
        validity_score=validity_score,
    )

    logger.info("[runbook] saved %s", runbook_path)
    return {
        "runbook_id": runbook_id,
        "runbook_path": str(runbook_path),
        "runbook_md": runbook_md,
    }


def _render_runbook(
    *,
    alert_name: str,
    root_cause: str,
    root_cause_category: str,
    causal_chain: list[str],
    remediation_steps: list[str],
    validated_claims: list[dict],
    non_validated_claims: list[dict],
    validity_score: float,
    raw_alert: dict[str, Any],
    evidence_entries: list[dict],
    runbook_id: str,
    generated_at: datetime,
) -> str:
    lines: list[str] = []

    lines += [
        f"# Runbook: {alert_name}",
        "",
        f"> **Generated:** {generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"> **Runbook ID:** `{runbook_id}`  ",
        f"> **Root Cause Category:** `{root_cause_category}`  ",
        f"> **Confidence:** {validity_score:.0%}",
        "",
        "---",
        "",
        "## 1. Root Cause Summary",
        "",
        root_cause or "_No root cause recorded._",
        "",
    ]

    if causal_chain:
        lines += ["## 2. Causal Chain", ""]
        for i, step in enumerate(causal_chain, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    if remediation_steps:
        lines += ["## 3. Remediation Playbook", ""]
        for i, step in enumerate(remediation_steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    lines += [
        "## 4. Detection Signals",
        "",
        "The following alert triggered this investigation:",
        "",
    ]
    if raw_alert:
        service = raw_alert.get("service") or raw_alert.get("resource") or ""
        env = raw_alert.get("environment") or raw_alert.get("env") or ""
        severity = raw_alert.get("severity") or raw_alert.get("urgency") or ""
        if service:
            lines.append(f"- **Service / Resource:** {service}")
        if env:
            lines.append(f"- **Environment:** {env}")
        if severity:
            lines.append(f"- **Severity:** {severity}")
    lines += [f"- **Alert Name:** {alert_name}", ""]

    if evidence_entries:
        lines += ["## 5. Evidence Collected", ""]
        for entry in evidence_entries[:10]:
            tool = entry.get("tool") or entry.get("source") or "unknown"
            summary = entry.get("summary") or entry.get("result_summary") or ""
            if summary:
                lines.append(f"- **{tool}:** {summary}")
        lines.append("")

    validated = [c.get("claim", "") for c in validated_claims if c.get("claim")]
    unvalidated = [c.get("claim", "") for c in non_validated_claims if c.get("claim")]

    if validated:
        lines += ["## 6. Validated Claims", ""]
        for c in validated:
            lines.append(f"- ✓ {c}")
        lines.append("")

    if unvalidated:
        lines += ["## 7. Unvalidated Claims", ""]
        for c in unvalidated:
            lines.append(f"- ? {c}")
        lines.append("")

    lines += [
        "## 8. Prevention & Monitoring",
        "",
        "- [ ] Add or tune alert thresholds based on this incident's signals",
        "- [ ] Review remediation steps above and automate where possible",
        "- [ ] Schedule a post-mortem if severity was P1/P2",
        "- [ ] Update this runbook after the next occurrence",
        "",
        "---",
        "",
        f"_Auto-generated by opensore · {generated_at.strftime('%Y-%m-%d %H:%M UTC')}_",
    ]

    return "\n".join(lines)


def _update_index(
    *,
    runbook_id: str,
    filename: str,
    alert_name: str,
    root_cause_category: str,
    generated_at: datetime,
    validity_score: float,
) -> None:
    index_path = _runbook_dir() / "index.json"
    try:
        index: list[dict[str, Any]] = (
            json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        )
    except Exception:
        index = []

    index.insert(
        0,
        {
            "runbook_id": runbook_id,
            "filename": filename,
            "alert_name": alert_name,
            "root_cause_category": root_cause_category,
            "generated_at": generated_at.isoformat(),
            "validity_score": validity_score,
        },
    )
    index = index[:500]
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def list_runbooks(
    category: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent runbook index entries, optionally filtered by category."""
    index_path = _runbook_dir() / "index.json"
    if not index_path.exists():
        return []
    try:
        entries: list[dict[str, Any]] = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if category:
        entries = [e for e in entries if e.get("root_cause_category") == category]
    return entries[:limit]


def load_runbook(runbook_id: str) -> str | None:
    """Load the raw Markdown content of a runbook by ID."""
    index_path = _runbook_dir() / "index.json"
    if not index_path.exists():
        return None
    try:
        entries: list[dict[str, Any]] = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    for entry in entries:
        if entry.get("runbook_id") == runbook_id:
            path = _runbook_dir() / str(entry["filename"])
            if path.exists():
                return str(path.read_text(encoding="utf-8"))
    return None
