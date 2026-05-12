from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, TypeVar


class McpConfigScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    WORKSPACE = "workspace"
    PLUGIN = "plugin"
    RUNTIME = "runtime"


class McpTransportKind(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    WS = "ws"
    SDK = "sdk"
    INPROCESS = "inprocess"


class McpConfigState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class McpConnectionState(str, Enum):
    DISABLED = "disabled"
    PENDING = "pending"
    CONNECTED = "connected"
    NEEDS_AUTH = "needs-auth"
    FAILED = "failed"


class McpProjectionState(str, Enum):
    EMPTY = "empty"
    PARTIAL = "partial"
    READY = "ready"
    STALE = "stale"


_EnumT = TypeVar("_EnumT", bound=Enum)


def parse_enum(enum_cls: type[_EnumT], value: Any, *, field_name: str) -> _EnumT:
    try:
        return enum_cls(str(value or "").strip())
    except ValueError as exc:
        choices = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"invalid {field_name}: {value!r}; expected one of: {choices}") from exc


def coerce_text(value: Any, *, default: str = "") -> str:
    return str(value if value is not None else default)


def coerce_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def coerce_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def coerce_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]

