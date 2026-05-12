from __future__ import annotations

from typing import Any, Callable, Dict


def build_failure_payload(
    *,
    normalized_action: str,
    profile: str | None,
    target_tab: str | None,
    url: str | None,
    path: str | None,
    level: str | None,
    limit: int | None,
    outcome: str | None,
    method: str | None,
    storage_kind: str | None,
    ref: str | None,
    start_ref: str | None,
    end_ref: str | None,
    normalized_kind: str | None,
    fn: str | None,
    cookies: list[dict[str, Any]] | None,
    items: dict[str, Any] | None,
    width: int | None,
    height: int | None,
    input_ref: str | None,
    accept: bool | None,
    normalized_transport: str | None,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "action": normalized_action,
        "profile": profile,
        "target_id": target_tab,
        "url": url,
        "path": path,
        "level": level,
        "limit": limit,
        "outcome": outcome,
        "method": method,
        "storage_kind": storage_kind,
        "ref": ref,
        "start_ref": start_ref,
        "end_ref": end_ref,
        "kind": normalized_kind,
        "fn": fn,
        "cookies": [dict(item) for item in cookies] if cookies else None,
        "items": dict(items) if items else None,
        "width": width,
        "height": height,
        "input_ref": input_ref,
        "accept": accept,
        "requested_transport": normalized_transport,
    }


def build_request_kwargs(
    *,
    normalized_action: str,
    profile: str | None,
    target_tab: str | None,
    url: str | None,
    path: str | None,
    level: str | None,
    limit: int | None,
    outcome: str | None,
    method: str | None,
    storage_kind: str | None,
    ref: str | None,
    start_ref: str | None,
    end_ref: str | None,
    normalized_kind: str | None,
    fn: str | None,
    text: str | None,
    key: str | None,
    cookies: list[dict[str, Any]] | None,
    items: dict[str, Any] | None,
    values: list[str] | None,
    fields: list[dict[str, Any]] | None,
    time_ms: int | None,
    width: int | None,
    height: int | None,
    paths: list[str] | None,
    input_ref: str | None,
    accept: bool | None,
    prompt_text: str | None,
) -> Dict[str, Any]:
    request_kwargs: Dict[str, Any] = {
        "action": normalized_action,
        "profile": profile,
        "tab_id": target_tab,
        "url": url,
    }
    if path is not None:
        request_kwargs["path"] = path
    if level is not None:
        request_kwargs["level"] = level
    if limit is not None:
        request_kwargs["limit"] = int(limit)
    if outcome is not None:
        request_kwargs["outcome"] = outcome
    if method is not None:
        request_kwargs["method"] = method
    if storage_kind is not None:
        request_kwargs["storage_kind"] = storage_kind
    if ref is not None:
        request_kwargs["ref"] = ref
    if start_ref is not None:
        request_kwargs["start_ref"] = start_ref
    if end_ref is not None:
        request_kwargs["end_ref"] = end_ref
    if normalized_kind:
        request_kwargs["kind"] = normalized_kind
    text_payload = fn if normalized_kind == "evaluate" and fn is not None else text
    if text_payload is not None:
        request_kwargs["text"] = text_payload
    if key is not None:
        request_kwargs["key"] = key
    if cookies is not None:
        request_kwargs["cookies"] = [dict(item) for item in cookies]
    if items is not None:
        request_kwargs["items"] = dict(items)
    if values is not None:
        request_kwargs["values"] = list(values)
    if fields is not None:
        request_kwargs["fields"] = [dict(item) for item in fields]
    if time_ms is not None:
        request_kwargs["time_ms"] = int(time_ms)
    if width is not None:
        request_kwargs["width"] = int(width)
    if height is not None:
        request_kwargs["height"] = int(height)
    if paths is not None:
        request_kwargs["paths"] = list(paths)
    if input_ref is not None:
        request_kwargs["input_ref"] = input_ref
    if accept is not None:
        request_kwargs["accept"] = bool(accept)
    if prompt_text is not None:
        request_kwargs["prompt_text"] = prompt_text
    return request_kwargs


def perform_with_fallback(
    *,
    perform_fn: Callable[..., Any],
    request_kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return perform_fn(**request_kwargs) or {}
    except TypeError as exc:
        exc_text = str(exc)
        unsupported_key = None
        for candidate in (
            "path",
            "fields",
            "values",
            "time_ms",
            "key",
            "cookies",
            "items",
            "text",
            "kind",
            "outcome",
            "method",
            "storage_kind",
            "ref",
            "start_ref",
            "end_ref",
            "paths",
            "width",
            "height",
            "input_ref",
            "accept",
            "prompt_text",
        ):
            if f"unexpected keyword argument '{candidate}'" in exc_text:
                unsupported_key = candidate
                break
        if unsupported_key is None:
            raise
        request_kwargs.pop(unsupported_key, None)
        return perform_fn(**request_kwargs) or {}


def structured_or_event_result(
    *,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., Any],
    structured_name: str,
    structured_ref: str,
    structured_kwargs: Dict[str, Any],
    result_from_event: Callable[..., Any],
    fallback_message: str,
    fallback_event_call: Callable[..., Any],
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    structured = call_structured_helper(
        web_search_tools_factory(),
        structured_name,
        structured_ref,
        **structured_kwargs,
    )
    if structured is not None:
        return structured
    return result_from_event(
        fallback_message,
        fallback_event_call(),
        tool_name=tool_name,
        arguments=arguments,
    )
