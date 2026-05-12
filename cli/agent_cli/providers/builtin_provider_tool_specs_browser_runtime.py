from __future__ import annotations

from typing import Any, Callable


def browser_properties(
    *,
    provider_action_names: Callable[[str], tuple[str, ...]],
    browser_provider_actions: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "action": {
            "type": "string",
            "description": "Browser action to perform.",
            "enum": list(provider_action_names("browser") or browser_provider_actions),
        },
        "profile": {"type": "string", "description": "Target browser profile."},
        "transport": {
            "type": "string",
            "description": "Execution route override. Use local for host execution or proxy for the proxy/app-server path.",
            "enum": ["local", "proxy"],
        },
        "tab": {"type": "string", "description": "Target tab id when a browser action needs a specific tab."},
        "url": {"type": "string", "description": "URL to open or navigate to."},
        "path": {"type": "string", "description": "Relative output path under the managed downloads directory."},
        "level": {"type": "string", "description": "Severity filter for action=console."},
        "limit": {"type": "integer", "description": "Maximum number of entries to return for action=console, errors, or requests."},
        "outcome": {"type": "string", "description": "Request outcome filter for action=requests."},
        "method": {"type": "string", "description": "HTTP method filter for action=requests."},
        "storage_kind": {
            "type": "string",
            "description": "Storage scope for storage_get/storage_set/storage_clear.",
            "enum": ["local", "session"],
        },
        "ref": {"type": "string", "description": "Snapshot ref for element-level screenshot capture."},
        "kind": {
            "type": "string",
            "description": "Act verb when action=act.",
            "enum": [
                "click",
                "double_click",
                "type",
                "press",
                "hover",
                "scroll_into_view",
                "focus",
                "clear",
                "check",
                "uncheck",
                "drag",
                "resize",
                "select",
                "fill",
                "wait",
                "evaluate",
            ],
        },
        "start_ref": {"type": "string", "description": "Start ref for drag actions."},
        "end_ref": {"type": "string", "description": "End ref for drag actions."},
        "text": {"type": "string", "description": "Text payload for type actions."},
        "fn": {"type": "string", "description": "JavaScript function source for act kind=evaluate."},
        "key": {"type": "string", "description": "Keyboard key for press actions."},
        "width": {"type": "integer", "description": "Viewport width for resize actions."},
        "height": {"type": "integer", "description": "Viewport height for resize actions."},
        "values": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Selected values for select actions.",
        },
        "cookies": {
            "type": "array",
            "description": "Cookie objects for action=cookies_set.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "url": {"type": "string"},
                    "domain": {"type": "string"},
                    "path": {"type": "string"},
                    "httpOnly": {"type": "boolean"},
                    "secure": {"type": "boolean"},
                    "sameSite": {"type": "string"},
                    "expires": {"type": "number"},
                },
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
        "items": {
            "type": "object",
            "description": "Storage key/value map for action=storage_set.",
            "additionalProperties": {"type": "string"},
        },
        "fields": {
            "type": "array",
            "description": "Field refs and values for fill actions.",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["ref", "value"],
                "additionalProperties": False,
            },
        },
        "time_ms": {"type": "integer", "description": "Wait duration for wait actions or highlight timing."},
        "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Upload file paths for action=upload.",
        },
        "input_ref": {"type": "string", "description": "Input ref for action=upload."},
        "accept": {"type": "boolean", "description": "Dialog decision for action=dialog."},
        "prompt_text": {"type": "string", "description": "Prompt text for action=dialog."},
    }
