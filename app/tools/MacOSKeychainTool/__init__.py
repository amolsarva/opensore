"""macOS Keychain tool — metadata lookup via the macOS security CLI.

IMPORTANT: The macOS Keychain is protected by the operating system.
Any attempt to read a keychain secret ALWAYS triggers a system-level
password/biometric prompt visible to the user. Silent extraction is
impossible by design. This tool only surfaces metadata (service names,
account names) and delegates actual secret retrieval to macOS.
"""

from __future__ import annotations

from typing import Any

from app.services.macos_device.client import (
    is_macos,
    keychain_find_generic,
    keychain_list_services,
)
from app.tools.base import BaseTool


class MacOSKeychainTool(BaseTool):
    """Inspect the macOS Keychain via the system ``security`` CLI.

    Lists stored service names (no credentials exposed) and optionally
    triggers a privileged lookup that will prompt the macOS user for
    authorization. This tool can never extract passwords silently.
    """

    name = "inspect_macos_keychain"
    source = "local_device"
    description = (
        "Inspect the macOS Keychain using the system security CLI. Can list service/account "
        "metadata without credentials, and trigger a privileged lookup that macOS gates behind "
        "a mandatory user-approval dialog. Passwords are never silently extracted. macOS only."
    )
    use_cases = [
        "Listing which services (e.g., corporate VPN, cloud storage, email clients) have stored credentials",
        "Confirming whether a subject's device has credentials for a specific service under investigation",
        "Documenting keychain service inventory as part of a device forensics report",
        "Triggering a user-authorized lookup for a specific service account during a supervised examination",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_services", "find_entry"],
                "description": "'list_services' returns service names (no secrets). 'find_entry' triggers a macOS authorization prompt.",
                "default": "list_services",
            },
            "service": {
                "type": "string",
                "description": "Service name to search for (used with action=find_entry).",
            },
            "account": {
                "type": "string",
                "description": "Account/username to search for (used with action=find_entry).",
            },
        },
    }
    outputs = {
        "available": "Whether the security CLI is accessible on this platform",
        "action": "The action that was performed",
        "services": "List of service names (action=list_services only)",
        "entry": "Lookup result (action=find_entry only)",
    }

    def is_available(self, _sources: dict) -> bool:
        return is_macos()

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"action": "list_services"}

    def run(
        self,
        action: str = "list_services",
        service: str | None = None,
        account: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not is_macos():
            return {
                "source": "local_device",
                "available": False,
                "error": "macOS Keychain tools are only available on macOS.",
            }

        try:
            if action == "find_entry":
                entry = keychain_find_generic(service=service, account=account)
                return {
                    "source": "local_device",
                    "available": True,
                    "action": "find_entry",
                    "entry": entry,
                    "warning": (
                        "This action triggered a macOS authorization prompt. "
                        "The user must approve before any credential is disclosed."
                    ),
                }

            # list_services (default)
            services = keychain_list_services()
            return {
                "source": "local_device",
                "available": True,
                "action": "list_services",
                "services": services,
                "service_count": len(services),
                "note": "Service names only — no credentials are exposed by this action.",
            }
        except Exception as exc:
            return {"source": "local_device", "available": False, "error": str(exc)}


inspect_macos_keychain = MacOSKeychainTool()
