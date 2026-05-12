from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .models import GatewayEvent, TriggerRegistration
from .registry import GatewayRegistry


@dataclass(slots=True)
class RouteDecision:
    event: GatewayEvent
    trigger: Optional[TriggerRegistration]
    target_kind: str
    plugin_name: Optional[str]
    workflow_name: Optional[str]
    reason: str


def _payload_path_values(payload: Any, path: str) -> list[str]:
    if not path:
        return []
    current_items = [payload]
    for part in [item for item in str(path).split(".") if item]:
        next_items: list[Any] = []
        for current in current_items:
            if isinstance(current, dict):
                value = current.get(part)
                if value is not None:
                    next_items.append(value)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, dict):
                        value = item.get(part)
                        if value is not None:
                            next_items.append(value)
        current_items = next_items
        if not current_items:
            return []
    values: list[str] = []
    for item in current_items:
        if isinstance(item, str):
            text = item.strip()
            if text:
                values.append(text)
        elif item is not None:
            values.append(str(item))
    return values


def _matches_payload_contains(filter_payload: Any, event: GatewayEvent, *, require_all: bool) -> bool:
    if not isinstance(filter_payload, dict):
        return False
    paths = [str(item).strip() for item in filter_payload.get("paths") or [] if str(item).strip()]
    terms = [str(item).strip().lower() for item in filter_payload.get("terms") or [] if str(item).strip()]
    if not paths or not terms:
        return False
    haystack = " ".join(
        value.lower()
        for path in paths
        for value in _payload_path_values(event.payload, path)
    )
    if not haystack:
        return False
    if require_all:
        return all(term in haystack for term in terms)
    return any(term in haystack for term in terms)


def event_matches_trigger_filters(event: GatewayEvent, trigger: TriggerRegistration) -> bool:
    filters = dict(trigger.filters or {})
    if not filters:
        return True
    for key, value in filters.items():
        if key == "payload_contains_any":
            if not _matches_payload_contains(value, event, require_all=False):
                return False
            continue
        if key == "payload_contains_all":
            if not _matches_payload_contains(value, event, require_all=True):
                return False
            continue
        return False
    return True


def route_event(registry: GatewayRegistry, event: GatewayEvent) -> RouteDecision:
    matches = [item for item in registry.triggers_for_event(event) if event_matches_trigger_filters(event, item)]
    if not matches:
        return RouteDecision(
            event=event,
            trigger=None,
            target_kind="unrouted",
            plugin_name=event.plugin_name,
            workflow_name=None,
            reason="no_trigger_match",
        )
    selected = matches[0]
    return RouteDecision(
        event=event,
        trigger=selected,
        target_kind="plugin_workflow",
        plugin_name=selected.plugin_name,
        workflow_name=selected.workflow_name,
        reason="trigger_match",
    )
