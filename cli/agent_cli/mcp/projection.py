from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .models import McpRuntimeSnapshot
from .state import McpProjectionState, coerce_dict, parse_enum


@dataclass(slots=True)
class McpProjectionSnapshot:
    projection_state: McpProjectionState = McpProjectionState.EMPTY
    tool_names: List[str] = field(default_factory=list)
    prompt_names: List[str] = field(default_factory=list)
    resource_uris: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projection_state": self.projection_state.value,
            "tool_names": list(self.tool_names),
            "prompt_names": list(self.prompt_names),
            "resource_uris": list(self.resource_uris),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "McpProjectionSnapshot":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            projection_state=parse_enum(
                McpProjectionState,
                data.get("projection_state") or McpProjectionState.EMPTY.value,
                field_name="mcp_projection_snapshot.projection_state",
            ),
            tool_names=[str(item) for item in data.get("tool_names", []) if str(item or "").strip()],
            prompt_names=[str(item) for item in data.get("prompt_names", []) if str(item or "").strip()],
            resource_uris=[str(item) for item in data.get("resource_uris", []) if str(item or "").strip()],
        )


def runtime_snapshot_to_projection(snapshot: McpRuntimeSnapshot) -> McpProjectionSnapshot:
    return McpProjectionSnapshot(
        projection_state=snapshot.projection_state,
        tool_names=[item.name for item in snapshot.tools if item.name],
        prompt_names=[item.name for item in snapshot.prompts if item.name],
        resource_uris=[item.uri for item in snapshot.resources if item.uri],
    )


def runtime_snapshot_projection_payload(snapshot: McpRuntimeSnapshot) -> Dict[str, Any]:
    payload = runtime_snapshot_to_projection(snapshot).to_dict()
    payload["connections"] = {name: state.value for name, state in sorted(snapshot.connection_states.items())}
    payload["servers"] = [item.to_dict() for item in snapshot.servers]
    return payload


def projection_snapshot_from_payload(payload: Dict[str, Any] | None) -> McpProjectionSnapshot:
    return McpProjectionSnapshot.from_dict(coerce_dict(payload))

