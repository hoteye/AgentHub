from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.gateway_core.models import (
    ConnectorRegistration,
    PolicyRegistration,
    TriggerRegistration,
)
from cli.agent_cli.host.plugin_manifest import PluginManifest


_PLUGIN_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+@[A-Za-z0-9_-]+$")

CommandHandler = Callable[[str, Any], Tuple[str, List[Any]]]
ToolHandler = Callable[..., Any]
WorkflowHandler = Callable[..., Any]


class PluginStoreError(ValueError):
    pass


@dataclass(frozen=True)
class PluginId:
    plugin_name: str
    marketplace_name: str

    @staticmethod
    def parse(plugin_key: str) -> "PluginId":
        text = str(plugin_key or "").strip()
        if not _PLUGIN_KEY_PATTERN.match(text):
            raise PluginStoreError(f"invalid plugin key `{text}`; expected <plugin>@<marketplace>")
        plugin_name, marketplace_name = text.rsplit("@", 1)
        return PluginId(plugin_name=plugin_name, marketplace_name=marketplace_name)

    def as_key(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"


@dataclass
class RegisteredCommand:
    name: str
    usage: str
    description: str
    handler: CommandHandler
    plugin_name: str


@dataclass
class RegisteredTool:
    name: str
    description: str
    handler: ToolHandler
    plugin_name: str
    label: Optional[str] = None
    mutates_ui: bool = False
    requires_confirmation: bool = False


@dataclass
class RegisteredWorkflowHandler:
    workflow_name: str
    plugin_name: str
    handler: WorkflowHandler
    description: str = ""


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    plugin_name: str
    enabled: bool
    command_count: int
    tool_count: int
    connector_count: int
    trigger_count: int
    policy_count: int
    workflow_count: int
    provider_hooks: Any
    runtime_hooks: Any
    connector_registrations: List[ConnectorRegistration]
    trigger_registrations: List[TriggerRegistration]
    policy_registrations: List[PolicyRegistration]
    workflow_handlers: List[RegisteredWorkflowHandler]
    config_name: str = ""
    root: Path = field(default_factory=Path)
    error: Optional[str] = None
    skill_roots: List[Path] = field(default_factory=list)
    mcp_servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    apps: List[Dict[str, Any]] = field(default_factory=list)
    capability_declarations: List[Dict[str, Any]] = field(default_factory=list)
    capability_declaration_errors: List[str] = field(default_factory=list)
    installed: bool = False
    source_kind: str = "legacy"

    def is_active(self) -> bool:
        return self.enabled and not self.error


@dataclass(frozen=True)
class _PluginSource:
    config_name: str
    plugin_name: str
    root: Path
    enabled: bool
    manifest: Optional[PluginManifest]
    source_kind: str
    installed: bool


class PluginCommandRegistry:
    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name
        self._items: List[RegisteredCommand] = []

    def add_command(
        self,
        *,
        name: str,
        usage: str,
        description: str,
        handler: CommandHandler,
    ) -> None:
        self._items.append(
            RegisteredCommand(
                name=str(name).strip().lower(),
                usage=str(usage).strip(),
                description=str(description).strip(),
                handler=handler,
                plugin_name=self.plugin_name,
            )
        )

    @property
    def items(self) -> List[RegisteredCommand]:
        return list(self._items)


class PluginToolRegistry:
    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name
        self._items: List[RegisteredTool] = []

    def add_tool(
        self,
        *,
        name: str,
        description: str,
        handler: ToolHandler,
        label: Optional[str] = None,
        mutates_ui: bool = False,
        requires_confirmation: bool = False,
    ) -> None:
        self._items.append(
            RegisteredTool(
                name=str(name).strip(),
                description=str(description).strip(),
                handler=handler,
                plugin_name=self.plugin_name,
                label=str(label).strip() if label else None,
                mutates_ui=bool(mutates_ui),
                requires_confirmation=bool(requires_confirmation),
            )
        )

    @property
    def items(self) -> List[RegisteredTool]:
        return list(self._items)
