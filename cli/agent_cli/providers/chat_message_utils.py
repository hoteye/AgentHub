from __future__ import annotations

import json
import re
from typing import Any, Dict, List


class ChatMessageUtilsMixin:
    @staticmethod
    def _message_content_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _tool_call_dict(tool_call: Any) -> Dict[str, Any]:
        return {
            "id": str(getattr(tool_call, "id", "")),
            "type": "function",
            "function": {
                "name": str(getattr(getattr(tool_call, "function", None), "name", "")),
                "arguments": str(getattr(getattr(tool_call, "function", None), "arguments", "{}")),
            },
        }

    @staticmethod
    def _parse_tool_arguments(raw_arguments: str) -> Dict[str, Any]:
        text = str(raw_arguments or "").strip() or "{}"
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

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
            if isinstance(current, dict):
                current = current.get(token)
            else:
                current = getattr(current, token, None)
            if current is None:
                break
        return current

    def _message_reasoning_value(self, message: Any) -> Any:
        return self._message_field_value(message, self.reasoning_output_field or "reasoning_content")

    @staticmethod
    def _parse_json_payload(raw_text: Any) -> Dict[str, Any]:
        text = str(raw_text or "").strip()
        if not text:
            return {}
        candidates = [text]
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates.extend(fenced)
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start >= 0 and end > start:
                candidates.append(text[start : end + 1])
        for candidate in candidates:
            snippet = str(candidate or "").strip()
            if not snippet:
                continue
            try:
                payload = json.loads(snippet)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return {}

    def _assistant_message_dict(self, message: Any, *, content_text: str, tool_calls: List[Any]) -> Dict[str, Any]:
        assistant_message: Dict[str, Any] = {"role": "assistant"}
        if content_text:
            assistant_message["content"] = content_text
        reasoning_text = self._message_reasoning_text(self._message_reasoning_value(message))
        if self.supports_reasoning and reasoning_text:
            assistant_message[self.reasoning_output_field or "reasoning_content"] = reasoning_text
        if tool_calls:
            assistant_message["tool_calls"] = [self._tool_call_dict(tool_call) for tool_call in tool_calls]
        return assistant_message
