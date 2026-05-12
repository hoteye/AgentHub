from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import tool_commands_runtime as tool_commands_runtime_service
from cli.agent_cli.runtime_core.tool_commands_params_runtime import (
    parse_web_fetch_args,
    parse_web_search_args,
)

ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def _filter_blocked_domains(event: ToolEvent, blocked_domains: List[str]) -> ToolEvent:
    if not blocked_domains or not event.payload:
        return event
    blocked_set = {d.lower().lstrip("*.") for d in blocked_domains if d}
    results = list(event.payload.get("results") or [])
    filtered = []
    for item in results:
        url = str(item.get("url") or "")
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""
        host = host.lower()
        if any(host == b or host.endswith("." + b) for b in blocked_set):
            continue
        filtered.append(item)
    if len(filtered) == len(results):
        return event
    new_payload = dict(event.payload)
    new_payload["results"] = filtered
    new_payload["result_count"] = len(filtered)
    new_payload["count"] = len(filtered)
    new_payload["source_evidence"] = [
        {
            "rank": r.get("rank"),
            "title": str(r.get("title") or "").strip(),
            "url": str(r.get("url") or "").strip(),
            "source_domain": str(r.get("source_domain") or "").strip(),
        }
        for r in filtered if isinstance(r, dict)
    ]
    # Recompute function_call_output from filtered results
    query = str(new_payload.get("query") or "").strip()
    if filtered:
        lines = [f"已完成网页搜索：{query}", "结果："]
        for idx, item in enumerate(filtered[:3], start=1):
            title = str(item.get("title") or item.get("source_domain") or f"result-{idx}").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if title and url:
                lines.append(f"{idx}. {title} | {url}")
            elif title:
                lines.append(f"{idx}. {title}")
            if snippet:
                lines.append(snippet)
        new_payload["function_call_output"] = "\n".join(lines).strip()
    else:
        new_payload["function_call_output"] = f"网页搜索无结果（已过滤屏蔽域名）：{query}"
    new_payload["display_message"] = new_payload["function_call_output"]
    return ToolEvent(name=event.name, ok=event.ok, summary=event.summary, payload=new_payload)


def _filter_blocked_domains_in_result(result: Any, blocked_domains: List[str]) -> Any:
    from cli.agent_cli.models import CommandExecutionResult
    if not isinstance(result, CommandExecutionResult) or not blocked_domains:
        return result
    new_tool_events = [
        _filter_blocked_domains(e, blocked_domains) if getattr(e, "name", "") == "web_search" else e
        for e in list(getattr(result, "tool_events", []) or [])
    ]
    new_item_events = []
    for item_event in list(getattr(result, "item_events", []) or []):
        if not isinstance(item_event, dict):
            new_item_events.append(item_event)
            continue
        item = item_event.get("item")
        if not isinstance(item, dict) or str(item.get("tool") or "").strip() != "web_search":
            new_item_events.append(item_event)
            continue
        result_obj = item.get("result")
        if not isinstance(result_obj, dict):
            new_item_events.append(item_event)
            continue
        structured = result_obj.get("structured_content")
        if not isinstance(structured, dict):
            new_item_events.append(item_event)
            continue
        # Build a temporary ToolEvent to reuse _filter_blocked_domains
        from cli.agent_cli.models import ToolEvent as _ToolEvent
        tmp = _ToolEvent(name="web_search", ok=True, summary="", payload=structured)
        filtered_tmp = _filter_blocked_domains(tmp, blocked_domains)
        if filtered_tmp is tmp:
            new_item_events.append(item_event)
            continue
        new_result_obj = dict(result_obj)
        new_result_obj["structured_content"] = filtered_tmp.payload
        new_item = dict(item)
        new_item["result"] = new_result_obj
        new_item_events.append({**item_event, "item": new_item})
    # Rebuild assistant_text from the first filtered web_search tool event
    new_assistant_text = result.assistant_text
    fco = next(
        (
            e.payload.get("function_call_output") or e.payload.get("display_message")
            for e in new_tool_events
            if getattr(e, "name", "") == "web_search" and isinstance(getattr(e, "payload", None), dict)
        ),
        None,
    )
    if fco:
        new_assistant_text = str(fco)
    return CommandExecutionResult(
        assistant_text=new_assistant_text,
        tool_events=new_tool_events,
        item_events=new_item_events,
        turn_events=list(getattr(result, "turn_events", []) or []),
    )


def _default_error_event(name: str, summary: str, *, error: str, **payload: Any) -> ToolEvent:
    return ToolEvent(
        name=name,
        ok=False,
        summary=summary,
        payload={"ok": False, "error": error, **payload},
    )


def native_web_search_payload(*args, **kwargs):
    from cli.agent_cli.providers.anthropic_native_web_search_runtime import (
        native_web_search_payload as _native_web_search_payload,
    )

    return _native_web_search_payload(*args, **kwargs)


def runtime_provider_config(runtime) -> Any | None:
    agent = getattr(runtime, "agent", None)
    planner = getattr(agent, "_planner", None)
    config = getattr(planner, "config", None)
    if config is None:
        return None
    # Avoid importing provider modules at import-time to keep runtime_core init acyclic.
    return config


def anthropic_native_web_search_event(
    runtime,
    *,
    query: str,
    limit: int,
    domains: List[str] | None,
    recency_days: int | None,
    market: str | None,
    native_web_search_payload_fn: Callable[..., dict[str, Any]] = native_web_search_payload,
) -> ToolEvent | None:
    config = runtime_provider_config(runtime)
    if config is None:
        return None
    try:
        from cli.agent_cli.providers.tool_specs import supports_anthropic_native_web_search
    except Exception:
        return None
    if not supports_anthropic_native_web_search(config):
        return None
    try:
        payload = native_web_search_payload_fn(
            config,
            query=query,
            limit=limit,
            domains=domains,
            recency_days=recency_days,
            market=market,
        )
    except Exception:
        return None
    ok = bool(payload.get("ok"))
    summary = f"web results={int(payload.get('count') or 0)}" if ok else "web search failed"
    return ToolEvent(
        name="web_search",
        ok=ok,
        summary=summary,
        payload=payload,
    )


def install_runtime_web_search_provider_config(runtime) -> Callable[[], None]:
    tools = getattr(runtime, "tools", None)
    if tools is None:
        return lambda: None
    config = runtime_provider_config(runtime)
    marker = object()
    previous_factory = getattr(tools, "_web_search_provider_config_factory", marker)
    previous_config = getattr(tools, "_web_search_provider_config", marker)
    setattr(tools, "_web_search_provider_config_factory", lambda: config)
    setattr(tools, "_web_search_provider_config", config)

    def _restore() -> None:
        if previous_factory is marker:
            try:
                delattr(tools, "_web_search_provider_config_factory")
            except AttributeError:
                pass
        else:
            setattr(tools, "_web_search_provider_config_factory", previous_factory)
        if previous_config is marker:
            try:
                delattr(tools, "_web_search_provider_config")
            except AttributeError:
                pass
        else:
            setattr(tools, "_web_search_provider_config", previous_config)

    return _restore


def handle_web_search(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
    error_event: Callable[..., ToolEvent] | None = None,
    install_runtime_web_search_provider_config_fn: Callable[[Any], Callable[[], None]] = install_runtime_web_search_provider_config,
) -> ToolCommandResult:
    if error_event is None:
        error_event = _default_error_event
    parsed = parse_web_search_args(runtime._parse_args, arg_text)
    query = parsed["query"]
    if not query:
        return text_only_result(
            command_usage_text("web_search")
            or "Usage: /web_search <query> [limit <n>] [domains <a.com,b.com>] [recency-days <n>] [market <cc>]",
        )
    if not runtime.web_access_allowed():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Web search blocked.",
            event_name="web_search",
            summary="web search blocked",
            error="runtime network access is disabled",
            arguments={"query": query},
            error_event=error_event,
            single_event_result=single_event_result,
            payload={"query": query},
        )
    if not runtime.web_search_enabled():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Web search disabled.",
            event_name="web_search",
            summary="web search disabled",
            error="runtime web search mode is disabled",
            arguments={"query": query},
            error_event=error_event,
            single_event_result=single_event_result,
            payload={"query": query},
        )
    restore_provider_config = install_runtime_web_search_provider_config_fn(runtime)
    try:
        structured = call_structured(
            runtime.tools,
            "web_search_result",
            query,
            limit=parsed["limit"],
            domains=parsed["domains"],
            recency_days=parsed["recency_days"],
            market=parsed["market"],
        )
        if structured is not None:
            if parsed.get("blocked_domains"):
                structured = _filter_blocked_domains_in_result(structured, parsed["blocked_domains"])
            return structured
        event = runtime.tools.web_search(
            query,
            limit=parsed["limit"],
            domains=parsed["domains"],
            recency_days=parsed["recency_days"],
            market=parsed["market"],
        )
        if parsed.get("blocked_domains"):
            event = _filter_blocked_domains(event, parsed["blocked_domains"])
        return single_event_result(
            "Search the web.",
            event,
            arguments=parsed,
        )
    finally:
        restore_provider_config()


def handle_web_fetch(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
    error_event: Callable[..., ToolEvent] | None = None,
) -> ToolCommandResult:
    if error_event is None:
        error_event = _default_error_event
    parsed = parse_web_fetch_args(runtime._parse_args, arg_text)
    url = parsed["url"]
    if not url:
        return text_only_result(command_usage_text("web_fetch") or "Usage: /web_fetch <url> [max-chars <n>]")
    if not runtime.web_access_allowed():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Fetch blocked.",
            event_name="web_fetch",
            summary="web fetch blocked",
            error="runtime network access is disabled",
            arguments={"url": url},
            error_event=error_event,
            single_event_result=single_event_result,
            payload={"url": url},
        )
    structured = call_structured(runtime.tools, "web_fetch_result", url, max_chars=parsed["max_chars"])
    if structured is not None:
        return structured
    return single_event_result(
        "Fetch the webpage.",
        runtime.tools.web_fetch(url, max_chars=parsed["max_chars"]),
        arguments=parsed,
    )
