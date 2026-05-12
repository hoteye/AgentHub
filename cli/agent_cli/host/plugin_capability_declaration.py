from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers as _plugin_capability_declaration_helpers

PluginCapabilityKind = Literal["provider_tool", "mcp_server", "skill", "app_connector"]
PluginCapabilityDefaultVisibility = Literal["model_visible", "host_only", "operator_only", "disabled"]
PluginCapabilityMediaKind = Literal["image", "document", "audio", "video", "binary"]
PluginCapabilityMediaIngestSemantics = Literal["shared_media_ingest_v1"]
PluginCapabilityMediaSourceMode = Literal["tool_path", "user_attachment", "hybrid"]
PluginCapabilityMediaProjectionMode = Literal[
    "tool_native_continuation",
    "tool_result_content_block",
    "message_native_attachment",
]
ToolCapabilityKind = Literal[
    "local_runtime_tool",
    "provider_native_tool",
    "message_native_capability",
    "ui_only_capability",
]
ToolRuntimeBinding = Literal[
    "local_runtime",
    "provider_native",
    "shared_media_ingest",
    "plugin_runtime",
    "plugin_mcp_server",
    "plugin_app_connector",
]
CanonicalFamilySource = Literal["builtin", "dynamic"]

def _tool_family_metadata_runtime():
    from cli.agent_cli.providers import tool_family_metadata_runtime as runtime

    return runtime


@dataclass(frozen=True)
class PluginCanonicalFamilyRecord:
    canonical_family: str
    family_source: CanonicalFamilySource
    family_owner: str
    canonical_tool_names: Tuple[str, ...]
    compatibility_aliases: Tuple[str, ...]
    tool_capability_kind: ToolCapabilityKind
    tool_runtime_binding: ToolRuntimeBinding

    def as_dict(self) -> Dict[str, Any]:
        return {
            "canonical_family": self.canonical_family,
            "family_source": self.family_source,
            "family_owner": self.family_owner,
            "canonical_tool_names": list(self.canonical_tool_names),
            "compatibility_aliases": list(self.compatibility_aliases),
            "tool_capability_kind": self.tool_capability_kind,
            "tool_runtime_binding": self.tool_runtime_binding,
        }


@dataclass(frozen=True)
class PluginMediaCapabilityDeclaration:
    media_kind: PluginCapabilityMediaKind
    ingest_semantics: PluginCapabilityMediaIngestSemantics
    source_modes: Tuple[PluginCapabilityMediaSourceMode, ...]
    projection_modes: Tuple[PluginCapabilityMediaProjectionMode, ...]
    mime_types: Tuple[str, ...] = ()
    max_size_bytes: int | None = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "media_kind": self.media_kind,
            "ingest_semantics": self.ingest_semantics,
            "source_modes": list(self.source_modes),
            "projection_modes": list(self.projection_modes),
            "mime_types": list(self.mime_types),
        }
        if self.max_size_bytes is not None:
            payload["max_size_bytes"] = int(self.max_size_bytes)
        return payload


@dataclass(frozen=True)
class PluginCapabilityDeclaration:
    capability_id: str
    kind: PluginCapabilityKind
    tool_name: str
    canonical_family: str
    declared_canonical_family: str
    canonical_family_source: CanonicalFamilySource
    canonical_family_owner: str
    canonical_family_alias_input: str
    tool_capability_kind: ToolCapabilityKind
    tool_runtime_binding: ToolRuntimeBinding
    supported_profiles: Tuple[str, ...]
    default_visibility: PluginCapabilityDefaultVisibility
    plugin_name: str = ""
    media_capability: PluginMediaCapabilityDeclaration | None = None
    canonical_family_record: PluginCanonicalFamilyRecord | None = None

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "capability_id": self.capability_id,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "canonical_family": self.canonical_family,
            "declared_canonical_family": self.declared_canonical_family,
            "canonical_family_source": self.canonical_family_source,
            "canonical_family_owner": self.canonical_family_owner,
            "tool_capability_kind": self.tool_capability_kind,
            "tool_runtime_binding": self.tool_runtime_binding,
            "supported_profiles": list(self.supported_profiles),
            "default_visibility": self.default_visibility,
        }
        if self.canonical_family_alias_input:
            payload["canonical_family_alias_input"] = self.canonical_family_alias_input
        if self.plugin_name:
            payload["plugin_name"] = self.plugin_name
        if self.media_capability is not None:
            payload["media_capability"] = self.media_capability.as_dict()
        if self.canonical_family_record is not None:
            payload["canonical_family_record"] = self.canonical_family_record.as_dict()
        return payload


@dataclass(frozen=True)
class PluginCapabilityDeclarationLoadResult:
    declarations: Tuple[PluginCapabilityDeclaration, ...]
    errors: Tuple[str, ...]
    source_path: str = ""

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [item.as_dict() for item in self.declarations]


def normalize_plugin_capability_declaration(
    item: Any,
    *,
    allow_compat_aliases: bool = False,
) -> PluginCapabilityDeclaration:
    return _plugin_capability_declaration_helpers.normalize_plugin_capability_declaration_impl(
        item,
        allow_compat_aliases=allow_compat_aliases,
    )


def normalize_plugin_capability_declarations(
    items: Any,
    *,
    strict: bool = False,
    allow_compat_aliases: bool = False,
) -> PluginCapabilityDeclarationLoadResult:
    return _plugin_capability_declaration_helpers.normalize_plugin_capability_declarations_impl(
        items,
        strict=strict,
        allow_compat_aliases=allow_compat_aliases,
    )


def load_plugin_capability_declarations(
    plugin_root: Path,
    *,
    strict: bool = False,
) -> PluginCapabilityDeclarationLoadResult:
    return _plugin_capability_declaration_helpers.load_plugin_capability_declarations_impl(
        plugin_root,
        strict=strict,
    )
