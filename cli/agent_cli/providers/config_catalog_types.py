from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.model_context_window_runtime import (
    configured_model_auto_compact_token_limit,
    configured_model_context_window,
    configured_model_raw_context_window,
)
from cli.agent_cli.providers.auth_schema_runtime import (
    apply_typed_auth_to_provider_block,
    provider_auth_schema,
)
from cli.agent_cli.providers.config_catalog_types_build_helpers import (
    build_provider_catalog as _build_provider_catalog_impl,
)
from cli.agent_cli.providers.config_catalog_types_build_helpers import (
    default_model_entry as _default_model_entry_impl,
)
from cli.agent_cli.providers.config_catalog_types_build_helpers import (
    find_model_entry as _find_model_entry_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    default_reasoning_effort_for_model as _default_reasoning_effort_for_model_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    default_supports_reasoning_for_model as _default_supports_reasoning_for_model_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    infer_planner_kind as _infer_planner_kind_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    normalized_reasoning_efforts as _normalized_reasoning_efforts_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    optional_bool as _optional_bool_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    read_json_file as _read_json_file_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    read_toml_file as _read_toml_file_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    reasoning_effort_supported_for_model as _reasoning_effort_supported_for_model_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    resolve_model_migration as _resolve_model_migration_impl,
)
from cli.agent_cli.providers.config_catalog_types_pure_helpers import (
    supported_reasoning_efforts_for_model as _supported_reasoning_efforts_for_model_impl,
)
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    legacy_interaction_profile_alias_diagnostics_for_config,
)
from cli.agent_cli.providers.interaction_profile_config import (
    normalize_interaction_profile,
    resolve_configured_interaction_profile,
)


@dataclass
class ProviderConfig:
    model: str
    api_key: str
    provider_name: str = ""
    model_key: str = ""
    planner_kind: str = "openai_responses"
    wire_api: str = ""
    base_url: str | None = None
    reasoning_effort: str | None = None
    source: str = "unknown"
    config_path: str | None = None
    auth_path: str | None = None
    auth_mode: str = "api_key"
    auth: dict[str, Any] = field(default_factory=dict)
    auth_status: str = ""
    token_source: str = ""
    interaction_profile: str = ""
    interaction_profile_source: str = ""
    raw_provider: dict[str, Any] = field(default_factory=dict)
    raw_model: dict[str, Any] = field(default_factory=dict)

    def public_summary(self) -> dict[str, Any]:
        model_raw_context_window = configured_model_raw_context_window(self.raw_model)
        model_context_window = configured_model_context_window(self.raw_model)
        model_auto_compact_token_limit = configured_model_auto_compact_token_limit(self.raw_model)
        summary = {
            "configured": True,
            "provider_name": self.provider_name,
            "model_key": self.model_key,
            "planner_kind": self.planner_kind,
            "wire_api": self.wire_api,
            "model": self.model,
            "base_url": self.base_url,
            "reasoning_effort": self.reasoning_effort,
            "source": self.source,
            "config_path": self.config_path,
            "auth_path": self.auth_path,
            "auth_mode": self.auth_mode,
            "auth": dict(self.auth),
            "auth_status": self.auth_status,
            "token_source": self.token_source,
            "interaction_profile": self.interaction_profile,
            "interaction_profile_source": self.interaction_profile_source,
            "no_auth_guardrail_reason": str(
                self.raw_provider.get("no_auth_guardrail_reason") or ""
            ).strip()
            or "-",
            "no_auth_guardrail_pass": str(
                self.raw_provider.get("no_auth_guardrail_pass") or ""
            ).strip()
            or "false",
        }
        if model_raw_context_window > 0:
            summary["model_raw_context_window"] = model_raw_context_window
        if model_context_window > 0:
            summary["model_context_window"] = model_context_window
        if model_auto_compact_token_limit > 0:
            summary["model_auto_compact_token_limit"] = model_auto_compact_token_limit
        legacy_alias = legacy_interaction_profile_alias_diagnostics_for_config(self)
        if legacy_alias:
            summary["interaction_profile_legacy_alias"] = legacy_alias
        return summary


@dataclass
class ProviderPathResolution:
    config_path: Path
    auth_path: Path
    config_exists: bool
    auth_exists: bool
    used_project_local: bool


@dataclass
class ProviderCatalogEntry:
    provider_name: str
    display_name: str = ""
    base_url: str | None = None
    api_key_env: str = ""
    auth_mode: str = "api_key"
    auth: dict[str, Any] = field(default_factory=dict)
    planner_kind: str = ""
    wire_api: str = ""
    interaction_profile: str = ""
    default_model: str = ""
    raw_provider: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelCatalogEntry:
    key: str
    provider_name: str
    model_id: str
    display_name: str = ""
    planner_kind: str = ""
    wire_api: str = ""
    interaction_profile: str = ""
    supports_tools: bool = True
    supports_reasoning: bool = False
    supported_reasoning_efforts: tuple[str, ...] = ()
    default_reasoning_effort: str = ""
    reasoning_mode: str = ""
    reasoning_output_field: str = ""
    raw_model: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCatalog:
    providers: dict[str, ProviderCatalogEntry] = field(default_factory=dict)
    models: dict[str, ModelCatalogEntry] = field(default_factory=dict)


def resolve_model_migration(
    selector: str,
    toml_data: Mapping[str, Any],
) -> str:
    return _resolve_model_migration_impl(selector, toml_data)


def read_json_file(path: Path) -> dict[str, Any]:
    return _read_json_file_impl(path)


def read_toml_file(path: Path) -> dict[str, Any]:
    return _read_toml_file_impl(path)


def optional_bool(value: Any, default: bool = False) -> bool:
    return _optional_bool_impl(value, default)


def infer_planner_kind(
    provider_name: str, model: str, base_url: str | None, provider_block: dict[str, Any]
) -> str:
    return _infer_planner_kind_impl(provider_name, model, base_url, provider_block)


def normalized_reasoning_efforts(value: Any) -> tuple[str, ...]:
    return _normalized_reasoning_efforts_impl(value)


def default_supports_reasoning_for_model(
    *,
    provider_name: str,
    model_id: str,
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
) -> bool:
    return _default_supports_reasoning_for_model_impl(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
    )


def supported_reasoning_efforts_for_model(
    *,
    provider_name: str,
    model_id: str,
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
) -> tuple[str, ...]:
    return _supported_reasoning_efforts_for_model_impl(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
        default_supports_reasoning_for_model_fn=default_supports_reasoning_for_model,
    )


def default_reasoning_effort_for_model(
    *,
    provider_name: str,
    model_id: str,
    interaction_profile: str = "",
    planner_kind: str = "",
    wire_api: str = "",
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
) -> str:
    return _default_reasoning_effort_for_model_impl(
        provider_name=provider_name,
        model_id=model_id,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
        supported_reasoning_efforts_for_model_fn=supported_reasoning_efforts_for_model,
    )


def reasoning_effort_supported_for_model(
    reasoning_effort: str,
    *,
    provider_name: str,
    model_id: str,
    interaction_profile: str = "",
    planner_kind: str = "",
    wire_api: str = "",
    supports_reasoning: Any = None,
    reasoning_mode: str = "",
    reasoning_output_field: str = "",
    supported_reasoning_efforts: Any = None,
    default_reasoning_effort: Any = None,
) -> bool:
    return _reasoning_effort_supported_for_model_impl(
        reasoning_effort,
        provider_name=provider_name,
        model_id=model_id,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
        supports_reasoning=supports_reasoning,
        reasoning_mode=reasoning_mode,
        reasoning_output_field=reasoning_output_field,
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=default_reasoning_effort,
        supported_reasoning_efforts_for_model_fn=supported_reasoning_efforts_for_model,
    )


def build_provider_catalog(
    toml_data: dict[str, Any],
    *,
    optional_bool_fn: Callable[[Any, bool], bool] = optional_bool,
    infer_planner_kind_fn: Callable[
        [str, str, str | None, dict[str, Any]], str
    ] = infer_planner_kind,
) -> ProviderCatalog:
    return _build_provider_catalog_impl(
        toml_data,
        provider_catalog_factory=ProviderCatalog,
        provider_catalog_entry_factory=ProviderCatalogEntry,
        model_catalog_entry_factory=ModelCatalogEntry,
        apply_typed_auth_to_provider_block_fn=apply_typed_auth_to_provider_block,
        provider_auth_schema_fn=provider_auth_schema,
        resolve_configured_interaction_profile_fn=resolve_configured_interaction_profile,
        normalize_interaction_profile_fn=normalize_interaction_profile,
        resolve_model_migration_fn=resolve_model_migration,
        default_supports_reasoning_for_model_fn=default_supports_reasoning_for_model,
        supported_reasoning_efforts_for_model_fn=supported_reasoning_efforts_for_model,
        default_reasoning_effort_for_model_fn=default_reasoning_effort_for_model,
        find_model_entry_fn=find_model_entry,
        optional_bool_fn=optional_bool_fn,
        infer_planner_kind_fn=infer_planner_kind_fn,
    )


def find_model_entry(
    selector: str,
    catalog: ProviderCatalog,
    *,
    preferred_provider: str | None = None,
) -> ModelCatalogEntry | None:
    return _find_model_entry_impl(selector, catalog, preferred_provider=preferred_provider)


def default_model_entry(provider_name: str, catalog: ProviderCatalog) -> ModelCatalogEntry | None:
    return _default_model_entry_impl(
        provider_name,
        catalog,
        find_model_entry_fn=find_model_entry,
    )
