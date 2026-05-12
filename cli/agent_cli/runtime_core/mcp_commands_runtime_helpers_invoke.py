from __future__ import annotations

import json
from typing import Any, Callable

from cli.agent_cli.slash_surface import surface_usage_text


def invoke_mcp(
    invoke_first: Callable[..., Any],
    mcp_runtime: Any,
    method_names: tuple[str, ...],
    *args: Any,
    **kwargs: Any,
) -> tuple[Any | None, str | None]:
    try:
        return invoke_first(mcp_runtime, method_names, *args, **kwargs), None
    except AttributeError:
        return None, "mcp runtime unavailable"
    except ValueError as exc:
        return None, str(exc)


def invoke_mcp_runtime(
    invoke_first: Callable[..., Any],
    mcp_runtime: Any,
    method_names: tuple[str, ...],
    *args: Any,
    **kwargs: Any,
) -> tuple[Any | None, str | None]:
    try:
        return invoke_first(mcp_runtime, method_names, *args, **kwargs), None
    except AttributeError:
        return None, "mcp runtime unavailable"
    except RuntimeError as exc:
        return None, str(exc)
    except ValueError as exc:
        return None, str(exc)


def invoke_mcp_runtime_with_typeerror_fallback(
    invoke_first: Callable[..., Any],
    mcp_runtime: Any,
    method_names: tuple[str, ...],
    *,
    fallback_args: tuple[Any, ...],
    **kwargs: Any,
) -> tuple[Any | None, str | None]:
    try:
        return invoke_first(mcp_runtime, method_names, **kwargs), None
    except TypeError:
        return invoke_mcp_runtime(
            invoke_first,
            mcp_runtime,
            method_names,
            *fallback_args,
        )
    except AttributeError:
        return None, "mcp runtime unavailable"
    except RuntimeError as exc:
        return None, str(exc)
    except ValueError as exc:
        return None, str(exc)


def handle_mcp_tool_call_impl(
    runtime: Any,
    arg_text: str,
    *,
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_projected_mcp_tool_call_fn: Callable[[Any], str],
) -> tuple[str, list[Any]]:
    positionals, options = parse_args(runtime, arg_text)
    projected_name = str(options.get("projected-name") or options.get("projected_name") or "").strip()
    arguments_json = str(options.get("arguments-json") or options.get("arguments_json") or "{}").strip() or "{}"
    if not projected_name and positionals:
        projected_name = str(positionals[0] or "").strip()
    if not projected_name:
        return (f"Usage: {surface_usage_text('mcp_tool_call')}", [])
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        return (f"invalid arguments json: {exc.msg}", [])
    if not isinstance(arguments, dict):
        return ("invalid arguments json: expected object", [])
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("call_projected_tool",),
        projected_name=projected_name,
        arguments=arguments,
    )
    if error:
        return (error, [])
    return (format_projected_mcp_tool_call_fn(payload), [])
