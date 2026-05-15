from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import tool_call_runtime_helpers

_quote_value = tool_call_runtime_helpers.quote_value
_normalized_collab_items = tool_call_runtime_helpers.normalized_collab_items
_uses_legacy_spawn_agent_payload = tool_call_runtime_helpers.uses_legacy_spawn_agent_payload


def build_spawn_agent_command(
    arguments: dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
    normalized_collab_items_fn: Callable[[Any], list[dict[str, Any]] | None] | None = None,
    uses_legacy_spawn_agent_payload_fn: Callable[[dict[str, Any]], bool] | None = None,
) -> str | None:
    normalized_collab_items_fn = normalized_collab_items_fn or _normalized_collab_items
    uses_legacy_spawn_agent_payload_fn = (
        uses_legacy_spawn_agent_payload_fn or _uses_legacy_spawn_agent_payload
    )

    if uses_legacy_spawn_agent_payload_fn(arguments):
        task = str(
            arguments.get("task") or arguments.get("message") or arguments.get("prompt") or ""
        ).strip()
        if not task:
            return None
        payload: dict[str, Any] = {"task": task}
        role = str(arguments.get("role") or arguments.get("agent_type") or "").strip()
        if role:
            payload["role"] = role
        model = str(arguments.get("model") or "").strip()
        if model:
            payload["model"] = model
        provider = str(arguments.get("provider") or "").strip()
        if provider:
            payload["provider"] = provider
        reasoning_effort = str(arguments.get("reasoning_effort") or "").strip()
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        timeout = arguments.get("timeout")
        if timeout is not None:
            payload["timeout"] = timeout
        if "async" in arguments and arguments.get("async") is not None:
            payload["async"] = bool(arguments.get("async"))
        reason = str(arguments.get("reason") or "").strip()
        if reason:
            payload["reason"] = reason
        mode = str(arguments.get("mode") or "").strip()
        if mode:
            payload["mode"] = mode
        if "wait_required" in arguments and arguments.get("wait_required") is not None:
            payload["wait_required"] = bool(arguments.get("wait_required"))
        task_shape = str(arguments.get("task_shape") or "").strip()
        if task_shape:
            payload["task_shape"] = task_shape
        subagent_type = str(arguments.get("subagent_type") or "").strip()
        if subagent_type:
            payload["subagent_type"] = subagent_type
        return f"/spawn_agent {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    message = str(arguments.get("message") or arguments.get("prompt") or "").strip()
    items = normalized_collab_items_fn(arguments.get("items"))
    if bool(message) == bool(items):
        return None
    payload = {"message": message} if message else {"items": items}
    agent_type = str(arguments.get("agent_type") or arguments.get("role") or "").strip()
    if agent_type:
        payload["agent_type"] = agent_type
    if "fork_context" in arguments and arguments.get("fork_context") is not None:
        payload["fork_context"] = bool(arguments.get("fork_context"))
    return f"/spawn_agent {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"


def build_send_input_command(
    arguments: dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
    normalized_collab_items_fn: Callable[[Any], list[dict[str, Any]] | None] | None = None,
) -> str | None:
    normalized_collab_items_fn = normalized_collab_items_fn or _normalized_collab_items

    target = str(
        arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
    ).strip()
    message = str(
        arguments.get("message") or arguments.get("text") or arguments.get("prompt") or ""
    ).strip()
    items = normalized_collab_items_fn(arguments.get("items"))
    interrupt = bool(arguments.get("interrupt"))
    if not target or bool(message) == bool(items):
        return None
    if items is not None or "id" in arguments:
        payload: dict[str, Any] = {"id": target}
        if message:
            payload["message"] = message
        if items is not None:
            payload["items"] = items
        if interrupt:
            payload["interrupt"] = True
        return f"/send_input {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"
    command = f"/send_input {quote_arg_fn(target)} {quote_arg_fn(message)}"
    if interrupt:
        command += " --interrupt"
    return command


def build_resume_agent_command(
    arguments: dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
) -> str | None:
    target = str(
        arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
    ).strip()
    return f"/resume_agent {quote_arg_fn(target)}" if target else None


def build_wait_agent_command(
    arguments: dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
    quote_value_fn: Callable[[Any, Callable[[Any], str]], str] | None = None,
) -> str | None:
    quote_value_fn = quote_value_fn or _quote_value

    ids = arguments.get("targets")
    if ids is None:
        ids = arguments.get("ids")
    if isinstance(ids, list | tuple):
        normalized_ids = [str(item).strip() for item in ids if str(item).strip()]
        if not normalized_ids:
            return None
        payload: dict[str, Any] = {"ids": normalized_ids}
        timeout_ms = arguments.get("timeout_ms")
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        return f"/wait_agent {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    target = str(
        arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
    ).strip()
    if not target:
        return None
    command = f"/wait_agent {quote_arg_fn(target)}"
    timeout_ms = arguments.get("timeout_ms")
    if timeout_ms is not None:
        command += f" --timeout-ms {quote_value_fn(timeout_ms, quote_arg_fn)}"
    reason = str(arguments.get("reason") or "").strip()
    if reason:
        command += f" --reason {quote_arg_fn(reason)}"
    if "wait_required" in arguments and arguments.get("wait_required") is not None:
        command += (
            f" --wait-required {quote_arg_fn(str(bool(arguments.get('wait_required'))).lower())}"
        )
    return command
