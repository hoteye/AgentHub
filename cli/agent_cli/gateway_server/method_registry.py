from __future__ import annotations

from dataclasses import dataclass

from cli.agent_cli.gateway_protocol.methods import MethodMetadata, MethodRegistry, default_method_registry
from cli.agent_cli.gateway_server.methods import GatewayHandlerMap


@dataclass(frozen=True)
class GatewayMethodRegistration:
    metadata: MethodMetadata
    handler_registered: bool


class GatewayServerMethodRegistry:
    def __init__(
        self,
        *,
        metadata_registry: MethodRegistry | None = None,
        handlers: GatewayHandlerMap | None = None,
    ) -> None:
        self._metadata_registry = metadata_registry or default_method_registry()
        self._handlers = dict(handlers or {})

    def get(self, method: str) -> GatewayMethodRegistration | None:
        metadata = self._metadata_registry.get(method)
        if metadata is None:
            return None
        return GatewayMethodRegistration(
            metadata=metadata,
            handler_registered=metadata.method in self._handlers,
        )

    def require(self, method: str) -> GatewayMethodRegistration:
        registration = self.get(method)
        if registration is None:
            raise KeyError(f"unknown gateway method: {method}")
        return registration

    def list(self) -> list[GatewayMethodRegistration]:
        return [
            GatewayMethodRegistration(
                metadata=item,
                handler_registered=item.method in self._handlers,
            )
            for item in self._metadata_registry.list()
        ]

    def metadata(self) -> MethodRegistry:
        return self._metadata_registry


__all__ = [
    "GatewayMethodRegistration",
    "GatewayServerMethodRegistry",
]
