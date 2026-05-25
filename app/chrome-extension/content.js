/**
 * OpenSore Chrome Extension — content script.
 *
 * On opensore pages: signals to the page that the extension is installed and
 * bridges OAuth requests from the page to the background service worker.
 *
 * On ChatGPT / ChatGPT Atlas: injects a subtle sidebar widget so users know
 * OpenSore is available and can open the popup to manage sources.
 */

const IS_CHATGPT =
  location.hostname.includes("chat.openai.com") ||
  location.hostname.includes("chatgpt.com");

// Tell the page the extension is present — the /ui page listens for this.
document.documentElement.setAttribute("data-opensore-extension", "true");
window.dispatchEvent(
  new CustomEvent("opensore-extension-ready", {
    detail: { version: chrome.runtime.getManifest().version },
  }),
);

// Bridge: page → extension OAuth request
window.addEventListener("opensore-oauth-request", async (event) => {
  const { provider } = event.detail;
  const result = await chrome.runtime.sendMessage({ action: "oauth", provider });
  window.dispatchEvent(
    new CustomEvent("opensore-oauth-response", { detail: result }),
  );
});

if (IS_CHATGPT) {
  injectChatGPTWidget();
}

function injectChatGPTWidget() {
  if (document.getElementById("opensore-widget")) return;

  const tryInject = () => {
    // Try common ChatGPT sidebar selectors
    const sidebar =
      document.querySelector("nav[aria-label]") ||
      document.querySelector("[data-testid='sidebar']") ||
      document.querySelector("nav");

    if (!sidebar) {
      setTimeout(tryInject, 1500);
      return;
    }

    const widget = document.createElement("div");
    widget.id = "opensore-widget";
    widget.innerHTML = `
      <div id="opensore-widget-inner" style="
        margin:8px 8px 0;
        padding:10px 12px;
        background:linear-gradient(135deg,#0f172a,#1e1b4b);
        border:1px solid #312e81;
        border-radius:8px;
        font-family:system-ui,sans-serif;
        font-size:12px;
        color:#c7d2fe;
        display:flex;
        align-items:center;
        gap:9px;
        cursor:pointer;
        user-select:none;
        transition:border-color 0.15s;
      ">
        <span style="font-size:18px;flex-shrink:0">🕵️</span>
        <div style="min-width:0">
          <div style="font-weight:600;color:#e0e7ff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            OpenSore
          </div>
          <div style="opacity:0.65;font-size:11px;margin-top:1px">
            Manage evidence sources
          </div>
        </div>
      </div>
    `;

    const inner = widget.querySelector("#opensore-widget-inner");
    inner.addEventListener("mouseenter", () => {
      inner.style.borderColor = "#6366f1";
    });
    inner.addEventListener("mouseleave", () => {
      inner.style.borderColor = "#312e81";
    });

    // Clicking opens the extension popup (best-effort — Chrome may not allow this
    // from content scripts in all contexts; the visual cue is the main goal)
    inner.addEventListener("click", () => {
      chrome.runtime.sendMessage({ action: "ping" }, (resp) => {
        if (resp && resp.ok) {
          // If user clicks and server is up, open the extension popup page
          window.open(chrome.runtime.getURL("popup.html"), "_blank", "width=340,height=520");
        } else {
          inner.querySelector("div > div:last-child").textContent =
            "Start opensore locally first";
        }
      });
    });

    sidebar.prepend(widget);
  };

  // Delay to let ChatGPT's React tree mount
  setTimeout(tryInject, 2500);
}
