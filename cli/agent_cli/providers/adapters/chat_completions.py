from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.core.provider_session import (
    ProviderSession,
    ProviderSessionResult,
    ProviderToolCall,
    default_tool_result_items,
)
from cli.agent_cli.models import FunctionCallOutputPayload, ResponseInputItem, ToolEvent, default_response_items
from cli.agent_cli.providers.openai_client import call_with_provider_retries
from cli.agent_cli.workspace_context import render_workspace_reference_context_item_message


@dataclass
class ChatCompletionsSession(ProviderSession):
    client: Any
    model: str
    tool_specs: List[Dict[str, Any]]
    supports_tools: bool = True
    supports_developer_role: bool = True
    supports_parallel_tool_calls: bool = False
    tool_choice: str = "auto"
    extra_body: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None
    supports_reasoning: bool = False
    reasoning_output_field: str = "reasoning_content"
    interaction_profile: str = ""
    turn_protocol_policy: str = ""
    create_fn: Optional[Callable[..., Any]] = None
    _messages: List[Dict[str, Any]] = field(default_factory=list)
    _request_count: int = 0

    @staticmethod
    def _message_content_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").strip() in {"text", "output_text", "input_text"}:
                    parts.append(str(item.get("text") or ""))
            return "".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> Dict[str, Any]:
        try:
            arguments = json.loads(str(raw_arguments or "{}"))
        except json.JSONDecodeError:
            arguments = {}
        return arguments if isinstance(arguments, dict) else {}

    @staticmethod
    def _message_reasoning_text(reasoning_content: Any) -> str:
        if isinstance(reasoning_content, str):
            return reasoning_content.strip()
        if isinstance(reasoning_content, list):
            parts: List[str] = []
            for item in reasoning_content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif item:
                    parts.append(str(item))
            return "".join(parts).strip()
        return str(reasoning_content or "").strip()

    @staticmethod
    def _message_field_value(message: Any, field_name: str) -> Any:
        current: Any = message
        for token in str(field_name or "").split("."):
            token = token.strip()
            if not token:
                continue
            current = current.get(token) if isinstance(current, dict) else getattr(current, token, None)
            if current is None:
                break
        return current

    def _normalize_role(self, role: Any) -> str:
        normalized = str(role or "").strip()
        if normalized == "developer" and not self.supports_developer_role:
            return "system"
        return normalized

    def _normalize_messages(self, input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw in list(input_items or []):
            if not isinstance(raw, dict):
                continue
            item_type = str(raw.get("type") or "").strip()
            if item_type == "response_item":
                nested = raw.get("item")
                if not isinstance(nested, dict):
                    continue
                normalized_item = ResponseInputItem.from_dict(nested).to_dict()
                nested_type = str(normalized_item.get("type") or "").strip()
                if nested_type in {"function_call_output", "custom_tool_call_output"}:
                    call_id = str(normalized_item.get("call_id") or normalized_item.get("tool_call_id") or "").strip()
                    if not call_id:
                        continue
                    payload = FunctionCallOutputPayload.from_output(
                        normalized_item.get("output"),
                        success=normalized_item.get("success"),
                    )
                    normalized.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": payload.to_text() or "",
                        }
                    )
                    continue
                role = str(normalized_item.get("role") or "assistant").strip() or "assistant"
                text = self._message_content_text(normalized_item.get("content"))
                if text:
                    normalized.append({"role": role, "content": text})
                continue
            if item_type == "reference_context_item":
                payload = raw.get("item")
                if not isinstance(payload, dict):
                    continue
                rendered = render_workspace_reference_context_item_message(payload)
                if rendered:
                    normalized.append({"role": "user", "content": rendered})
                continue
            if item_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(raw.get("call_id") or raw.get("tool_call_id") or "").strip()
                if not call_id:
                    continue
                output = raw.get("output")
                if output is None:
                    output = raw.get("content")
                payload = FunctionCallOutputPayload.from_output(output, success=raw.get("success"))
                normalized.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": payload.to_text() or "",
                    }
                )
                continue
            if item_type == "message":
                normalized_item = ResponseInputItem.from_dict(raw).to_dict()
                if normalized_item:
                    normalized_item["role"] = self._normalize_role(normalized_item.get("role"))
                    normalized.append(normalized_item)
                continue
            role = self._normalize_role(raw.get("role"))
            if not role:
                continue
            if role != "tool" and "content" not in raw:
                continue
            if role == "tool":
                call_id = str(raw.get("tool_call_id") or raw.get("call_id") or "").strip()
                if not call_id:
                    continue
                content = raw.get("content")
                if content is None:
                    content = raw.get("output")
                payload = FunctionCallOutputPayload.from_output(content, success=raw.get("success"))
                normalized.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": payload.to_text() or "",
                    }
                )
                continue
            content = self._message_content_text(raw.get("content"))
            if content:
                normalized.append({"role": role, "content": content})
        return normalized

    def _assistant_message_dict(self, message: Any, *, content_text: str, tool_calls: List[Any]) -> Dict[str, Any]:
        assistant_message: Dict[str, Any] = {"role": "assistant"}
        if content_text:
            assistant_message["content"] = content_text
        reasoning_text = self._message_reasoning_text(
            self._message_field_value(message, self.reasoning_output_field or "reasoning_content")
        )
        if self.supports_reasoning and reasoning_text:
            assistant_message[self.reasoning_output_field or "reasoning_content"] = reasoning_text
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": str(getattr(tool_call, "id", "")),
                    "type": "function",
                    "function": {
                        "name": str(getattr(getattr(tool_call, "function", None), "name", "")),
                        "arguments": str(getattr(getattr(tool_call, "function", None), "arguments", "{}")),
                    },
                }
                for tool_call in tool_calls
            ]
        return assistant_message

    def _message_tool_calls(self, message: Any) -> List[ProviderToolCall]:
        calls: List[ProviderToolCall] = []
        for tool_call in list(getattr(message, "tool_calls", []) or []):
            function = getattr(tool_call, "function", None)
            call_id = str(getattr(tool_call, "id", "") or "").strip()
            name = str(getattr(function, "name", "") or "").strip()
            if not call_id or not name:
                continue
            calls.append(
                ProviderToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=self._parse_tool_arguments(getattr(function, "arguments", "{}")),
                )
            )
        return calls

    def send(
        self,
        *,
        input_items: List[Dict[str, Any]],
        allow_tools: bool = True,
        previous_response_id: Optional[str] = None,
        prompt_cache_key: Optional[str] = None,
        turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ProviderSessionResult:
        del previous_response_id, prompt_cache_key, turn_event_callback
        normalized_input = self._normalize_messages(input_items)
        if not self._messages:
            self._messages = list(normalized_input)
        else:
            self._messages.extend(list(normalized_input))
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": list(self._messages),
            "stream": False,
        }
        if self.timeout is not None:
            kwargs["timeout"] = self.timeout
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        if self.supports_tools and allow_tools:
            kwargs["tools"] = self.tool_specs
            kwargs["tool_choice"] = self.tool_choice
            if self.supports_parallel_tool_calls:
                kwargs["parallel_tool_calls"] = True

        create = self.create_fn or self.client.chat.completions.create
        def _request_once() -> Any:
            response = create(**kwargs)
            choice = response.choices[0]
            message = choice.message
            content_text = self._message_content_text(getattr(message, "content", ""))
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            finish_reason = str(getattr(choice, "finish_reason", "") or "").strip().lower()
            if not content_text and not tool_calls and finish_reason == "network_error":
                raise RuntimeError("chat completion finished with finish_reason=network_error and no content")
            return response

        response = call_with_provider_retries(_request_once)
        choice = response.choices[0]
        message = choice.message
        content_text = self._message_content_text(getattr(message, "content", ""))
        tool_calls = list(getattr(message, "tool_calls", []) or [])
        finish_reason = str(getattr(choice, "finish_reason", "") or "").strip()
        self._messages.append(self._assistant_message_dict(message, content_text=content_text, tool_calls=tool_calls))
        self._request_count += 1
        return ProviderSessionResult(
            output_text=content_text,
            tool_calls=self._message_tool_calls(message),
            response_items=default_response_items(assistant_text=content_text),
            raw_response=response,
            response_id=f"chatcmpl-{self._request_count}",
            trace={
                "tool_calls": [call.name for call in self._message_tool_calls(message)],
                "tool_call_count": len(tool_calls),
                "answered": bool(not tool_calls and content_text),
                "answer_preview": content_text[:120] if not tool_calls and content_text else "",
                "finish_reason": finish_reason,
                "interaction_profile": str(self.interaction_profile or "").strip(),
                "turn_protocol_policy": str(self.turn_protocol_policy or "").strip(),
            },
        )

    def build_tool_result_items(
        self,
        *,
        call_id: str,
        command_text: Optional[str],
        assistant_text: str,
        events: List[ToolEvent],
    ) -> List[Dict[str, Any]]:
        return default_tool_result_items(
            call_id=call_id,
            command_text=command_text,
            assistant_text=assistant_text,
            events=events,
        )
