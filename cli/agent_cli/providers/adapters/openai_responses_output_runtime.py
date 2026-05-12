from __future__ import annotations

import json
import re
import shlex
from typing import Any, Dict, List

from cli.agent_cli.core.provider_session import ProviderToolCall
from cli.agent_cli.debug_timeline import _preview_text

# Shell operator tokens that must not be quoted when reconstructing a command string
# from an argv list — quoting them turns operators into literal strings, which
# defeats security classification (e.g. '>' is no longer seen as a redirect).
_SHELL_OPERATOR_RE = re.compile(
    r'^(>>|>|<<[-]?|<|[|][|]|&&|[|]|&|;;|;|\(|\)|\{|\}|[12&]>>|[12&]>)$'
)


def _shell_argv_token(token: str) -> str:
    """Return token unquoted if it is a shell operator, otherwise shlex-quoted."""
    if _SHELL_OPERATOR_RE.match(token):
        return token
    # Heredoc operators with delimiter: <<EOF, <<'EOF', <<"EOF", <<-EOF
    if token.startswith("<<") or token.startswith("<(") or token.startswith(">("):
        return token
    return shlex.quote(token)


def response_field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]

    for method_name in ("model_dump", "to_dict", "dict"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            if method_name == "model_dump":
                return json_ready(method(mode="json"))
            return json_ready(method())
        except Exception:
            continue

    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        return {str(key): json_ready(item) for key, item in data.items() if not str(key).startswith("_")}
    return str(value)


def response_content_item_to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    payload = json_ready(item)
    if isinstance(payload, dict):
        return payload

    item_type = str(response_field(item, "type") or "").strip()
    payload = {}
    if item_type:
        payload["type"] = item_type

    text = response_field(item, "text")
    if text is not None and text != "":
        payload["text"] = str(text)
    refusal = response_field(item, "refusal")
    if refusal is not None and refusal != "":
        payload["refusal"] = str(refusal)
    image_url = response_field(item, "image_url")
    if image_url is not None and image_url != "":
        payload["image_url"] = str(image_url)
    detail = response_field(item, "detail")
    if detail is not None and detail != "":
        payload["detail"] = detail
    return payload


def response_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        item_type = str(response_field(item, "type") or "").strip()
        if item_type in {"input_text", "output_text", "text"}:
            text = str(response_field(item, "text") or "").strip()
        elif item_type == "refusal":
            text = str(response_field(item, "refusal") or response_field(item, "text") or "").strip()
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def response_message_content(content: Any) -> Any:
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return []
        return [{"type": "output_text", "text": text}]
    if not isinstance(content, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for entry in content:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                normalized.append({"type": "output_text", "text": text})
            continue
        payload = response_content_item_to_dict(entry)
        if payload:
            normalized.append(payload)
    return normalized


def response_reasoning_content(item: Any) -> List[Dict[str, Any]]:
    content = response_field(item, "content")
    if isinstance(content, list):
        normalized: List[Dict[str, Any]] = []
        for entry in content:
            payload = response_content_item_to_dict(entry)
            if not payload:
                continue
            entry_type = str(payload.get("type") or "").strip()
            if entry_type == "summary_text":
                normalized.append({"type": "reasoning", "text": str(payload.get("text") or "")})
                continue
            if entry_type in {"reasoning", "text", "output_text", "input_text"}:
                normalized.append({"type": "reasoning", "text": str(payload.get("text") or "")})
        if normalized:
            return [entry for entry in normalized if str(entry.get("text") or "").strip()]

    summary = response_field(item, "summary")
    if isinstance(summary, list):
        text_parts: List[str] = []
        for entry in summary:
            if isinstance(entry, dict):
                text = str(entry.get("text") or "").strip()
            else:
                text = str(response_field(entry, "text") or "").strip()
            if text:
                text_parts.append(text)
        if text_parts:
            return [{"type": "reasoning", "text": "\n\n".join(text_parts)}]
    return []


def stream_item_to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if item is None:
        return {}
    payload = json_ready(item)
    return payload if isinstance(payload, dict) else {}


def shell_tool_arguments(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = dict(payload.get("action") or {}) if isinstance(payload.get("action"), dict) else {}
    command_parts: List[str] = []
    raw_command = action.get("command")
    if isinstance(raw_command, (list, tuple)):
        command_parts = [str(item).strip() for item in raw_command if str(item).strip()]
    elif isinstance(action.get("commands"), (list, tuple)):
        command_parts = [str(item).strip() for item in list(action.get("commands") or []) if str(item).strip()]
    else:
        scalar_command = str(raw_command or payload.get("command") or "").strip()
        if scalar_command:
            command_parts = [scalar_command]

    command_text = " ".join(_shell_argv_token(part) for part in command_parts).strip()
    if not command_text and command_parts:
        command_text = " ".join(command_parts).strip()

    arguments: Dict[str, Any] = {"command": command_text}
    if command_parts:
        arguments["argv"] = list(command_parts)
    workdir = str(action.get("working_directory") or payload.get("workdir") or "").strip()
    if workdir:
        arguments["workdir"] = workdir
    for key in ("timeout_ms", "max_output_length"):
        value = action.get(key)
        if value is None:
            value = payload.get(key)
        if value is not None:
            arguments[key] = value
    return arguments


def provider_tool_call_from_payload(payload: Dict[str, Any]) -> ProviderToolCall | None:
    item_type = str(payload.get("type") or "").strip()
    if item_type == "function_call":
        arguments_raw = payload.get("arguments")
        if not isinstance(arguments_raw, dict):
            try:
                arguments_raw = json.loads(str(arguments_raw or "{}"))
            except Exception:
                arguments_raw = {}
        if not isinstance(arguments_raw, dict):
            arguments_raw = {}
        call_id = str(payload.get("call_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if call_id and name:
            return ProviderToolCall(
                call_id=call_id,
                name=name,
                arguments=arguments_raw,
                item_type=item_type,
                raw_item=dict(payload),
            )
        return None
    if item_type == "custom_tool_call":
        call_id = str(payload.get("call_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        tool_input = str(payload.get("input") or "").strip()
        if call_id and name and tool_input:
            arguments = {"patch": tool_input} if name == "apply_patch" else {"input": tool_input}
            return ProviderToolCall(
                call_id=call_id,
                name=name,
                arguments=arguments,
                item_type=item_type,
                raw_item=dict(payload),
            )
        return None
    if item_type in {"shell_call", "local_shell_call"}:
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            return None
        return ProviderToolCall(
            call_id=call_id,
            name="shell",
            arguments=shell_tool_arguments(payload),
            item_type=item_type,
            raw_item=dict(payload),
        )
    return None


def summarize_output_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    item_type = str(payload.get("type") or "").strip()
    summary: Dict[str, Any] = {"type": item_type or None}
    for key in ("id", "call_id", "name", "role", "status", "phase"):
        value = payload.get(key)
        if value not in (None, ""):
            summary[key] = value
    arguments = payload.get("arguments")
    if arguments not in (None, "", {}):
        if isinstance(arguments, dict):
            summary["arguments"] = arguments
        else:
            summary["arguments_preview"] = _preview_text(arguments, max_chars=200)
    content = payload.get("content")
    if isinstance(content, list):
        text_fragments: List[str] = []
        content_types: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            content_type = str(item.get("type") or "").strip()
            if content_type:
                content_types.append(content_type)
            text = str(item.get("text") or item.get("refusal") or "").strip()
            if text:
                text_fragments.append(text)
        if content_types:
            summary["content_types"] = content_types
        if text_fragments:
            summary["text_preview"] = _preview_text("\n".join(text_fragments), max_chars=200)
    reasoning_summary = payload.get("summary")
    if isinstance(reasoning_summary, list):
        summary["summary_len"] = len(reasoning_summary)
    return summary


def extract_output_text_items(output: List[Any]) -> str:
    parts: List[str] = []
    for item in output:
        item_type = str(response_field(item, "type") or "").strip()
        if item_type in {"output_text", "text"}:
            text = str(response_field(item, "text") or "").strip()
        elif item_type in {"message", "output_message"}:
            text = response_content_text(response_field(item, "content"))
        elif item_type == "refusal":
            text = str(response_field(item, "refusal") or response_field(item, "text") or "").strip()
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()
