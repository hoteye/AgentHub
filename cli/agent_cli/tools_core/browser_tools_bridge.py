from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.browser_action_normalization import (
    browser_event_name,
    browser_request_error,
    normalize_browser_payload,
)
from cli.agent_cli.tools_core.browser_bridge import browser_action_result as build_browser_action_result
from cli.agent_cli.tools_core import browser_tools_bridge_helpers as browser_bridge_helpers
from cli.agent_cli.tools_core.browser_proxy_client import _browser_text, _normalize_browser_act_kind


def execute_browser_action(
    *,
    action: str,
    profile: str | None = None,
    tab_id: str | None = None,
    tab: str | None = None,
    url: str | None = None,
    path: str | None = None,
    level: str | None = None,
    limit: int | None = None,
    outcome: str | None = None,
    method: str | None = None,
    storage_kind: str | None = None,
    ref: str | None = None,
    start_ref: str | None = None,
    end_ref: str | None = None,
    kind: str | None = None,
    text: str | None = None,
    fn: str | None = None,
    key: str | None = None,
    cookies: list[dict[str, Any]] | None = None,
    items: dict[str, Any] | None = None,
    values: list[str] | None = None,
    fields: list[dict[str, Any]] | None = None,
    time_ms: int | None = None,
    width: int | None = None,
    height: int | None = None,
    paths: list[str] | None = None,
    input_ref: str | None = None,
    accept: bool | None = None,
    prompt_text: str | None = None,
    transport: str | None = None,
    get_browser_executor: Callable[..., Any | None],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    normalized_action = str(action or "").strip().lower()
    normalized_transport = _browser_text(transport).lower() or None
    client = get_browser_executor(profile=profile, transport=normalized_transport)
    normalized_kind = _normalize_browser_act_kind(kind) if normalized_action == "act" else _browser_text(kind)
    target_tab = str(tab or tab_id or "").strip() or None
    summary = f"Browser {normalized_action}"
    failure_payload = browser_bridge_helpers.build_failure_payload(
        normalized_action=normalized_action,
        profile=profile,
        target_tab=target_tab,
        url=url,
        path=path,
        level=level,
        limit=limit,
        outcome=outcome,
        method=method,
        storage_kind=storage_kind,
        ref=ref,
        start_ref=start_ref,
        end_ref=end_ref,
        normalized_kind=normalized_kind,
        fn=fn,
        cookies=cookies,
        items=items,
        width=width,
        height=height,
        input_ref=input_ref,
        accept=accept,
        normalized_transport=normalized_transport,
    )
    request_error = browser_request_error(
        action=normalized_action,
        kind=normalized_kind,
        ref=ref,
        start_ref=start_ref,
        end_ref=end_ref,
        width=width,
        height=height,
    )
    if request_error:
        return event_factory(
            browser_event_name(normalized_action),
            False,
            f"{summary} failed",
            {**failure_payload, "error": request_error},
        )
    if client is None:
        return event_factory(
            "browser_action",
            False,
            "browser capability unavailable",
            failure_payload,
        )
    try:
        request_kwargs = browser_bridge_helpers.build_request_kwargs(
            normalized_action=normalized_action,
            profile=profile,
            target_tab=target_tab,
            url=url,
            path=path,
            level=level,
            limit=limit,
            outcome=outcome,
            method=method,
            storage_kind=storage_kind,
            ref=ref,
            start_ref=start_ref,
            end_ref=end_ref,
            normalized_kind=normalized_kind,
            fn=fn,
            text=text,
            key=key,
            cookies=cookies,
            items=items,
            values=values,
            fields=fields,
            time_ms=time_ms,
            width=width,
            height=height,
            paths=paths,
            input_ref=input_ref,
            accept=accept,
            prompt_text=prompt_text,
        )
        payload = browser_bridge_helpers.perform_with_fallback(
            perform_fn=client.perform,
            request_kwargs=request_kwargs,
        )
        raw_payload = payload if isinstance(payload, dict) else {"ok": True}
        normalized_payload = normalize_browser_payload(
            raw_payload,
            client=client,
            action=normalized_action,
            profile=profile,
            requested_target=target_tab,
            requested_url=url,
            requested_ref=ref,
            requested_start_ref=start_ref,
            requested_end_ref=end_ref,
            requested_kind=normalized_kind,
            requested_width=width,
            requested_height=height,
            requested_values=values,
            requested_fields=fields,
            requested_paths=paths,
            requested_input_ref=input_ref,
            requested_accept=accept,
            requested_prompt_text=prompt_text,
        )
        if normalized_transport and not _browser_text(normalized_payload.get("requested_transport")):
            normalized_payload["requested_transport"] = normalized_transport
        ok = bool(normalized_payload.get("ok") if isinstance(normalized_payload, dict) else True)
        event_name = browser_event_name(normalized_action)
        summary = event_name.replace("_", " ")
        return event_factory(event_name, ok, summary, normalized_payload)
    except Exception as exc:
        return event_factory(
            browser_event_name(normalized_action),
            False,
            f"{summary} failed",
            {**failure_payload, "error": str(exc)},
        )


def execute_browser_result(
    *,
    action: str,
    kwargs: Dict[str, Any],
    browser_call: Callable[..., ToolEvent],
    compact_arguments: Callable[[Dict[str, Any] | None], Dict[str, Any]],
) -> CommandExecutionResult:
    event = browser_call(action, **kwargs)
    return build_browser_action_result(
        action=str(action or "").strip().lower(),
        payload=dict(event.payload or {}),
        arguments=compact_arguments(dict(kwargs or {})),
        tool_name="browser",
    )


def execute_open(
    *,
    ref: str,
    line: int,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = web_search_tools_factory().open(ref, line=line)
    ok = bool(payload.get("ok"))
    summary = "page opened" if ok else "open failed"
    return event_factory("open", ok, summary, payload)


def execute_open_result(
    *,
    ref: str,
    line: int,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    open_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return browser_bridge_helpers.structured_or_event_result(
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        structured_name="open_result",
        structured_ref=ref,
        structured_kwargs={"line": line},
        result_from_event=result_from_event,
        fallback_message="Open webpage.",
        fallback_event_call=lambda: open_call(ref, line=line),
        tool_name="open",
        arguments={"ref": ref, "line": line},
    )


def execute_click(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = web_search_tools_factory().click(ref_id, id=id)
    ok = bool(payload.get("ok"))
    summary = "link opened" if ok else "click failed"
    return event_factory("click", ok, summary, payload)


def execute_click_result(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    click_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return browser_bridge_helpers.structured_or_event_result(
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        structured_name="click_result",
        structured_ref=ref_id,
        structured_kwargs={"id": id},
        result_from_event=result_from_event,
        fallback_message="Open clicked link.",
        fallback_event_call=lambda: click_call(ref_id, id=id),
        tool_name="click",
        arguments={"ref_id": ref_id, "id": id},
    )


def execute_find(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    payload = web_search_tools_factory().find(ref_id, pattern=pattern)
    ok = bool(payload.get("ok"))
    summary = f"matches={int(payload.get('count') or 0)}" if ok else "find failed"
    return event_factory("find", ok, summary, payload)


def execute_find_result(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    find_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return browser_bridge_helpers.structured_or_event_result(
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        structured_name="find_result",
        structured_ref=ref_id,
        structured_kwargs={"pattern": pattern},
        result_from_event=result_from_event,
        fallback_message="Find text in page.",
        fallback_event_call=lambda: find_call(ref_id, pattern=pattern),
        tool_name="find",
        arguments={"ref_id": ref_id, "pattern": pattern},
    )
