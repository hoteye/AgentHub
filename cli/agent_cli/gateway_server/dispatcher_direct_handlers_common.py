from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

JsonMap = dict[str, Any]


@dataclass(slots=True, frozen=True)
class GatewayDispatchResult:
    ok: bool
    result: JsonMap | None = None
    error_code: int | None = None
    error_message: str | None = None
    error_data: JsonMap = field(default_factory=dict)
    transport_context: JsonMap = field(default_factory=dict)


def _success(result: JsonMap) -> GatewayDispatchResult:
    return GatewayDispatchResult(ok=True, result=dict(result or {}))


def _failure(code: int, message: str, *, detail: str) -> GatewayDispatchResult:
    return GatewayDispatchResult(
        ok=False,
        error_code=int(code),
        error_message=str(message),
        error_data={"detail": str(detail)},
    )


def build_direct_method_handlers(
    workflow_handlers: Mapping[str, Callable[..., GatewayDispatchResult]],
    direct_handlers: Mapping[str, Callable[..., GatewayDispatchResult]],
) -> dict[str, Callable[..., GatewayDispatchResult]]:
    mapping = dict(direct_handlers)
    mapping.update(
        {
            "gateway.trace.timeline": workflow_handlers["gateway.trace.timeline"],
            "workflows.list": workflow_handlers["workflows.list"],
            "workflows.get": workflow_handlers["workflows.get"],
            "workflows.resume": workflow_handlers["workflows.resume"],
            "approvals.list": workflow_handlers["approvals.list"],
            "approvals.get": workflow_handlers["approvals.get"],
        }
    )
    return mapping
