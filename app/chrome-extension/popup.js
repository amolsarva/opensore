/** OpenSore extension popup logic. */

const PROVIDER_ICONS = { slack: "💬", google: "📧", google_workspace: "📧" };

async function init() {
  const { serverPort = 8000 } = await chrome.storage.local.get({ serverPort: 8000 });
  document.getElementById("port-input").value = serverPort;

  // Show redirect URI so users know what to register with Slack / Google
  const redirectUriRow = document.getElementById("redirect-uri-row");
  const redirectUriValue = document.getElementById("redirect-uri-value");
  redirectUriRow.hidden = false;
  redirectUriValue.textContent = `https://${chrome.runtime.id}.chromiumapp.org/<provider>`;

  const pingResult = await chrome.runtime.sendMessage({ action: "ping" });
  const statusEl = document.getElementById("server-status");

  if (pingResult && pingResult.ok) {
    statusEl.textContent = `Running on :${pingResult.port ?? serverPort}`;
    statusEl.className = "subtitle ok";
    enableProviderButtons();
    await loadConnections();
  } else {
    statusEl.textContent = "Local server not running";
    statusEl.className = "subtitle err";
    document.getElementById("connections-list").innerHTML =
      '<div class="empty-state">Start opensore to connect sources.</div>';
    document.getElementById("provider-hint").hidden = false;
  }
}

function enableProviderButtons() {
  document.getElementById("btn-slack").disabled = false;
  document.getElementById("btn-google").disabled = false;
}

async function loadConnections() {
  const result = await chrome.runtime.sendMessage({ action: "getConnections" });
  const listEl = document.getElementById("connections-list");

  if (!result.ok || !result.connections || result.connections.length === 0) {
    listEl.innerHTML = '<div class="empty-state">No sources connected yet.</div>';
    return;
  }

  listEl.innerHTML = result.connections
    .map((c) => {
      const icon = PROVIDER_ICONS[c.kind] ?? "🔌";
      const date = c.connected_at
        ? new Date(c.connected_at).toLocaleDateString()
        : "";
      return `
        <div class="connection-item">
          <span class="connection-icon">${icon}</span>
          <div class="connection-details">
            <div class="connection-label">${escHtml(c.label)}</div>
            <div class="connection-meta">${escHtml(c.kind)} · ${escHtml(date)}</div>
          </div>
        </div>
      `;
    })
    .join("");
}

async function handleOAuth(provider) {
  const btn = document.getElementById(`btn-${provider}`);
  const statusEl = document.getElementById(`status-${provider}`);

  btn.disabled = true;
  statusEl.textContent = "⏳";
  statusEl.className = "provider-status pending";

  const result = await chrome.runtime.sendMessage({ action: "oauth", provider });

  if (result && result.ok) {
    statusEl.textContent = "✓";
    statusEl.className = "provider-status success";
    await loadConnections();
  } else {
    statusEl.textContent = "✗";
    statusEl.className = "provider-status error";
    // Show error briefly below the button
    const errDiv = document.createElement("div");
    errDiv.className = "oauth-error";
    errDiv.textContent = (result && result.error) || "OAuth failed";
    btn.insertAdjacentElement("afterend", errDiv);
    setTimeout(() => errDiv.remove(), 6000);
  }

  btn.disabled = false;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("btn-slack").addEventListener("click", () => handleOAuth("slack"));
document.getElementById("btn-google").addEventListener("click", () => handleOAuth("google"));

document.getElementById("save-port").addEventListener("click", async () => {
  const port = parseInt(document.getElementById("port-input").value, 10);
  if (Number.isFinite(port) && port > 0 && port < 65536) {
    await chrome.runtime.sendMessage({ action: "setPort", port });
    await init();
  }
});

init();
