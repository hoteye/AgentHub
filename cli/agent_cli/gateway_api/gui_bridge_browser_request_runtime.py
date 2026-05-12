from __future__ import annotations

from typing import Any, Dict


def browser_action_type_from_request(request: Dict[str, Any]) -> str:
    command = str(request.get("action") or "act").strip().lower()
    kind = str(request.get("kind") or "").strip().lower().replace("-", "_")
    if command == "act" and kind:
        return f"browser.act.{kind}"
    return f"browser.{command}"


def browser_request_from_gui_payload(
    payload: Dict[str, Any],
    *,
    default_action: str,
) -> Dict[str, Any]:
    request = {
        "transport": str(payload.get("transport") or "client").strip().lower() or "client",
        "action": (
            str(payload.get("command") or payload.get("action") or default_action).strip().lower()
            or default_action
        ),
        "profile": payload.get("profile"),
        "target_id": payload.get("target_id") or payload.get("tab_id"),
        "url": payload.get("url"),
        "ref": payload.get("ref"),
        "start_ref": payload.get("start_ref"),
        "end_ref": payload.get("end_ref"),
        "level": payload.get("level"),
        "limit": payload.get("limit"),
        "path": payload.get("path"),
        "kind": payload.get("kind"),
        "text": payload.get("text") or payload.get("value"),
        "key": payload.get("key"),
        "values": payload.get("values"),
        "fields": payload.get("fields"),
        "time_ms": payload.get("time_ms"),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "paths": payload.get("paths"),
        "input_ref": payload.get("input_ref"),
        "accept": payload.get("accept"),
        "prompt_text": payload.get("prompt_text"),
        "method": payload.get("method"),
        "query": payload.get("query") if isinstance(payload.get("query"), dict) else None,
        "body": payload.get("body"),
        "timeout_ms": payload.get("timeout_ms") or payload.get("time_ms"),
    }
    return {key: value for key, value in request.items() if value is not None and value != ""}


def browser_proxy_params(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "method": str(payload.get("method") or "GET"),
        "path": str(payload.get("path") or ""),
        "query": payload.get("query") if isinstance(payload.get("query"), dict) else None,
        "body": payload.get("body"),
        "timeout_ms": int(payload["timeout_ms"]) if payload.get("timeout_ms") is not None else None,
        "profile": str(payload.get("profile") or "").strip() or None,
    }


def browser_client_params(payload: Dict[str, Any], *, command: str) -> Dict[str, Any]:
    return {
        "action": command,
        "profile": payload.get("profile"),
        "tab_id": payload.get("target_id") or payload.get("tab_id"),
        "url": payload.get("url"),
        "ref": payload.get("ref"),
        "start_ref": payload.get("start_ref"),
        "end_ref": payload.get("end_ref"),
        "level": payload.get("level"),
        "limit": payload.get("limit"),
        "path": payload.get("path"),
        "kind": payload.get("kind") or payload.get("action"),
        "text": payload.get("text") or payload.get("value"),
        "key": payload.get("key"),
        "values": payload.get("values"),
        "fields": payload.get("fields"),
        "time_ms": payload.get("time_ms"),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "paths": payload.get("paths"),
        "input_ref": payload.get("input_ref"),
        "accept": payload.get("accept"),
        "prompt_text": payload.get("prompt_text"),
    }
