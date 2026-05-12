from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.browser_proxy_client import _BrowserProxyToolClient
from cli.agent_cli.tools_core.browser_tools_bridge import (
    execute_browser_action,
    execute_browser_result,
)
from cli.agent_cli.tools_core import web_tools_runtime

try:
    from shared.web_automation.client import BrowserClient
    from shared.web_automation.config import load_config as load_browser_config
    from shared.web_automation.profiles import resolve_profiles as resolve_browser_profiles
    from shared.web_automation.proxy_client import create_browser_proxy_transport
except ImportError:
    BrowserClient = None
    load_browser_config = None
    resolve_browser_profiles = None
    create_browser_proxy_transport = None


def get_browser_client(registry: Any) -> Any | None:
    if BrowserClient is None:
        return None
    if registry._browser_client is None:
        registry._browser_client = BrowserClient()
    return registry._browser_client


def profile_prefers_local_browser(registry: Any, *, profile: str | None) -> bool:
    del registry
    if load_browser_config is None or resolve_browser_profiles is None:
        return False
    config = load_browser_config()
    requested_profile = str(profile or config.default_profile or "").strip() or config.default_profile
    if not requested_profile:
        return False
    try:
        profiles = resolve_browser_profiles(config)
    except Exception:
        return False
    spec = profiles.get(requested_profile)
    if spec is None:
        return False
    return str(getattr(spec, "driver", "") or "").strip().lower() == "existing-session"


def get_browser_executor(
    registry: Any,
    *,
    profile: str | None = None,
    transport: str | None = None,
) -> Any | None:
    config_loader = load_browser_config
    if config_loader is None:
        return get_browser_client(registry)
    config = config_loader()
    requested_transport = str(transport or "").strip().lower()
    if requested_transport == "local":
        return get_browser_client(registry)
    transport_mode = str(getattr(config, "proxy_transport", "local") or "local").strip().lower()
    use_proxy = requested_transport == "proxy" or transport_mode == "http"
    if not use_proxy:
        return get_browser_client(registry)
    if profile_prefers_local_browser(registry, profile=profile):
        return get_browser_client(registry)
    if create_browser_proxy_transport is None:
        return get_browser_client(registry)
    if registry._browser_proxy_client is None:
        transport_client = create_browser_proxy_transport(config=config)
        registry._browser_proxy_client = _BrowserProxyToolClient(transport_client)
    return registry._browser_proxy_client


def web_fetch(
    registry: Any,
    url: str,
    *,
    max_chars: int = 12000,
) -> ToolEvent:
    return web_tools_runtime.web_fetch(
        url=url,
        max_chars=max_chars,
        web_search_tools_factory=registry._get_web_search_tools,
        event_factory=registry._event,
    )


def web_fetch_result(
    registry: Any,
    url: str,
    *,
    max_chars: int = 12000,
) -> CommandExecutionResult:
    return web_tools_runtime.web_fetch_result(
        url=url,
        max_chars=max_chars,
        web_search_tools_factory=registry._get_web_search_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        web_fetch_call=registry.web_fetch,
    )


def browser(
    registry: Any,
    action: str,
    *,
    profile: str | None = None,
    tab_id: str | None = None,
    tab: str | None = None,
    url: str | None = None,
    path: str | None = None,
    line: int | None = None,
    id: int | None = None,
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
) -> ToolEvent:
    normalized_action = str(action or "").strip().lower()
    if normalized_action == "open_legacy":
        target_ref = str(ref or url or "").strip()
        target_line = int(line) if line is not None else 1
        return web_tools_runtime.open(
            ref=target_ref,
            line=target_line,
            web_search_tools_factory=registry._get_web_search_tools,
            event_factory=registry._event,
        )
    if normalized_action == "click_legacy":
        target_ref = str(ref or "").strip()
        if not target_ref or id is None:
            return registry._event(
                "click",
                False,
                "click failed",
                {"ok": False, "error": "missing ref or id", "ref_id": target_ref, "id": id},
            )
        return web_tools_runtime.click(
            ref_id=target_ref,
            id=int(id),
            web_search_tools_factory=registry._get_web_search_tools,
            event_factory=registry._event,
        )
    if normalized_action == "find_legacy":
        target_ref = str(ref or "").strip()
        target_pattern = str(text or "").strip()
        if not target_ref or not target_pattern:
            return registry._event(
                "find",
                False,
                "find failed",
                {"ok": False, "error": "missing ref or pattern", "ref_id": target_ref, "pattern": target_pattern},
            )
        return web_tools_runtime.find(
            ref_id=target_ref,
            pattern=target_pattern,
            web_search_tools_factory=registry._get_web_search_tools,
            event_factory=registry._event,
        )
    return execute_browser_action(
        action=action,
        profile=profile,
        tab_id=tab_id,
        tab=tab,
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
        kind=kind,
        text=text,
        fn=fn,
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
        transport=transport,
        get_browser_executor=registry._get_browser_executor,
        event_factory=registry._event,
    )


def browser_result(
    registry: Any,
    action: str,
    *,
    kwargs: Dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return execute_browser_result(
        action=action,
        kwargs=dict(kwargs or {}),
        browser_call=registry.browser,
        compact_arguments=registry._compact_arguments,
    )


def open(
    registry: Any,
    ref: str,
    *,
    line: int = 1,
) -> ToolEvent:
    return web_tools_runtime.open(
        ref=ref,
        line=line,
        web_search_tools_factory=registry._get_web_search_tools,
        event_factory=registry._event,
    )


def open_result(
    registry: Any,
    ref: str,
    *,
    line: int = 1,
) -> CommandExecutionResult:
    return web_tools_runtime.open_result(
        ref=ref,
        line=line,
        web_search_tools_factory=registry._get_web_search_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        open_call=registry.open,
    )


def click(
    registry: Any,
    ref_id: str,
    *,
    id: int,
) -> ToolEvent:
    return web_tools_runtime.click(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=registry._get_web_search_tools,
        event_factory=registry._event,
    )


def click_result(
    registry: Any,
    ref_id: str,
    *,
    id: int,
) -> CommandExecutionResult:
    return web_tools_runtime.click_result(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=registry._get_web_search_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        click_call=registry.click,
    )


def find(
    registry: Any,
    ref_id: str,
    *,
    pattern: str,
) -> ToolEvent:
    return web_tools_runtime.find(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=registry._get_web_search_tools,
        event_factory=registry._event,
    )


def find_result(
    registry: Any,
    ref_id: str,
    *,
    pattern: str,
) -> CommandExecutionResult:
    return web_tools_runtime.find_result(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=registry._get_web_search_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        find_call=registry.find,
    )
