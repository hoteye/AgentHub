from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

from shared.web_automation.proxy import BrowserProxyExecutor


def synthesize_gui_bridge_events(action: str, response: dict[str, Any]) -> list[dict[str, Any]]:
    if not response.get("ok"):
        return [
            {
                "request_id": response.get("request_id") or "req_gui_bridge",
                "kind": "task_failed",
                "name": action.replace(".", "_"),
                "status": "error",
                "summary": str(response.get("error", {}).get("message") or action),
                "payload": response.get("error") or {},
            }
        ]
    data = response.get("data") or {}
    base = {
        "request_id": response.get("request_id") or "req_gui_bridge",
        "name": action.replace(".", "_"),
        "status": "ok",
    }
    if action == "task.run":
        return [
            {
                **base,
                "kind": "task_completed",
                "summary": str(data.get("assistant_text") or "Task completed"),
                "payload": data,
            }
        ]
    if action == "shell.run":
        shell_ok = bool(data.get("ok")) and not bool(data.get("approval_required"))
        if bool(data.get("approval_required")):
            return [
                {
                    **base,
                    "kind": "approval_requested",
                    "status": "warning",
                    "summary": str(data.get("assistant_text") or "Shell approval requested"),
                    "payload": data,
                }
            ]
        return [
            {
                **base,
                "kind": "tool_event",
                "status": "ok" if shell_ok else "error",
                "summary": str(data.get("status") or f"shell rc={data.get('exit_code')}"),
                "payload": data,
            }
        ]
    if action == "chat.send":
        return [
            {
                **base,
                "kind": "task_progress",
                "summary": str(data.get("assistant_text") or "Chat message accepted"),
                "payload": data,
            }
        ]
    if action.startswith("browser.workflow.") or action.startswith("browser.playbook."):
        mode = str(data.get("mode") or "").strip().lower()
        workflow_run = data.get("workflow_run") or {}
        return [
            {
                **base,
                "kind": (
                    "browser_workflow_paused"
                    if mode == "approval_required"
                    else "browser_workflow_changed"
                ),
                "summary": str(
                    workflow_run.get("result_summary")
                    or workflow_run.get("status")
                    or data.get("mode")
                    or action
                ),
                "payload": data,
            }
        ]
    if action.startswith("browser."):
        return [
            {
                **base,
                "kind": (
                    "tool_event"
                    if action in {"browser.snapshot", "browser.console"}
                    else "browser_state_changed"
                ),
                "summary": str(data.get("message") or data.get("action") or action),
                "payload": data,
            }
        ]
    if action == "approval.resolve":
        return [
            {
                **base,
                "kind": "approval_resolved",
                "summary": str(data.get("status") or "approval resolved"),
                "payload": data,
            }
        ]
    if action == "plugin.list":
        return []
    if action.startswith("plugin."):
        return [
            {
                **base,
                "kind": "plugin_state_changed",
                "summary": str(data.get("accepted") or action),
                "payload": data,
            }
        ]
    if action == "settings.update":
        return [
            {
                **base,
                "kind": "settings_changed",
                "summary": "settings updated",
                "payload": data,
            }
        ]
    return []


def execute_browser_proxy_http(
    proxy: BrowserProxyExecutor,
    *,
    method: str,
    parsed,
    headers,
    rfile,
    base_path: str,
) -> dict[str, Any]:
    prefix = f"{base_path}/browser-proxy"
    raw_path = parsed.path
    suffix = raw_path[len(prefix) :] if raw_path.startswith(prefix) else ""
    browser_path = suffix if suffix else "/"
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
    body = _parse_browser_proxy_body(method=method, headers=headers, rfile=rfile)
    timeout_raw = (body or {}).get("timeoutMs")
    if timeout_raw is None:
        timeout_raw = (body or {}).get("timeout_ms")
    if timeout_raw is None:
        timeout_raw = query.get("timeoutMs") or query.get("timeout_ms")
    return proxy.run(
        method=method,
        path=browser_path,
        query=query,
        body=body,
        profile=str((body or {}).get("profile") or query.get("profile") or "").strip() or None,
        timeout_ms=(
            int(timeout_raw) if timeout_raw is not None and str(timeout_raw).strip() else None
        ),
    )


def _parse_browser_proxy_body(*, method: str, headers, rfile) -> dict[str, Any] | None:
    if method not in {"POST", "DELETE"}:
        return None
    content_length = int(headers.get("Content-Length") or "0")
    raw_body = rfile.read(content_length) if content_length > 0 else b""
    if not raw_body:
        return None
    try:
        parsed_body = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{exc}") from exc
    if not isinstance(parsed_body, dict):
        raise ValueError("invalid_body")
    return parsed_body
