from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.providers.adapters.chat_completions import ChatCompletionsSession
from cli.agent_cli.providers.config_catalog import ProviderConfig


def route_uses_chat_completions(route_config: ProviderConfig) -> bool:
    wire_api = str(route_config.wire_api or "").strip().lower()
    planner_kind = str(route_config.planner_kind or "").strip().lower()
    return wire_api == "openai_chat" or planner_kind in {
        "openai_chat",
        "deepseek_chat",
        "deepseek_reasoner",
    }


def route_client(
    *,
    planner: Any,
    route_name: str,
    route_config: ProviderConfig,
    build_client_fn: Callable[[ProviderConfig], Any],
) -> Any:
    if (
        str(route_config.provider_name or "") == str(planner.config.provider_name or "")
        and str(route_config.model or "") == str(planner.config.model or "")
        and str(route_config.base_url or "") == str(planner.config.base_url or "")
        and str(route_config.api_key or "") == str(planner.config.api_key or "")
    ):
        return planner.client
    cache_key = route_client_cache_key(route_name=route_name, route_config=route_config)
    cached = planner._route_client_cache.get(cache_key)
    if cached is not None:
        return cached
    client = build_client_fn(route_config)
    planner._route_client_cache[cache_key] = client
    return client


def route_client_cache_key(*, route_name: str, route_config: ProviderConfig) -> str:
    return "|".join(
        [
            str(route_name or "").strip(),
            str(route_config.provider_name or "").strip(),
            str(route_config.model or "").strip(),
            str(route_config.base_url or "").strip(),
        ]
    )


def route_request_client(
    *,
    planner: Any,
    route_name: str,
    route_config: ProviderConfig,
    timeout: int | None,
    route_client_fn: Callable[[str, ProviderConfig], Any],
) -> Any:
    client = route_client_fn(route_name, route_config)
    if not timeout:
        return client
    with_options = getattr(client, "with_options", None)
    if callable(with_options):
        try:
            return with_options(timeout=timeout)
        except Exception:
            return client
    return client


def reasoning_request_for_config(config: ProviderConfig) -> dict[str, Any] | None:
    effort = str(config.reasoning_effort or "").strip()
    if not effort:
        return None
    return {"effort": effort, "summary": "auto"}


def chat_route_extra_body(config: ProviderConfig) -> dict[str, Any]:
    raw_model = dict(config.raw_model or {})
    reasoning_mode = str(raw_model.get("reasoning_mode") or "").strip().lower()
    if reasoning_mode == "enable_thinking":
        return {"enable_thinking": True}
    if reasoning_mode == "thinking.type":
        return {"thinking": {"type": "enabled", "clear_thinking": False}}
    return {}


def chat_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        text = ""
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(getattr(item, "text", "") or "").strip()
        if text:
            parts.append(text)
    return "".join(parts).strip()


def chat_route_supports_reasoning(
    route_config: ProviderConfig,
    *,
    optional_bool_fn: Callable[[Any, bool], bool],
) -> bool:
    raw_model = route_config.raw_model or {}
    return optional_bool_fn(raw_model.get("supports_reasoning"), False) or (
        str(route_config.planner_kind or "").strip().lower() == "deepseek_reasoner"
    ) or ("reasoner" in str(route_config.model or "").lower())


def chat_route_reasoning_output_field(route_config: ProviderConfig) -> str:
    return str((route_config.raw_model or {}).get("reasoning_output_field") or "reasoning_content").strip()


def chat_route_create_fn(
    *,
    route_name: str,
    route_config: ProviderConfig,
    request_client: Any,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
):
    def _create(**kwargs: Any) -> Any:
        if timeline_debug_enabled_fn():
            log_timeline_fn(
                "openai_planner.chat_route_followup.request_raw",
                route_name=route_name,
                provider_name=str(route_config.provider_name or ""),
                base_url=str(route_config.base_url or ""),
                request=json_ready_fn(kwargs),
            )
        response = request_client.chat.completions.create(**kwargs)
        if timeline_debug_enabled_fn():
            log_timeline_fn(
                "openai_planner.chat_route_followup.response_raw",
                route_name=route_name,
                provider_name=str(route_config.provider_name or ""),
                base_url=str(route_config.base_url or ""),
                response=json_ready_fn(response),
            )
        return response

    return _create


def chat_route_session(
    *,
    request_client: Any,
    route_name: str,
    route_config: ProviderConfig,
    timeout: int | None,
    tool_specs: list[dict[str, Any]],
    supports_tools: bool,
    supports_parallel_tool_calls: bool,
    extra_body: dict[str, Any] | None,
    supports_reasoning: bool,
    reasoning_output_field: str,
    create_fn: Callable[..., Any],
) -> ChatCompletionsSession:
    return ChatCompletionsSession(
        client=request_client,
        model=route_config.model,
        tool_specs=tool_specs,
        supports_tools=supports_tools,
        supports_parallel_tool_calls=supports_parallel_tool_calls,
        extra_body=extra_body,
        timeout=timeout,
        supports_reasoning=supports_reasoning,
        reasoning_output_field=reasoning_output_field,
        create_fn=create_fn,
    )
