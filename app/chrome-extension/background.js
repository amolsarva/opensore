/**
 * OpenSore Chrome Extension — background service worker.
 *
 * Handles all OAuth flows via chrome.identity.launchWebAuthFlow and relays
 * authorization codes to the local OpenSore server for token exchange.
 */

const DEFAULT_PORT = 8000;

const GOOGLE_SCOPES = [
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/drive.readonly",
  "https://www.googleapis.com/auth/calendar.readonly",
  "openid",
  "email",
  "profile",
].join(" ");

async function getServerPort() {
  const data = await chrome.storage.local.get({ serverPort: DEFAULT_PORT });
  return data.serverPort;
}

function serverUrl(port, path) {
  return `http://localhost:${port}${path}`;
}

function extensionRedirectUri(provider) {
  return `https://${chrome.runtime.id}.chromiumapp.org/${provider}`;
}

async function fetchConfig(port) {
  const resp = await fetch(serverUrl(port, "/api/extension/config"), {
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error("OpenSore local server not reachable");
  return resp.json();
}

async function oauthSlack(clientId) {
  const redirectUri = extensionRedirectUri("slack");
  const state = crypto.randomUUID();

  const url = new URL("https://slack.com/oauth/v2/authorize");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("user_scope", "search:read,users:read");
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("state", state);

  const responseUrl = await chrome.identity.launchWebAuthFlow({
    url: url.toString(),
    interactive: true,
  });

  const params = new URL(responseUrl).searchParams;
  const code = params.get("code");
  if (!code) throw new Error("Slack OAuth cancelled or failed");
  return { code, redirect_uri: redirectUri };
}

async function oauthGoogle(clientId) {
  const redirectUri = extensionRedirectUri("google");

  // PKCE — required because the extension cannot keep a client secret private
  const verifierBytes = crypto.getRandomValues(new Uint8Array(32));
  const verifier = btoa(String.fromCharCode(...verifierBytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  const challenge = btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");

  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", GOOGLE_SCOPES);
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");

  const responseUrl = await chrome.identity.launchWebAuthFlow({
    url: url.toString(),
    interactive: true,
  });

  const params = new URL(responseUrl).searchParams;
  const code = params.get("code");
  if (!code) throw new Error("Google OAuth cancelled or failed");
  return { code, redirect_uri: redirectUri, code_verifier: verifier };
}

async function completeOAuth(port, provider, data) {
  const resp = await fetch(serverUrl(port, "/api/extension/oauth/complete"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, ...data }),
    signal: AbortSignal.timeout(15000),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token exchange failed: ${text}`);
  }
  return resp.json();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.action === "ping") {
    (async () => {
      try {
        const port = await getServerPort();
        const resp = await fetch(serverUrl(port, "/api/extension/ping"), {
          signal: AbortSignal.timeout(2500),
        });
        sendResponse({ ok: resp.ok, port });
      } catch {
        sendResponse({ ok: false });
      }
    })();
    return true;
  }

  if (message.action === "oauth") {
    (async () => {
      try {
        const port = await getServerPort();
        const config = await fetchConfig(port);

        let data;
        if (message.provider === "slack") {
          if (!config.slack_client_id) {
            throw new Error(
              "OPENSORE_SLACK_CLIENT_ID not set — add it to your environment and restart opensore.",
            );
          }
          data = await oauthSlack(config.slack_client_id);
        } else if (message.provider === "google") {
          if (!config.google_client_id) {
            throw new Error(
              "OPENSORE_GOOGLE_CLIENT_ID not set — add it to your environment and restart opensore.",
            );
          }
          data = await oauthGoogle(config.google_client_id);
        } else {
          throw new Error(`Unknown provider: ${message.provider}`);
        }

        const result = await completeOAuth(port, message.provider, data);
        sendResponse({ ok: true, result });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    })();
    return true;
  }

  if (message.action === "getConnections") {
    (async () => {
      try {
        const port = await getServerPort();
        const resp = await fetch(serverUrl(port, "/api/extension/connections"), {
          signal: AbortSignal.timeout(5000),
        });
        if (!resp.ok) throw new Error("Failed to fetch connections");
        const data = await resp.json();
        sendResponse({ ok: true, connections: data.connections });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
    })();
    return true;
  }

  if (message.action === "setPort") {
    chrome.storage.local.set({ serverPort: message.port });
    sendResponse({ ok: true });
    return true;
  }
});
