from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class JsonRpcNotification:
    method: str
    params: JsonObject = field(default_factory=dict)
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JsonRpcServerRequest:
    request_id: int | str
    method: str
    params: JsonObject = field(default_factory=dict)
    raw: JsonObject = field(default_factory=dict)
