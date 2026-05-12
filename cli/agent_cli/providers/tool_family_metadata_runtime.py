from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Tuple

from . import tool_family_metadata_base_specs_runtime as _base_specs_runtime
from . import tool_family_mapping_runtime as _mapping_runtime

ToolCapabilityKind = str
ToolRuntimeBinding = str


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _compatibility_alias_to_family() -> Dict[str, str]:
    alias_map: Dict[str, str] = {
        "shell": _mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY,
        "file_search": "grep_files",
        "file_read": "read_file",
        "file_list": "list_dir",
        "open": "browser",
        "click": "browser",
        "find": "browser",
    }
    return alias_map


def _default_family_classification(canonical_family: str) -> tuple[ToolCapabilityKind, ToolRuntimeBinding]:
    normalized = _normalized_text(canonical_family)
    if normalized == "web_search":
        return "provider_native_tool", "provider_native"
    if normalized == "view_image":
        return "local_runtime_tool", "shared_media_ingest"
    if normalized == _normalized_text(_mapping_runtime.EXPERT_REVIEW_CANONICAL_FAMILY):
        return "local_runtime_tool", _mapping_runtime.EXPERT_REVIEW_RUNTIME_BINDING
    return "local_runtime_tool", "local_runtime"


def _clone_family_record(record: Dict[str, Any]) -> Dict[str, Any]:
    cloned = dict(record)
    cloned["canonical_tool_names"] = tuple(record.get("canonical_tool_names") or ())
    cloned["compatibility_aliases"] = tuple(record.get("compatibility_aliases") or ())
    return cloned


@lru_cache(maxsize=1)
def _builtin_family_registry_payload() -> tuple[
    Tuple[Dict[str, Any], ...],
    Dict[str, Dict[str, Any]],
    Dict[str, str],
    Dict[str, str],
]:
    alias_to_family = _compatibility_alias_to_family()
    records_by_family: Dict[str, Dict[str, Any]] = {}
    tool_name_to_family: Dict[str, str] = {}
    for metadata in build_base_capability_metadata(
        browser_runtime_actions=_mapping_runtime.BROWSER_RUNTIME_ACTIONS,
        browser_provider_actions=_mapping_runtime.BROWSER_PROVIDER_ACTIONS,
    ):
        name = _normalized_text(metadata.get("name"))
        if not name:
            continue
        canonical_family = _normalized_text(metadata.get("canonical_family")) or alias_to_family.get(name) or name
        is_alias = alias_to_family.get(name) == canonical_family or _normalized_text(
            metadata.get("model_default_exposure")
        ) == "compatibility_alias"
        if not is_alias:
            tool_name_to_family[name] = canonical_family
        record = records_by_family.setdefault(
            canonical_family,
            {
                "canonical_family": canonical_family,
                "family_source": "builtin",
                "family_owner": "builtin",
                "canonical_tool_names": [],
                "compatibility_aliases": [],
            },
        )
        if is_alias:
            if name not in record["compatibility_aliases"]:
                record["compatibility_aliases"].append(name)
            continue
        if name not in record["canonical_tool_names"]:
            record["canonical_tool_names"].append(name)
    ordered_records: list[Dict[str, Any]] = []
    records_by_name: Dict[str, Dict[str, Any]] = {}
    for family_name in sorted(records_by_family):
        record = dict(records_by_family[family_name])
        capability_kind, runtime_binding = _default_family_classification(family_name)
        record["canonical_tool_names"] = tuple(record.get("canonical_tool_names") or ())
        record["compatibility_aliases"] = tuple(record.get("compatibility_aliases") or ())
        record["tool_capability_kind"] = capability_kind
        record["tool_runtime_binding"] = runtime_binding
        ordered_records.append(record)
        records_by_name[family_name] = record
    return (
        tuple(ordered_records),
        records_by_name,
        dict(tool_name_to_family),
        dict(alias_to_family),
    )


def _tool(
    name: str,
    label: str,
    description: str,
    *,
    usage_text: str | None = None,
    provider_description: str | None = None,
    mutates_ui: bool = False,
    requires_confirmation: bool = False,
    slash_actions: Tuple[str, ...] | None = None,
    provider_actions: Tuple[str, ...] | None = None,
    model_default_exposure: str | None = None,
    **extra_metadata: Any,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "name": name,
        "label": label,
        "description": description,
        "mutates_ui": mutates_ui,
        "requires_confirmation": requires_confirmation,
    }
    if usage_text:
        metadata["usage_text"] = usage_text
    if provider_description:
        metadata["provider_description"] = provider_description
    if slash_actions:
        metadata["slash_actions"] = slash_actions
    if provider_actions:
        metadata["provider_actions"] = provider_actions
    if model_default_exposure:
        metadata["model_default_exposure"] = model_default_exposure
    if extra_metadata:
        metadata.update(extra_metadata)
    return metadata


def build_base_capability_metadata(
    *,
    browser_runtime_actions: Tuple[str, ...],
    browser_provider_actions: Tuple[str, ...],
) -> Tuple[Dict[str, Any], ...]:
    specs = _base_specs_runtime.build_base_capability_tool_specs(
        browser_runtime_actions=browser_runtime_actions,
        browser_provider_actions=browser_provider_actions,
    )
    return tuple(_tool(**spec) for spec in specs)


def builtin_canonical_family_registry() -> Tuple[Dict[str, Any], ...]:
    records, _records_by_name, _tool_name_to_family, _alias_to_family = _builtin_family_registry_payload()
    return tuple(_clone_family_record(item) for item in records)


def builtin_canonical_family_metadata(name: str) -> Dict[str, Any] | None:
    normalized = _normalized_text(name)
    if not normalized:
        return None
    _records, records_by_name, _tool_name_to_family, _alias_to_family = _builtin_family_registry_payload()
    record = records_by_name.get(normalized)
    return _clone_family_record(record) if isinstance(record, dict) else None


def builtin_canonical_family_for_tool_name(name: str) -> str:
    normalized = _normalized_text(name)
    if not normalized:
        return ""
    _records, _records_by_name, tool_name_to_family, _alias_to_family = _builtin_family_registry_payload()
    return str(tool_name_to_family.get(normalized) or "").strip()


def builtin_canonical_family_for_compatibility_alias(name: str) -> str:
    normalized = _normalized_text(name)
    if not normalized:
        return ""
    _records, _records_by_name, _tool_name_to_family, alias_to_family = _builtin_family_registry_payload()
    return str(alias_to_family.get(normalized) or "").strip()


def resolve_builtin_canonical_family(
    name: str,
    *,
    allow_compat_aliases: bool = False,
) -> Dict[str, Any] | None:
    normalized = _normalized_text(name)
    if not normalized:
        return None
    family_record = builtin_canonical_family_metadata(normalized)
    if family_record is not None:
        resolved = dict(family_record)
        resolved["resolved_from"] = "family"
        resolved["resolved_input"] = normalized
        return resolved
    family_name = builtin_canonical_family_for_tool_name(normalized)
    if family_name:
        resolved = builtin_canonical_family_metadata(family_name) or {}
        if resolved:
            resolved["resolved_from"] = "tool_name"
            resolved["resolved_input"] = normalized
            return resolved
    if allow_compat_aliases:
        family_name = builtin_canonical_family_for_compatibility_alias(normalized)
        if family_name:
            resolved = builtin_canonical_family_metadata(family_name) or {}
            if resolved:
                resolved["resolved_from"] = "compatibility_alias"
                resolved["resolved_input"] = normalized
                return resolved
    return None
