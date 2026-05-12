from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from cli.agent_cli.models import CommandExecutionResult, ToolEvent


Payload = dict[str, Any]
ProjectedT = TypeVar("ProjectedT")


def build_workspace_file_payload(**kwargs: Any) -> Payload:
    return dict(kwargs)


def build_workspace_file_result_payload(
    request_payload: Mapping[str, Any],
    *,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    fallback_arg_name: str,
    fallback_call: Callable[..., ToolEvent],
) -> Payload:
    payload = dict(request_payload)
    payload["call_structured_helper"] = call_structured_helper
    payload["result_from_event"] = result_from_event
    payload[fallback_arg_name] = fallback_call
    return payload


def project_workspace_file_payload(
    projection: Callable[..., ProjectedT],
    payload: Mapping[str, Any],
) -> ProjectedT:
    return projection(**dict(payload))


__all__ = [
    "Payload",
    "build_workspace_file_payload",
    "build_workspace_file_result_payload",
    "project_workspace_file_payload",
]
