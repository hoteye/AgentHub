from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli import (
    runtime_shell_bindings_helpers_runtime as runtime_shell_bindings_helpers_runtime_service,
)
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import CommandExecutionResult, PromptResponse, ToolEvent
from cli.agent_cli.runtime_services import approval_runtime as approval_runtime_service
from cli.agent_cli.runtime_services import shell_runtime as shell_runtime_service


def _normalize_shell_exec_mode(value: str | None) -> str:
    return shell_runtime_service.normalize_shell_exec_mode(value)


def _host_platform(self: Any) -> HostPlatform:
    return shell_runtime_service.host_platform(self)


def _normalize_shell_override(self: Any, shell: str | None) -> str | None:
    return shell_runtime_service.normalize_shell_override(self, shell)


def _shell_command_text(command: str, *, exec_mode: str) -> str:
    return shell_runtime_service.shell_command_text(command, exec_mode=exec_mode)


def _shell_start_event_from_session(
    session: dict[str, Any],
    *,
    command: str,
    exec_mode: str,
) -> ToolEvent:
    return shell_runtime_service.shell_start_event_from_session(
        session,
        command=command,
        exec_mode=exec_mode,
    )


def _shell_result_from_event(
    assistant_text: str,
    event: ToolEvent,
    *,
    command: str | None = None,
) -> CommandExecutionResult:
    return shell_runtime_service.shell_result_from_event(
        assistant_text,
        event,
        command=command,
    )


def run_shell_command(
    self: Any,
    command: str,
    *,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    return shell_runtime_service.run_shell_command(
        self,
        command,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def run_shell_command_result(
    self: Any,
    command: str,
    *,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> CommandExecutionResult:
    return shell_runtime_service.run_shell_command_result(
        self,
        command,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def shell_approval_response(
    self: Any,
    command: str,
    *,
    requested_by: str = "cli",
    timeout_sec: int = 60,
    exec_mode: str = "exec_once",
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    metadata: dict[str, Any] | None = None,
    policy_payload: dict[str, Any] | None = None,
) -> PromptResponse:
    return runtime_shell_bindings_helpers_runtime_service.shell_approval_response(
        self,
        command,
        requested_by=requested_by,
        timeout_sec=timeout_sec,
        exec_mode=exec_mode,
        cwd=cwd,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        metadata=metadata,
        policy_payload=policy_payload,
    )


def begin_shell_request(
    self: Any,
    command: str,
    *,
    requested_by: str = "cli",
    exec_mode: str = "exec_once",
    timeout_sec: int = 60,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    metadata: dict[str, Any] | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    return runtime_shell_bindings_helpers_runtime_service.begin_shell_request(
        self,
        command,
        requested_by=requested_by,
        exec_mode=exec_mode,
        timeout_sec=timeout_sec,
        cwd=cwd,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        metadata=metadata,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def bind_runtime_shell_methods(
    runtime_cls: Any,
    *,
    trace: Callable[..., None],
    preview_text: Callable[..., str],
    connector_key: str,
    plugin_name: str,
    approval_reason: str,
) -> None:
    def start_shell_session(
        self: Any,
        command: str,
        *,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return shell_runtime_service.start_shell_session(
            self,
            command,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            trace=trace,
        )

    def write_shell_stdin(
        self: Any,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ToolEvent:
        return shell_runtime_service.write_shell_stdin(
            self,
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def write_shell_stdin_result(
        self: Any,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandExecutionResult:
        return shell_runtime_service.write_shell_stdin_result(
            self,
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
            trace=trace,
            preview_text=preview_text,
        )

    def terminate_shell_session(
        self: Any,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_runtime_service.terminate_shell_session(
            self,
            session_id,
            on_activity=on_activity,
        )

    def terminate_shell_session_result(
        self: Any,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> CommandExecutionResult:
        return shell_runtime_service.terminate_shell_session_result(
            self,
            session_id,
            on_activity=on_activity,
        )

    def subscribe_shell_session(
        self: Any,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_runtime_service.subscribe_shell_session(
            self,
            session_id,
            on_activity=on_activity,
        )

    def subscribe_shell_session_result(
        self: Any,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> CommandExecutionResult:
        return shell_runtime_service.subscribe_shell_session_result(
            self,
            session_id,
            on_activity=on_activity,
        )

    def request_shell_approval(
        self: Any,
        command: str,
        *,
        requested_by: str = "cli",
        timeout_sec: int = 60,
        exec_mode: str = "exec_once",
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        metadata: dict[str, Any] | None = None,
        sandbox_permissions: str | None = None,
        justification: str | None = None,
        prefix_rule: list[str] | tuple[str, ...] | None = None,
        additional_permissions: dict[str, Any] | None = None,
        policy_payload: dict[str, Any] | None = None,
    ) -> ToolEvent:
        return approval_runtime_service.request_shell_approval(
            self,
            command,
            requested_by=requested_by,
            timeout_sec=timeout_sec,
            exec_mode=exec_mode,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            metadata=metadata,
            sandbox_permissions=sandbox_permissions,
            justification=justification,
            prefix_rule=prefix_rule,
            additional_permissions=additional_permissions,
            policy_payload=policy_payload,
            connector_key=connector_key,
            plugin_name=plugin_name,
            approval_reason=approval_reason,
        )

    runtime_cls._normalize_shell_exec_mode = staticmethod(_normalize_shell_exec_mode)
    runtime_cls._host_platform = _host_platform
    runtime_cls._normalize_shell_override = _normalize_shell_override
    runtime_cls._shell_command_text = staticmethod(_shell_command_text)
    runtime_cls._shell_start_event_from_session = staticmethod(_shell_start_event_from_session)
    runtime_cls._shell_result_from_event = staticmethod(_shell_result_from_event)
    runtime_cls.run_shell_command = run_shell_command
    runtime_cls.run_shell_command_result = run_shell_command_result
    runtime_cls.start_shell_session = start_shell_session
    runtime_cls.write_shell_stdin = write_shell_stdin
    runtime_cls.write_shell_stdin_result = write_shell_stdin_result
    runtime_cls.terminate_shell_session = terminate_shell_session
    runtime_cls.terminate_shell_session_result = terminate_shell_session_result
    runtime_cls.subscribe_shell_session = subscribe_shell_session
    runtime_cls.subscribe_shell_session_result = subscribe_shell_session_result
    runtime_cls.shell_approval_response = shell_approval_response
    runtime_cls.begin_shell_request = begin_shell_request
    runtime_cls.request_shell_approval = request_shell_approval
