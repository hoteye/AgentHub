from __future__ import annotations

from typing import Any

from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers_pure as _pure


def _derived_dynamic_tool_capability_kind(*, source_kind: str) -> str:
    if source_kind in {"skill", "app_connector"}:
        return "ui_only_capability"
    return "local_runtime_tool"


def _derived_dynamic_tool_runtime_binding(*, source_kind: str, media_capability: Any) -> str:
    if media_capability is not None:
        return "shared_media_ingest"
    if source_kind == "mcp_server":
        return "plugin_mcp_server"
    if source_kind == "app_connector":
        return "plugin_app_connector"
    return "plugin_runtime"


def _dynamic_canonical_family_record(
    *,
    canonical_family: str,
    plugin_name: str,
    tool_name: str,
    tool_capability_kind: str,
    tool_runtime_binding: str,
) -> Any:
    runtime = _pure.declaration_runtime()
    owner = plugin_name or "plugin"
    return runtime.PluginCanonicalFamilyRecord(
        canonical_family=canonical_family,
        family_source="dynamic",
        family_owner=owner,
        canonical_tool_names=(tool_name,) if tool_name else (),
        compatibility_aliases=(),
        tool_capability_kind=tool_capability_kind,
        tool_runtime_binding=tool_runtime_binding,
    )


def resolve_canonical_family(
    *,
    declared_canonical_family: str,
    tool_name: str,
    plugin_name: str,
    source_kind: str,
    media_capability: Any,
    declared_tool_capability_kind: str,
    declared_tool_runtime_binding: str,
    allow_compat_aliases: bool,
) -> tuple[str, str, str, str, str, str, Any]:
    runtime = _pure.declaration_runtime()
    tool_family_metadata_runtime = runtime._tool_family_metadata_runtime()
    builtin_record = tool_family_metadata_runtime.resolve_builtin_canonical_family(
        declared_canonical_family,
        allow_compat_aliases=allow_compat_aliases,
    )
    if builtin_record is not None:
        resolved_kind = str(builtin_record.get("tool_capability_kind") or "").strip().lower()
        resolved_binding = str(builtin_record.get("tool_runtime_binding") or "").strip().lower()
        if declared_tool_capability_kind and declared_tool_capability_kind != resolved_kind:
            raise ValueError(
                "builtin canonical family `"
                f"{builtin_record.get('canonical_family')}` requires tool_capability_kind `{resolved_kind}`"
            )
        if declared_tool_runtime_binding and declared_tool_runtime_binding != resolved_binding:
            raise ValueError(
                "builtin canonical family `"
                f"{builtin_record.get('canonical_family')}` requires tool_runtime_binding `{resolved_binding}`"
            )
        family_record = runtime.PluginCanonicalFamilyRecord(
            canonical_family=str(builtin_record.get("canonical_family") or "").strip(),
            family_source="builtin",
            family_owner="builtin",
            canonical_tool_names=tuple(
                str(item or "").strip() for item in builtin_record.get("canonical_tool_names") or ()
            ),
            compatibility_aliases=tuple(
                str(item or "").strip() for item in builtin_record.get("compatibility_aliases") or ()
            ),
            tool_capability_kind=resolved_kind,
            tool_runtime_binding=resolved_binding,
        )
        alias_input = (
            str(builtin_record.get("resolved_input") or "").strip()
            if str(builtin_record.get("resolved_from") or "").strip() == "compatibility_alias"
            else ""
        )
        return (
            family_record.canonical_family,
            "builtin",
            family_record.family_owner,
            alias_input,
            family_record.tool_capability_kind,
            family_record.tool_runtime_binding,
            family_record,
        )

    if tool_family_metadata_runtime.builtin_canonical_family_for_compatibility_alias(declared_canonical_family):
        raise ValueError(
            f"`canonical_family` {declared_canonical_family!r} is a compatibility alias; declare the canonical family instead"
        )

    resolved_kind = declared_tool_capability_kind or _derived_dynamic_tool_capability_kind(source_kind=source_kind)
    resolved_binding = declared_tool_runtime_binding or _derived_dynamic_tool_runtime_binding(
        source_kind=source_kind,
        media_capability=media_capability,
    )
    family_record = _dynamic_canonical_family_record(
        canonical_family=declared_canonical_family,
        plugin_name=plugin_name,
        tool_name=tool_name,
        tool_capability_kind=resolved_kind,
        tool_runtime_binding=resolved_binding,
    )
    return (
        family_record.canonical_family,
        "dynamic",
        family_record.family_owner,
        "",
        family_record.tool_capability_kind,
        family_record.tool_runtime_binding,
        family_record,
    )
