from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _copy_mapping_list(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(value or []):
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _starts_with(value: Any, prefix: str) -> bool:
    return _normalized_text(value).lower().startswith(prefix.lower())


def _host_from_browser_fields(url: Any, domain: Any = None) -> str:
    normalized_domain = _normalized_text(domain).lower()
    if normalized_domain:
        return normalized_domain
    normalized_url = _normalized_text(url)
    if not normalized_url:
        return ""
    parsed = urlparse(normalized_url if "://" in normalized_url else f"https://{normalized_url}")
    return str(parsed.netloc or "").strip().lower()


def build_approval_overlay_payload(
    *,
    approval_ticket: Any,
    action_request: Any | None,
) -> dict[str, Any]:
    ticket_map = getattr(approval_ticket, "to_dict", None)
    if callable(ticket_map):
        ticket = dict(ticket_map() or {})
    else:
        ticket = {
            "approval_id": getattr(approval_ticket, "approval_id", None),
            "summary": getattr(approval_ticket, "summary", None),
            "reason": getattr(approval_ticket, "reason", None),
            "available_decisions": getattr(approval_ticket, "available_decisions", None),
            "proposed_rule": getattr(approval_ticket, "proposed_rule", None),
            "grant_root": getattr(approval_ticket, "grant_root", None),
            "status": getattr(approval_ticket, "status", None),
        }
    action_payload = _copy_mapping(getattr(action_request, "payload", None))
    action_metadata = _copy_mapping(getattr(action_request, "metadata", None))
    action_type = _normalized_text(getattr(action_request, "action_type", None))
    projected = {
        "approval_id": _normalized_text(ticket.get("approval_id")),
        "summary": _normalized_text(ticket.get("summary")),
        "reason": _normalized_text(ticket.get("reason")),
        "status": _normalized_text(ticket.get("status")) or "pending",
        "action_type": action_type,
        "available_decisions": _copy_mapping_list(ticket.get("available_decisions")),
        "proposed_rule": _copy_mapping(ticket.get("proposed_rule")) or None,
        "grant_root": _normalized_text(ticket.get("grant_root")) or None,
    }
    if action_type == "shell_command":
        projected.update(
            {
                "command": _normalized_text(action_payload.get("command")),
                "cwd": _normalized_text(action_payload.get("cwd")) or None,
                "exec_mode": _normalized_text(action_payload.get("exec_mode")) or None,
                "additional_permissions": (
                    _copy_mapping(action_payload.get("additional_permissions"))
                    or _copy_mapping(action_metadata.get("additional_permissions"))
                    or None
                ),
            }
        )
    elif action_type == "apply_patch":
        preview = _copy_mapping(action_payload.get("preview"))
        projected.update(
            {
                "file_count": preview.get("file_count"),
                "added_count": preview.get("added_count"),
                "updated_count": preview.get("updated_count"),
                "deleted_count": preview.get("deleted_count"),
                "moved_count": preview.get("moved_count"),
                "changes": _copy_mapping_list(preview.get("changes")),
            }
        )
    elif _starts_with(action_type, "browser."):
        browser_request = _copy_mapping(action_payload.get("browser_request"))
        browser_metadata = _copy_mapping(action_metadata.get("browser"))
        browser_host = (
            _normalized_text(browser_metadata.get("host"))
            or _host_from_browser_fields(
                browser_request.get("url"),
                browser_request.get("domain"),
            )
        )
        projected.update(
            {
                "browser_command": (
                    _normalized_text(browser_metadata.get("command"))
                    or _normalized_text(browser_request.get("action"))
                    or None
                ),
                "browser_action_kind": (
                    _normalized_text(browser_metadata.get("action_kind"))
                    or _normalized_text(browser_request.get("kind"))
                    or None
                ),
                "browser_action_class": (
                    _normalized_text(browser_metadata.get("action_class"))
                    or _normalized_text(action_metadata.get("action_class"))
                    or _normalized_text(getattr(action_request, "action_class", None))
                    or None
                ),
                "browser_host": browser_host or None,
                "browser_url": _normalized_text(browser_request.get("url")) or None,
                "browser_transport": _normalized_text(browser_request.get("transport")) or None,
                "browser_target_id": (
                    _normalized_text(browser_request.get("target_id"))
                    or _normalized_text(browser_request.get("tab_id"))
                    or None
                ),
                "browser_ref": _normalized_text(browser_request.get("ref")) or None,
                "browser_method": _normalized_text(browser_request.get("method")) or None,
                "browser_path": _normalized_text(browser_request.get("path")) or None,
                "approval_policy": (
                    _normalized_text(getattr(action_request, "approval_policy", None))
                    or _normalized_text(action_metadata.get("approval_policy"))
                    or _normalized_text(browser_metadata.get("approval_policy"))
                    or None
                ),
                "audit_stage": (
                    _normalized_text(getattr(action_request, "audit_stage", None))
                    or _normalized_text(action_metadata.get("audit_stage"))
                    or _normalized_text(browser_metadata.get("audit_stage"))
                    or None
                ),
            }
        )
    else:
        for key in (
            "task",
            "provider",
            "model",
            "reasoning_effort",
            "cwd",
            "queue_cwd",
            "sandbox_mode",
            "approval_policy",
            "allowed_paths",
            "blocked_paths",
            "timeout_seconds",
        ):
            value = action_payload.get(key)
            if value in ("", None, [], {}):
                continue
            if isinstance(value, list):
                projected[key] = [str(item) for item in value if _normalized_text(item)]
            else:
                projected[key] = value
    return projected


__all__ = ["build_approval_overlay_payload"]
