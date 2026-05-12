from __future__ import annotations

from typing import Any, Callable


def call_with_workspace_root(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    **kwargs: Any,
) -> Any:
    workspace_root_factory = getattr(registry, "file_workspace_root", None)
    if not callable(workspace_root_factory):
        workspace_root_factory = registry.workspace_root
    return runtime_fn(
        **kwargs,
        workspace_root_factory=workspace_root_factory,
        cwd_root_factory=registry.workspace_root,
    )


def call_structured_with_workspace_root(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    fallback_arg: str,
    fallback_call: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    workspace_root_factory = getattr(registry, "file_workspace_root", None)
    if not callable(workspace_root_factory):
        workspace_root_factory = registry.workspace_root
    return runtime_fn(
        **kwargs,
        workspace_root_factory=workspace_root_factory,
        cwd_root_factory=registry.workspace_root,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        **{fallback_arg: fallback_call},
    )


def call_office_tool(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    **kwargs: Any,
) -> Any:
    return runtime_fn(
        **kwargs,
        office_tools_factory=registry._get_office_tools,
        event_factory=registry._event,
    )


def call_office_tool_result(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    fallback_arg: str,
    fallback_call: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    return runtime_fn(
        **kwargs,
        office_tools_factory=registry._get_office_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        **{fallback_arg: fallback_call},
    )


def call_web_search_tool(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    **kwargs: Any,
) -> Any:
    return runtime_fn(
        **kwargs,
        web_search_tools_factory=registry._get_web_search_tools,
        event_factory=registry._event,
    )


def call_web_search_tool_result(
    runtime_fn: Callable[..., Any],
    registry: Any,
    /,
    fallback_arg: str,
    fallback_call: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    return runtime_fn(
        **kwargs,
        web_search_tools_factory=registry._get_web_search_tools,
        call_structured_helper=registry._call_structured_helper,
        result_from_event=registry._result_from_event,
        **{fallback_arg: fallback_call},
    )
