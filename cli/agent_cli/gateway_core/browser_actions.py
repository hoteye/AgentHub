from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


BROWSER_ACTION_FAMILY = "browser"
BROWSER_ACTION_CLASS_READ_ONLY = "read_only"
BROWSER_ACTION_CLASS_STATE_MUTATING = "state_mutating"
BROWSER_ACTION_CLASS_EXTERNAL_SIDE_EFFECTING = "external_side_effecting"

_READ_ONLY_COMMANDS = {
    "status",
    "profiles",
    "tabs",
    "snapshot",
    "console",
    "errors",
    "requests",
    "screenshot",
    "pdf",
    "cookies",
    "cookies_get",
    "storage_state",
    "storage_get",
}
_STATE_MUTATING_COMMANDS = {
    "start",
    "stop",
    "open",
    "focus",
    "close",
    "navigate",
    "highlight",
    "trace_start",
    "trace_stop",
    "cookies_set",
    "cookies_clear",
    "storage_set",
    "storage_clear",
    "upload",
    "dialog",
}
_EXTERNAL_SIDE_EFFECTING_COMMANDS = {
    "download",
    "wait_download",
}

_READ_ONLY_ACT_KINDS = {
    "wait",
}
_STATE_MUTATING_ACT_KINDS = {
    "fill",
    "type",
    "select",
    "check",
    "uncheck",
    "hover",
    "scroll_into_view",
    "resize",
}
_EXTERNAL_SIDE_EFFECTING_ACT_KINDS = {
    "click",
    "dblclick",
    "double_click",
    "press",
    "drag",
    "evaluate",
    "submit",
}


def _normalize_browser_word(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


@dataclass(slots=True)
class BrowserActionClassification:
    command: str
    action_kind: Optional[str]
    action_class: str
    approval_policy: str
    audit_stage: str

    @property
    def action_family(self) -> str:
        return BROWSER_ACTION_FAMILY

    @property
    def approval_required(self) -> bool:
        return self.approval_policy != "never"

    def to_metadata(self, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = dict(existing or {})
        browser_metadata = dict(metadata.get("browser") or {})
        browser_metadata.setdefault("command", self.command)
        if self.action_kind:
            browser_metadata.setdefault("action_kind", self.action_kind)
        browser_metadata["action_class"] = self.action_class
        browser_metadata["approval_policy"] = self.approval_policy
        browser_metadata["audit_stage"] = self.audit_stage
        metadata["browser"] = browser_metadata
        metadata.setdefault("action_family", self.action_family)
        metadata["action_class"] = self.action_class
        metadata["approval_policy"] = self.approval_policy
        metadata["audit_stage"] = self.audit_stage
        return metadata


def classify_browser_action(
    action_type: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[BrowserActionClassification]:
    normalized_action_type = _normalize_browser_word(action_type)
    if not normalized_action_type.startswith("browser"):
        return None

    remainder = normalized_action_type.split(".", 1)[1] if "." in normalized_action_type else ""
    command = remainder.split(".", 1)[0] if remainder else "act"
    action_kind: Optional[str] = None
    combined = dict(metadata or {})
    combined_payload = dict(payload or {})

    if command == "act":
        if "." in remainder:
            action_kind = remainder.split(".", 1)[1]
        if not action_kind:
            action_kind = _normalize_browser_word(
                combined_payload.get("kind")
                or combined.get("browser_action_kind")
                or (combined.get("browser") or {}).get("action_kind")
            )
        if not action_kind:
            action_kind = "act"

    if command in _READ_ONLY_COMMANDS:
        action_class = BROWSER_ACTION_CLASS_READ_ONLY
    elif command in _STATE_MUTATING_COMMANDS:
        action_class = BROWSER_ACTION_CLASS_STATE_MUTATING
    elif command in _EXTERNAL_SIDE_EFFECTING_COMMANDS:
        action_class = BROWSER_ACTION_CLASS_EXTERNAL_SIDE_EFFECTING
    elif command == "act":
        if action_kind in _EXTERNAL_SIDE_EFFECTING_ACT_KINDS:
            action_class = BROWSER_ACTION_CLASS_EXTERNAL_SIDE_EFFECTING
        elif action_kind in _READ_ONLY_ACT_KINDS:
            action_class = BROWSER_ACTION_CLASS_READ_ONLY
        else:
            action_class = BROWSER_ACTION_CLASS_STATE_MUTATING
    elif command == "proxy":
        method = _normalize_browser_word(
            combined_payload.get("method")
            or combined.get("browser_proxy_method")
            or (combined.get("browser") or {}).get("proxy_method")
        )
        action_class = (
            BROWSER_ACTION_CLASS_READ_ONLY
            if method in {"", "get"}
            else BROWSER_ACTION_CLASS_EXTERNAL_SIDE_EFFECTING
        )
    else:
        action_class = BROWSER_ACTION_CLASS_STATE_MUTATING

    if action_class == BROWSER_ACTION_CLASS_READ_ONLY:
        approval_policy = "never"
        audit_stage = "browser_read"
    elif action_class == BROWSER_ACTION_CLASS_STATE_MUTATING:
        approval_policy = "always"
        audit_stage = "browser_state_change"
    else:
        approval_policy = "always"
        audit_stage = "browser_external_effect"

    return BrowserActionClassification(
        command=command,
        action_kind=action_kind,
        action_class=action_class,
        approval_policy=approval_policy,
        audit_stage=audit_stage,
    )
