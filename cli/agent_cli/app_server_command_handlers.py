from __future__ import annotations

import threading
from typing import Any, Callable

from cli.agent_cli import app_server_command_handlers_runtime, app_server_command_runtime
from cli.agent_cli import app_server_command_handlers_helpers
from cli.agent_cli.app_server_shell_protocol import (
    _command_response_shell_metadata,
    _exit_code_for_response,
    _first_text,
    _shell_options_from_params,
)
from cli.agent_cli.headless import prompt_response_to_dict
from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent


def _activity_event_to_dict(item: ActivityEvent) -> dict[str, Any]:
    return app_server_command_runtime.activity_event_to_dict(item)


class AppServerCommandHandlersMixin:
    def _handle_command_exec(self, request_id: Any, params: dict[str, Any]) -> None:
        command = params.get("command")
        if not isinstance(command, str) or not command.strip():
            self._emit_error_response(
                request_id=request_id,
                code=-32602,
                message="Invalid params",
                data={"detail": "params.command must be a non-empty string"},
            )
            return
        if self._has_active_job() or self.runtime.has_active_run():
            self._emit_error_response(
                request_id=request_id,
                code=-32003,
                message="Runtime busy",
            )
            return
        response = self._run_direct_shell_command(
            command.strip(),
            request_id=request_id,
            stream=bool(params.get("stream")),
            cancel_event=None,
            shell_options={
                **_shell_options_from_params(params, interactive=False),
                "metadata": {"source": "app_server_command_exec"},
            },
        )
        self._emit_result(
            request_id,
            {
                **_command_response_shell_metadata(response),
                "response": prompt_response_to_dict(response),
                "exitCode": _exit_code_for_response(response),
            },
        )

    def _handle_command_start(self, request_id: Any, params: dict[str, Any]) -> None:
        command = params.get("command")
        if not isinstance(command, str) or not command.strip():
            self._emit_error_response(
                request_id=request_id,
                code=-32602,
                message="Invalid params",
                data={"detail": "params.command must be a non-empty string"},
            )
            return
        if self._has_active_job() or self.runtime.has_active_run():
            self._emit_error_response(
                request_id=request_id,
                code=-32003,
                message="Runtime busy",
            )
            return
        result = self.runtime.begin_shell_request(
            command.strip(),
            requested_by="app_server",
            exec_mode="session_start",
            metadata={
                "source": "app_server_command_start",
                "app_server_request_id": request_id,
                "app_server_stream": bool(params.get("stream", True)),
            },
            on_activity=lambda payload: self._emit_command_session_activity(
                request_id=request_id,
                stream=bool(params.get("stream", True)),
                payload=payload,
            ),
            **_shell_options_from_params(params, interactive=True),
        )
        if result.get("status") == "approval_required":
            response = result.get("response")
            self._emit_result(
                request_id,
                {
                    "accepted": False,
                    "approvalRequired": True,
                    "response": prompt_response_to_dict(response),
                    "exitCode": _exit_code_for_response(response),
                },
            )
            return
        if result.get("status") == "started":
            session = dict(result.get("session") or {})
            session_id = str(session.get("session_id") or "").strip()
            process_id = str(session.get("process_id") or session_id).strip() or session_id
            stream = bool(params.get("stream", True))
            shell_options = _shell_options_from_params(params, interactive=True)
            self._command_sessions[session_id] = app_server_command_handlers_runtime.build_command_session_entry(
                request_id=request_id,
                command=command.strip(),
                stream=stream,
                process_id=process_id,
                shell_options=shell_options,
            )
            self._emit_command_session_activity(
                request_id=request_id,
                stream=stream,
                payload=app_server_command_handlers_runtime.build_started_payload(
                    session=session,
                    command=command.strip(),
                    session_id=session_id,
                    process_id=process_id,
                ),
            )
            self._emit_result(
                request_id,
                app_server_command_handlers_runtime.build_command_start_result(
                    session=session,
                    session_id=session_id,
                    job_id=request_id,
                ),
            )
            return
        tool_event = result.get("tool_event")
        response = self._tool_event_prompt_response(command.strip(), tool_event, exec_mode="session_start")
        self._emit_result(
            request_id,
            {
                "accepted": False,
                "response": prompt_response_to_dict(response),
                "exitCode": _exit_code_for_response(response),
            },
        )

    def _handle_command_write_stdin(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_command_handlers_helpers.handle_command_write_stdin(self, request_id, params)

    def _write_command_session_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        tools_write = getattr(getattr(self.runtime, "tools", None), "shell_write_stdin", None)
        if callable(tools_write):
            options: dict[str, Any] = {}
            if on_activity is not None:
                options["on_activity"] = on_activity
            if yield_time_ms is not None:
                options["yield_time_ms"] = int(yield_time_ms)
            try:
                return tools_write(session_id, chars, **options)
            except TypeError:
                if "yield_time_ms" in options:
                    options.pop("yield_time_ms", None)
                    return tools_write(session_id, chars, **options)
        return self.runtime.write_shell_stdin(
            session_id,
            chars,
            on_activity=on_activity,
        )

    def _handle_command_terminate(self, request_id: Any, params: dict[str, Any]) -> None:
        session_id = _first_text(params, "sessionId", "session_id")
        if not session_id and len(self._command_sessions) == 1:
            session_id = next(iter(self._command_sessions.keys()))
        if session_id:
            entry = self._command_sessions.get(session_id)
            if entry is not None:
                tool_event = self.runtime.terminate_shell_session(
                    session_id,
                    on_activity=lambda payload: self._emit_command_session_activity(
                        request_id=entry["request_id"],
                        stream=bool(entry.get("stream")),
                        payload=payload,
                    ),
                )
                if str((tool_event.payload or {}).get("status") or "").strip() == "unsupported":
                    self._emit_error_response(
                        request_id=request_id,
                        code=-32005,
                        message="Interactive shell unsupported",
                    )
                    return
                if session_id in self._command_sessions:
                    session_turn_events = list((entry or {}).get("turn_events") or [])
                    self._emit_command_session_completed(
                        request_id=entry["request_id"],
                        session_id=session_id,
                        command=str(entry.get("command") or ""),
                        tool_event=tool_event,
                        session_turn_events=session_turn_events,
                    )
                    self._command_sessions.pop(session_id, None)
                self._emit_result(
                    request_id,
                    app_server_command_handlers_runtime.build_terminate_result(
                        payload=dict(tool_event.payload or {}),
                        session_id=session_id,
                        command=str(entry.get("command") or ""),
                    ),
                )
                return
        with self._jobs_lock:
            cancel_event = self._active_command_cancel_event
            job_id = self._active_command_job_id
        if cancel_event is not None:
            already_requested = cancel_event.is_set()
            cancel_event.set()
            self._emit_result(
                request_id,
                {
                    "ok": True,
                    "interrupted": not already_requested,
                    "already_requested": already_requested,
                    "run_token": job_id,
                    "run_label": "command",
                },
            )
            return
        payload = self.runtime.interrupt_active_run()
        self._emit_result(request_id, payload)

    @staticmethod
    def _tool_event_prompt_response(command: str, tool_event: ToolEvent, *, exec_mode: str = "exec_once") -> PromptResponse:
        return app_server_command_runtime.tool_event_prompt_response(
            command,
            tool_event,
            exec_mode=exec_mode,
        )

    def _register_approved_shell_session(self, *, request_id: Any, result: dict[str, Any]) -> None:
        registration = app_server_command_handlers_runtime.approved_shell_session_registration(
            request_id=request_id,
            result=result,
        )
        if registration is None:
            return
        source_request_id = registration["request_id"]
        stream = bool(registration["stream"])
        session_id = str(registration["session_id"])
        self._command_sessions[session_id] = dict(registration["session_entry"])
        self._emit_command_session_activity(
            request_id=source_request_id,
            stream=stream,
            payload=dict(registration["activity_payload"]),
        )
        self.runtime.subscribe_shell_session(
            session_id,
            on_activity=lambda activity_payload: self._emit_command_session_activity(
                request_id=source_request_id,
                stream=stream,
                payload=activity_payload,
            ),
        )

    def _emit_command_session_activity(
        self,
        *,
        request_id: Any,
        stream: bool,
        payload: dict[str, Any],
    ) -> None:
        app_server_command_runtime.emit_command_session_activity(
            self,
            request_id=request_id,
            stream=stream,
            payload=payload,
        )

    def _emit_command_session_completed(
        self,
        *,
        request_id: Any,
        session_id: str,
        command: str,
        tool_event: ToolEvent,
        session_turn_events: list[dict[str, Any]] | None = None,
    ) -> None:
        app_server_command_runtime.emit_command_session_completed(
            self,
            request_id=request_id,
            session_id=session_id,
            command=command,
            tool_event=tool_event,
            session_turn_events=session_turn_events,
        )

    def _run_direct_shell_command(
        self,
        command: str,
        *,
        request_id: Any,
        stream: bool,
        cancel_event: threading.Event | None,
        shell_options: dict[str, Any] | None = None,
    ) -> PromptResponse:
        return app_server_command_runtime.run_direct_shell_command(
            self,
            command,
            request_id=request_id,
            stream=stream,
            cancel_event=cancel_event,
            shell_options=shell_options,
        )
