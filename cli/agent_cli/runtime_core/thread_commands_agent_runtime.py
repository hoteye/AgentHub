from __future__ import annotations

import inspect
import shlex
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set


def _normalized_collab_items(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list | tuple):
        return None
    normalized: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item_type = str(item.get("type") or "").strip().lower()
        if not item_type:
            continue
        item["type"] = item_type
        if item_type == "image":
            image_url = str(item.get("image_url") or item.get("url") or "").strip()
            if image_url:
                item["image_url"] = image_url
                item.pop("url", None)
        normalized.append(item)
    return normalized or None


def _collab_item_preview(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "text":
        return str(item.get("text") or "").strip()
    if item_type == "image":
        return "[image]"
    if item_type in {"local_image", "localimage"}:
        path = str(item.get("path") or "").strip()
        return f"[local_image:{path}]" if path else "[local_image]"
    if item_type == "skill":
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if name and path:
            return f"[skill:${name}]({path})"
        return "[skill]"
    if item_type == "mention":
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if name and path:
            return f"[mention:${name}]({path})"
        if name:
            return f"@{name}"
        return "[mention]"
    return "[input]"


def collab_items_preview(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    return "\n".join(
        text for text in (_collab_item_preview(item) for item in items) if text
    ).strip()


def parse_spawn_agent_payload(
    *,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], dict[str, Any]],
    decode_raw_text_arg: Callable[[str], str],
    bool_option: Callable[..., bool],
) -> dict[str, Any] | None:
    if not arg_text:
        return None
    try:
        payload = parse_json_tool_arg(arg_text)
    except ValueError:
        task_text = decode_raw_text_arg(arg_text)
        if not task_text:
            return None
        payload = {"task": task_text}
    input_items = _normalized_collab_items(payload.get("items"))
    message_text = str(payload.get("message") or "").strip()
    if message_text and input_items:
        return {"error": "Provide either message or items, but not both"}
    legacy_task_text = str(payload.get("task") or payload.get("prompt") or "").strip()
    task_text = message_text or legacy_task_text or collab_items_preview(input_items)
    if not task_text:
        return {}
    return {
        "task": task_text,
        "role": str(payload.get("role") or payload.get("agent_type") or "subagent").strip()
        or "subagent",
        "model": str(payload.get("model") or "").strip() or None,
        "provider": str(payload.get("provider") or "").strip() or None,
        "reasoning_effort": str(payload.get("reasoning_effort") or "").strip() or None,
        "timeout": payload.get("timeout"),
        "async_mode": (
            bool_option(payload.get("async"), default=False) if "async" in payload else None
        ),
        "reason": str(payload.get("reason") or "").strip() or None,
        "mode": str(payload.get("mode") or "").strip() or None,
        "wait_required": payload.get("wait_required") if "wait_required" in payload else None,
        "task_shape": str(payload.get("task_shape") or "").strip() or None,
        "subagent_type": str(payload.get("subagent_type") or "").strip() or None,
        "input_items": input_items,
        "source_message": message_text or None,
        "fork_context": (
            bool_option(payload.get("fork_context"), default=False)
            if "fork_context" in payload
            else None
        ),
        "codex_collab_payload": bool(
            message_text or input_items is not None or "fork_context" in payload
        ),
    }


def spawn_agent_arguments(payload: dict[str, Any]) -> dict[str, Any]:
    if bool(payload.get("codex_collab_payload")):
        arguments: dict[str, Any] = {}
        if payload.get("source_message"):
            arguments["message"] = payload["source_message"]
        if payload.get("input_items") is not None:
            arguments["items"] = [
                dict(item)
                for item in list(payload.get("input_items") or [])
                if isinstance(item, dict)
            ]
        if payload.get("role"):
            arguments["agent_type"] = payload["role"]
        if payload.get("fork_context") is not None:
            arguments["fork_context"] = bool(payload.get("fork_context"))
        return arguments
    return {
        "task": payload["task"],
        "role": payload["role"],
        "model": payload.get("model"),
        "provider": payload.get("provider"),
        "reasoning_effort": payload.get("reasoning_effort"),
        "timeout": payload.get("timeout"),
        "async": payload.get("async_mode"),
        **({"reason": payload["reason"]} if payload.get("reason") else {}),
        **({"mode": payload["mode"]} if payload.get("mode") else {}),
        **(
            {"wait_required": payload["wait_required"]}
            if payload.get("wait_required") is not None
            else {}
        ),
        **({"task_shape": payload["task_shape"]} if payload.get("task_shape") else {}),
        **({"subagent_type": payload["subagent_type"]} if payload.get("subagent_type") else {}),
    }


def _slash_parsed_args(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[Any], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def parse_target_command_payload(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], dict[str, Any]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[dict[str, Any], tuple[list[Any], dict[str, Any]]]:
    payload: dict[str, Any] = {}
    try:
        payload = parse_json_tool_arg(arg_text) if arg_text else {}
    except ValueError:
        payload = {}
    slash_args = _slash_parsed_args(slash_invocation)
    if slash_args is not None:
        return payload, slash_args
    parse_args = getattr(runtime, "_parse_args", None)
    if callable(parse_args):
        return payload, parse_args(arg_text)
    try:
        return payload, (shlex.split(str(arg_text or ""), posix=True), {})
    except ValueError:
        return payload, ([item for item in str(arg_text or "").split() if item], {})


def target_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("target") or payload.get("agent_id") or payload.get("id") or "").strip()


def _filter_runner_kwargs(handler: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return kwargs
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def run_target_command(
    *,
    runtime: Any,
    runner_name: str,
    event_name: str,
    unavailable_summary: str,
    failed_summary: str,
    runner_args: tuple[Any, ...],
    runner_kwargs: dict[str, Any],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    arguments: dict[str, Any],
    target_for_error: str | None = None,
) -> CommandExecutionResult | tuple[str, list[ToolEvent]] | None:
    runner = getattr(runtime, runner_name, None)
    if not callable(runner):
        return error_result(
            error_event(
                event_name, unavailable_summary, error=f"{event_name} runtime is unavailable"
            ),
            arguments=arguments,
        )
    filtered_runner_kwargs = _filter_runner_kwargs(runner, runner_kwargs)
    try:
        return runner(*runner_args, **filtered_runner_kwargs)
    except Exception as exc:
        error_kwargs = {"error": str(exc)}
        if target_for_error:
            error_kwargs["target"] = target_for_error
        return error_result(
            error_event(event_name, failed_summary, **error_kwargs),
            arguments=arguments,
        )
