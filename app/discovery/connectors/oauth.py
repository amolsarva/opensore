"""Local loopback OAuth server — opens browser, waits for callback, returns (code, redirect_uri).

This is used by the Slack connector flow. Google's own InstalledAppFlow already provides
a loopback server, so we only use this module for providers that require a manual exchange.
"""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.parse
import webbrowser
from collections.abc import Callable

_SUCCESS_HTML = b"""<!DOCTYPE html><html><body>
<h2>OpenSore: authentication complete.</h2>
<p>You can close this tab and return to the terminal.</p>
</body></html>"""


def _find_free_port() -> int:
    """Bind to port 0 to let the OS pick an available port, then return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_loopback_oauth(
    build_auth_url: Callable[[str], str],
    *,
    timeout: float = 120.0,
) -> tuple[str, str]:
    """Open the browser for an OAuth flow; return ``(code, redirect_uri)``.

    Args:
        build_auth_url: Callable that receives the ``redirect_uri`` string and
            returns the full authorization URL to open in the browser.
        timeout: Seconds to wait for the browser callback before raising
            ``TimeoutError``.

    Returns:
        A 2-tuple of ``(authorization_code, redirect_uri)`` where
        ``redirect_uri`` must be sent verbatim in the token-exchange request.

    Raises:
        TimeoutError: The user did not complete the OAuth flow within *timeout* seconds.
        RuntimeError: The provider returned an error parameter in the callback URL.
    """
    port = _find_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"

    code_container: list[str] = []
    error_container: list[str] = []

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802  — stdlib naming convention
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            error = params.get("error", [None])[0]
            code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)
            if error:
                error_container.append(error)
            elif code:
                code_container.append(code)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # suppress request logging to keep the terminal clean

    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = timeout

    auth_url = build_auth_url(redirect_uri)
    webbrowser.open(auth_url)

    shutdown_event = threading.Event()

    def _serve() -> None:
        while not shutdown_event.is_set():
            server.handle_request()
            if code_container or error_container:
                break

    serve_thread = threading.Thread(target=_serve, daemon=True)
    serve_thread.start()
    serve_thread.join(timeout=timeout)
    server.server_close()

    if error_container:
        raise RuntimeError(f"OAuth provider returned an error: {error_container[0]}")
    if not code_container:
        raise TimeoutError(
            f"OAuth flow timed out after {timeout:.0f}s — no authorization code received."
        )
    return code_container[0], redirect_uri
