from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.routing import normalize_kernel_engine
from cli.agent_cli.runtime_tools_surface_runtime import runtime_tools_capabilities


def handle_provider_status(server: Any, *, request_id: Any) -> None:
    status = dict(server.runtime.agent.provider_status() or {})
    server._emit_result(request_id, {"providerStatus": status})


def handle_thread_start(
    server: Any,
    *,
    request_id: Any,
    params: dict[str, Any],
    thread_response_payload_fn,
) -> None:
    engine = normalize_kernel_engine(params.get("engine"))
    if engine == "codex_sidecar":
        sidecar_starter = getattr(server, "_start_codex_sidecar_thread", None)
        if callable(sidecar_starter):
            sidecar_starter(request_id=request_id, params=params)
            return
        server._emit_error_response(
            request_id=request_id,
            code=-32010,
            message="Thread start failed",
            data={"detail": "codex_sidecar engine is not available on this server"},
        )
        return
    try:
        thread_record = server.runtime.start_thread(
            name=str(params.get("name") or "").strip() or None,
            cwd=str(params.get("cwd") or "").strip() or None,
        )
    except Exception as exc:
        server._emit_error_response(
            request_id=request_id,
            code=-32010,
            message="Thread start failed",
            data={"detail": f"{type(exc).__name__}: {exc}"},
        )
        return
    thread = server.runtime.describe_thread(thread_record, status="idle", turns=[])
    server._emit_result(request_id, thread_response_payload_fn(server.runtime, thread))


def handle_thread_list(
    server: Any,
    *,
    request_id: Any,
    params: dict[str, Any],
) -> None:
    try:
        threads = server.runtime.list_threads(
            limit=int(params.get("limit") or 50),
            cwd=str(params.get("cwd") or "").strip() or None,
        )
    except Exception as exc:
        server._emit_error_response(
            request_id=request_id,
            code=-32011,
            message="Thread list failed",
            data={"detail": f"{type(exc).__name__}: {exc}"},
        )
        return
    loaded_thread_id = server.runtime.thread_id
    active_thread_id = loaded_thread_id or (
        server.runtime.thread_store.get_active_thread_id()
        if server.runtime.thread_store is not None
        else None
    )
    thread_items = [
        server.runtime.describe_thread(
            item,
            status=(
                "idle"
                if str(item.get("thread_id") or "") == str(loaded_thread_id or "")
                else "not_loaded"
            ),
            turns=[],
        )
        for item in threads
    ]
    server._emit_result(
        request_id,
        {
            "threads": thread_items,
            "activeThreadId": active_thread_id,
        },
    )


def handle_tools_list(
    server: Any,
    *,
    request_id: Any,
    runtime_registry_mcp_server_entries_fn,
) -> None:
    payload = runtime_tools_capabilities(server.runtime)
    plugin_manager = getattr(server.runtime.tools, "_plugin_manager", None)
    mcp_server_entries = runtime_registry_mcp_server_entries_fn(
        plugin_manager,
        runtime_capabilities=dict(payload or {}),
    )
    mcp_servers = dict(payload.get("mcp_servers") or {})
    if not mcp_servers:
        mcp_servers = {
            str(item.get("name") or ""): dict(item)
            for item in mcp_server_entries
            if str(item.get("name") or "").strip()
        }
    server._emit_result(
        request_id,
        {
            "tools": payload.get("tools") or [],
            "ok": bool(payload.get("ok", True)),
            "workspaceTrust": str(payload.get("workspace_trust") or "trusted"),
            "mcpServers": mcp_servers,
            "mcpServerEntries": mcp_server_entries,
            "appConnectors": list(payload.get("app_connectors") or []),
        },
    )
