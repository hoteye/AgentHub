from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .models import ConnectorRegistration, GatewayEvent, TriggerRegistration


class GatewayRegistrationConflictError(ValueError):
    """Raised when connector or trigger registration keys collide."""


@dataclass(slots=True)
class GatewayRegistry:
    connectors: Dict[str, ConnectorRegistration]
    triggers: Dict[str, TriggerRegistration]

    def __init__(self) -> None:
        self.connectors = {}
        self.triggers = {}

    def register_connector(self, registration: ConnectorRegistration) -> ConnectorRegistration:
        existing = self.connectors.get(registration.connector_key)
        if existing is not None:
            raise GatewayRegistrationConflictError(
                "duplicate connector_key "
                f"'{registration.connector_key}' for plugin '{registration.plugin_name}'; "
                f"already registered by plugin '{existing.plugin_name}'"
            )
        self.connectors[registration.connector_key] = registration
        return registration

    def register_trigger(self, registration: TriggerRegistration) -> TriggerRegistration:
        existing = self.triggers.get(registration.trigger_key)
        if existing is not None:
            raise GatewayRegistrationConflictError(
                "duplicate trigger_key "
                f"'{registration.trigger_key}' for plugin '{registration.plugin_name}'; "
                f"already registered by plugin '{existing.plugin_name}'"
            )
        self.triggers[registration.trigger_key] = registration
        return registration

    def load_from_plugin_manager(self, plugin_manager: Any) -> "GatewayRegistry":
        for registration in plugin_manager.connector_registrations():
            self.register_connector(registration)
        for registration in plugin_manager.trigger_registrations():
            self.register_trigger(registration)
        return self

    def list_connectors(self) -> List[ConnectorRegistration]:
        return list(self.connectors.values())

    def list_triggers(self) -> List[TriggerRegistration]:
        return list(self.triggers.values())

    def triggers_for_event(self, event: GatewayEvent) -> List[TriggerRegistration]:
        matches: List[TriggerRegistration] = []
        for registration in self.triggers.values():
            if not registration.enabled:
                continue
            if registration.event_types and event.event_type not in registration.event_types:
                continue
            if registration.connector_key and registration.connector_key != event.connector_key:
                continue
            matches.append(registration)
        matches.sort(key=lambda item: (int(item.priority), item.trigger_key))
        return matches
