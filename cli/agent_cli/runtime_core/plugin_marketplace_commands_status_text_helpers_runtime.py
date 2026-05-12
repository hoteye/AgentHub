from __future__ import annotations


def entry_action_success_text(action: str, plugin_key: str) -> str:
    if action == "add":
        return f"Added plugin marketplace entry: {plugin_key}"
    if action == "update":
        return f"Updated plugin marketplace entry: {plugin_key}"
    return f"Removed plugin marketplace entry: {plugin_key}"


def entry_action_success_summary(action: str, plugin_key: str) -> str:
    if action == "add":
        return f"plugin marketplace entry added: {plugin_key}"
    if action == "update":
        return f"plugin marketplace entry updated: {plugin_key}"
    return f"plugin marketplace entry removed: {plugin_key}"


def plugin_install_status_text(plugin_key: str, ok: bool) -> str:
    if ok:
        return f"Installed plugin from marketplace: {plugin_key}"
    return "Plugin marketplace install failed."


def plugin_install_status_summary(plugin_key: str, ok: bool) -> str:
    if ok:
        return f"plugin installed from marketplace: {plugin_key}"
    return f"failed to install plugin from marketplace: {plugin_key}"


def plugin_state_change_status_text(action: str, plugin_ref: str, ok: bool) -> str:
    if ok:
        if action == "uninstall":
            return f"Uninstalled plugin: {plugin_ref}"
        if action == "enable":
            return f"Enabled plugin: {plugin_ref}"
        return f"Disabled plugin: {plugin_ref}"
    return f"Plugin {action} failed."


def plugin_state_change_status_summary(action: str, plugin_ref: str, ok: bool) -> str:
    if ok:
        return plugin_state_change_status_text(action, plugin_ref, ok=True)
    return f"{action} plugin failed: {plugin_ref}"


def policy_blocked_text(action: str, error_text: str) -> str:
    return f"Plugin marketplace {action} blocked by policy: {error_text}"
