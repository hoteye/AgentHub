from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import FunctionCallOutputPayload


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_arguments(arguments: Any) -> str:
    if isinstance(arguments, str):
        text = arguments.strip()
        return text or "{}"
    try:
        return json.dumps(arguments or {}, ensure_ascii=False)
    except TypeError:
        return "{}"


@dataclass
class MessageItem:
    role: str
    text: str
    item_type: str = "message"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MessageItem":
        item = dict(payload or {})
        role = str(item.get("role") or "").strip() or "user"
        text = ""
        content = item.get("content")
        if isinstance(content, list):
            parts: List[str] = []
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                entry_type = str(entry.get("type") or "").strip()
                if entry_type in {"input_text", "output_text", "reasoning", "text"}:
                    parts.append(str(entry.get("text") or ""))
            text = "".join(parts)
        else:
            text = str(content or item.get("text") or "")
        return cls(role=role, text=_compact_text(text))

    def to_dict(self) -> Dict[str, Any]:
        content_type = "input_text" if self.role == "user" else "output_text"
        return {
            "type": self.item_type,
            "role": self.role,
            "content": [{"type": content_type, "text": self.text}],
        }


@dataclass
class ReasoningItem:
    text: str
    item_type: str = "reasoning"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReasoningItem":
        item = dict(payload or {})
        text = ""
        content = item.get("content")
        if isinstance(content, list):
            parts: List[str] = []
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("type") or "").strip() == "reasoning":
                    parts.append(str(entry.get("text") or ""))
            text = "".join(parts)
        else:
            text = str(content or item.get("text") or "")
        return cls(text=_compact_text(text))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.item_type,
            "content": [{"type": "reasoning", "text": self.text}],
        }


@dataclass
class FunctionCallItem:
    name: str
    arguments: str
    call_id: str
    item_type: str = "function_call"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FunctionCallItem":
        item = dict(payload or {})
        name = _compact_text(item.get("name"))
        call_id = _compact_text(item.get("call_id") or item.get("id") or "")
        arguments = _normalize_arguments(item.get("arguments") or item.get("input"))
        return cls(name=name, arguments=arguments, call_id=call_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.item_type,
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }


@dataclass
class FunctionCallOutputItem:
    call_id: str
    output: FunctionCallOutputPayload
    success: Optional[bool] = None
    item_type: str = "function_call_output"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FunctionCallOutputItem":
        item = dict(payload or {})
        call_id = _compact_text(item.get("call_id") or item.get("id") or "")
        success = item.get("success")
        if success is not None:
            success = bool(success)
        return cls(
            call_id=call_id,
            output=FunctionCallOutputPayload.from_output(item.get("output"), success=success),
            success=success,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": self.item_type,
            "call_id": self.call_id,
            "output": self.output.wire_value(),
        }
        if self.success is not None:
            data["success"] = self.success
        return data


def turn_item_from_dict(payload: Dict[str, Any]):
    item_type = str((payload or {}).get("type") or "").strip().lower()
    if item_type == "message":
        return MessageItem.from_dict(payload)
    if item_type == "reasoning":
        return ReasoningItem.from_dict(payload)
    if item_type in {"function_call", "custom_tool_call"}:
        return FunctionCallItem.from_dict(payload)
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        return FunctionCallOutputItem.from_dict(payload)
    return payload


__all__ = [
    "MessageItem",
    "ReasoningItem",
    "FunctionCallItem",
    "FunctionCallOutputItem",
    "turn_item_from_dict",
]
