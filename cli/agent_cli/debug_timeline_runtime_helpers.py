from __future__ import annotations

from typing import Any, Callable


def is_llm_io_stage(stage: str) -> bool:
    normalized = str(stage or "").strip()
    return ".request_raw" in normalized or ".response_raw" in normalized


def is_turn_action_stage(stage: str) -> bool:
    return not is_llm_io_stage(stage)


def is_tool_stage(stage: str) -> bool:
    normalized = str(stage or "").strip()
    return normalized.startswith("tool.") or ".tool." in normalized


def primary_category(stage: str) -> str:
    normalized = str(stage or "").strip()
    if not normalized:
        return "runtime"
    if is_llm_io_stage(normalized):
        return "api"
    if is_tool_stage(normalized):
        return "tool"
    prefix = normalized.split(".", 1)[0]
    if prefix in {"runtime", "turn_engine"}:
        return "runtime"
    if prefix in {"headless", "stream"}:
        return "headless"
    if prefix in {"app", "driver", "presentation", "composer", "ui"}:
        return "ui"
    if prefix in {"startup"}:
        return "startup"
    return prefix or "runtime"


def stage_categories(stage: str) -> set[str]:
    normalized = str(stage or "").strip()
    prefix = normalized.split(".", 1)[0] if normalized else "runtime"
    categories = {primary_category(normalized), prefix or "runtime"}
    if is_llm_io_stage(normalized):
        categories.update({"api", "llm"})
    if is_tool_stage(normalized):
        categories.add("tool")
    if normalized.startswith("turn_engine."):
        categories.add("turn")
    if normalized.startswith("headless."):
        categories.add("headless")
    return {item for item in categories if item}


def filter_allows(stage: str, raw_filter: str) -> bool:
    raw = str(raw_filter or "").strip()
    if not raw or raw == "*":
        return True
    categories = stage_categories(stage)
    include: set[str] = set()
    exclude: set[str] = set()
    for token in raw.replace(" ", ",").split(","):
        normalized = token.strip()
        if not normalized or normalized == "*":
            continue
        if normalized.startswith("!"):
            excluded = normalized[1:].strip()
            if excluded:
                exclude.add(excluded)
            continue
        include.add(normalized)
    if exclude and categories.intersection(exclude):
        return False
    if include and not categories.intersection(include):
        return False
    return True


def payload_scalar_parts(
    payload: dict[str, Any],
    *,
    keys: list[str],
    preview_text_fn: Callable[..., str],
    structured_output_preview_fn: Callable[..., str],
) -> list[str]:
    parts: list[str] = []
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool)):
            text = preview_text_fn(value, max_chars=120)
        else:
            text = structured_output_preview_fn(value)
        if text:
            parts.append(f"{key}={text}")
    return parts


def provider_stage_name(stage: str, *, suffix: str) -> str:
    normalized = str(stage or "").strip()
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized or "provider"


def display_category(stage: str) -> str:
    normalized = str(stage or "").strip()
    if normalized.endswith(".request_raw"):
        return "API REQUEST"
    if normalized.endswith(".response_raw"):
        return "API RESPONSE"
    if is_tool_stage(normalized):
        return "TOOL"
    prefix = normalized.split(".", 1)[0] if normalized else "runtime"
    if prefix == "startup":
        return "STARTUP"
    if prefix in {"runtime", "turn_engine", "headless", "stream"}:
        return "RUNTIME"
    if prefix in {"app", "driver", "presentation", "composer", "ui"}:
        return "UI"
    return (prefix or "runtime").upper()


def request_summary(payload: dict[str, Any]) -> str:
    stage = str(payload.get("stage") or "").strip()
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    parts = [provider_stage_name(stage, suffix=".request_raw")]
    model = str(request.get("model") or "").strip()
    if model:
        parts.append(f"model={model}")
    if isinstance(request.get("messages"), list):
        parts.append(f"messages={len(request.get('messages') or [])}")
    if isinstance(request.get("input"), list):
        parts.append(f"input={len(request.get('input') or [])}")
    if isinstance(request.get("tools"), list):
        parts.append(f"tools={len(request.get('tools') or [])}")
    if request.get("system") is not None:
        parts.append("system=yes")
    return " ".join(part for part in parts if part)


def response_summary(payload: dict[str, Any]) -> str:
    stage = str(payload.get("stage") or "").strip()
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    parts = [provider_stage_name(stage, suffix=".response_raw")]
    response_id = str(payload.get("response_id") or response.get("id") or "").strip()
    if response_id:
        parts.append(f"response_id={response_id}")
    stop_reason = str(response.get("stop_reason") or "").strip()
    if stop_reason:
        parts.append(f"stop_reason={stop_reason}")
    content = response.get("content") if isinstance(response.get("content"), list) else []
    if content:
        parts.append(f"content={len(content)}")
    if payload.get("content_count"):
        parts.append(f"content_count={payload.get('content_count')}")
    return " ".join(part for part in parts if part)


def debug_summary(
    stage: str,
    payload: dict[str, Any],
    *,
    preview_text_fn: Callable[..., str],
    structured_output_preview_fn: Callable[..., str],
) -> str:
    normalized = str(stage or "").strip()
    if normalized.endswith(".request_raw"):
        return request_summary({**payload, "stage": normalized})
    if normalized.endswith(".response_raw"):
        return response_summary({**payload, "stage": normalized})
    if normalized == "turn_engine.round.provider_result":
        parts = ["Provider result"]
        parts.extend(
            payload_scalar_parts(
                payload,
                keys=[
                    "response_id",
                    "tool_call_count",
                    "model_elapsed_ms",
                    "provider_native_continuation_pending",
                ],
                preview_text_fn=preview_text_fn,
                structured_output_preview_fn=structured_output_preview_fn,
            )
        )
        preview = preview_text_fn(payload.get("output_text_preview"), max_chars=160)
        if preview:
            parts.append(f"output={preview}")
        return " ".join(part for part in parts if part)
    if normalized == "turn_engine.tool.execute.begin":
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        parts = [f"{tool_name} started"]
        parts.extend(
            payload_scalar_parts(
                payload,
                keys=["call_id", "mode"],
                preview_text_fn=preview_text_fn,
                structured_output_preview_fn=structured_output_preview_fn,
            )
        )
        command = preview_text_fn(payload.get("command_text"), max_chars=160)
        if command:
            parts.append(f"command={command}")
        return " ".join(part for part in parts if part)
    if normalized == "turn_engine.tool.execute.end":
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        parts = [f"{tool_name} completed"]
        parts.extend(
            payload_scalar_parts(
                payload,
                keys=["call_id", "execution_elapsed_ms"],
                preview_text_fn=preview_text_fn,
                structured_output_preview_fn=structured_output_preview_fn,
            )
        )
        command = preview_text_fn(payload.get("command_text"), max_chars=160)
        if command:
            parts.append(f"command={command}")
        return " ".join(part for part in parts if part)
    if normalized == "turn_engine.tool.provisional_started.emit":
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        parts = payload_scalar_parts(
            payload,
            keys=["call_id"],
            preview_text_fn=preview_text_fn,
            structured_output_preview_fn=structured_output_preview_fn,
        )
        return " ".join(part for part in [f"{tool_name} pending", *parts] if part)
    if normalized == "turn_engine.tool.item_events.ready":
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        parts = payload_scalar_parts(
            payload,
            keys=["call_id"],
            preview_text_fn=preview_text_fn,
            structured_output_preview_fn=structured_output_preview_fn,
        )
        return " ".join(part for part in [f"{tool_name} result ready", *parts] if part)
    if normalized in {
        "runtime.handle_prompt.started",
        "runtime.handle_prompt.completed",
        "runtime.run.begin",
        "runtime.run.finish",
    }:
        parts: list[str] = []
        if normalized == "runtime.handle_prompt.started":
            parts.append("Prompt started")
        elif normalized == "runtime.handle_prompt.completed":
            parts.append("Prompt completed")
        elif normalized == "runtime.run.begin":
            parts.append("Run started")
        elif normalized == "runtime.run.finish":
            parts.append("Run finished")
        user_text = preview_text_fn(payload.get("user_text"), max_chars=120)
        if user_text:
            parts.append(f"user={user_text}")
        assistant_text = preview_text_fn(payload.get("assistant_text_preview"), max_chars=160)
        if assistant_text:
            parts.append(f"assistant={assistant_text}")
        parts.extend(
            payload_scalar_parts(
                payload,
                keys=["tool_event_count", "response_item_count", "thread_id", "run_token"],
                preview_text_fn=preview_text_fn,
                structured_output_preview_fn=structured_output_preview_fn,
            )
        )
        return " ".join(part for part in parts if part)
    scalar_parts = payload_scalar_parts(
        payload,
        keys=[
            "thread_id",
            "run_token",
            "response_id",
            "tool_name",
            "call_id",
            "model_elapsed_ms",
            "tool_call_count",
            "status",
        ],
        preview_text_fn=preview_text_fn,
        structured_output_preview_fn=structured_output_preview_fn,
    )
    if scalar_parts:
        return f"{normalized} {' '.join(scalar_parts)}"
    return normalized


def debug_text_line(
    record: dict[str, Any],
    *,
    preview_text_fn: Callable[..., str],
    structured_output_preview_fn: Callable[..., str],
) -> str:
    stage = str(record.get("stage") or "").strip()
    category = display_category(stage)
    message = debug_summary(
        stage,
        dict(record.get("payload") or {}),
        preview_text_fn=preview_text_fn,
        structured_output_preview_fn=structured_output_preview_fn,
    )
    return f"{record.get('ts')} [DEBUG] [{category}] {message}".rstrip()


def routed_debug_filenames(stage: str) -> list[str]:
    filenames: list[str] = []
    if is_llm_io_stage(stage):
        filenames.append("llm_io.jsonl")
    elif is_turn_action_stage(stage):
        filenames.append("turn_actions.jsonl")
    if is_tool_stage(stage):
        filenames.append("tool_trace.jsonl")
    return filenames
