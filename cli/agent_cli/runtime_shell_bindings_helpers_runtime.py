from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli import runtime_action_policy_runtime
from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent
from cli.agent_cli import runtime_runtime


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
    metadata: Dict[str, Any] | None = None,
    policy_payload: Dict[str, Any] | None = None,
) -> PromptResponse:
    return runtime_runtime.shell_approval_response(
        command=command,
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
        normalize_shell_exec_mode_fn=self._normalize_shell_exec_mode,
        request_shell_approval_fn=self.request_shell_approval,
        shell_command_text_fn=lambda value, normalized_exec_mode: self._shell_command_text(
            value,
            exec_mode=normalized_exec_mode,
        ),
        activity_event_factory=ActivityEvent,
        prompt_response_factory=PromptResponse,
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
    metadata: Dict[str, Any] | None = None,
    on_activity: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: threading.Event | None = None,
) -> Dict[str, Any]:
    return runtime_runtime.begin_shell_request(
        command=command,
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
        evaluate_exec_command_runtime_policy_fn=lambda command_text, workdir: runtime_action_policy_runtime.evaluate_exec_command_action_policy(
            self,
            command_text,
            workdir=workdir,
        ),
        shell_approval_is_cached_fn=lambda **kwargs: approval_contract_runtime.shell_approval_is_cached(
            self,
            **kwargs,
        ),
        normalize_shell_exec_mode_fn=self._normalize_shell_exec_mode,
        shell_approval_response_fn=self.shell_approval_response,
        start_shell_session_fn=self.start_shell_session,
        tool_event_factory=ToolEvent,
        shell_result_from_event_fn=lambda assistant_text, event, command_text: self._shell_result_from_event(
            assistant_text,
            event,
            command=command_text,
        ),
        shell_start_event_from_session_fn=lambda session, command_text, normalized_exec_mode: self._shell_start_event_from_session(
            session,
            command=command_text,
            exec_mode=normalized_exec_mode,
        ),
        run_shell_command_result_fn=self.run_shell_command_result,
    )
