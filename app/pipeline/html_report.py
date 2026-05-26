"""Investigation HTML report generator — produces shareable standalone reports.

Call ``generate_html_report(state, runbook_md)`` to get an HTML string, or
``export_runbook_as_html(runbook_id)`` to load a runbook by ID and write it to disk.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
from typing import Any

_CSS = """\
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem; color: #1a1a2e;
         background: #f0f2f5; line-height: 1.6; }
  h1 { color: #16213e; border-bottom: 3px solid #0f3460; padding-bottom: .5rem;
       font-size: 1.7rem; margin-bottom: .5rem; }
  h2 { color: #0f3460; margin-top: 2rem; font-size: 1.25rem; }
  h3 { color: #533483; font-size: 1.05rem; }
  .card { background: #fff; border: 1px solid #dde1e7; border-radius: 10px;
          padding: 1.25rem 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .meta-grid { display: grid; grid-template-columns: 160px 1fr; gap: .3rem .8rem; }
  .meta-label { font-weight: 600; color: #495057; }
  .badge { display: inline-block; padding: .15rem .55rem; border-radius: 4px;
           font-size: .78rem; font-weight: 700; letter-spacing: .02em; }
  .badge-critical { background: #fde8e8; color: #c0392b; }
  .badge-high     { background: #fff3cd; color: #856404; }
  .badge-medium   { background: #d4edda; color: #155724; }
  .badge-low      { background: #e8ecf0; color: #495057; }
  .score          { font-size: 1.5rem; font-weight: 800; color: #0f3460; }
  pre  { background: #1e1e2e; color: #cdd6f4; padding: 1.1rem; border-radius: 8px;
         overflow-x: auto; font-size: .84rem; line-height: 1.55; margin: .8rem 0; }
  code { background: #eef0f3; padding: .1rem .35rem; border-radius: 3px; font-size: .88em; }
  pre code { background: transparent; padding: 0; }
  .runbook-body { line-height: 1.7; }
  .runbook-body h1, .runbook-body h2, .runbook-body h3 { margin-top: 1.4rem; }
  .similar-item { border-left: 4px solid #0f3460; padding: .65rem 1rem; margin-bottom: .5rem;
                  border-radius: 0 6px 6px 0; background: #f8f9ff; }
  .step { display: flex; gap: .8rem; padding: .4rem 0; align-items: flex-start; }
  .step-num { background: #0f3460; color: #fff; border-radius: 50%; min-width: 26px;
              height: 26px; display: flex; align-items: center; justify-content: center;
              font-size: .75rem; font-weight: 700; flex-shrink: 0; margin-top: .1rem; }
  .footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #dde1e7;
            color: #868e96; font-size: .82rem; text-align: center; }
  ul { padding-left: 1.4rem; }
  li { margin-bottom: .3rem; }
  blockquote { border-left: 4px solid #0f3460; margin: .8rem 0; padding: .5rem 1rem;
               color: #495057; background: #f8f9ff; border-radius: 0 6px 6px 0; }
  a { color: #0f3460; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #dde1e7; padding: .4rem .7rem; text-align: left; }
  th { background: #f0f2f5; }
</style>"""


# ── minimal Markdown → HTML converter (no external deps) ────────────────────

_CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.S)
_H3 = re.compile(r"^### (.+)$", re.M)
_H2 = re.compile(r"^## (.+)$", re.M)
_H1 = re.compile(r"^# (.+)$", re.M)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"\*(.+?)\*")
_CODE_INLINE = re.compile(r"`([^`]+)`")
_BLOCKQUOTE = re.compile(r"^> (.+)$", re.M)
_UL = re.compile(r"^[-*] (.+)$", re.M)
_OL = re.compile(r"^\d+\. (.+)$", re.M)


def _md_to_html(text: str) -> str:
    # Protect code blocks first (escape HTML inside them)
    blocks: list[str] = []

    def _save_block(m: re.Match[str]) -> str:
        idx = len(blocks)
        blocks.append(f"<pre><code>{html.escape(m.group(1).rstrip())}</code></pre>")
        return f"\x00BLOCK{idx}\x00"

    out = _CODE_BLOCK_RE.sub(_save_block, text)
    out = _H3.sub(r"<h3>\1</h3>", out)
    out = _H2.sub(r"<h2>\1</h2>", out)
    out = _H1.sub(r"<h1>\1</h1>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    out = _CODE_INLINE.sub(r"<code>\1</code>", out)
    out = _BLOCKQUOTE.sub(r"<blockquote>\1</blockquote>", out)
    out = _UL.sub(r"<li>\1</li>", out)
    out = _OL.sub(r"<li>\1</li>", out)

    # Wrap consecutive <li> in <ul>
    out = re.sub(r"(<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", out, flags=re.S)

    # Wrap bare text lines in <p>
    lines = out.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("<") and "\x00BLOCK" not in stripped:
            result.append(f"<p>{stripped}</p>")
        else:
            result.append(line)
    out = "\n".join(result)

    # Restore code blocks
    for i, block in enumerate(blocks):
        out = out.replace(f"\x00BLOCK{i}\x00", block)
    return out


# ── report generator ─────────────────────────────────────────────────────────


def generate_html_report(state: dict[str, Any], runbook_md: str = "") -> str:
    """Render an investigation state dict and optional runbook Markdown into standalone HTML."""
    from datetime import UTC, datetime

    alert_name = html.escape(str(state.get("alert_name") or "Incident"))
    root_cause = str(state.get("root_cause") or "")
    category = html.escape(str(state.get("root_cause_category") or "unknown"))
    severity = str(
        state.get("severity")
        or (state.get("raw_alert") or {}).get("severity")
        or "unknown"
    ).lower()
    score = float(state.get("validity_score") or 0.0)
    remediation = list(state.get("remediation_steps") or [])
    similar = list(state.get("similar_incidents") or [])
    runbook_id = html.escape(str(state.get("runbook_id") or ""))
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    badge_class = {
        "critical": "badge-critical",
        "high": "badge-high",
        "medium": "badge-medium",
        "low": "badge-low",
    }.get(severity, "badge-low")

    runbook_html = (
        f'<div class="runbook-body">{_md_to_html(runbook_md)}</div>'
        if runbook_md
        else "<p><em>No runbook content available.</em></p>"
    )

    steps_html = ""
    for i, step in enumerate(remediation, 1):
        steps_html += (
            f'<div class="step">'
            f'<div class="step-num">{i}</div>'
            f"<div>{html.escape(str(step))}</div>"
            f"</div>\n"
        )
    if not steps_html:
        steps_html = "<p><em>No remediation steps recorded.</em></p>"

    similar_html = ""
    for s in similar[:5]:
        sid = html.escape(str(s.get("runbook_id", "")))
        sname = html.escape(str(s.get("alert_name", "")))
        sscore = float(s.get("similarity_score", 0))
        scat = html.escape(str(s.get("root_cause_category", "")))
        similar_html += (
            f'<div class="similar-item">'
            f"<strong>{sname}</strong>&ensp;"
            f"<small style='color:#868e96'>{scat}</small>&ensp;"
            f'<span class="badge badge-low">{sscore:.0%} match</span>&ensp;'
            f"<small style='color:#adb5bd'>{sid}</small>"
            f"</div>\n"
        )
    if not similar_html:
        similar_html = "<p><em>No similar past incidents found.</em></p>"

    raw_json = json.dumps(dict(state.get("raw_alert") or {}), indent=2, default=str)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RCA — {alert_name}</title>
{_CSS}
</head>
<body>

<h1>RCA Report — {alert_name}</h1>

<div class="card">
  <div class="meta-grid">
    <span class="meta-label">Alert</span><span><strong>{alert_name}</strong></span>
    <span class="meta-label">Severity</span><span><span class="badge {badge_class}">{severity}</span></span>
    <span class="meta-label">Category</span><span>{category}</span>
    <span class="meta-label">Confidence</span><span><span class="score">{score:.0%}</span></span>
    <span class="meta-label">Runbook ID</span><span><code>{runbook_id}</code></span>
    <span class="meta-label">Generated</span><span>{generated}</span>
  </div>
</div>

<h2>Root Cause</h2>
<div class="card">
  {f"<p>{html.escape(root_cause)}</p>" if root_cause else "<p><em>Root cause not determined.</em></p>"}
</div>

<h2>Remediation Steps</h2>
<div class="card">
  {steps_html}
</div>

<h2>Investigation Runbook</h2>
<div class="card">
  {runbook_html}
</div>

<h2>Similar Past Incidents</h2>
<div class="card">
  {similar_html}
</div>

<h2>Raw Alert Payload</h2>
<pre><code>{html.escape(raw_json)}</code></pre>

<div class="footer">
  Generated by <strong>opensore</strong> &middot; {generated}
</div>

</body>
</html>"""


def export_runbook_as_html(
    runbook_id: str,
    output_path: pathlib.Path | None = None,
) -> tuple[str, pathlib.Path]:
    """Load a runbook by ID and export it as standalone HTML.

    Returns ``(html_string, written_path)``.
    """
    from app.pipeline.runbook import _RUNBOOK_DIR, load_runbook

    md = load_runbook(runbook_id)
    if md is None:
        raise FileNotFoundError(f"Runbook '{runbook_id}' not found.")

    # Load index entry for metadata (non-fatal)
    state: dict[str, Any] = {}
    index_path = _RUNBOOK_DIR / "index.json"
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
            for entry in entries:
                if entry.get("runbook_id") == runbook_id:
                    state = dict(entry)
                    break
        except Exception:
            pass

    report_html = generate_html_report(state, runbook_md=md)

    if output_path is None:
        output_path = _RUNBOOK_DIR / f"{runbook_id}.html"

    output_path.write_text(report_html, encoding="utf-8")
    return report_html, output_path
