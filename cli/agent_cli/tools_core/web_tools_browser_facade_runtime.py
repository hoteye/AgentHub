from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.web_tools_browser_bridge_runtime import (
    click as _click,
    click_result as _click_result,
    find as _find,
    find_result as _find_result,
    open as _open,
    open_result as _open_result,
)


def open(
    *,
    ref: str,
    line: int = 1,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return _open(
        ref=ref,
        line=line,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def open_result(
    *,
    ref: str,
    line: int = 1,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    open_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return _open_result(
        ref=ref,
        line=line,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        open_call=open_call,
    )


def click(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return _click(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def click_result(
    *,
    ref_id: str,
    id: int,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    click_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return _click_result(
        ref_id=ref_id,
        id=id,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        click_call=click_call,
    )


def find(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return _find(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=web_search_tools_factory,
        event_factory=event_factory,
    )


def find_result(
    *,
    ref_id: str,
    pattern: str,
    web_search_tools_factory: Callable[[], Any],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    find_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return _find_result(
        ref_id=ref_id,
        pattern=pattern,
        web_search_tools_factory=web_search_tools_factory,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        find_call=find_call,
    )
