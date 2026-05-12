from __future__ import annotations

from typing import Any

from cli.agent_cli.tools_core import browser_web_runtime


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
) -> Any:
    return browser_web_runtime.browser(
        registry,
        action=action,
        profile=profile,
        tab_id=tab_id,
        tab=tab,
        url=url,
        path=path,
        line=line,
        id=id,
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
    )


def browser_result(registry: Any, action: str, **kwargs: Any) -> Any:
    return browser_web_runtime.browser_result(
        registry,
        action=action,
        kwargs=dict(kwargs or {}),
    )


def open_tool(registry: Any, ref: str, *, line: int = 1) -> Any:
    return browser_web_runtime.open(
        registry,
        ref=ref,
        line=line,
    )


def open_result(registry: Any, ref: str, *, line: int = 1) -> Any:
    return browser_web_runtime.open_result(
        registry,
        ref=ref,
        line=line,
    )


def click(registry: Any, ref_id: str, *, id: int) -> Any:
    return browser_web_runtime.click(
        registry,
        ref_id=ref_id,
        id=id,
    )


def click_result(registry: Any, ref_id: str, *, id: int) -> Any:
    return browser_web_runtime.click_result(
        registry,
        ref_id=ref_id,
        id=id,
    )


def find(registry: Any, ref_id: str, *, pattern: str) -> Any:
    return browser_web_runtime.find(
        registry,
        ref_id=ref_id,
        pattern=pattern,
    )


def find_result(registry: Any, ref_id: str, *, pattern: str) -> Any:
    return browser_web_runtime.find_result(
        registry,
        ref_id=ref_id,
        pattern=pattern,
    )


__all__ = [
    "browser",
    "browser_result",
    "click",
    "click_result",
    "find",
    "find_result",
    "open_result",
    "open_tool",
]
