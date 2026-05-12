from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

try:
    import pty as pty_module
except ImportError:
    pty_module = None

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    shell_bridge_exec_runtime,
    shell_bridge_lifecycle_runtime,
    shell_bridge_process_runtime,
    shell_bridge_runtime,
    shell_bridge_session_manager_runtime,
    shell_command_runtime,
    shell_event_payloads,
    shell_session_runtime,
    shell_stream_bridge,
)
from cli.agent_cli.tools_core.shell_bridge_helpers import (
    _join_aggregated_output,
    _shell_command_result,
    _shell_exec_args,
    _trim_output,
    session_started_event_from_session,
)
from cli.agent_cli.tools_core.shell_bridge_manager_facade_runtime import (
    ShellSessionManagerFacadeMixin,
)
from cli.agent_cli.tools_core.shell_completed_runtime import ShellCompletedSessionCache
from cli.agent_cli.tools_core.shell_session_state import _ShellSession

# Keep legacy module attributes reachable for downstream monkeypatches.
_MONKEYPATCH_EXPORTS = (
    shell_command_runtime,
    ShellCompletedSessionCache,
    shell_bridge_runtime,
    shell_event_payloads,
    shell_session_runtime,
    shell_stream_bridge,
    shell_bridge_process_runtime,
    _join_aggregated_output,
    _shell_command_result,
    _trim_output,
    session_started_event_from_session,
)


def execute_shell(
    *,
    host_platform: HostPlatform,
    command: str,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    return shell_bridge_exec_runtime.execute_shell(
        host_platform=host_platform,
        command=command,
        manager_factory=lambda platform: ShellSessionManager(host_platform=platform),
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def execute_shell_result(
    *,
    host_platform: HostPlatform,
    command: str,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> CommandExecutionResult:
    return shell_bridge_exec_runtime.execute_shell_result(
        host_platform=host_platform,
        command=command,
        execute_shell_fn=execute_shell,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


class ShellSessionManager(ShellSessionManagerFacadeMixin):
    def __init__(
        self,
        *,
        host_platform: HostPlatform,
        max_live_sessions: int = 32,
        completed_cache_limit: int = 128,
        workspace_root_getter: Callable[[], str | None] | None = None,
    ) -> None:
        shell_bridge_session_manager_runtime.init_manager(
            self,
            host_platform=host_platform,
            max_live_sessions=max_live_sessions,
            completed_cache_limit=completed_cache_limit,
            workspace_root_getter=workspace_root_getter,
        )

    def _get_session(self, session_id: str) -> _ShellSession | None:
        return shell_bridge_session_manager_runtime.get_session(self, session_id)

    def _get_completed_payload(self, session_id: str) -> dict[str, Any] | None:
        return shell_bridge_session_manager_runtime.get_completed_payload(self, session_id)

    def _record_completed_payload(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        event_history: list[dict[str, Any]] | None = None,
    ) -> None:
        shell_bridge_session_manager_runtime.record_completed_payload(
            self,
            session_id,
            payload,
            event_history=event_history,
        )

    def _sessions_to_prune_after_start(self, *, keep_session_id: str) -> list[_ShellSession]:
        return shell_bridge_session_manager_runtime.sessions_to_prune_after_start(
            self,
            keep_session_id=keep_session_id,
        )

    def _prune_session(self, session: _ShellSession) -> None:
        shell_bridge_session_manager_runtime.prune_session(self, session)

    def start_session(
        self,
        *,
        command: str,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        return shell_bridge_lifecycle_runtime.start_session(
            self,
            command=command,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
            pty_module=pty_module,
            shell_exec_args_builder=_shell_exec_args,
        )

    def _workspace_root(self) -> str | None:
        return shell_bridge_session_manager_runtime.workspace_root(self)

    def interrupt_sessions_for_cancel_event(
        self,
        cancel_event: threading.Event | None,
        *,
        reason: str = "user_interrupt",
    ) -> dict[str, Any]:
        return shell_bridge_session_manager_runtime.interrupt_sessions_for_cancel_event(
            self,
            cancel_event,
            reason=reason,
        )

    def wait_for_completion(
        self,
        session_id: str,
        *,
        timeout_sec: int | float | None = None,
        cancel_event: threading.Event | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return shell_bridge_session_manager_runtime.wait_for_completion(
            self,
            session_id,
            timeout_sec=timeout_sec,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )

    def write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ToolEvent:
        return shell_bridge_session_manager_runtime.write_stdin(
            self,
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def subscribe(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_bridge_session_manager_runtime.subscribe(
            self,
            session_id,
            on_activity=on_activity,
        )

    def terminate(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_bridge_session_manager_runtime.terminate(
            self,
            session_id,
            on_activity=on_activity,
        )

    @classmethod
    def _interrupt_session(cls, session: _ShellSession, *, reason: str) -> None:
        shell_bridge_lifecycle_runtime.interrupt_session(cls, session, reason=reason)

    @staticmethod
    def _terminate_process(session: _ShellSession) -> None:
        shell_bridge_lifecycle_runtime.terminate_process(session)

    def _start_reader(self, session: _ShellSession, stream_name: str, stream: Any) -> None:
        shell_bridge_lifecycle_runtime.start_reader(session, stream_name, stream)

    def _start_pty_reader(self, session: _ShellSession) -> None:
        shell_bridge_lifecycle_runtime.start_pty_reader(session)

    def _watch_session(self, session: _ShellSession) -> None:
        shell_bridge_lifecycle_runtime.watch_session(self, session)

    def _remove_live_session(self, session_id: str) -> None:
        shell_bridge_session_manager_runtime.remove_live_session(self, session_id)

    def _drain_incremental_output(
        self,
        session: _ShellSession,
        *,
        yield_time_ms: int,
        max_output_chars: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        return shell_bridge_lifecycle_runtime.drain_incremental_output(
            self,
            session,
            yield_time_ms=yield_time_ms,
            max_output_chars=max_output_chars,
            cancel_event=cancel_event,
        )
