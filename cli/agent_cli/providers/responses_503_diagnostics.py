from __future__ import annotations

import json
import re
from typing import Any, Dict, List


_SYNTHETIC_ITEM_ID_RE = re.compile(r"^item_\d+$")


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in list(content or []):
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or block.get("refusal") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _is_environment_context_message(item: Dict[str, Any]) -> bool:
    if str(item.get("role") or "").strip().lower() != "user":
        return False
    return "<environment_context>" in _content_text(item.get("content"))


def _parse_json_maybe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _has_reasoning_text_content(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for entry in list(content or []):
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip()
        if entry_type not in {"reasoning", "summary_text", "text", "output_text", "input_text"}:
            continue
        if str(entry.get("text") or "").strip():
            return True
    return False


def _issue(index: int | None, element: str, reason: str, detail: str) -> Dict[str, Any]:
    return {
        "index": index,
        "element": element,
        "reason": reason,
        "detail": detail,
    }


def diagnose_responses_request_503_risks(
    request_or_items: Dict[str, Any] | List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    if isinstance(request_or_items, dict):
        input_items = [dict(item) for item in list(request_or_items.get("input") or []) if isinstance(item, dict)]
    else:
        input_items = [dict(item) for item in list(request_or_items or []) if isinstance(item, dict)]

    issues: List[Dict[str, Any]] = []

    if input_items and not any(_is_environment_context_message(item) for item in input_items):
        issues.append(
            _issue(
                None,
                "environment_context",
                "missing_environment_context_message",
                "缺少 <environment_context> 消息。",
            )
        )

    for index, item in enumerate(input_items):
        item_type = str(item.get("type") or "").strip()
        role = str(item.get("role") or "").strip().lower()

        if role and "content" in item and item_type != "message":
            element = "environment_context_message" if _is_environment_context_message(item) else f"{role}_message"
            issues.append(
                _issue(
                    index,
                    element,
                    "message_missing_type",
                    "message 缺少 type=message。",
                )
            )
            continue

        if item_type == "reasoning":
            detail_parts: List[str] = []
            if _has_reasoning_text_content(item.get("content")) and not str(item.get("encrypted_content") or "").strip():
                detail_parts.append("reasoning 使用明文 content 重放，缺少 encrypted_content")
            unsupported = [name for name in ("id", "status") if item.get(name) not in (None, "", [], {})]
            if unsupported:
                detail_parts.append(f"包含上游可能拒绝的字段: {', '.join(unsupported)}")
            if detail_parts:
                issues.append(
                    _issue(
                        index,
                        "previous_turn_reasoning",
                        "reasoning_shape_mismatch",
                        "；".join(detail_parts) + "。",
                    )
                )
            continue

        if item_type == "function_call":
            detail_parts = []
            call_id = str(item.get("call_id") or "").strip()
            if _SYNTHETIC_ITEM_ID_RE.match(call_id):
                detail_parts.append(f"call_id={call_id} 是本地合成 id")
            arguments = _parse_json_maybe(item.get("arguments"))
            if isinstance(arguments, dict):
                if set(arguments.keys()) == {"cmd"}:
                    detail_parts.append("arguments 只有 cmd，缺少 workdir/yield_time_ms/max_output_tokens 等执行上下文")
            else:
                detail_parts.append("arguments 不是 provider 期望的 JSON 对象")
            if "content" in item:
                detail_parts.append("包含额外的 content 字段")
            if detail_parts:
                issues.append(
                    _issue(
                        index,
                        "previous_turn_function_call",
                        "function_call_shape_mismatch",
                        "；".join(detail_parts) + "。",
                    )
                )
            continue

        if item_type == "function_call_output":
            detail_parts = []
            call_id = str(item.get("call_id") or "").strip()
            if _SYNTHETIC_ITEM_ID_RE.match(call_id):
                detail_parts.append(f"call_id={call_id} 是本地合成 id")
            output = item.get("output")
            parsed_output = _parse_json_maybe(output)
            if isinstance(parsed_output, dict) and any(
                key in parsed_output for key in ("command", "aggregated_output", "exit_code", "status", "stdout", "stderr")
            ):
                detail_parts.append("output 是 AgentHub JSON 摘要 blob，不是原始工具输出文本")
            elif isinstance(output, dict):
                detail_parts.append("output 不是 provider 期望的原始字符串")
            if detail_parts:
                issues.append(
                    _issue(
                        index,
                        "previous_turn_function_call_output",
                        "function_call_output_shape_mismatch",
                        "；".join(detail_parts) + "。",
                    )
                )
            continue

    return {
        "issue_count": len(issues),
        "issues": issues,
    }


def format_responses_request_503_risks(diagnostics: Dict[str, Any] | None) -> List[str]:
    payload = dict(diagnostics or {})
    issues = [dict(item) for item in list(payload.get("issues") or []) if isinstance(item, dict)]
    if not issues:
        return []
    lines = ["503 请求结构诊断:"]
    for issue in issues:
        index = issue.get("index")
        location = f"input[{index}]" if index is not None else "prelude"
        element = str(issue.get("element") or "request_element").strip()
        detail = str(issue.get("detail") or issue.get("reason") or "").strip()
        if detail:
            lines.append(f"- {location} {element}: {detail}")
        else:
            lines.append(f"- {location} {element}")
    return lines


def attach_responses_503_risks(
    exc: Exception,
    request_or_items: Dict[str, Any] | List[Dict[str, Any]] | None,
    *,
    source: str,
) -> None:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "error code: 503" not in text and "proxy_unavailable" not in text:
        return
    diagnostics = diagnose_responses_request_503_risks(request_or_items)
    if not diagnostics.get("issues"):
        return
    diagnostics["source"] = str(source or "").strip() or None
    setattr(exc, "agenthub_provider_diagnostics", diagnostics)
