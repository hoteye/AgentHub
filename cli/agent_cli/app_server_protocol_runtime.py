from __future__ import annotations

from typing import Any

from cli.agent_cli import __version__
from cli.agent_cli import app_server_protocol_action_helpers_runtime as _action_helpers
from cli.agent_cli import app_server_protocol_catalog_helpers_runtime as _catalog_helpers
from cli.agent_cli import app_server_protocol_dispatch_helpers_runtime as _dispatch_helpers
from cli.agent_cli import app_server_protocol_flow_helpers_runtime as _flow_helpers
from cli.agent_cli import app_server_protocol_normalization_helpers_runtime as _normalization_helpers
from cli.agent_cli import app_server_protocol_projection_helpers_runtime as _projection_helpers
from cli.agent_cli import app_server_protocol_pure_helpers_runtime as _pure_helpers
from cli.agent_cli import app_server_protocol_thread_helpers_runtime as _thread_helpers
from cli.agent_cli import app_server_protocol_turn_helpers_runtime as _turn_helpers
from cli.agent_cli import app_server_session_runtime_helpers
from cli.agent_cli.app_server_payloads import (
    reference_mcp_server_status_payload,
    reference_model_list_payload,
    reference_thread_payload,
    reference_turn_runtime_payload,
    thread_resume_payload as _thread_resume_payload,
)
from cli.agent_cli.app_server_shell_protocol import (
    _first_text,
)
from cli.agent_cli.runtime_core.tool_call_context_runtime import (
    active_app_server_turn_id,
)
from cli.agent_cli.gateway_server.dispatcher import (
    gateway_dispatcher_methods,
    gateway_dispatcher_supports_method,
)
from cli.agent_cli.runtime_core.thread_session import validate_resume_history
from cli.agent_cli.tools_core.registry import runtime_registry_mcp_server_entries
from cli.agent_cli.models import (
    prompt_response_turn_events,
)
from workers.actions import ActionError

APP_SERVER_BASE_METHODS: tuple[str, ...] = (
    "initialize",
    "session/run",
    "session/start",
    "session/interrupt",
    "session/providerStatus",
    "thread/start",
    "thread/list",
    "thread/read",
    "thread/resume",
    "thread/fork",
    "turn/start",
    "model/list",
    "mcpServerStatus/list",
    "gateway/dispatch",
    "gateway/webhook",
    "gateway/state",
    "approval/list",
    "approval/decide",
    "action/execute",
    "tools/list",
    "browser/proxy",
    "command/exec",
    "command/start",
    "command/writeStdin",
    "command/terminate",
    "server/ping",
)

REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS: dict[str, str] = {
    "turn/interrupt": "session/interrupt",
    "skills/list": "tools/list",
    "config/read": "session/providerStatus",
}

APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND = "Method not found"
APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS = "Invalid params"
APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED = "Not initialized"
APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT = "params must be an object"
APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED = "send initialize and initialized before other methods"
APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD = "unsupported_reference_method"


def _build_app_server_gateway_extension_methods() -> tuple[str, ...]:
    return _pure_helpers.build_app_server_gateway_extension_methods(
        base_methods=APP_SERVER_BASE_METHODS,
        gateway_methods=gateway_dispatcher_methods(),
    )


APP_SERVER_GATEWAY_EXTENSION_METHODS: tuple[str, ...] = _build_app_server_gateway_extension_methods()
APP_SERVER_CAPABILITY_METHODS: tuple[str, ...] = (*APP_SERVER_BASE_METHODS, *APP_SERVER_GATEWAY_EXTENSION_METHODS)


def app_server_capability_methods() -> list[str]:
    return list(APP_SERVER_CAPABILITY_METHODS)


def app_server_gateway_extension_methods() -> list[str]:
    return list(APP_SERVER_GATEWAY_EXTENSION_METHODS)


def unsupported_reference_method_error_data(method: str) -> dict[str, Any] | None:
    return _projection_helpers.unsupported_reference_method_error_data(
        method,
        replacements=REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS,
        compatibility=APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
    )


_booleanish = _normalization_helpers.booleanish
_parse_cursor = _normalization_helpers.parse_cursor
_paginate_items = _normalization_helpers.paginate_items
_parse_limit = _normalization_helpers.parse_limit
_reference_approval_policy_value = _normalization_helpers.reference_approval_policy_value
_reference_sandbox_policy_payload = _projection_helpers.reference_sandbox_policy_payload
_reasoning_effort_value = _normalization_helpers.reasoning_effort_value
_service_tier_value = _normalization_helpers.service_tier_value
_turn_prompt_from_input_items = _projection_helpers.turn_prompt_from_input_items
_completed_turn_payload_from_response = _projection_helpers.completed_turn_payload_from_response
_failed_turn_payload = _projection_helpers.failed_turn_payload


def handle_line(server: Any, line: str) -> None:
    _dispatch_helpers.handle_line(
        server,
        line,
        unsupported_reference_method_error_data_fn=unsupported_reference_method_error_data,
        gateway_dispatcher_supports_method_fn=gateway_dispatcher_supports_method,
        invalid_params_message=APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
        invalid_params_detail=APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT,
        not_initialized_message=APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED,
        not_initialized_detail=APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED,
    )


def handle_initialized_notification(server: Any, params: dict[str, Any]) -> None:
    _dispatch_helpers.handle_initialized_notification(server, params)


def handle_initialize(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _dispatch_helpers.handle_initialize(
        server,
        request_id,
        params,
        version=__version__,
        app_server_capability_methods_fn=app_server_capability_methods,
    )


def handle_thread_read(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_thread_read(
        server,
        request_id,
        params,
        first_text_fn=_first_text,
        thread_helpers=_thread_helpers,
        reference_thread_payload_fn=reference_thread_payload,
    )


def handle_thread_fork(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_thread_fork(
        server,
        request_id,
        params,
        first_text_fn=_first_text,
        thread_helpers=_thread_helpers,
        reference_thread_payload_fn=reference_thread_payload,
        reference_approval_policy_value_fn=_reference_approval_policy_value,
        reference_sandbox_policy_payload_fn=_reference_sandbox_policy_payload,
        reasoning_effort_value_fn=_reasoning_effort_value,
        service_tier_value_fn=_service_tier_value,
    )


def _run_turn_start_job(
    server: Any,
    *,
    job_id: str,
    request_id: Any,
    thread_id: str,
    turn_id: str,
    prompt: str,
    attachments: list[Any],
) -> None:
    _flow_helpers.run_turn_start_job(
        server,
        job_id=job_id,
        request_id=request_id,
        thread_id=thread_id,
        turn_id=turn_id,
        prompt=prompt,
        attachments=attachments,
        session_runtime_helpers=app_server_session_runtime_helpers,
        turn_helpers=_turn_helpers,
        reference_turn_runtime_payload_fn=reference_turn_runtime_payload,
        completed_turn_payload_from_response_fn=_completed_turn_payload_from_response,
        failed_turn_payload_fn=_failed_turn_payload,
        prompt_response_turn_events_fn=prompt_response_turn_events,
        active_app_server_turn_id_fn=active_app_server_turn_id,
    )


def _start_turn_start_job(
    server: Any,
    *,
    request_id: Any,
    thread_id: str,
    turn_id: str,
    prompt: str,
    attachments: list[Any],
) -> None:
    _flow_helpers.start_turn_start_job(
        server,
        request_id=request_id,
        thread_id=thread_id,
        turn_id=turn_id,
        prompt=prompt,
        attachments=attachments,
        job_runner_fn=_run_turn_start_job,
    )


def handle_turn_start(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_turn_start(
        server,
        request_id,
        params,
        first_text_fn=_first_text,
        turn_prompt_from_input_items_fn=_turn_prompt_from_input_items,
        reference_turn_runtime_payload_fn=reference_turn_runtime_payload,
        start_turn_start_job_fn=_start_turn_start_job,
    )


def handle_model_list(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_model_list(
        server,
        request_id,
        params,
        first_text_fn=_first_text,
        parse_cursor_fn=_parse_cursor,
        parse_limit_fn=_parse_limit,
        booleanish_fn=_booleanish,
        paginate_items_fn=_paginate_items,
        catalog_helpers=_catalog_helpers,
        reference_model_list_payload_fn=reference_model_list_payload,
    )


def handle_mcp_server_status_list(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_mcp_server_status_list(
        server,
        request_id,
        params,
        parse_cursor_fn=_parse_cursor,
        parse_limit_fn=_parse_limit,
        paginate_items_fn=_paginate_items,
        catalog_helpers=_catalog_helpers,
        runtime_registry_mcp_server_entries_fn=runtime_registry_mcp_server_entries,
        reference_mcp_server_status_payload_fn=reference_mcp_server_status_payload,
    )


def handle_thread_resume(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_thread_resume(
        server,
        request_id,
        params,
        validate_resume_history_fn=validate_resume_history,
        thread_resume_payload_fn=_thread_resume_payload,
    )


def handle_action_execute(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    _flow_helpers.handle_action_execute(
        server,
        request_id,
        params,
        action_execute_request_payload_fn=_action_helpers.action_execute_request_payload,
        first_text_fn=_first_text,
        action_error_cls=ActionError,
    )
