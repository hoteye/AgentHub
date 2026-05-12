from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cli.agent_cli.gateway_core import InMemoryGatewayStateStore
from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_kernels.base import KernelSession, StartTurnRequest
from cli.agent_cli.runtime_kernels.codex_sidecar import approval as codex_approval
from cli.agent_cli.runtime_kernels.codex_sidecar.commands import handle_sidecar_slash_command
from cli.agent_cli.runtime_kernels.codex_sidecar.dynamic_tools import (
    CODEX_DYNAMIC_TOOL_CALL_METHOD,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.evaluation_bridge import (
    CodexSidecarEvaluationBridge,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.fs_bridge import CodexSidecarFsBridge
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel import CodexSidecarKernel
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper import (
    CodexSidecarTurnEventMapper,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.model_catalog import CodexSidecarModelCatalog
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_agent import (
    CodexSidecarRuntimeAgent,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_commands import (
    CodexSidecarRuntimeCommandsMixin,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_gateway import (
    CodexSidecarRuntimeGatewayMixin,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_models import (
    _model_item_from_sidecar,
    _provider_status_path,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_orchestration import (
    CodexSidecarRuntimeOrchestrationMixin,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_server_requests import (
    CodexSidecarRuntimeServerRequestsMixin,
    _activity_for_server_request_diagnostic,
    _activity_for_unsupported_server_request,
    _normalize_codex_request_user_input_questions,
    _server_request_from_envelope,
    _server_request_matches_turn,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter_turns import (
    CodexSidecarRuntimeTurnMixin,
    _notification_matches_turn,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.server_requests import (
    CodexServerRequestRegistry,
)
from cli.agent_cli.slash_commands import match_slash_commands

__all__ = [
    "CodexSidecarRuntimeAdapter",
    "CodexSidecarRuntimeAgent",
    "_activity_for_server_request_diagnostic",
    "_activity_for_unsupported_server_request",
    "_model_item_from_sidecar",
    "_normalize_codex_request_user_input_questions",
    "_notification_matches_turn",
    "_provider_status_path",
    "_server_request_from_envelope",
    "_server_request_matches_turn",
]


class CodexSidecarRuntimeAdapter(
    CodexSidecarRuntimeTurnMixin,
    CodexSidecarRuntimeServerRequestsMixin,
    CodexSidecarRuntimeGatewayMixin,
    CodexSidecarRuntimeOrchestrationMixin,
    CodexSidecarRuntimeCommandsMixin,
):
    """Runtime-like wrapper used by the existing TUI request worker."""

    def __init__(
        self,
        *,
        kernel: CodexSidecarKernel,
        session: KernelSession,
        gateway_state_store: Any | None = None,
    ) -> None:
        self.kernel = kernel
        self.kernel_session = session
        self.thread_id = session.thread_id
        self.thread_name = session.thread_name
        self.cwd = session.cwd
        self.history: list[dict[str, Any]] = []
        self.history_turns: list[dict[str, Any]] = []
        self.turn_results: list[PromptResponse] = []
        self.activity_callback = None
        self.turn_event_callback = None
        self.thread_store_update_active_getter = None
        self.request_user_input_handler = None
        self.presentation_locale = ""
        self.gateway_state_store = gateway_state_store or InMemoryGatewayStateStore()
        self._pending_sidecar_approval_requests: dict[str, Any] = {}
        self._pending_sidecar_approval_lock = threading.Lock()
        self._server_request_registry = CodexServerRequestRegistry()
        self._server_request_registry.register(
            codex_approval.CODEX_COMMAND_APPROVAL_METHOD,
            lambda _runtime, envelope: self._handle_approval_server_request(envelope),
        )
        self._server_request_registry.register(
            codex_approval.CODEX_FILE_CHANGE_APPROVAL_METHOD,
            lambda _runtime, envelope: self._handle_approval_server_request(envelope),
        )
        self._server_request_registry.register(
            codex_approval.CODEX_PERMISSION_APPROVAL_METHOD,
            lambda _runtime, envelope: self._handle_approval_server_request(envelope),
        )
        self._server_request_registry.register(
            "item/tool/requestUserInput",
            lambda _runtime, envelope: self._handle_tool_request_user_input(envelope),
        )
        self._server_request_registry.register(
            "mcpServer/elicitation/request",
            lambda _runtime, envelope: self._handle_mcp_elicitation_request(envelope),
        )
        self._server_request_registry.register(
            CODEX_DYNAMIC_TOOL_CALL_METHOD,
            lambda _runtime, envelope: self._handle_dynamic_tool_call(envelope),
        )
        self._active_turn_lock = threading.Lock()
        self._active_turn_id = ""
        self._active_turn_started_at = 0.0
        self._active_turn_status = ""
        self._active_turn_interrupt_requested = False
        self.model_catalog = CodexSidecarModelCatalog(kernel)
        self.fs_bridge = CodexSidecarFsBridge(
            kernel=kernel,
            workspace_root=session.cwd or ".",
        )
        self.evaluation_bridge = CodexSidecarEvaluationBridge(
            kernel=kernel,
            thread_id=session.thread_id,
        )
        self.agent = CodexSidecarRuntimeAgent(
            session=session,
            artifact_metadata=self._artifact_metadata(),
            model_catalog=self.model_catalog,
        )

    def handle_prompt(
        self,
        text: str,
        *,
        attachments: list[PromptAttachment] | None = None,
    ) -> PromptResponse:
        command_result = self._agenthub_command_prompt_response(text)
        if command_result is not None:
            self.turn_results.append(command_result)
            return command_result
        command_response = handle_sidecar_slash_command(self, text)
        if command_response is not None:
            self.turn_results.append(command_response)
            return command_response
        request = StartTurnRequest(
            session_id=self.kernel_session.session_id,
            text=str(text or ""),
            attachments=list(attachments or []),
        )
        turn = asyncio.run(self.kernel.start_turn(request))
        self._mark_active_turn_started(turn.turn_id)
        mapper = CodexSidecarTurnEventMapper()
        try:
            turn_events = self._collect_turn_events(
                turn_id=turn.turn_id,
                mapper=mapper,
            )
            raw_events = list(mapper.raw_events)
            status = self.agent.provider_status()
            status.update(mapper.status_updates)
            assistant_text = mapper.final_assistant_text
            self._record_history_turn(
                user_text=str(text or ""),
                attachments=list(attachments or []),
                turn_id=turn.turn_id,
                turn_events=turn_events,
                raw_events=raw_events,
                status=status,
                assistant_text=assistant_text,
            )
            response = PromptResponse(
                user_text=str(text or ""),
                assistant_text=assistant_text,
                attachments=list(attachments or []),
                status=status,
                turn_events=turn_events,
                protocol_diagnostics={
                    "runtime_kernel": "codex_sidecar",
                    "kernel_session_id": self.kernel_session.session_id,
                    "turn_id": turn.turn_id,
                    "raw_result": dict(turn.metadata.get("raw_result") or {}),
                    "codex_sidecar_events": raw_events,
                },
            )
            self.turn_results.append(response)
            return response
        finally:
            self._clear_active_turn(turn.turn_id)

    def interrupt_active_run(self) -> dict[str, object]:
        turn_id = self._active_turn_snapshot()[0]
        if not turn_id:
            return {"ok": False, "interrupted": False, "reason": "no_active_run"}
        try:
            self.kernel.cancel_turn_sync(self.kernel_session.session_id, turn_id)
        except Exception as exc:
            return {
                "ok": False,
                "interrupted": False,
                "reason": "interrupt_failed",
                "error": str(exc),
            }
        with self._active_turn_lock:
            if self._active_turn_id == turn_id:
                self._active_turn_interrupt_requested = True
                self._active_turn_status = "interrupt_requested"
        return {
            "ok": True,
            "interrupted": True,
            "run_token": turn_id,
            "run_label": turn_id,
        }

    def replace_kernel_session(self, session: KernelSession) -> None:
        self.kernel_session = session
        self.thread_id = session.thread_id
        self.thread_name = session.thread_name
        if session.cwd:
            self.cwd = session.cwd
            self.fs_bridge.workspace_root = Path(session.cwd).expanduser().resolve()
        self.evaluation_bridge.thread_id = session.thread_id
        self.agent._session = session

    def has_active_run(self) -> bool:
        return bool(self._active_turn_snapshot()[0])

    @staticmethod
    def pending_steer_supported() -> bool:
        return True

    def steer_active_run(
        self,
        text: str,
        *,
        attachments: list[PromptAttachment] | None = None,
    ) -> dict[str, object]:
        del attachments
        turn_id = self._active_turn_snapshot()[0]
        if not turn_id:
            return {"accepted": False, "fallback_queue": True, "reason": "no_active_run"}
        normalized = str(text or "").strip()
        if not normalized:
            return {"accepted": False, "fallback_queue": False, "reason": "empty_text"}
        try:
            result = self.kernel.steer_turn_sync(
                session_id=self.kernel_session.session_id,
                turn_id=turn_id,
                text=normalized,
            )
        except Exception as exc:
            return {
                "accepted": False,
                "fallback_queue": True,
                "reason": "steer_failed",
                "error": str(exc),
            }
        return {
            "accepted": True,
            "fallback_queue": False,
            "reason": "accepted",
            "turn_id": str(result.get("turnId") or result.get("turn_id") or turn_id),
        }

    @staticmethod
    def take_pending_steer_input_items(*, limit: int | None = None) -> list[dict[str, object]]:
        del limit
        return []

    @staticmethod
    def slash_command_matches(query: str) -> list[dict[str, str]]:
        return [
            {
                "name": str(spec.name),
                "usage": str(spec.usage),
                "description": str(spec.description),
                "description_key": str(getattr(spec, "description_key", "") or ""),
            }
            for spec in match_slash_commands(str(query or ""))
        ]

    @staticmethod
    def slash_command_completion(query: str) -> str | None:
        del query
        return None

    def _record_history_turn(
        self,
        *,
        user_text: str,
        attachments: list[PromptAttachment],
        turn_id: str,
        turn_events: list[dict[str, Any]],
        raw_events: list[dict[str, Any]],
        status: dict[str, Any],
        assistant_text: str,
    ) -> None:
        user_item = {
            "type": "message",
            "role": "user",
            "content": user_text,
        }
        self.history.append(user_item)
        self.history_turns.append(
            {
                "user_text": user_text,
                "assistant_text": assistant_text,
                "attachments": [asdict(attachment) for attachment in attachments],
                "turn_events": list(turn_events),
                "codex_sidecar_events": list(raw_events),
                "status": dict(status),
                "codex_turn_id": turn_id,
            }
        )

    def _artifact_metadata(self) -> dict[str, Any]:
        artifact = getattr(self.kernel, "artifact", None)
        projected_config = getattr(self.kernel, "projected_config", None)
        if artifact is None:
            metadata: dict[str, Any] = {}
        else:
            metadata = {
                "path": str(getattr(artifact, "path", "") or ""),
                "source": str(getattr(artifact, "source", "") or ""),
                "platform_key": str(getattr(artifact, "platform_key", "") or ""),
                "version": str(getattr(artifact, "version", "") or ""),
                "sha256": str(getattr(artifact, "sha256", "") or ""),
            }
        status_fields = getattr(projected_config, "status_fields", None)
        if callable(status_fields):
            metadata["projected_config"] = status_fields()
        return metadata
