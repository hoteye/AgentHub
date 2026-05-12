from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from cli.agent_cli import agent_provider_catalog_normalization_helpers_runtime as _normalization_helpers
from cli.agent_cli.providers.availability_models import DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS
from cli.agent_cli.providers.provider_status_management_runtime import provider_catalog_entry_status_fields

_model_hidden = _normalization_helpers.model_hidden
_normalized_local_model_item = _normalization_helpers.normalized_local_model_item
_normalized_remote_model_item = _normalization_helpers.normalized_remote_model_item
_picker_priority = _normalization_helpers.picker_priority
_public_provider_name_for_entry = _normalization_helpers.public_provider_name_for_entry
_strip_private_fields = _normalization_helpers.strip_private_fields


def available_provider_items(
    catalog: Any,
    *,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
    env_mapping: Mapping[str, Any] | None = None,
    auth_data: Mapping[str, Any] | None = None,
    auth_path: Path | None = None,
    availability_registry: Any | None = None,
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
) -> List[Dict[str, str]]:
    deduped: Dict[str, Dict[str, str]] = {}
    for provider_name, entry in catalog.providers.items():
        default_model_entry = default_model_entry_fn(provider_name, catalog)
        public_name = _public_provider_name_for_entry(
            provider_name,
            catalog=catalog,
            provider_entry=entry,
            public_provider_name_fn=public_provider_name_fn,
            default_model_entry_fn=default_model_entry_fn,
        )
        default_model = (
            (default_model_entry.key if default_model_entry is not None else "")
            or entry.default_model
            or "-"
        )
        existing = deduped.get(public_name)
        item = {
            "provider_name": public_name,
            "config_provider_name": provider_name,
            "display_name": public_name,
            "base_url": entry.base_url or "-",
            "planner_kind": (
                entry.planner_kind
                or str(getattr(vendor_for_name_fn(public_name), "default_protocol_family", "") or "")
                or "-"
            ),
            "wire_api": entry.wire_api or "-",
            "default_model": default_model,
            "api_key_env": entry.api_key_env or "-",
        }
        if env_mapping is not None or auth_data is not None or availability_registry is not None:
            item.update(
                provider_catalog_entry_status_fields(
                    provider_name=provider_name,
                    provider_entry=entry,
                    default_model_entry=default_model_entry,
                    env_mapping=env_mapping,
                    auth_data=auth_data,
                    auth_path=auth_path,
                    availability_registry=availability_registry,
                    stale_after_seconds=stale_after_seconds,
                )
            )
        if existing is None or existing.get("config_provider_name") != public_name:
            deduped[public_name] = item
    return sorted(deduped.values(), key=lambda item: item["provider_name"])


def resolve_model_provider_filter(
    filter_name: str,
    *,
    catalog: Any,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
) -> str | None:
    if not filter_name:
        return None
    if filter_name in catalog.providers:
        return filter_name
    filter_vendor = vendor_for_name_fn(filter_name)
    if filter_vendor is None:
        return None
    matching = [
        key
        for key, entry in catalog.providers.items()
        if _public_provider_name_for_entry(
            key,
            catalog=catalog,
            provider_entry=entry,
            public_provider_name_fn=public_provider_name_fn,
            default_model_entry_fn=default_model_entry_fn,
        )
        == filter_vendor.name
    ]
    if len(matching) == 1:
        return matching[0]
    return None


def available_model_items(
    catalog: Any,
    *,
    provider_name: str | None,
    include_hidden: bool = False,
    remote_model_items_by_provider: Dict[str, List[Dict[str, Any]]] | None = None,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
) -> List[Dict[str, str]]:
    items: List[Dict[str, Any]] = []
    resolved_filter = resolve_model_provider_filter(
        str(provider_name or "").strip(),
        catalog=catalog,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
    )
    for entry in catalog.models.values():
        if resolved_filter and entry.provider_name != resolved_filter:
            continue
        items.append(
            _normalized_local_model_item(
                catalog=catalog,
                entry=entry,
                public_provider_name_fn=public_provider_name_fn,
                default_model_entry_fn=default_model_entry_fn,
            )
        )
    local_keys = {
        (
            str(item.get("config_provider_name") or "").strip(),
            str(item.get("model_key") or "").strip(),
            str(item.get("model_id") or "").strip(),
        )
        for item in items
    }
    for remote_provider_name, remote_items in dict(remote_model_items_by_provider or {}).items():
        if resolved_filter and remote_provider_name != resolved_filter:
            continue
        for remote_item in list(remote_items or []):
            if not isinstance(remote_item, dict):
                continue
            normalized = _normalized_remote_model_item(
                catalog=catalog,
                provider_name=remote_provider_name,
                remote_item=remote_item,
                public_provider_name_fn=public_provider_name_fn,
                default_model_entry_fn=default_model_entry_fn,
            )
            if normalized is None:
                continue
            model_key = str(normalized.get("model_key") or "").strip()
            model_id = str(normalized.get("model_id") or "").strip()
            dedupe_key = (remote_provider_name, model_key, model_id)
            if dedupe_key in local_keys:
                continue
            items.append(normalized)
    if include_hidden:
        return [
            _strip_private_fields(item)
            for item in sorted(items, key=lambda item: (str(item["provider_name"]), str(item["model_key"])))
        ]
    visible_items = [item for item in items if not _model_hidden(item)]
    deduped: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in visible_items:
        dedupe_key = (str(item.get("provider_name") or ""), str(item.get("model_id") or ""))
        existing = deduped.get(dedupe_key)
        if existing is None or _picker_priority(item) > _picker_priority(existing):
            deduped[dedupe_key] = item
    return [
        _strip_private_fields(item)
        for item in sorted(deduped.values(), key=lambda item: (str(item["provider_name"]), str(item["model_key"])))
    ]


def resolve_switch_provider_entry(
    provider_name: str,
    *,
    catalog: Any,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
) -> Any:
    resolved_provider_name = provider_name
    entry = default_model_entry_fn(resolved_provider_name, catalog)
    if entry is not None:
        return entry
    requested_vendor = vendor_for_name_fn(provider_name)
    if requested_vendor is None:
        return None
    matching_providers = [
        key
        for key, item in catalog.providers.items()
        if _public_provider_name_for_entry(
            key,
            catalog=catalog,
            provider_entry=item,
            public_provider_name_fn=public_provider_name_fn,
            default_model_entry_fn=default_model_entry_fn,
        )
        == requested_vendor.name
    ]
    if not matching_providers:
        return None
    resolved_provider_name = sorted(
        matching_providers,
        key=lambda item: (item != requested_vendor.name, item),
    )[0]
    return default_model_entry_fn(resolved_provider_name, catalog)
