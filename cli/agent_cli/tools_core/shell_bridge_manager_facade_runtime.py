from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import shell_result_runtime, shell_stream_bridge
from cli.agent_cli.tools_core.shell_completed_runtime import ShellCompletedSessionCache
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


class ShellSessionManagerFacadeMixin:
    @staticmethod
    def _completed_replay_event(completed_payload: dict[str, Any]) -> ToolEvent:
        return ShellCompletedSessionCache.completed_replay_event(completed_payload)

    @staticmethod
    def _subscribe_payload_from_completed_payload(
        completed_payload: dict[str, Any]
    ) -> dict[str, Any]:
        return ShellCompletedSessionCache.subscribe_payload_from_completed_payload(
            completed_payload
        )

    @staticmethod
    def _replayable_event_history(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return ShellCompletedSessionCache.replayable_event_history(payloads)

    @staticmethod
    def _completed_event_history(completed_payload: dict[str, Any]) -> list[dict[str, Any]]:
        return ShellCompletedSessionCache.completed_event_history(completed_payload)

    @staticmethod
    def _completed_readonly_write_payload(
        completed_payload: dict[str, Any],
        *,
        input_chars: str,
    ) -> dict[str, Any]:
        return ShellCompletedSessionCache.completed_readonly_write_payload(
            completed_payload,
            input_chars=input_chars,
        )

    def start_session_result(
        self,
        *,
        command: str,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Any = None,
        cancel_event: Any = None,
        exec_mode: str = "session_start",
    ) -> CommandExecutionResult:
        session = self.start_session(
            command=command,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )
        event = shell_result_runtime.session_started_event_from_session(
            session,
            command=command,
            exec_mode=exec_mode,
        )
        return shell_result_runtime.shell_command_result(
            assistant_text="Start shell session.",
            event=event,
            command=command,
        )

    def write_stdin_result(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Any = None,
        cancel_event: Any = None,
    ) -> CommandExecutionResult:
        event = self.write_stdin(
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )
        command = str((event.payload or {}).get("command") or "").strip() or None
        return shell_result_runtime.shell_command_result(
            assistant_text="Write shell stdin.",
            event=event,
            command=command,
        )

    def subscribe_result(
        self,
        session_id: str,
        *,
        on_activity: Any = None,
    ) -> CommandExecutionResult:
        event = self.subscribe(
            session_id,
            on_activity=on_activity,
        )
        command = str((event.payload or {}).get("command") or "").strip() or None
        return shell_result_runtime.shell_command_result(
            assistant_text="Subscribe shell session.",
            event=event,
            command=command,
        )

    def terminate_result(
        self,
        session_id: str,
        *,
        on_activity: Any = None,
    ) -> CommandExecutionResult:
        event = self.terminate(
            session_id,
            on_activity=on_activity,
        )
        command = str((event.payload or {}).get("command") or "").strip() or None
        return shell_result_runtime.shell_command_result(
            assistant_text="Terminate shell session.",
            event=event,
            command=command,
        )

    @staticmethod
    def _build_fallback_payload(session: _ShellSession) -> dict[str, Any]:
        return shell_stream_bridge.build_fallback_payload(session)

    @staticmethod
    def _normalize_write_yield_time_ms(
        value: int | float | None,
        *,
        empty_input: bool,
        allow_extended_empty_poll: bool = False,
    ) -> int:
        return shell_stream_bridge.normalize_write_yield_time_ms(
            value,
            empty_input=empty_input,
            allow_extended_empty_poll=allow_extended_empty_poll,
        )

    @staticmethod
    def _output_snapshot_payload(
        session: _ShellSession, incremental: dict[str, str]
    ) -> dict[str, Any]:
        return shell_result_runtime.output_snapshot_payload(session, incremental)

    @staticmethod
    def _final_status_fields(session: _ShellSession) -> dict[str, Any]:
        return shell_result_runtime.final_status_fields(session)
