from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli import approval_contract_runtime


@dataclass(frozen=True)
class ApprovalOptionSpec:
    decision_type: str
    label: str
    command: str
    display_shortcut: str
    extra_shortcuts: tuple[str, ...] = ()

    def matches_key(self, key: str) -> bool:
        normalized = str(key or "").strip().lower()
        if not normalized:
            return False
        return normalized == self.display_shortcut or normalized in self.extra_shortcuts


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _starts_with(value: Any, prefix: str) -> bool:
    return _normalized_text(value).lower().startswith(prefix.lower())


def _format_rule_preview(proposed_rule: dict[str, Any]) -> str:
    raw_pattern = proposed_rule.get("pattern")
    if isinstance(raw_pattern, (list, tuple)):
        pattern_items = [_normalized_text(item) for item in raw_pattern if _normalized_text(item)]
        pattern = " ".join(pattern_items).strip()
        if pattern and "\n" not in pattern and "\r" not in pattern:
            return pattern
    pattern = _normalized_text(raw_pattern)
    if pattern and "\n" not in pattern and "\r" not in pattern:
        return pattern
    normalized_command = _normalized_text(proposed_rule.get("normalized_command"))
    if normalized_command and "\n" not in normalized_command and "\r" not in normalized_command:
        return normalized_command
    tokens = [
        _normalized_text(item)
        for item in list(proposed_rule.get("command_tokens") or [])
        if _normalized_text(item)
    ]
    preview = " ".join(tokens).strip()
    if preview and "\n" not in preview and "\r" not in preview:
        return preview
    return ""


def format_additional_permissions_rule(additional_permissions: dict[str, Any] | None) -> str:
    permissions = _copy_mapping(additional_permissions)
    if not permissions:
        return ""
    parts: list[str] = []
    network = permissions.get("network")
    if isinstance(network, dict):
        if bool(network.get("enabled")):
            parts.append("network")
    elif network is True:
        parts.append("network")
    file_system = permissions.get("file_system")
    if isinstance(file_system, dict):
        reads = [
            _normalized_text(item)
            for item in list(file_system.get("read") or [])
            if _normalized_text(item)
        ]
        writes = [
            _normalized_text(item)
            for item in list(file_system.get("write") or [])
            if _normalized_text(item)
        ]
        if reads:
            parts.append("read " + ", ".join(f"`{item}`" for item in reads))
        if writes:
            parts.append("write " + ", ".join(f"`{item}`" for item in writes))
    return "; ".join(parts)


def _option_label(payload: dict[str, Any], decision: dict[str, Any]) -> str:
    decision_type = _normalized_text(decision.get("type"))
    action_type = _normalized_text(payload.get("action_type"))
    is_browser_action = _starts_with(action_type, "browser.")
    browser_host = _normalized_text(payload.get("browser_host"))
    additional_rule = format_additional_permissions_rule(
        _copy_mapping(payload.get("additional_permissions")) or None
    )
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT:
        if is_browser_action and browser_host:
            return "Yes, just this once"
        return "Yes, proceed"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION:
        if action_type == "apply_patch":
            return "Yes, and don't ask again for these files"
        if is_browser_action and browser_host:
            return "Yes, and allow this host for this conversation"
        if additional_rule:
            return "Yes, and allow these permissions for this session"
        if action_type == "shell_command":
            return "Yes, and don't ask again for this command in this session"
        return "Yes, and don't ask again for this session"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT:
        preview = _format_rule_preview(_copy_mapping(decision.get("proposed_rule")))
        if preview:
            return f"Yes, and don't ask again for commands that start with `{preview}`"
        return "Yes, and don't ask again for commands matching this rule"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_DECLINE:
        if action_type == "apply_patch":
            return "No, continue without applying it"
        if action_type == "shell_command":
            return "No, continue without running it"
        if is_browser_action:
            return "No, continue without this browser action"
        return "No, continue without this action"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_CANCEL:
        return "No, and tell AgentHub what to do differently"
    return decision_type or "Unknown decision"


def _command_for_decision(approval_id: str, decision_type: str) -> str:
    normalized_id = _normalized_text(approval_id)
    if not normalized_id:
        return ""
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT:
        return f"/approve {normalized_id}"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION:
        return f"/approve {normalized_id} mode session"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT:
        return f"/approve {normalized_id} mode rule"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_DECLINE:
        return f"/reject {normalized_id}"
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_CANCEL:
        return f"/reject {normalized_id} mode cancel"
    return ""


def approval_option_specs(payload: dict[str, Any]) -> list[ApprovalOptionSpec]:
    approval_id = _normalized_text(payload.get("approval_id"))
    result: list[ApprovalOptionSpec] = []
    for item in approval_contract_runtime.normalize_available_decisions(payload.get("available_decisions")):
        decision_type = _normalized_text(item.get("type"))
        command = _command_for_decision(approval_id, decision_type)
        if not command:
            continue
        if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT:
            shortcut = "y"
            aliases: tuple[str, ...] = ()
        elif decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION:
            shortcut = "a"
            aliases = ()
        elif decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT:
            shortcut = "p"
            aliases = ()
        elif decision_type == approval_contract_runtime.APPROVAL_DECISION_DECLINE:
            shortcut = "d"
            aliases = ()
        elif decision_type == approval_contract_runtime.APPROVAL_DECISION_CANCEL:
            shortcut = "escape"
            aliases = ("n",)
        else:
            continue
        result.append(
            ApprovalOptionSpec(
                decision_type=decision_type,
                label=_option_label(payload, item),
                command=command,
                display_shortcut=shortcut,
                extra_shortcuts=aliases,
            )
        )
    return result


__all__ = [
    "ApprovalOptionSpec",
    "approval_option_specs",
    "format_additional_permissions_rule",
]
