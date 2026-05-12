from __future__ import annotations

from typing import Any

from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers_projection as _projection
from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers_pure as _pure


def _normalize_media_capability(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("`media_capability` must be an object")
    runtime = _pure.declaration_runtime()
    source_modes = _pure.normalize_media_mode_list(
        _pure.value_with_aliases(value, "source_modes", "sourceModes"),
        field_name="source_modes",
        allowed_values=_pure._ALLOWED_MEDIA_SOURCE_MODES,
    )
    projection_modes = _pure.normalize_media_mode_list(
        _pure.value_with_aliases(
            value,
            "projection_modes",
            "projectionModes",
            "media_projection_modes",
            "mediaProjectionModes",
        ),
        field_name="projection_modes",
        allowed_values=_pure._ALLOWED_MEDIA_PROJECTION_MODES,
    )
    return runtime.PluginMediaCapabilityDeclaration(
        media_kind=_pure.normalize_media_kind(_pure.value_with_aliases(value, "media_kind", "mediaKind")),
        ingest_semantics=_pure.normalize_media_ingest_semantics(
            _pure.value_with_aliases(value, "ingest_semantics", "ingestSemantics")
        ),
        source_modes=source_modes,
        projection_modes=projection_modes,
        mime_types=_pure.normalize_mime_types(
            _pure.value_with_aliases(
                value,
                "mime_types",
                "mimeTypes",
                "supported_mime_types",
                "supportedMimeTypes",
            )
        ),
        max_size_bytes=_pure.normalize_max_size_bytes(
            _pure.value_with_aliases(value, "max_size_bytes", "maxSizeBytes")
        ),
    )


def normalize_plugin_capability_declaration_impl(
    item: Any,
    *,
    allow_compat_aliases: bool = False,
) -> Any:
    if not isinstance(item, dict):
        raise ValueError("capability declaration must be an object")
    runtime = _pure.declaration_runtime()
    plugin_name = _pure.normalize_optional_text(item.get("plugin_name"))
    declared_canonical_family = _pure.normalize_canonical_family_name(item.get("canonical_family"))
    media_capability = _normalize_media_capability(_pure.value_with_aliases(item, "media_capability", "mediaCapability"))
    source_kind = _pure.normalize_kind(item.get("kind"))
    declared_tool_capability_kind = _pure.normalize_tool_capability_kind(
        _pure.value_with_aliases(item, "tool_capability_kind", "toolCapabilityKind"),
        required=False,
    )
    declared_tool_runtime_binding = _pure.normalize_tool_runtime_binding(
        _pure.value_with_aliases(item, "tool_runtime_binding", "toolRuntimeBinding"),
        required=False,
    )
    tool_name = _pure.normalize_required_text(item.get("tool_name"), field_name="tool_name")
    (
        canonical_family,
        canonical_family_source,
        canonical_family_owner,
        canonical_family_alias_input,
        tool_capability_kind,
        tool_runtime_binding,
        canonical_family_record,
    ) = _projection.resolve_canonical_family(
        declared_canonical_family=declared_canonical_family,
        tool_name=tool_name,
        plugin_name=plugin_name,
        source_kind=source_kind,
        media_capability=media_capability,
        declared_tool_capability_kind=declared_tool_capability_kind,
        declared_tool_runtime_binding=declared_tool_runtime_binding,
        allow_compat_aliases=allow_compat_aliases,
    )
    return runtime.PluginCapabilityDeclaration(
        capability_id=_pure.normalize_required_text(item.get("capability_id"), field_name="capability_id"),
        kind=source_kind,
        tool_name=tool_name,
        canonical_family=canonical_family,
        declared_canonical_family=declared_canonical_family,
        canonical_family_source=canonical_family_source,
        canonical_family_owner=canonical_family_owner,
        canonical_family_alias_input=canonical_family_alias_input,
        tool_capability_kind=tool_capability_kind,
        tool_runtime_binding=tool_runtime_binding,
        supported_profiles=_pure.normalize_supported_profiles(item.get("supported_profiles")),
        default_visibility=_pure.normalize_default_visibility(item.get("default_visibility")),
        plugin_name=plugin_name,
        media_capability=media_capability,
        canonical_family_record=canonical_family_record,
    )


def normalize_plugin_capability_declarations_impl(
    items: Any,
    *,
    strict: bool = False,
    allow_compat_aliases: bool = False,
) -> Any:
    runtime = _pure.declaration_runtime()
    if items is None:
        return runtime.PluginCapabilityDeclarationLoadResult(declarations=(), errors=())
    if not isinstance(items, list):
        error_text = "capabilities payload must be a list"
        if strict:
            raise ValueError(error_text)
        return runtime.PluginCapabilityDeclarationLoadResult(declarations=(), errors=(error_text,))

    declarations: list[Any] = []
    errors: list[str] = []
    seen_capability_ids: set[str] = set()
    for index, raw_item in enumerate(items):
        try:
            normalized = normalize_plugin_capability_declaration_impl(
                raw_item,
                allow_compat_aliases=allow_compat_aliases,
            )
            if normalized.capability_id in seen_capability_ids:
                raise ValueError(f"duplicate capability_id `{normalized.capability_id}`")
            seen_capability_ids.add(normalized.capability_id)
            declarations.append(normalized)
        except Exception as exc:
            error_text = f"[{index}] {exc}"
            if strict:
                raise ValueError(error_text) from exc
            errors.append(error_text)
    return runtime.PluginCapabilityDeclarationLoadResult(
        declarations=tuple(declarations),
        errors=tuple(errors),
    )
