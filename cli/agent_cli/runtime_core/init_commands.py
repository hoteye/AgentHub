from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from cli.agent_cli.init_prompt_runtime import build_init_llm_prompt
from cli.agent_cli.init_scan_runtime import build_init_scan_summary
from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.slash_surface import surface_usage_text
from cli.agent_cli.workspace_context import DEFAULT_PROJECT_DOC_FILENAME


class _InitToolExecutor:
    def __init__(self, runtime: Any, *, allow_request_user_input: bool) -> None:
        self._runtime = runtime
        self._allow_request_user_input = bool(allow_request_user_input)

    def __call__(self, text: str) -> tuple[str, list[Any]]:
        result = self.run_structured(text)
        return str(result.assistant_text or ""), list(result.tool_events or [])

    def run_structured(self, text: str) -> CommandExecutionResult:
        previous = bool(getattr(self._runtime, "default_mode_request_user_input", False))
        if self._allow_request_user_input and str(text or "").lstrip().startswith(
            "/request_user_input"
        ):
            self._runtime.default_mode_request_user_input = True
        try:
            return self._runtime._run_command_text_result(text)
        finally:
            self._runtime.default_mode_request_user_input = previous

    def interrupt_requested(self) -> bool:
        checker = getattr(self._runtime, "_is_interrupt_requested", None)
        return bool(checker()) if callable(checker) else False

    def interrupt_result(self) -> tuple[str, list[Any]]:
        builder = getattr(self._runtime, "_interrupt_tuple", None)
        return builder() if callable(builder) else ("", [])


def handle_init_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> CommandExecutionResult | tuple[str, list[Any]] | None:
    if name != "init":
        return None
    positionals, options = parse_args(arg_text)
    if positionals:
        return (f"Usage: {surface_usage_text('init')}", [])
    if options.get("refresh"):
        message = (
            "AENGTHUB.md refresh is not supported by /init. "
            "Edit AENGTHUB.md directly, or delete it and rerun /init."
        )
        return CommandExecutionResult(assistant_text=message, command_display_text=message)
    auto_confirm = bool(options.get("yes"))
    interactive_available = callable(getattr(runtime, "request_user_input_handler", None))
    runtime_cwd = _runtime_cwd(runtime)
    if (runtime_cwd / DEFAULT_PROJECT_DOC_FILENAME).is_file():
        message = "AENGTHUB.md already exists here. Skipping /init to avoid overwriting it."
        return CommandExecutionResult(assistant_text=message, command_display_text=message)
    scan_summary = build_init_scan_summary(runtime_cwd)
    prompt_text = build_init_llm_prompt(
        scan_summary,
        refresh=False,
        auto_confirm=auto_confirm,
        interactive_available=interactive_available and not auto_confirm,
    )
    return _run_llm_init_prompt(
        runtime,
        prompt_text=prompt_text,
        allow_request_user_input=False,
    )


def _run_llm_init_prompt(
    runtime: Any,
    *,
    prompt_text: str,
    allow_request_user_input: bool,
) -> CommandExecutionResult:
    agent = getattr(runtime, "agent", None)
    planner = getattr(agent, "plan", None)
    if not callable(planner):
        return CommandExecutionResult(assistant_text="`/init` unavailable: agent planner missing.")

    tool_executor = _InitToolExecutor(
        runtime,
        allow_request_user_input=allow_request_user_input,
    )
    plan_kwargs = _filter_plan_kwargs(
        runtime,
        planner,
        {
            "history": _planner_history(runtime),
            "tool_executor": tool_executor,
            "attachments": [],
            "input_items": _planner_input_items(runtime),
            "prompt_cache_key": getattr(runtime, "thread_id", None),
            "turn_event_callback": _planner_turn_event_callback(runtime),
            "current_dt": _current_datetime(runtime),
            "environment_snapshot": dict(
                getattr(runtime, "_environment_context_snapshot", {}) or {}
            ),
        },
    )
    if plan_kwargs.get("input_items") is not None and "history" in plan_kwargs:
        plan_kwargs["history"] = []

    previous_default_mode = bool(getattr(runtime, "default_mode_request_user_input", False))
    if allow_request_user_input:
        runtime.default_mode_request_user_input = True
    try:
        intent = planner(prompt_text, **plan_kwargs)
    finally:
        runtime.default_mode_request_user_input = previous_default_mode

    executor = getattr(runtime, "_execute_agent_intent_result", None)
    if callable(executor):
        return executor(intent)
    return CommandExecutionResult(
        assistant_text=str(getattr(intent, "assistant_text", "") or ""),
        tool_events=list(getattr(intent, "tool_events", []) or []),
        turn_events=[
            dict(item)
            for item in list(getattr(intent, "turn_events", []) or [])
            if isinstance(item, dict)
        ],
    )


def _planner_history(runtime: Any) -> list[Any] | None:
    builder = getattr(runtime, "_planner_history", None)
    if callable(builder):
        try:
            history = builder()
            return list(history or [])
        except Exception:
            pass
    history = getattr(runtime, "history", None)
    return list(history or []) if history is not None else None


def _planner_input_items(runtime: Any) -> list[dict[str, Any]] | None:
    builder = getattr(runtime, "_planner_conversation_input_items", None)
    if not callable(builder):
        return None
    try:
        items = builder()
    except Exception:
        return None
    normalized = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    return normalized or None


def _current_datetime(runtime: Any) -> Any:
    builder = getattr(runtime, "_current_datetime", None)
    if not callable(builder):
        return None
    try:
        return builder()
    except Exception:
        return None


def _planner_turn_event_callback(runtime: Any) -> Any:
    callback = getattr(runtime, "turn_event_callback", None)
    if callable(callback):
        return callback

    def _noop_turn_event_callback(_event: dict[str, Any]) -> None:
        return None

    return _noop_turn_event_callback


def _filter_plan_kwargs(runtime: Any, planner: Any, payload: dict[str, Any]) -> dict[str, Any]:
    filter_handler = getattr(runtime, "_filter_handler_kwargs", None)
    if callable(filter_handler):
        try:
            return dict(filter_handler(planner, payload) or {})
        except Exception:
            pass
    try:
        signature = inspect.signature(planner)
    except (TypeError, ValueError):
        return {key: value for key, value in payload.items() if value is not None}
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return {key: value for key, value in payload.items() if value is not None}
    return {
        key: value
        for key, value in payload.items()
        if value is not None and key in signature.parameters
    }


def _runtime_cwd(runtime: Any) -> Path:
    value = getattr(runtime, "cwd", None)
    return Path(value or Path.cwd()).resolve()
