from __future__ import annotations

import json
from math import ceil
from typing import Any

from cli.agent_cli.models import ResponseInputItem, response_items_to_text
from cli.agent_cli.runtime_services import planner_context_history_runtime

DEFAULT_AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT = 90
DEFAULT_MODEL_SUMMARY_MAX_CHARS = 12_000


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text_token_estimate(text: str) -> int:
    normalized = str(text or "")
    if not normalized:
        return 0
    ascii_chars = sum(1 for char in normalized if ord(char) < 128)
    non_ascii_chars = len(normalized) - ascii_chars
    return max(1, ceil(ascii_chars / 4) + non_ascii_chars)


def estimate_input_item_tokens(items: list[dict[str, Any]]) -> int:
    total = 0
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
        total += _text_token_estimate(serialized)
    return total


def model_context_window(runtime: Any) -> int:
    provider_status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(provider_status_getter):
        return 0
    try:
        status = dict(provider_status_getter() or {})
    except Exception:
        return 0
    return _int(
        status.get("model_context_window")
        or status.get("provider_model_context_window")
        or status.get("context_window_tokens")
        or status.get("context_window")
    )


def model_auto_compact_token_limit(runtime: Any) -> int:
    provider_status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if not callable(provider_status_getter):
        return 0
    try:
        status = dict(provider_status_getter() or {})
    except Exception:
        return 0
    return _int(
        status.get("model_auto_compact_token_limit")
        or status.get("provider_model_auto_compact_token_limit")
        or status.get("auto_compact_token_limit")
    )


def auto_compaction_token_limit(runtime: Any, *, context_window: int | None = None) -> int:
    explicit_limit = _int(getattr(runtime, "_AUTO_COMPACT_TRIGGER_TOKENS", 0))
    if explicit_limit > 0:
        return explicit_limit
    provider_limit = model_auto_compact_token_limit(runtime)
    if provider_limit > 0:
        return provider_limit
    window = int(context_window if context_window is not None else model_context_window(runtime))
    if window <= 0:
        return 0
    percent = _int(
        getattr(
            runtime,
            "_AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT",
            DEFAULT_AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT,
        )
    )
    if percent <= 0:
        percent = DEFAULT_AUTO_COMPACT_TOKEN_THRESHOLD_PERCENT
    return max(1, window * min(percent, 100) // 100)


def auto_compaction_decision(runtime: Any) -> dict[str, Any]:
    conversation_item_count = runtime._planner_conversation_item_count()
    context_window = model_context_window(runtime)
    token_limit = auto_compaction_token_limit(runtime, context_window=context_window)
    estimated_tokens = 0
    if token_limit > 0:
        estimated_tokens = estimate_input_item_tokens(runtime._planner_conversation_input_items())
    item_limit = int(getattr(runtime, "_AUTO_COMPACT_TRIGGER_ITEMS", 0) or 0)
    token_triggered = token_limit > 0 and estimated_tokens >= token_limit
    item_triggered = item_limit > 0 and conversation_item_count > item_limit
    will_run = bool(runtime.history_turns) and (token_triggered or item_triggered)
    trigger_reason = ""
    if token_triggered:
        trigger_reason = "auto_pre_turn_token_limit"
    elif item_triggered:
        trigger_reason = "auto_pre_turn_history_limit"
    return {
        "will_run": will_run,
        "trigger_reason": trigger_reason,
        "conversation_item_count": conversation_item_count,
        "trigger_items": item_limit,
        "estimated_tokens": estimated_tokens,
        "trigger_tokens": token_limit,
        "context_window": context_window,
        "history_turn_count": len(list(runtime.history_turns or [])),
    }


def _history_compaction_source_text(runtime: Any) -> str:
    lines: list[str] = []
    for index, turn in enumerate(list(runtime.history_turns or []), start=1):
        if not isinstance(turn, dict):
            continue
        if not runtime._turn_used_provider(turn):
            continue
        user_text = str(turn.get("user_text") or "").strip()
        assistant_text = planner_context_history_runtime.history_summary_text_for_turn(turn)
        if user_text:
            lines.append(f"Turn {index} user:\n{user_text}")
        if assistant_text:
            lines.append(f"Turn {index} assistant:\n{assistant_text}")
    return "\n\n".join(lines).strip()


def _summary_prompt(source_text: str, *, instructions: str) -> str:
    custom = str(instructions or "").strip()
    custom_block = f"\nCustom instructions:\n{custom}\n" if custom else ""
    return (
        "You are compacting an AgentHub engineering session so the same agent can continue later.\n"
        "Summarize only facts that are useful for continuing the work.\n"
        "Keep user goals, decisions, constraints, files changed or inspected, commands and tests, failures, and next steps.\n"
        "Do not invent facts. Do not include generic advice. Return only the compacted summary.\n"
        f"{custom_block}\n"
        "Conversation transcript:\n"
        f"{source_text}"
    )


def _intent_text(intent: Any) -> str:
    assistant_text = str(getattr(intent, "assistant_text", "") or "").strip()
    if assistant_text:
        return assistant_text
    response_items = []
    for raw in list(getattr(intent, "response_items", []) or []):
        if isinstance(raw, ResponseInputItem):
            response_items.append(raw)
        elif isinstance(raw, dict):
            response_items.append(ResponseInputItem.from_dict(raw))
    return response_items_to_text(response_items).strip()


def _call_model_summary(runtime: Any, prompt: str) -> str:
    agent = getattr(runtime, "agent", None)
    if getattr(agent, "_planner", None) is None:
        return ""
    plan = getattr(agent, "plan", None)
    if not callable(plan):
        return ""
    try:
        kwargs = {
            "tool_executor": None,
            "attachments": [],
            "input_items": [],
        }
        filter_kwargs = getattr(runtime, "_filter_handler_kwargs", None)
        if callable(filter_kwargs):
            kwargs = filter_kwargs(plan, kwargs)
        intent = plan(prompt, history=[], **kwargs)
    except Exception as exc:
        runtime._last_compaction_model_summary_error = f"{type(exc).__name__}: {exc}"
        return ""
    return _intent_text(intent)


def build_compaction_replacement_history(
    runtime: Any,
    *,
    instructions: str = "",
    prefer_model_summary: bool = False,
) -> list[dict[str, str]]:
    metadata: dict[str, Any] = {"summary_strategy": "deterministic"}
    source_text = _history_compaction_source_text(runtime)
    if not source_text:
        runtime._last_compaction_summary_metadata = metadata
        return []
    if prefer_model_summary:
        max_chars = _int(
            getattr(runtime, "_MODEL_COMPACT_SOURCE_MAX_CHARS", DEFAULT_MODEL_SUMMARY_MAX_CHARS)
        )
        bounded_source = source_text[-max_chars:] if max_chars > 0 else source_text
        model_summary = _call_model_summary(
            runtime,
            _summary_prompt(bounded_source, instructions=instructions),
        ).strip()
        if model_summary:
            metadata = {
                "summary_strategy": "model",
                "model_summary_source_chars": len(bounded_source),
                "model_summary_truncated": len(bounded_source) < len(source_text),
            }
            runtime._last_compaction_summary_metadata = metadata
            return [
                {"role": "assistant", "content": "Previous conversation summary:\n" + model_summary}
            ]
        error_text = str(getattr(runtime, "_last_compaction_model_summary_error", "") or "").strip()
        if error_text:
            metadata["model_summary_error"] = error_text
    replacement_history = planner_context_history_runtime.build_auto_compaction_replacement_history(
        runtime
    )
    runtime._last_compaction_summary_metadata = metadata
    return replacement_history
