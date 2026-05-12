from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import runtime_runtime
from cli.agent_cli.background_tasks import build_background_task_adapter
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.provider import build_planner
from cli.agent_cli.providers.reference_parity import reference_default_mode_request_user_input


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    return runtime_runtime.preview_text(value, max_chars=max_chars)


def tool_runtime_trace(stage: str, **payload: Any) -> None:
    if not timeline_debug_enabled():
        return
    log_timeline(stage, **payload)


def runtime_now_iso() -> str:
    return runtime_runtime.runtime_now_iso()


def runtime_build_planner(*args: Any, **kwargs: Any) -> Any:
    return build_planner(*args, **kwargs)


def runtime_background_task_adapter_builder() -> Callable[..., Any]:
    return build_background_task_adapter


def runtime_build_background_task_adapter(*args: Any, **kwargs: Any) -> Any:
    return runtime_background_task_adapter_builder()(*args, **kwargs)


def runtime_request_user_input_default_mode_enabled(*, agent: Any) -> bool:
    planner = getattr(agent, "_planner", None)
    config = getattr(planner, "config", None)
    if config is None:
        return False
    try:
        return bool(reference_default_mode_request_user_input(config))
    except Exception:
        return False


def sync_runtime_request_user_input_mode(runtime: Any) -> bool:
    enabled = runtime_request_user_input_default_mode_enabled(
        agent=getattr(runtime, "agent", None),
    )
    setattr(runtime, "default_mode_request_user_input", enabled)
    return enabled
