from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

Payload = dict[str, Any]
ProjectedT = TypeVar("ProjectedT")


def build_file_tools_bridge_payload(**kwargs: Any) -> Payload:
    return dict(kwargs)


def project_file_tools_bridge_payload(
    projection: Callable[..., ProjectedT],
    payload: Mapping[str, Any],
) -> ProjectedT:
    return projection(**dict(payload))


__all__ = [
    "Payload",
    "build_file_tools_bridge_payload",
    "project_file_tools_bridge_payload",
]
