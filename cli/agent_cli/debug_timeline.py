from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .debug_cli import (
    DEBUG_FILTER_ENV_KEY,
    DEBUG_LOG_DIR_ENV_KEY,
    DEBUG_TEXT_LOG_ENV_KEY,
)
from .debug_timeline_runtime_helpers import (
    debug_summary as _debug_summary_impl,
    debug_text_line as _debug_text_line_impl,
    filter_allows as _filter_allows_impl,
    is_llm_io_stage as _is_llm_io_stage,
    is_tool_stage as _is_tool_stage,
    is_turn_action_stage as _is_turn_action_stage,
    primary_category as _primary_category,
    request_summary as _request_summary,
    response_summary as _response_summary,
    routed_debug_filenames as _routed_debug_filenames,
    stage_categories as _stage_categories,
)
from .debug_timeline_helpers import (
    _commands_preview as _commands_preview_helper,
    _content_summary as _content_summary_helper,
    _content_text as _content_text_helper,
    _is_plain_user_message as _is_plain_user_message_helper,
    _preview_text as _preview_text_helper,
    _structured_output_preview as _structured_output_preview_helper,
    summarize_current_turn_driver_tail as summarize_current_turn_driver_tail_helper,
    summarize_input_item,
    summarize_input_items_tail,
    summarize_protocol_items_tail,
)

_STARTED_AT = perf_counter()
_LOCK = threading.Lock()
_ENV_KEY = "AGENTHUB_DEBUG_RESPONSES_TIMELINE"
_LOG_DIR_ENV_KEY = DEBUG_LOG_DIR_ENV_KEY
_TEXT_LOG_ENV_KEY = DEBUG_TEXT_LOG_ENV_KEY
_FILTER_ENV_KEY = DEBUG_FILTER_ENV_KEY


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _destination() -> str:
    return str(os.environ.get(_ENV_KEY) or "").strip()


def _text_debug_destination() -> str:
    return str(os.environ.get(_TEXT_LOG_ENV_KEY) or "").strip()


def _debug_filter() -> str:
    return str(os.environ.get(_FILTER_ENV_KEY) or "").strip()


def _debug_log_dir() -> Path | None:
    configured = str(os.environ.get(_LOG_DIR_ENV_KEY) or "").strip()
    if configured:
        return Path(configured)
    destination = _destination()
    if not destination or destination in {"1", "stderr"}:
        return None
    path = Path(destination)
    return path.parent if path.suffix else path


def _preview_text(value: Any, *, max_chars: int = 120) -> str:
    return _preview_text_helper(value, max_chars=max_chars)


def _content_text(content: Any) -> str:
    return _content_text_helper(content)


def _structured_output_preview(value: Any) -> str:
    return _structured_output_preview_helper(value)


def _commands_preview(action: Any) -> str:
    return _commands_preview_helper(action)


def _is_plain_user_message(item: Any) -> bool:
    return _is_plain_user_message_helper(item)


def _content_summary(content: Any) -> list[dict[str, Any]]:
    return _content_summary_helper(content)


def _record(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": _timestamp(),
        "t_rel_ms": int((perf_counter() - _STARTED_AT) * 1000),
        "stage": str(stage or "").strip() or "unknown",
        "payload": payload,
    }


def _json_line(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False)


def _filter_allows(stage: str) -> bool:
    return _filter_allows_impl(stage, _debug_filter())


def _debug_summary(stage: str, payload: dict[str, Any]) -> str:
    return _debug_summary_impl(
        stage,
        payload,
        preview_text_fn=_preview_text,
        structured_output_preview_fn=_structured_output_preview,
    )


def _debug_text_line(record: dict[str, Any]) -> str:
    return _debug_text_line_impl(
        record,
        preview_text_fn=_preview_text,
        structured_output_preview_fn=_structured_output_preview,
    )


def _emit_text_debug_line(record: dict[str, Any]) -> None:
    destination = _text_debug_destination()
    if not destination or not _filter_allows(str(record.get("stage") or "")):
        return
    line = _debug_text_line(record)
    with _LOCK:
        if destination in {"1", "stderr"}:
            print(line, file=sys.stderr, flush=True)
            return
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")


def timeline_debug_enabled() -> bool:
    return bool(_destination() or _text_debug_destination() or str(os.environ.get(_LOG_DIR_ENV_KEY) or "").strip())


def log_timeline(stage: str, **payload: Any) -> None:
    record = _record(stage, payload)
    destination = _destination()
    line = _json_line(record)
    if destination:
        with _LOCK:
            if destination in {"1", "stderr"}:
                print(line, file=sys.stderr, flush=True)
            else:
                path = Path(destination)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
    log_dir = _debug_log_dir()
    if log_dir is not None:
        with _LOCK:
            log_dir.mkdir(parents=True, exist_ok=True)
            for target_name in _routed_debug_filenames(record["stage"]):
                with (log_dir / target_name).open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
    _emit_text_debug_line(record)


def append_debug_jsonl(filename: str, **payload: Any) -> None:
    log_dir = _debug_log_dir()
    if log_dir is None:
        return
    record = {
        "ts": _timestamp(),
        "t_rel_ms": int((perf_counter() - _STARTED_AT) * 1000),
        **payload,
    }
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / str(filename or "debug.jsonl").strip()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")


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


def summarize_current_turn_driver_tail(items: list[Any] | None, *, tail_len: int = 8) -> list[dict[str, Any]]:
    try:
        from cli.agent_cli.provider import extract_current_turn_prelude_items

        extractor = extract_current_turn_prelude_items
    except Exception:
        extractor = None
    return summarize_current_turn_driver_tail_helper(
        items,
        tail_len=tail_len,
        extract_current_turn_prelude_items_fn=extractor,
    )
