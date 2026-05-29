/** OpenSore Extension Popup */

let currentPort = 8000;

const PROVIDERS = {
  google: {
    label: "Google Workspace",
    icon: "📧",
    helpUrl: "https://console.cloud.google.com/apis/credentials",
    helpLabel: "Open Google Cloud Console ↗",
    needsSecret: false,
    credFields: [
      { key: "client_id", label: "OAuth 2.0 Client ID", placeholder: "xxxx.apps.googleusercontent.com" },
    ],
    steps: [
      "Go to Google Cloud Console → APIs & Services → Credentials. Create an OAuth 2.0 Client ID (type: Web application).",
      "Add the Redirect URI below to your OAuth 2.0 Client ID under Authorised redirect URIs.",
      "Paste your Client ID here, then click Save & Connect.",
    ],
  },
  slack: {
    label: "Slack",
    icon: "💬",
    helpUrl: "https://api.slack.com/apps",
    helpLabel: "Open Slack API Dashboard ↗",
    needsSecret: true,
    credFields: [
      { key: "client_id", label: "Client ID", placeholder: "1234567890.1234567890" },
      { key: "client_secret", label: "Client Secret", placeholder: "abcdef1234..." },
    ],
    steps: [
      "Go to api.slack.com/apps → Create New App → From scratch. Then open OAuth & Permissions.",
      "Add the Redirect URL below under OAuth & Permissions → Redirect URLs.",
      "Enable user scopes: search:read and users:read. Then paste your Client ID and Client Secret.",
    ],
  },
};

async function init() {
  const data = await chrome.storage.local.get({ serverPort: 8000 });
  currentPort = data.serverPort;
  document.getElementById("port-input").value = currentPort;
  document.getElementById("port-display").textContent = currentPort;
  await checkServer();
}

async function checkServer() {
  const statusEl = document.getElementById("server-status");
  let ok = false;
  try {
    const resp = await fetch(`http://localhost:${currentPort}/api/extension/ping`, {
      signal: AbortSignal.timeout(2500),
    });
    ok = resp.ok;
  } catch { /* unreachable */ }

  if (ok) {
    statusEl.textContent = `Running on :${currentPort}`;
    statusEl.className = "subtitle ok";
    await renderHome();
  } else {
    statusEl.textContent = "Server not running";
    statusEl.className = "subtitle err";
    renderOffline();
  }
}

function renderOffline() {
  document.getElementById("app").innerHTML = `
    <div class="offline-msg">
      <div class="offline-icon">⚡</div>
      <div class="offline-title">OpenSore isn&apos;t running</div>
      <div class="offline-sub">Double-click <code>OpenSore.command</code> or run <code>./start.sh</code> to start the local server.</div>
    </div>`;
}

async function renderHome() {
  let connections = [];
  let serverConfig = { slack_client_id: "", google_client_id: "" };
  try {
    const [connResp, cfgResp] = await Promise.all([
      fetch(`http://localhost:${currentPort}/api/extension/connections`, { signal: AbortSignal.timeout(3000) }),
      fetch(`http://localhost:${currentPort}/api/extension/config`, { signal: AbortSignal.timeout(3000) }),
    ]);
    if (connResp.ok) connections = (await connResp.json()).connections || [];
    if (cfgResp.ok) serverConfig = await cfgResp.json();
  } catch { /* server may have stopped */ }

  const stored = await chrome.storage.local.get({
    google_client_id: "",
    slack_client_id: "",
    slack_client_secret: "",
  });

  function provState(kind, serverKey) {
    return {
      connected: connections.some(c => c.kind === kind),
      configured: !!(serverConfig[serverKey] || stored[serverKey]),
    };
  }
  const google = provState("google_workspace", "google_client_id");
  const slack = provState("slack", "slack_client_id");

  const chips = connections.map(c => {
    const icon = c.kind === "slack" ? "💬" : "📧";
    return `<div class="conn-chip">${icon} ${escHtml(c.label)}</div>`;
  }).join("");

  document.getElementById("app").innerHTML = `
    <div class="provider-section">
      ${providerCardHtml("google", google)}
      ${providerCardHtml("slack", slack)}
    </div>
    ${connections.length ? `<div class="connections-row">${chips}</div>` : ""}`;

  for (const prov of ["google", "slack"]) {
    document.getElementById(`btn-connect-${prov}`)?.addEventListener("click", () => doConnect(prov));
    document.getElementById(`btn-setup-${prov}`)?.addEventListener("click", () => renderWizard(prov));
  }
}

function providerCardHtml(provider, { connected, configured }) {
  const p = PROVIDERS[provider];
  if (connected) {
    return `<div class="provider-card connected">
      <span class="picon">${p.icon}</span>
      <span class="pname">${p.label}</span>
      <span class="pbadge">✓ Connected</span>
      <button class="pbtn-sm" id="btn-connect-${provider}">Reconnect</button>
    </div>`;
  }
  if (configured) {
    return `<div class="provider-card">
      <span class="picon">${p.icon}</span>
      <span class="pname">${p.label}</span>
      <button class="pbtn" id="btn-connect-${provider}">Connect</button>
      <button class="pbtn-text" id="btn-setup-${provider}">Edit setup</button>
    </div>`;
  }
  return `<div class="provider-card needs-setup">
    <span class="picon">${p.icon}</span>
    <span class="pname">${p.label}</span>
    <button class="pbtn-setup" id="btn-setup-${provider}">Set up →</button>
  </div>`;
}

async function renderWizard(provider) {
  const p = PROVIDERS[provider];
  const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/${provider}`;
  const stored = await chrome.storage.local.get({
    google_client_id: "",
    slack_client_id: "",
    slack_client_secret: "",
  });

  const fields = p.credFields.map(f => {
    const val = provider === "google" ? stored.google_client_id : (stored[`slack_${f.key}`] || "");
    return `<label class="field-label">${escHtml(f.label)}</label>
      <input class="field-input" id="cred-${f.key}" type="text"
        placeholder="${escAttr(f.placeholder)}" value="${escAttr(val)}"
        autocomplete="off" spellcheck="false">`;
  }).join("");

  document.getElementById("app").innerHTML = `
    <div class="wizard">
      <div class="wizard-header">
        <button class="back-btn" id="wizard-back">← Back</button>
        <span class="wizard-title">${p.icon} Connect ${p.label}</span>
      </div>

      <div class="wizard-step">
        <div class="step-num">Step 1 — Create OAuth app</div>
        <a class="step-link" href="${escAttr(p.helpUrl)}" target="_blank" rel="noopener">${p.helpLabel}</a>
        <div class="step-hint">${escHtml(p.steps[0])}</div>
      </div>

      <div class="wizard-step">
        <div class="step-num">Step 2 — Copy Redirect URI</div>
        <div class="copy-row">
          <code class="copy-val">${escHtml(redirectUri)}</code>
          <button class="copy-btn" id="copy-redirect">Copy</button>
        </div>
        <div class="step-hint">${escHtml(p.steps[1])}</div>
      </div>

      <div class="wizard-step">
        <div class="step-num">Step 3 — Paste credentials</div>
        <div class="step-hint">${escHtml(p.steps[2])}</div>
        <div class="cred-fields">${fields}</div>
      </div>

      <div class="wizard-actions">
        <button class="btn-primary" id="wizard-save">Save &amp; Connect</button>
        <div class="wizard-error" id="wizard-error" hidden></div>
      </div>
    </div>`;

  document.getElementById("wizard-back").addEventListener("click", () => renderHome());

  document.getElementById("copy-redirect").addEventListener("click", async () => {
    await navigator.clipboard.writeText(redirectUri);
    const btn = document.getElementById("copy-redirect");
    btn.textContent = "Copied!";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 2000);
  });

  document.getElementById("wizard-save").addEventListener("click", () => onSaveAndConnect(provider));
}

async function onSaveAndConnect(provider) {
  const saveBtn = document.getElementById("wizard-save");
  const errEl = document.getElementById("wizard-error");
  errEl.hidden = true;

  const clientId = document.getElementById("cred-client_id")?.value.trim() || "";
  const clientSecret = document.getElementById("cred-client_secret")?.value.trim() || "";

  if (!clientId) {
    errEl.textContent = "Client ID is required.";
    errEl.hidden = false;
    return;
  }
  if (PROVIDERS[provider].needsSecret && !clientSecret) {
    errEl.textContent = "Client Secret is required.";
    errEl.hidden = false;
    return;
  }

  const toStore = provider === "google"
    ? { google_client_id: clientId }
    : { slack_client_id: clientId, slack_client_secret: clientSecret };
  await chrome.storage.local.set(toStore);

  saveBtn.disabled = true;
  saveBtn.textContent = "Connecting…";

  const result = await chrome.runtime.sendMessage({ action: "oauth", provider });
  if (result && result.ok) {
    await renderHome();
  } else {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save & Connect";
    errEl.textContent = (result && result.error) || "OAuth failed. Check your credentials and try again.";
    errEl.hidden = false;
  }
}

async function doConnect(provider) {
  const btn = document.getElementById(`btn-connect-${provider}`);
  if (btn) { btn.disabled = true; btn.textContent = "Connecting…"; }

  const result = await chrome.runtime.sendMessage({ action: "oauth", provider });
  await renderHome();

  if (!(result && result.ok)) {
    const msg = (result && result.error) || "OAuth failed";
    const toast = document.createElement("div");
    toast.className = "toast-error";
    toast.textContent = msg;
    document.getElementById("app").prepend(toast);
    setTimeout(() => toast.remove(), 6000);
  }
}

document.getElementById("port-toggle").addEventListener("click", () => {
  const el = document.getElementById("port-edit");
  el.hidden = !el.hidden;
});

document.getElementById("save-port").addEventListener("click", async () => {
  const port = parseInt(document.getElementById("port-input").value, 10);
  if (Number.isFinite(port) && port > 0 && port < 65536) {
    await chrome.storage.local.set({ serverPort: port });
    currentPort = port;
    document.getElementById("port-display").textContent = port;
    document.getElementById("port-edit").hidden = true;
    await checkServer();
  }
});

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(str) {
  return String(str).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

init();
