from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from cli.agent_cli import agent_provider_catalog_listing_helpers_runtime as _listing_helpers
from cli.agent_cli import agent_provider_catalog_normalization_helpers_runtime as _normalization_helpers
from cli.agent_cli.providers.availability_models import DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS

_booleanish = _normalization_helpers.booleanish
_aliased_mapping_value = _normalization_helpers.aliased_mapping_value
_model_hidden = _normalization_helpers.model_hidden
_default_model_key = _normalization_helpers.default_model_key
_normalized_local_model_item = _normalization_helpers.normalized_local_model_item
_normalized_remote_model_item = _normalization_helpers.normalized_remote_model_item
_picker_priority = _normalization_helpers.picker_priority
_strip_private_fields = _normalization_helpers.strip_private_fields


def public_provider_name_for_entry(
    provider_name: str,
    *,
    catalog: Any,
    provider_entry: Any,
    public_provider_name_fn,
    default_model_entry_fn,
) -> str:
    return _normalization_helpers.public_provider_name_for_entry(
        provider_name,
        catalog=catalog,
        provider_entry=provider_entry,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
    )


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
    return _listing_helpers.available_provider_items(
        catalog,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
        env_mapping=env_mapping,
        auth_data=auth_data,
        auth_path=auth_path,
        availability_registry=availability_registry,
        stale_after_seconds=stale_after_seconds,
    )


def resolve_model_provider_filter(
    filter_name: str,
    *,
    catalog: Any,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
) -> str | None:
    return _listing_helpers.resolve_model_provider_filter(
        filter_name,
        catalog=catalog,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
    )


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
    return _listing_helpers.available_model_items(
        catalog,
        provider_name=provider_name,
        include_hidden=include_hidden,
        remote_model_items_by_provider=remote_model_items_by_provider,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
    )


def resolve_switch_provider_entry(
    provider_name: str,
    *,
    catalog: Any,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
) -> Any:
    return _listing_helpers.resolve_switch_provider_entry(
        provider_name,
        catalog=catalog,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
    )
