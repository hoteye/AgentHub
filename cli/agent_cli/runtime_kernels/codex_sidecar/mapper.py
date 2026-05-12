from __future__ import annotations

# ruff: noqa: F401,I001

from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_events import (
    _turn_error_message,
    _turn_event_metadata,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_items import (
    _content_text,
    _input_text_from_content,
    _mcp_result_text,
    _reasoning_text,
    map_thread_item,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_normalization import (
    _field,
    _id_from_item,
    _list,
    _mapping,
    _notification_item,
    _snake_case,
    _status,
    _text,
    _thread_id_from_payload,
    _turn_id_from_payload,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_usage import (
    _int_field,
    _int_value,
    _normalize_usage,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonRpcNotification


@dataclass
class CodexSidecarProjectionState:
    agent_message_texts: dict[str, str] = field(default_factory=dict)
    agent_message_phases: dict[str, str] = field(default_factory=dict)
    reasoning_summary_parts: dict[str, dict[int, str]] = field(default_factory=dict)
    reasoning_content_parts: dict[str, dict[int, str]] = field(default_factory=dict)
    command_items: dict[str, dict[str, Any]] = field(default_factory=dict)
    command_outputs: dict[str, str] = field(default_factory=dict)
    latest_usage: dict[str, int] = field(default_factory=dict)
    latest_context_window: int = 0
    turn_started_emitted: bool = False
    terminal_seen: bool = False
    terminal_error_message: str = ""
    final_assistant_text: str = ""


class CodexSidecarTurnEventMapper:
    def __init__(self) -> None:
        self.state = CodexSidecarProjectionState()
        self.raw_events: list[dict[str, Any]] = []

    @property
    def terminal_seen(self) -> bool:
        return self.state.terminal_seen

    @property
    def status_updates(self) -> dict[str, Any]:
        status: dict[str, Any] = {}
        if self.state.latest_usage:
            status.update(self.state.latest_usage)
            status["usage"] = dict(self.state.latest_usage)
        if self.state.latest_context_window > 0:
            status["model_context_window"] = self.state.latest_context_window
            status["context_window_tokens"] = self.state.latest_context_window
        if self.state.terminal_error_message:
            status["terminal_state"] = "failed"
            status["error"] = self.state.terminal_error_message
        return status

    @property
    def final_assistant_text(self) -> str:
        return self.state.final_assistant_text

    def map_notification(self, notification: JsonRpcNotification) -> list[dict[str, Any]]:
        params = _mapping(notification.params)
        self.raw_events.append(
            {
                "type": "codex_sidecar.notification",
                "method": notification.method,
                "params": params,
                "raw_event": _mapping(notification.raw),
            }
        )
        method = _text(notification.method)
        if method == "turn/started":
            return self._map_turn_started(params)
        if method == "turn/completed":
            return self._map_turn_completed(params)
        if method == "item/started":
            return self._map_item_event(params, event_type="item.started")
        if method == "item/completed":
            return self._map_item_event(params, event_type="item.completed")
        if method == "item/agentMessage/delta":
            return self._map_agent_message_delta(params)
        if method == "item/reasoning/summaryTextDelta":
            return self._map_reasoning_delta(params, field_name="summary")
        if method == "item/reasoning/textDelta":
            return self._map_reasoning_delta(params, field_name="content")
        if method == "item/commandExecution/outputDelta":
            return self._map_command_output_delta(params)
        if method == "thread/tokenUsage/updated":
            self._capture_usage(params)
            return []
        if method == "error":
            return self._map_error(params)
        if method.startswith("$agenthub/"):
            return self._map_protocol_error(params)
        return []

    def synthesize_turn_started(
        self,
        *,
        thread_id: str,
        turn_id: str,
    ) -> dict[str, Any] | None:
        if self.state.turn_started_emitted:
            return None
        self.state.turn_started_emitted = True
        event: dict[str, Any] = {"type": "turn.started"}
        if thread_id:
            event["thread_id"] = thread_id
        if turn_id:
            event["turn_id"] = turn_id
        return event

    def _map_turn_started(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self.state.turn_started_emitted:
            return []
        self.state.turn_started_emitted = True
        return [{"type": "turn.started", **_turn_event_metadata(params)}]

    def _map_turn_completed(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._capture_usage(params)
        turn = _mapping(params.get("turn"))
        status = _status(_field(turn, "status"), default="completed")
        self.state.terminal_seen = True
        if status == "interrupted":
            message = _turn_error_message(turn) or "interrupted"
            self.state.terminal_error_message = message
            return [
                {
                    "type": "turn.interrupted",
                    **_turn_event_metadata(params),
                    "error": {"message": message},
                }
            ]
        if status == "failed":
            message = _turn_error_message(turn) or status.replace("_", " ")
            self.state.terminal_error_message = message
            return [
                {
                    "type": "turn.failed",
                    **_turn_event_metadata(params),
                    "error": {"message": message},
                }
            ]
        event: dict[str, Any] = {"type": "turn.completed", **_turn_event_metadata(params)}
        if self.state.latest_usage:
            event["usage"] = dict(self.state.latest_usage)
        return [event]

    def _map_item_event(self, params: dict[str, Any], *, event_type: str) -> list[dict[str, Any]]:
        item = map_thread_item(_notification_item(params))
        if not item:
            return []
        item_id = _id_from_item(item)
        if item["type"] == "agent_message":
            phase = _text(item.get("phase"))
            if phase and item_id:
                self.state.agent_message_phases[item_id] = phase
            text = _text(item.get("text"))
            if text and item_id:
                self.state.agent_message_texts[item_id] = text
                self.state.final_assistant_text = text
        if item["type"] == "reasoning" and item_id:
            text = _text(item.get("text"))
            if text:
                self.state.reasoning_summary_parts[item_id] = {0: text}
        if item["type"] == "command_execution" and item_id:
            self.state.command_items[item_id] = dict(item)
            output = str(item.get("aggregated_output") or "")
            if output:
                self.state.command_outputs[item_id] = output
        return [{"type": event_type, **_turn_event_metadata(params), "item": item}]

    def _map_agent_message_delta(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        item_id = _text(_field(params, "itemId", "item_id"))
        delta = str(_field(params, "delta") or "")
        if not item_id or not delta:
            return []
        text = self.state.agent_message_texts.get(item_id, "") + delta
        self.state.agent_message_texts[item_id] = text
        item: dict[str, Any] = {"id": item_id, "type": "agent_message", "text": text}
        phase = self.state.agent_message_phases.get(item_id)
        if phase:
            item["phase"] = phase
        return [{"type": "item.updated", **_turn_event_metadata(params), "item": item}]

    def _map_reasoning_delta(
        self,
        params: dict[str, Any],
        *,
        field_name: str,
    ) -> list[dict[str, Any]]:
        item_id = _text(_field(params, "itemId", "item_id"))
        delta = str(_field(params, "delta") or "")
        if not item_id or not delta:
            return []
        if field_name == "content":
            index = _int_field(params, "contentIndex", "content_index")
            target = self.state.reasoning_content_parts.setdefault(item_id, {})
        else:
            index = _int_field(params, "summaryIndex", "summary_index")
            target = self.state.reasoning_summary_parts.setdefault(item_id, {})
        target[index] = target.get(index, "") + delta
        text = self._reasoning_text_for_item(item_id)
        if not text:
            return []
        return [
            {
                "type": "item.updated",
                **_turn_event_metadata(params),
                "item": {"id": item_id, "type": "reasoning", "text": text},
            }
        ]

    def _reasoning_text_for_item(self, item_id: str) -> str:
        summary = self.state.reasoning_summary_parts.get(item_id, {})
        content = self.state.reasoning_content_parts.get(item_id, {})
        parts = [text for _, text in sorted(summary.items()) if str(text or "").strip()] + [
            text for _, text in sorted(content.items()) if str(text or "").strip()
        ]
        return "\n\n".join(parts).strip()

    def _map_command_output_delta(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        item_id = _text(_field(params, "itemId", "item_id"))
        delta = str(_field(params, "delta") or "")
        if not item_id or not delta:
            return []
        output = self.state.command_outputs.get(item_id, "") + delta
        self.state.command_outputs[item_id] = output
        item = dict(
            self.state.command_items.get(
                item_id,
                {
                    "id": item_id,
                    "type": "command_execution",
                    "command": "",
                    "status": "in_progress",
                    "exit_code": None,
                },
            )
        )
        item["aggregated_output"] = output
        item["status"] = _status(item.get("status"), default="in_progress")
        return [{"type": "item.updated", **_turn_event_metadata(params), "item": item}]

    def _capture_usage(self, params: dict[str, Any]) -> None:
        raw_usage = _mapping(_field(params, "tokenUsage", "token_usage"))
        if not raw_usage:
            turn = _mapping(params.get("turn"))
            raw_usage = _mapping(_field(turn, "tokenUsage", "token_usage", "usage"))
        if not raw_usage:
            raw_usage = _mapping(params.get("usage"))
        usage = (
            _normalize_usage(_field(raw_usage, "last"))
            or _normalize_usage(_field(raw_usage, "total"))
            or _normalize_usage(raw_usage)
        )
        if usage:
            self.state.latest_usage = usage
        context_window = _int_value(_field(raw_usage, "modelContextWindow", "model_context_window"))
        if context_window > 0:
            self.state.latest_context_window = context_window

    def _map_error(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        error = _mapping(params.get("error"))
        message = _text(
            _field(error, "message")
            or _field(error, "additionalDetails", "additional_details")
            or "codex sidecar error"
        )
        will_retry = bool(_field(params, "willRetry", "will_retry"))
        if will_retry:
            return [{"type": "provider.retry", "message": message, **_turn_event_metadata(params)}]
        self.state.terminal_seen = True
        self.state.terminal_error_message = message
        return [
            {
                "type": "turn.failed",
                **_turn_event_metadata(params),
                "error": {"message": message},
            }
        ]

    def _map_protocol_error(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        message = _text(params.get("error") or "codex sidecar protocol error")
        self.state.terminal_seen = True
        self.state.terminal_error_message = message
        return [{"type": "turn.failed", "error": {"message": message}}]
