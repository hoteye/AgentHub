from __future__ import annotations

from typing import Any


def resolve_mcp_runtime(runtime: Any) -> Any | None:
    getter = getattr(runtime, "get_mcp_runtime", None)
    if callable(getter):
        value = getter()
        if value is not None:
            return value
    direct = getattr(runtime, "mcp_runtime", None)
    if callable(direct):
        value = direct()
        if value is not None:
            return value
    elif direct is not None:
        return direct
    return getattr(runtime, "_mcp_runtime", None)


def invoke_first(target: Any, method_names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    for method_name in method_names:
        fn = getattr(target, method_name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    raise AttributeError("mcp runtime unavailable")
