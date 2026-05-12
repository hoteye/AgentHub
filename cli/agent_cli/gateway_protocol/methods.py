from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable

from cli.agent_cli.gateway_protocol import methods_runtime as methods_runtime_service


def _copy_list(values: Iterable[str] | None = None) -> list[str]:
    return methods_runtime_service.copy_list(list(values or []))


def _copy_map(value: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return methods_runtime_service.copy_map(value)


@dataclass(slots=True, frozen=True)
class MethodMetadata:
    method: str
    family: str
    description: str = ""
    auth_required: bool = True
    required_scopes: list[str] = field(default_factory=list)
    control_plane_write: bool = False
    emits_events: bool = False
    idempotent: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MethodRegistry:
    def __init__(self, methods: Iterable[MethodMetadata] | None = None) -> None:
        self._methods: dict[str, MethodMetadata] = {}
        for item in methods or []:
            self.register(item)

    def register(self, item: MethodMetadata) -> MethodMetadata:
        method = str(item.method or "").strip()
        if not method:
            raise ValueError("method is required")
        if method in self._methods:
            raise ValueError(f"duplicate gateway method: {method}")
        self._methods[method] = item
        return item

    def get(self, method: str) -> MethodMetadata | None:
        return self._methods.get(str(method or "").strip())

    def require(self, method: str) -> MethodMetadata:
        item = self.get(method)
        if item is None:
            raise KeyError(f"unknown gateway method: {method}")
        return item

    def list(self) -> list[MethodMetadata]:
        return [self._methods[key] for key in sorted(self._methods)]


def default_method_registry() -> MethodRegistry:
    return MethodRegistry(
        methods=[
            MethodMetadata(
                method=str(payload.get("method") or "").strip(),
                family=str(payload.get("family") or "").strip(),
                description=str(payload.get("description") or ""),
                auth_required=bool(payload.get("auth_required", True)),
                required_scopes=_copy_list(payload.get("required_scopes")),
                control_plane_write=bool(payload.get("control_plane_write", False)),
                emits_events=bool(payload.get("emits_events", False)),
                idempotent=bool(payload.get("idempotent", True)),
                metadata=_copy_map(payload.get("metadata")),
            )
            for payload in methods_runtime_service.default_method_payloads()
        ],
    )
