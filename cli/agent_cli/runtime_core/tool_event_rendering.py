from __future__ import annotations

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core import tool_event_browser_rendering_runtime as browser_rendering_runtime


def append_elapsed_detail(detail: str, payload: dict) -> str:
    elapsed_ms = payload.get("planner_elapsed_ms")
    if elapsed_ms is None:
        return detail
    suffix = f"time={float(elapsed_ms) / 1000:.2f}s"
    if not detail:
        return suffix
    if "\n" in detail:
        return f"{detail}\n{suffix}"
    return f"{detail} | {suffix}"


def browser_activity_detail(event: ToolEvent) -> str:
    return browser_rendering_runtime.browser_activity_detail(
        event,
        browser_activity_repr_fn=browser_activity_repr,
        append_elapsed_detail_fn=append_elapsed_detail,
    )


def browser_activity_repr(event: ToolEvent) -> tuple[str, str, str]:
    return browser_rendering_runtime.browser_activity_repr(event)
