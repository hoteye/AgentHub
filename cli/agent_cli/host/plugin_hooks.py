from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class ProviderHooks:
    tool_specs: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt_fragments: List[str] = field(default_factory=list)
    routing_hints: List[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class RuntimeHooks:
    pre_route: Optional[Callable[..., Any]] = None
    enrich_local_plan: Optional[Callable[..., Dict[str, Any]]] = None
    build_activity_events: Optional[Callable[..., List[Any]]] = None
    build_connector_registrations: Optional[Callable[..., List[Any]]] = None
    build_trigger_registrations: Optional[Callable[..., List[Any]]] = None
    build_policy_registrations: Optional[Callable[..., List[Any]]] = None
    build_workflow_handlers: Optional[Callable[..., List[Any]]] = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
