from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.core.provider_session import (
    ProviderSession,
    ProviderSessionResult,
    ProviderToolCall,
    default_tool_result_items,
)
from cli.agent_cli.debug_timeline import (
    log_timeline,
    timeline_debug_enabled,
)
from cli.agent_cli.models import ResponseInputItem, ToolEvent
from cli.agent_cli.providers.adapters import (
    openai_responses_adapter_runtime as openai_responses_adapter_runtime_service,
)
from cli.agent_cli.providers.adapters import (
    openai_responses_input as openai_responses_input_service,
)
from cli.agent_cli.providers.adapters import (
    openai_responses_runtime as openai_responses_runtime_service,
)
from cli.agent_cli.providers.adapters.openai_responses_output import (
    _provider_tool_call_from_payload,
    _stream_item_to_dict,
    extract_responses_output_text,
)
from cli.agent_cli.providers.adapters.openai_responses_output import (
    extract_responses_message_items as _extract_responses_message_items,
)
from cli.agent_cli.providers.reference_parity import reference_default_text_verbosity_for_model

_REFERENCE_TURN_STATE_HEADER = "x-reference-turn-state"
_CODEX_TURN_STATE_HEADER = "x-codex-turn-state"
_REFERENCE_SESSION_ID_HEADER = "session_id"
_REASONING_ENCRYPTED_CONTENT_INCLUDE = "reasoning.encrypted_content"


def extract_responses_message_items(response: Any) -> list[ResponseInputItem]:
    return _extract_responses_message_items(response)


@dataclass
class OpenAIResponsesSession(ProviderSession):
    client: Any
    model: str
    instructions: str
    tool_specs: list[dict[str, Any]]
    provider_name: str = ""
    base_url: str | None = None
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None
    text_verbosity: str | None = None
    client_metadata: dict[str, str] | None = None
    prompt_cache_key: str | None = None
    reference_parity: bool = False
    interrupt_requested: Callable[[], bool] | None = None
    session_id: str | None = None
    turn_id: str | None = None
    sandbox_mode: str | None = None
    _turn_state: str | None = field(default=None, init=False, repr=False)
    _previous_response_id_enabled: bool = field(default=True, init=False, repr=False)
    _previous_response_id_disabled_reason: str | None = field(default=None, init=False, repr=False)
    _active_stream_interrupter: Callable[[], None] | None = field(
        default=None, init=False, repr=False
    )
    _active_stream_activity_callback: Callable[[], None] | None = field(
        default=None, init=False, repr=False
    )
    _active_stream_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def _reasoning_request(self) -> dict[str, Any] | None:
        summary = self.reasoning_summary
        if summary is None and not self.reference_parity:
            summary = "auto"
        return openai_responses_adapter_runtime_service.reasoning_request(
            self.reasoning_effort,
            reasoning_summary=summary,
        )

    def _text_request(self) -> dict[str, Any] | None:
        verbosity = self.text_verbosity
        if verbosity is None and self.reference_parity:
            verbosity = reference_default_text_verbosity_for_model(self.model)
        return openai_responses_adapter_runtime_service.text_request(verbosity)

    def _client_metadata_request(self) -> dict[str, str]:
        metadata = self.client_metadata or {}
        return {str(key): str(value) for key, value in metadata.items() if str(key) and str(value)}

    def _uses_previous_response_id_transport(self) -> bool:
        if not self.reference_parity:
            return True
        transport_kind = str(getattr(self.client, "transport_kind", "") or "").strip().lower()
        return "websocket" in transport_kind

    def _uses_previous_response_id(self) -> bool:
        # Codex reference sends response cursors only on its WebSocket incremental path.
        # HTTP/SSE turns rely on full item replay plus prompt/session cache headers.
        return bool(
            self._previous_response_id_enabled and self._uses_previous_response_id_transport()
        )

    def uses_incremental_continuation(self) -> bool:
        return self._uses_previous_response_id()

    def disable_incremental_continuation(self, *, reason: str | None = None) -> None:
        self._previous_response_id_enabled = False
        normalized_reason = str(reason or "").strip() or None
        if normalized_reason:
            self._previous_response_id_disabled_reason = normalized_reason
        if timeline_debug_enabled():
            log_timeline(
                "responses.session.incremental_continuation.disabled",
                reason=normalized_reason,
            )

    def _responses_include(self) -> list[str]:
        if self._reasoning_request() is None:
            return []
        return [_REASONING_ENCRYPTED_CONTENT_INCLUDE]

    def _request_extra_headers(
        self, *, prompt_cache_key: str | None = None, stream: bool = False
    ) -> dict[str, str]:
        return openai_responses_adapter_runtime_service.request_extra_headers(
            prompt_cache_key=prompt_cache_key,
            session_prompt_cache_key=self.prompt_cache_key,
            session_id=self.session_id,
            turn_state=self._turn_state,
            session_id_header=_REFERENCE_SESSION_ID_HEADER,
            turn_state_header=(
                _CODEX_TURN_STATE_HEADER if self.reference_parity else _REFERENCE_TURN_STATE_HEADER
            ),
            reference_parity=self.reference_parity,
            turn_id=self.turn_id,
            sandbox_mode=self.sandbox_mode,
            stream=stream,
        )

    def _capture_transport_state(self, response: Any) -> None:
        normalized = openai_responses_adapter_runtime_service.capture_transport_state(
            response,
            turn_state_header=(
                _CODEX_TURN_STATE_HEADER if self.reference_parity else _REFERENCE_TURN_STATE_HEADER
            ),
            timeline_debug_enabled_fn=timeline_debug_enabled,
            log_timeline_fn=log_timeline,
        )
        if normalized:
            self._turn_state = normalized

    @staticmethod
    def _response_function_calls(response: Any) -> list[ProviderToolCall]:
        return openai_responses_adapter_runtime_service.response_function_calls(
            response,
            stream_item_to_dict_fn=_stream_item_to_dict,
            provider_tool_call_from_payload_fn=_provider_tool_call_from_payload,
        )

    @staticmethod
    def _response_output_text(response: Any) -> str:
        return extract_responses_output_text(response)

    @staticmethod
    def _content_text(content: Any) -> str:
        return openai_responses_input_service.content_text(content)

    @classmethod
    def _message_input_blocks(cls, role: str, content: Any) -> list[dict[str, Any]]:
        del cls
        return openai_responses_input_service.message_input_blocks(role, content)

    @classmethod
    def _typed_message_input_item(cls, role: str, content: Any) -> dict[str, Any] | None:
        del cls
        return openai_responses_input_service.typed_message_input_item(role, content)

    @staticmethod
    def _workspace_context_message_text(payload: dict[str, Any], *, reference_parity: bool) -> str:
        return openai_responses_input_service.workspace_context_message_text(
            payload, reference_parity=reference_parity
        )

    @classmethod
    def _is_workspace_context_message(cls, item: dict[str, Any]) -> bool:
        del cls
        return openai_responses_input_service.is_workspace_context_message(item)

    @classmethod
    def _is_environment_context_message(cls, item: dict[str, Any]) -> bool:
        del cls
        return openai_responses_input_service.is_environment_context_message(item)

    @staticmethod
    def _reference_environment_context_text(text: str) -> str:
        return openai_responses_input_service.reference_environment_context_text(text)

    @classmethod
    def _reference_environment_context_message(cls, item: dict[str, Any]) -> dict[str, Any]:
        del cls
        return openai_responses_input_service.reference_environment_context_message(item)

    @staticmethod
    def _merge_user_message_blocks(target: dict[str, Any], source: dict[str, Any]) -> None:
        openai_responses_input_service.merge_user_message_blocks(target, source)

    @classmethod
    def _normalize_input_items(
        cls, input_items: list[dict[str, Any]], *, reference_parity: bool = False
    ) -> list[dict[str, Any]]:
        return openai_responses_input_service.normalize_input_items(
            input_items,
            reference_parity=reference_parity,
            typed_message_input_item_fn=cls._typed_message_input_item,
            workspace_context_message_text_fn=lambda payload, parity: cls._workspace_context_message_text(
                payload,
                reference_parity=parity,
            ),
            is_workspace_context_message_fn=cls._is_workspace_context_message,
            is_environment_context_message_fn=cls._is_environment_context_message,
            reference_environment_context_message_fn=cls._reference_environment_context_message,
            merge_user_message_blocks_fn=cls._merge_user_message_blocks,
        )

    @staticmethod
    def _sync_runtime_debug_hooks() -> None:
        openai_responses_adapter_runtime_service.sync_runtime_debug_hooks(
            openai_responses_runtime_service,
            timeline_debug_enabled_fn=timeline_debug_enabled,
            log_timeline_fn=log_timeline,
        )

    def _is_interrupt_requested(self) -> bool:
        checker = self.interrupt_requested
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:
            return False

    def register_active_stream_interrupter(self, interrupter: Callable[[], None] | None) -> None:
        with self._active_stream_lock:
            self._active_stream_interrupter = interrupter

    def clear_active_stream_interrupter(
        self, interrupter: Callable[[], None] | None = None
    ) -> None:
        with self._active_stream_lock:
            if interrupter is not None and self._active_stream_interrupter is not interrupter:
                return
            self._active_stream_interrupter = None

    def register_active_stream_activity_callback(self, callback: Callable[[], None] | None) -> None:
        with self._active_stream_lock:
            self._active_stream_activity_callback = callback

    def clear_active_stream_activity_callback(
        self, callback: Callable[[], None] | None = None
    ) -> None:
        with self._active_stream_lock:
            if callback is not None and self._active_stream_activity_callback is not callback:
                return
            self._active_stream_activity_callback = None

    def mark_active_stream_activity(self) -> None:
        with self._active_stream_lock:
            callback = self._active_stream_activity_callback
        if not callable(callback):
            return
        try:
            callback()
        except Exception:
            return

    def interrupt_active_stream(self) -> bool:
        with self._active_stream_lock:
            interrupter = self._active_stream_interrupter
        if not callable(interrupter):
            return False
        try:
            interrupter()
        except Exception:
            return False
        return True

    def send(
        self,
        *,
        input_items: list[dict[str, Any]],
        allow_tools: bool = True,
        previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ProviderSessionResult:
        self._sync_runtime_debug_hooks()
        return openai_responses_runtime_service.send(
            self,
            input_items=input_items,
            allow_tools=allow_tools,
            previous_response_id=previous_response_id,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
        )

    def _send_streaming(
        self,
        kwargs: dict[str, Any],
        *,
        turn_event_callback: Callable[[dict[str, Any]], None],
    ) -> ProviderSessionResult:
        self._sync_runtime_debug_hooks()
        return openai_responses_runtime_service.send_streaming(
            self,
            kwargs,
            turn_event_callback=turn_event_callback,
        )

    def _consume_stream(
        self,
        stream: Any,
        *,
        turn_event_callback: Callable[[dict[str, Any]], None],
        initial_input_items: list[dict[str, Any]] | None = None,
    ) -> ProviderSessionResult:
        self._sync_runtime_debug_hooks()
        return openai_responses_runtime_service.consume_stream(
            self,
            stream,
            turn_event_callback=turn_event_callback,
            initial_input_items=initial_input_items,
        )

    def build_tool_result_items(
        self,
        *,
        call_id: str,
        command_text: str | None,
        assistant_text: str,
        events: list[ToolEvent],
    ) -> list[dict[str, Any]]:
        return default_tool_result_items(
            call_id=call_id,
            command_text=command_text,
            assistant_text=assistant_text,
            events=events,
            tool_result_projection_policy="codex_like" if self.reference_parity else "",
        )
