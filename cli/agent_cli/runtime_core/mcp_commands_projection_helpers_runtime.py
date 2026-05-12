from __future__ import annotations

from typing import Any

from cli.agent_cli.mcp.remote_calls import format_projected_mcp_tool_call
from cli.agent_cli.slash_parser import SlashInvocation

from . import mcp_commands_runtime as _runtime_impl
from .mcp_commands_normalization_helpers_runtime import parse_args_callback
from .mcp_commands_pure_helpers_runtime import invoke_first, resolve_mcp_runtime


def handle_mcp_list(runtime: Any) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_list(
        runtime,
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_list_payload=_runtime_impl.format_mcp_list_payload,
    )


def handle_mcp_mutation(runtime: Any, action: str, target: str) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_mutation(
        runtime,
        action,
        target,
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_action_payload=_runtime_impl.format_mcp_action_payload,
    )


def handle_mcp_inspect(runtime: Any, target: str) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_inspect(
        runtime,
        target,
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_inspect_payload=_runtime_impl.format_mcp_inspect_payload,
    )


def handle_mcp_auth(
    runtime: Any,
    arg_text: str,
    *,
    mode_hint: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_auth(
        runtime,
        arg_text,
        mode_hint=mode_hint,
        resolve_mcp_runtime=resolve_mcp_runtime,
        parse_args=parse_args_callback(slash_invocation),
        parse_headers_json_fn=_runtime_impl.parse_headers_json,
        parse_callback_json_fn=_runtime_impl.parse_callback_json,
        handle_mcp_auth_set_fn=handle_mcp_auth_set,
        handle_mcp_auth_clear_fn=handle_mcp_auth_clear,
    )


def handle_mcp_auth_set(
    mcp_runtime: Any,
    *,
    server_name: str,
    token: str,
    headers: dict[str, str],
    callback_mode: bool,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_auth_set(
        mcp_runtime,
        server_name=server_name,
        token=token,
        headers=headers,
        callback_mode=callback_mode,
        invoke_first=invoke_first,
        format_auth_payload=_runtime_impl.format_mcp_auth_payload,
    )


def handle_mcp_auth_clear(mcp_runtime: Any, *, server_name: str) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_auth_clear(
        mcp_runtime,
        server_name=server_name,
        invoke_first=invoke_first,
        format_auth_payload=_runtime_impl.format_mcp_auth_payload,
    )


def handle_mcp_resource(
    runtime: Any,
    arg_text: str,
    *,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_resource(
        runtime,
        arg_text,
        parse_args=parse_args_callback(slash_invocation),
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_resource_list_payload=_runtime_impl.format_mcp_resource_list_payload,
        format_resource_read_payload=_runtime_impl.format_mcp_resource_read_payload,
    )


def handle_mcp_tool_call(
    runtime: Any,
    arg_text: str,
    *,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_tool_call(
        runtime,
        arg_text,
        parse_args=parse_args_callback(slash_invocation),
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_projected_mcp_tool_call_fn=format_projected_mcp_tool_call,
    )


def handle_mcp_channel(
    runtime: Any,
    arg_text: str,
    *,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_channel(
        runtime,
        arg_text,
        resolve_mcp_runtime=resolve_mcp_runtime,
        parse_args=parse_args_callback(slash_invocation),
        invoke_first=invoke_first,
        format_channel_list_payload=_format_mcp_channel_list_payload,
    )


def handle_mcp_permission(
    runtime: Any,
    arg_text: str,
    *,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    return _runtime_impl.handle_mcp_permission(
        runtime,
        arg_text,
        resolve_mcp_runtime=resolve_mcp_runtime,
        parse_args=parse_args_callback(slash_invocation),
        invoke_first=invoke_first,
        parse_bool_flag_fn=_runtime_impl.parse_bool_flag,
        format_permission_list_payload=_format_mcp_permission_list_payload,
        format_permission_respond_payload=_runtime_impl.format_mcp_permission_respond_payload,
    )


def _format_mcp_channel_list_payload(payload: Any, *, server_name: str | None) -> str:
    return _runtime_impl.format_mcp_channel_list_payload(
        payload,
        server_name=server_name,
        normalize_payload_items_fn=_runtime_impl.normalize_payload_items,
    )


def _format_mcp_permission_list_payload(payload: Any, *, server_name: str | None) -> str:
    return _runtime_impl.format_mcp_permission_list_payload(
        payload,
        server_name=server_name,
        normalize_payload_items_fn=_runtime_impl.normalize_payload_items,
    )
