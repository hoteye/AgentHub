from __future__ import annotations

# ruff: noqa: E402,F401,I001

import json
import sys
import threading
from collections.abc import Callable
from typing import Any, TextIO

from cli.agent_cli.app_server_main_runtime import _configure_stdio, _ensure_repo_root_on_path


_configure_stdio()
_ensure_repo_root_on_path()

from cli.agent_cli import (  # noqa: E402
    app_server_helpers,
    app_server_protocol_runtime,
    app_server_request_bridge,
    app_server_session_runtime,
)
from cli.agent_cli.app_server_command_handlers import AppServerCommandHandlersMixin  # noqa: E402
from cli.agent_cli.app_server_connection_runtime import _ConnectionState  # noqa: E402
from cli.agent_cli.app_server_codex_sidecar_thread_mixin import (  # noqa: E402
    CodexSidecarThreadMixin,
)
from cli.agent_cli.app_server_payloads import (  # noqa: E402
    thread_response_payload as _thread_response_payload,
)
from cli.agent_cli.app_server_shell_protocol import _exit_code_for_response  # noqa: E402,F401
from cli.agent_cli.gateway_server.dispatcher import dispatch_gateway_method  # noqa: E402
from cli.agent_cli.models import PromptResponse  # noqa: E402
from cli.agent_cli.runtime import AgentCliRuntime  # noqa: E402
from cli.agent_cli.runtime_factory import build_persistent_runtime  # noqa: E402
from cli.agent_cli.tools_core.registry import runtime_registry_mcp_server_entries  # noqa: E402
from workers.actions import ControlledActionWorker  # noqa: E402


class AgentCliAppServer(CodexSidecarThreadMixin, AppServerCommandHandlersMixin):
    def __init__(
        self,
        *,
        runtime: AgentCliRuntime | None = None,
        action_worker: ControlledActionWorker | None = None,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        self.runtime = runtime or build_persistent_runtime()
        self._primary_runtime = self.runtime
        self.action_worker = action_worker or ControlledActionWorker()
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.state = _ConnectionState()
        self._emit_lock = threading.Lock()
        self._jobs_lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_command_job_id: str | None = None
        self._active_command_cancel_event: threading.Event | None = None
        self._command_sessions: dict[str, dict[str, Any]] = {}
        self._pending_server_requests_lock = threading.Lock()
        self._pending_server_requests: dict[
            str, app_server_request_bridge._PendingServerRequest
        ] = {}
        self._codex_sidecar_kernel: Any = None
        self._runtime_by_thread_id: dict[str, Any] = {}

    def run(self) -> int:
        try:
            for raw_line in self.stdin:
                line = raw_line.strip()
                if not line:
                    continue
                self._handle_line(line)
            self._abort_pending_server_requests()
            self._wait_for_jobs()
            return 0
        finally:
            self._close_codex_sidecar_kernel()

    def _handle_line(self, line: str) -> None:
        app_server_protocol_runtime.handle_line(self, line)

    def _handle_initialized_notification(self, params: dict[str, Any]) -> None:
        app_server_protocol_runtime.handle_initialized_notification(self, params)

    def _handle_initialize(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_protocol_runtime.handle_initialize(self, request_id, params)

    def _handle_gateway_method(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        outcome = dispatch_gateway_method(
            method=method,
            params=params,
            runtime=self.runtime,
            action_worker=self.action_worker,
            request_id=request_id,
            client_info=self._gateway_client_info(),
        )
        if not outcome.ok:
            self._emit_error_response(
                request_id=request_id,
                code=int(outcome.error_code or -32000),
                message=str(outcome.error_message or "Gateway dispatch failed"),
                data=dict(outcome.error_data or {}),
            )
            return
        approval_result = outcome.transport_context.get("approval_decision_result")
        if isinstance(approval_result, dict):
            self._register_approved_shell_session(request_id=request_id, result=approval_result)
        self._emit_result(request_id, dict(outcome.result or {}))

    def _gateway_client_info(self) -> dict[str, Any]:
        payload = dict(self.state.client_info or {})
        payload.setdefault("connId", self.state.connection_id)
        return payload

    def _handle_session_run(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_session_runtime.handle_session_run(self, request_id, params)

    def _handle_session_start(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_session_runtime.handle_session_start(self, request_id, params)

    def _handle_session_interrupt(self, request_id: Any) -> None:
        app_server_session_runtime.handle_session_interrupt(self, request_id)

    def _handle_provider_status(self, request_id: Any) -> None:
        app_server_helpers.handle_provider_status(self, request_id=request_id)

    def _handle_thread_start(self, request_id: Any, params: dict[str, Any]) -> None:
        self._select_runtime_for_thread("")
        app_server_helpers.handle_thread_start(
            self,
            request_id=request_id,
            params=params,
            thread_response_payload_fn=_thread_response_payload,
        )

    def _handle_thread_list(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_helpers.handle_thread_list(
            self,
            request_id=request_id,
            params=params,
        )

    def _handle_thread_resume(self, request_id: Any, params: dict[str, Any]) -> None:
        if self._handle_codex_sidecar_thread_resume(request_id=request_id, params=params):
            return
        app_server_protocol_runtime.handle_thread_resume(self, request_id, params)

    def _handle_thread_read(self, request_id: Any, params: dict[str, Any]) -> None:
        if self._handle_codex_sidecar_thread_read(request_id=request_id, params=params):
            return
        app_server_protocol_runtime.handle_thread_read(self, request_id, params)

    def _handle_thread_fork(self, request_id: Any, params: dict[str, Any]) -> None:
        if self._handle_codex_sidecar_thread_fork(request_id=request_id, params=params):
            return
        app_server_protocol_runtime.handle_thread_fork(self, request_id, params)

    def _handle_turn_start(self, request_id: Any, params: dict[str, Any]) -> None:
        thread_id = str(params.get("threadId") or params.get("thread_id") or "").strip()
        self._select_runtime_for_thread(thread_id)
        app_server_protocol_runtime.handle_turn_start(self, request_id, params)

    def _handle_model_list(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_protocol_runtime.handle_model_list(self, request_id, params)

    def _handle_mcp_server_status_list(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_protocol_runtime.handle_mcp_server_status_list(self, request_id, params)

    def _handle_gateway_dispatch(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "gateway/dispatch", params)

    def _handle_gateway_webhook(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "gateway/webhook", params)

    def _handle_gateway_state(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "gateway/state", params)

    def _handle_approval_list(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "approval/list", params)

    def _handle_approval_decide(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "approval/decide", params)

    def _handle_action_execute(self, request_id: Any, params: dict[str, Any]) -> None:
        app_server_protocol_runtime.handle_action_execute(self, request_id, params)

    def _handle_tools_list(self, request_id: Any) -> None:
        app_server_helpers.handle_tools_list(
            self,
            request_id=request_id,
            runtime_registry_mcp_server_entries_fn=runtime_registry_mcp_server_entries,
        )

    def _handle_browser_proxy(self, request_id: Any, params: dict[str, Any]) -> None:
        self._handle_gateway_method(request_id, "browser/proxy", params)

    def _handle_server_request_response(self, message: dict[str, Any]) -> bool:
        return app_server_request_bridge._handle_server_request_response(
            message=message,
            pending_server_requests_lock=self._pending_server_requests_lock,
            pending_server_requests=self._pending_server_requests,
            emit_notification=self._emit_notification,
        )

    def _abort_pending_server_requests(self) -> None:
        app_server_request_bridge._abort_pending_server_requests(
            pending_server_requests_lock=self._pending_server_requests_lock,
            pending_server_requests=self._pending_server_requests,
        )

    def _start_job(
        self,
        *,
        job_id: str,
        kind: str,
        prompt: str,
        stream: bool,
        completed_method: str,
    ) -> None:
        app_server_session_runtime.start_job(
            self,
            job_id=job_id,
            kind=kind,
            prompt=prompt,
            stream=stream,
            completed_method=completed_method,
        )

    def _run_job(
        self,
        *,
        job_id: str,
        kind: str,
        prompt: str,
        stream: bool,
        completed_method: str,
        started_event: threading.Event,
    ) -> None:
        app_server_session_runtime.run_job(
            self,
            job_id=job_id,
            kind=kind,
            prompt=prompt,
            stream=stream,
            completed_method=completed_method,
            started_event=started_event,
        )

    def _wait_for_jobs(self) -> None:
        app_server_session_runtime.wait_for_jobs(self)

    def _has_active_job(self) -> bool:
        return app_server_session_runtime.has_active_job(self)

    def _run_prompt(self, prompt: str, *, request_id: Any, stream: bool) -> PromptResponse:
        return app_server_session_runtime.run_prompt(
            self,
            prompt,
            request_id=request_id,
            stream=stream,
        )

    def _select_runtime_for_thread(self, thread_id: str) -> Any:
        runtime = self._runtime_by_thread_id.get(str(thread_id or "").strip())
        self.runtime = runtime if runtime is not None else self._primary_runtime
        return self.runtime

    def _emit_result(self, request_id: Any, result: dict[str, Any]) -> None:
        self._emit({"id": request_id, "result": result})

    def _emit_error_response(
        self,
        *,
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if data:
            payload["error"]["data"] = data
        self._emit(payload)

    def _emit_notification(self, method: str, params: dict[str, Any]) -> None:
        self._emit({"method": method, "params": params})

    def _emit(self, payload: dict[str, Any]) -> None:
        with self._emit_lock:
            print(json.dumps(payload, ensure_ascii=False), file=self.stdout, flush=True)

    def _make_request_user_input_handler(
        self, *, request_id: Any
    ) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
        return app_server_request_bridge._make_request_user_input_handler(
            request_id=request_id,
            request_thread_id=lambda request_id_value: self._request_thread_id(
                request_id=request_id_value
            ),
            request_user_input_via_client=self._request_user_input_via_client,
        )

    def _request_thread_id(self, *, request_id: Any) -> str:
        runtime_thread_id = str(getattr(self.runtime, "thread_id", "") or "").strip()
        if runtime_thread_id:
            return runtime_thread_id
        return f"thread_{request_id}"

    def _request_user_input_via_client(
        self,
        *,
        payload: dict[str, Any],
        thread_id: str,
    ) -> dict[str, Any] | None:
        return app_server_request_bridge._request_user_input_via_client(
            payload=payload,
            thread_id=thread_id,
            pending_server_requests_lock=self._pending_server_requests_lock,
            pending_server_requests=self._pending_server_requests,
            emit=self._emit,
        )


def main(
    *,
    runtime: AgentCliRuntime | None = None,
    action_worker: ControlledActionWorker | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    server = AgentCliAppServer(
        runtime=runtime, action_worker=action_worker, stdin=stdin, stdout=stdout
    )
    return server.run()


if __name__ == "__main__":
    raise SystemExit(main())
