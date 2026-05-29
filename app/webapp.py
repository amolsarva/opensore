from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Query, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError

from app.config import LLMSettings, get_environment
from app.discovery.models import (
    DiscoveryInvestigationPlan,
    DiscoveryInvestigationRequest,
    DiscoveryKeywordSet,
    build_discovery_plan,
    default_keyword_sets,
    discovery_plan_csv,
)
from app.entrypoints.extension_api import router as extension_router
from app.entrypoints.webhook_api import router as webhook_router
from app.utils.sentry_sdk import init_sentry
from app.version import get_version

init_sentry(entrypoint="webapp")

_REPO_ROOT = Path(__file__).parent.parent


class HealthResponse(BaseModel):
    ok: bool
    version: str
    llm_configured: bool
    env: str
    git_sha: str = ""


app = FastAPI(title="OpenSore Discovery")
app.include_router(extension_router)
app.include_router(webhook_router)


def _llm_configured() -> bool:
    try:
        LLMSettings.from_env()
    except ValidationError:
        return False
    return True


def _get_git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_health_response() -> HealthResponse:
    llm_configured = _llm_configured()

    return HealthResponse(
        ok=llm_configured,
        version=get_version(),
        llm_configured=llm_configured,
        env=get_environment().value,
        git_sha=_get_git_sha(),
    )


# ── Admin / dev endpoints ─────────────────────────────────────────────────────


async def _exec_restart() -> None:
    await asyncio.sleep(0.4)
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn"] + sys.argv[1:])


@app.post("/api/admin/restart")
async def admin_restart() -> dict[str, bool]:
    """Restart the uvicorn process in-place (dev use)."""
    asyncio.create_task(_exec_restart())
    return {"ok": True}


@app.post("/api/admin/update")
def admin_update() -> dict[str, object]:
    """Git pull + uv sync if deps changed; caller should then POST /api/admin/restart."""
    steps: list[dict[str, object]] = []

    r = subprocess.run(
        ["git", "pull", "--ff-only"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    steps.append({
        "cmd": "git pull",
        "stdout": r.stdout.strip(),
        "stderr": r.stderr.strip(),
        "returncode": r.returncode,
    })

    content = b"".join(
        (_REPO_ROOT / f).read_bytes()
        for f in ("pyproject.toml", "uv.lock")
        if (_REPO_ROOT / f).exists()
    )
    current_hash = hashlib.sha256(content).hexdigest()
    stamp = _REPO_ROOT / ".opensore_install_stamp"
    stored_hash = stamp.read_text().strip() if stamp.exists() else ""

    if current_hash != stored_hash:
        r2 = subprocess.run(
            ["uv", "sync", "--frozen", "--extra", "dev"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        steps.append({
            "cmd": "uv sync",
            "stdout": r2.stdout.strip(),
            "stderr": r2.stderr.strip(),
            "returncode": r2.returncode,
        })
        if r2.returncode == 0:
            stamp.write_text(current_hash)
    else:
        steps.append({"cmd": "uv sync", "skipped": True, "reason": "deps unchanged"})

    return {"ok": True, "steps": steps}


@app.get("/api/admin/logs")
def admin_logs(n: int = Query(default=100, le=500)) -> dict[str, list[str]]:
    """Return the last n lines of the web server log."""
    log_path = Path("/tmp/opensore_web.log")
    if not log_path.exists():
        return {"lines": []}
    lines = log_path.read_text(errors="replace").splitlines()
    return {"lines": lines[-n:]}


@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
@app.get("/ok", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    health_response = get_health_response()
    response.status_code = (
        status.HTTP_200_OK if health_response.ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return health_response


@app.get("/ui", response_class=HTMLResponse)
def discovery_ui() -> str:
    """Render the first hosted discovery setup screen.

    The web surface is intentionally static for now: it introduces the new
    product direction and points clients at the no-retention API contracts.
    """

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenSore Discovery</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #f7f4ef; color: #202124; }
    main { max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }
    header { display: grid; gap: 18px; margin-bottom: 36px; }
    h1 { font-size: 44px; line-height: 1.05; margin: 0; letter-spacing: 0; max-width: 780px; }
    p.lead { font-size: 17px; line-height: 1.55; max-width: 760px; margin: 0; }
    .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
    .btn { display: inline-flex; align-items: center; gap: 7px; border: 1px solid #202124;
      background: #202124; color: #fff; padding: 11px 16px; border-radius: 6px;
      text-decoration: none; font-weight: 650; font-size: 14px; cursor: pointer; }
    .btn-secondary { background: transparent; color: #202124; }
    section { border-top: 1px solid #d7d0c5; padding-top: 28px; margin-top: 32px; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    .card { background: #fff; border: 1px solid #ddd5ca; border-radius: 8px; padding: 20px; }
    h2 { margin: 0 0 16px; font-size: 22px; }
    h3 { margin: 0 0 8px; font-size: 16px; }
    p { margin: 0; line-height: 1.6; }
    ul { margin: 0; padding-left: 20px; line-height: 1.75; }
    code { background: #eee8df; padding: 2px 6px; border-radius: 4px; font-size: 13px; font-family: ui-monospace, monospace; }

    /* Extension install card */
    .ext-card { border-radius: 10px; padding: 24px 28px; margin-top: 4px; }
    .ext-card-install { background: #1e1b4b; border: 1px solid #4338ca; color: #c7d2fe; }
    .ext-card-connected { background: #052e16; border: 1px solid #16a34a; color: #bbf7d0; }
    .ext-card-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .ext-icon { font-size: 26px; flex-shrink: 0; }
    .ext-card-title { font-size: 17px; font-weight: 700; color: #e0e7ff; margin: 0 0 3px; }
    .ext-card-connected .ext-card-title { color: #dcfce7; }
    .ext-card-subtitle { font-size: 13px; color: #a5b4fc; margin: 0; }
    .ext-card-connected .ext-card-subtitle { color: #86efac; }
    .steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px; }
    .step { background: rgba(255,255,255,0.07); border: 1px solid rgba(99,102,241,0.3);
      border-radius: 7px; padding: 14px 16px; }
    .step-num { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
      color: #818cf8; margin-bottom: 6px; }
    .step-text { font-size: 13px; color: #e0e7ff; line-height: 1.5; }
    .step-text code { background: rgba(255,255,255,0.12); color: #c7d2fe; }
    .ext-cta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
    .btn-ext-primary { background: #4f46e5; border-color: #4f46e5; color: #fff; }
    .btn-ext-primary:hover { background: #4338ca; border-color: #4338ca; }
    .btn-ext-secondary { background: transparent; border-color: #6366f1; color: #a5b4fc; font-size: 13px; padding: 8px 14px; }
    .connection-list { display: flex; flex-wrap: wrap; gap: 8px; }
    .connection-chip { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.1);
      border: 1px solid rgba(74,222,128,0.4); border-radius: 20px; padding: 4px 12px; font-size: 13px;
      color: #bbf7d0; }

    @media (max-width: 760px) {
      h1 { font-size: 32px; }
      .grid { grid-template-columns: 1fr; }
      .steps { grid-template-columns: 1fr; }
      .ext-card { padding: 18px 20px; }
    }

    /* ── Dev controls bar ─────────────────── */
    .dev-bar {
      display: flex; align-items: center; gap: 12px;
      background: #1e293b; border: 1px solid #334155; border-radius: 10px;
      padding: 12px 18px; margin-bottom: 24px; flex-wrap: wrap;
    }
    .dev-info { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
    .dev-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: .06em; color: #475569; }
    .dev-chip { font-size: 12px; background: #0f172a; border: 1px solid #334155;
      border-radius: 5px; padding: 2px 8px; color: #94a3b8; font-family: ui-monospace, monospace; }
    .dev-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .dev-btn {
      padding: 6px 14px; border: 1px solid #334155; border-radius: 6px;
      background: #0f172a; color: #e2e8f0; font-size: 12px; font-weight: 500;
      cursor: pointer; transition: border-color .12s, background .12s; white-space: nowrap;
    }
    .dev-btn:hover:not(:disabled) { border-color: #6366f1; background: #1e1b4b; color: #c7d2fe; }
    .dev-btn:disabled { opacity: .45; cursor: not-allowed; }
    .dev-btn-primary {
      background: #4f46e5; border-color: #4f46e5; color: #fff;
    }
    .dev-btn-primary:hover:not(:disabled) { background: #4338ca; border-color: #4338ca; }
    .dev-btn-icon { padding: 6px 10px; border: 1px solid #334155; border-radius: 6px;
      background: #0f172a; color: #64748b; font-size: 13px; cursor: pointer;
      transition: border-color .12s, color .12s; }
    .dev-btn-icon:hover { border-color: #475569; color: #94a3b8; }
    .dev-status {
      font-size: 12px; color: #94a3b8; padding: 8px 18px;
      background: #1e293b; border: 1px solid #334155; border-radius: 8px;
      margin-bottom: 16px; line-height: 1.5;
    }
    .dev-status.err { background: #450a0a; border-color: #991b1b; color: #fca5a5; }
    .dev-status.ok  { background: #052e16; border-color: #166534; color: #86efac; }
    .dev-logs {
      background: #0f172a; border: 1px solid #1e293b; border-radius: 8px;
      margin-bottom: 24px; overflow: hidden;
    }
    .dev-logs-header {
      display: flex; align-items: center; gap: 10px; padding: 8px 14px;
      border-bottom: 1px solid #1e293b; font-size: 11px; color: #475569;
    }
    .dev-logs-header span { flex: 1; font-weight: 600; text-transform: uppercase;
      letter-spacing: .06em; }
    .dev-logs-header label { display: flex; align-items: center; gap: 5px;
      cursor: pointer; user-select: none; }
    .dev-btn-sm { padding: 3px 8px; border: 1px solid #1e293b; border-radius: 4px;
      background: transparent; color: #475569; font-size: 10px; cursor: pointer; }
    .dev-btn-sm:hover { border-color: #334155; color: #64748b; }
    .dev-logs-pre {
      margin: 0; padding: 12px 14px; font-size: 11px; line-height: 1.6;
      font-family: ui-monospace, monospace; color: #64748b; max-height: 320px;
      overflow-y: auto; white-space: pre-wrap; word-break: break-all;
    }
  </style>
</head>
<body>
<main>

  <!-- Dev controls bar -->
  <div class="dev-bar" id="dev-bar">
    <div class="dev-info">
      <span class="dev-label">Server</span>
      <span class="dev-chip" id="dev-version">…</span>
      <span class="dev-chip" id="dev-sha">…</span>
    </div>
    <div class="dev-actions">
      <button class="dev-btn" id="btn-restart">↺ Restart</button>
      <button class="dev-btn dev-btn-primary" id="btn-pull-restart">⬇ Pull &amp; Restart</button>
      <button class="dev-btn-icon" id="btn-logs-toggle" title="Toggle server logs">📋</button>
    </div>
  </div>
  <div class="dev-status" id="dev-status" hidden></div>
  <div class="dev-logs" id="dev-logs" hidden>
    <div class="dev-logs-header">
      <span>Server logs</span>
      <label><input type="checkbox" id="logs-auto" checked> Auto-refresh</label>
      <button class="dev-btn-sm" id="btn-logs-clear">Clear view</button>
    </div>
    <pre class="dev-logs-pre" id="dev-logs-pre"></pre>
  </div>

  <header>
    <h1>Workplace misconduct discovery without storing evidence on this host.</h1>
    <p class="lead">Run targeted investigations across communication and work systems for harassment,
    executive misconduct, retaliation, and sexual misconduct matters. Accounts authenticate directly,
    and exports land as CSV files in the user's Google Drive.</p>
    <div class="actions">
      <a class="btn btn-secondary" href="/api/discovery/default-keywords">View keyword seeds</a>
      <a class="btn btn-secondary" href="/api/discovery/schema">API schema</a>
    </div>
  </header>

  <!-- Extension: install state (shown when extension absent) -->
  <div id="ext-install" class="ext-card ext-card-install" style="display:none">
    <div class="ext-card-header">
      <span class="ext-icon">🧩</span>
      <div>
        <p class="ext-card-title">Install the OpenSore Chrome Extension</p>
        <p class="ext-card-subtitle">Connect Slack and Google directly from your browser — no copy-pasting tokens.</p>
      </div>
    </div>
    <div class="steps">
      <div class="step">
        <div class="step-num">Step 1</div>
        <div class="step-text">Open Chrome and go to <code>chrome://extensions</code></div>
      </div>
      <div class="step">
        <div class="step-num">Step 2</div>
        <div class="step-text">Toggle <strong style="color:#e0e7ff">Developer mode</strong> on (top-right switch)</div>
      </div>
      <div class="step">
        <div class="step-num">Step 3</div>
        <div class="step-text">Click <strong style="color:#e0e7ff">Load unpacked</strong> and select the <code>app/chrome-extension</code> folder from this repo</div>
      </div>
      <div class="step">
        <div class="step-num">Step 4</div>
        <div class="step-text">Reload this page — the extension will connect automatically</div>
      </div>
    </div>
    <div class="ext-cta">
      <a class="btn btn-ext-primary" href="chrome://extensions" id="ext-open-mgr">Open chrome://extensions</a>
      <a class="btn btn-ext-secondary" href="https://github.com/amolsarva/opensore/tree/main/app/chrome-extension" target="_blank" rel="noopener">View extension source</a>
      <a class="btn btn-ext-secondary" href="https://github.com/amolsarva/opensore#chrome-extension" target="_blank" rel="noopener">Install guide</a>
    </div>
  </div>

  <!-- Extension: connected state (shown when extension present) -->
  <div id="ext-connected" class="ext-card ext-card-connected" style="display:none">
    <div class="ext-card-header">
      <span class="ext-icon">✅</span>
      <div>
        <p class="ext-card-title">Chrome Extension Connected</p>
        <p class="ext-card-subtitle">Click the OpenSore icon in your toolbar to manage source connections.</p>
      </div>
    </div>
    <div id="ext-connections" class="connection-list"></div>
  </div>

  <script>
    (function () {
      var installEl = document.getElementById('ext-install');
      var connectedEl = document.getElementById('ext-connected');
      var connectionsEl = document.getElementById('ext-connections');

      // chrome:// links can't be navigated via <a> — open them programmatically
      var mgr = document.getElementById('ext-open-mgr');
      if (mgr) {
        mgr.addEventListener('click', function (e) {
          e.preventDefault();
          // Works from extension context; in plain page just copy the URL.
          window.open('chrome://extensions', '_blank');
        });
      }

      function showInstall() {
        if (installEl) installEl.style.display = 'block';
        if (connectedEl) connectedEl.style.display = 'none';
      }

      function showConnected(connections) {
        if (installEl) installEl.style.display = 'none';
        if (connectedEl) connectedEl.style.display = 'block';
        if (connectionsEl && connections && connections.length) {
          connectionsEl.innerHTML = connections.map(function (c) {
            return '<span class="connection-chip"><span>' + (c.icon || '🔗') + '</span>'
              + '<span>' + (c.label || c.service || c) + '</span></span>';
          }).join('');
        }
      }

      function checkExtension() {
        var hasExt = document.documentElement.getAttribute('data-opensore-extension') === 'true';
        if (hasExt) {
          // Try to fetch live connection state from extension / local server
          fetch('http://localhost:8000/api/extension/connections', { signal: AbortSignal.timeout(1500) })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
              showConnected(data && data.connections ? data.connections : []);
            })
            .catch(function () { showConnected([]); });
        } else {
          showInstall();
        }
      }

      // Extension signals readiness via a custom event
      window.addEventListener('opensore-extension-ready', function () { checkExtension(); });
      // Fallback: check after 600 ms if the event never fires
      setTimeout(checkExtension, 600);
    })();
  </script>

  <script>
    (function () {
      var statusEl = document.getElementById('dev-status');
      var logsEl = document.getElementById('dev-logs');
      var logsPreEl = document.getElementById('dev-logs-pre');
      var logsVisible = false;
      var logsTimer = null;

      // Populate version / sha from /ok
      fetch('/ok').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
        if (!d) return;
        document.getElementById('dev-version').textContent = 'v' + d.version;
        document.getElementById('dev-sha').textContent = d.git_sha || 'unknown';
      }).catch(function () {});

      function setStatus(msg, cls) {
        statusEl.textContent = msg;
        statusEl.className = 'dev-status' + (cls ? ' ' + cls : '');
        statusEl.hidden = false;
        if (cls !== 'err') setTimeout(function () { statusEl.hidden = true; }, 10000);
      }

      function clearStatus() { statusEl.hidden = true; }

      async function pollReady(maxMs) {
        var end = Date.now() + maxMs;
        while (Date.now() < end) {
          await new Promise(function (r) { setTimeout(r, 700); });
          try {
            var r = await fetch('/ok', { signal: AbortSignal.timeout(1200) });
            if (r.ok) return true;
          } catch (e) { /* still starting */ }
        }
        return false;
      }

      function disableBtns() {
        document.getElementById('btn-restart').disabled = true;
        document.getElementById('btn-pull-restart').disabled = true;
      }
      function enableBtns() {
        document.getElementById('btn-restart').disabled = false;
        document.getElementById('btn-pull-restart').disabled = false;
      }

      document.getElementById('btn-restart').addEventListener('click', async function () {
        disableBtns();
        setStatus('Restarting server…');
        try { await fetch('/api/admin/restart', { method: 'POST', signal: AbortSignal.timeout(3000) }); } catch (e) {}
        var ok = await pollReady(20000);
        enableBtns();
        if (ok) {
          setStatus('Server restarted.', 'ok');
          refreshVersion();
          if (logsVisible) loadLogs();
        } else {
          setStatus('Server did not come back within 20 s — check your terminal.', 'err');
        }
      });

      document.getElementById('btn-pull-restart').addEventListener('click', async function () {
        disableBtns();
        setStatus('Pulling latest changes…');
        try {
          var r = await fetch('/api/admin/update', { method: 'POST', signal: AbortSignal.timeout(180000) });
          var data = await r.json();
          var summary = data.steps.map(function (s) {
            return s.skipped
              ? (s.cmd + ': skipped (' + s.reason + ')')
              : (s.cmd + ': exit ' + s.returncode + (s.stderr ? ' — ' + s.stderr.split('\n')[0] : ''));
          }).join(' | ');
          setStatus(summary + ' — restarting…');
          try { await fetch('/api/admin/restart', { method: 'POST', signal: AbortSignal.timeout(3000) }); } catch (e) {}
        } catch (e) {
          setStatus('Update failed: ' + e.message, 'err');
          enableBtns();
          return;
        }
        var ok = await pollReady(25000);
        enableBtns();
        if (ok) {
          setStatus('Server updated and restarted.', 'ok');
          refreshVersion();
          if (logsVisible) loadLogs();
        } else {
          setStatus('Server did not come back after update — check your terminal.', 'err');
        }
      });

      function refreshVersion() {
        fetch('/ok').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
          if (!d) return;
          document.getElementById('dev-version').textContent = 'v' + d.version;
          document.getElementById('dev-sha').textContent = d.git_sha || 'unknown';
        }).catch(function () {});
      }

      document.getElementById('btn-logs-toggle').addEventListener('click', function () {
        logsVisible = !logsVisible;
        logsEl.hidden = !logsVisible;
        if (logsVisible) loadLogs();
      });

      document.getElementById('btn-logs-clear').addEventListener('click', function () {
        logsPreEl.textContent = '';
      });

      document.getElementById('logs-auto').addEventListener('change', function () {
        if (this.checked && logsVisible) loadLogs();
      });

      function loadLogs() {
        fetch('/api/admin/logs?n=120').then(function (r) { return r.json(); }).then(function (d) {
          var lines = d.lines || [];
          logsPreEl.textContent = lines.length ? lines.join('\n') : '(no log output yet)';
          logsPreEl.scrollTop = logsPreEl.scrollHeight;
        }).catch(function () {});
      }

      setInterval(function () {
        if (logsVisible && document.getElementById('logs-auto').checked) loadLogs();
      }, 4000);
    })();
  </script>

  <section class="grid">
    <div class="card"><h3>1. Create matter</h3><p>Name the investigation, add custodians, date range, and keyword sets.</p></div>
    <div class="card"><h3>2. Connect sources</h3><p>Authorize Google Workspace, Slack, Microsoft 365, GitHub, Jira, or CSV via the extension — read-only.</p></div>
    <div class="card"><h3>3. Export to Drive</h3><p>Write reviewable CSV outputs to the user's Drive and discard transient buffers on this host.</p></div>
  </section>
  <section>
    <h2>What this is not</h2>
    <ul>
      <li>It is not legal advice or a replacement for counsel.</li>
      <li>It should not decide whether misconduct happened by itself.</li>
      <li>It should not retain user evidence on the hosted OpenSore server.</li>
    </ul>
  </section>
</main>
</body>
</html>"""


@app.get("/api/discovery/default-keywords", response_model=list[DiscoveryKeywordSet])
def discovery_default_keywords() -> list[DiscoveryKeywordSet]:
    return default_keyword_sets()


@app.get("/api/discovery/schema")
def discovery_schema() -> dict[str, object]:
    return {
        "request": DiscoveryInvestigationRequest.model_json_schema(),
        "plan": DiscoveryInvestigationPlan.model_json_schema(),
    }


@app.post("/api/discovery/investigations/preview", response_model=DiscoveryInvestigationPlan)
def discovery_preview(request: DiscoveryInvestigationRequest) -> DiscoveryInvestigationPlan:
    """Return a no-evidence plan for a workplace discovery investigation."""

    return build_discovery_plan(request)


@app.post("/api/discovery/investigations/preview.csv", response_class=PlainTextResponse)
def discovery_preview_csv(request: DiscoveryInvestigationRequest) -> str:
    """Return a CSV summary of a no-evidence discovery plan."""

    return discovery_plan_csv(build_discovery_plan(request))
