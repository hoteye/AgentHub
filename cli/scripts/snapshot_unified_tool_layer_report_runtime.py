from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from cli.scripts.script_runtime_helpers import (
    normalize_optional_provider_home_override,
    resolve_effective_script_provider_home_dir,
)

CLI_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _temporary_env(name: str, value: str) -> Iterator[None]:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        yield
        return
    previous = os.environ.get(name)
    os.environ[name] = normalized_value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _provider_home_report_fields(
    provider_home: str,
    *,
    resolve_provider_home_dir_fn=resolve_effective_script_provider_home_dir,
) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_provider_home_dir_fn(
                cwd=CLI_ROOT,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": (
            "explicit_override" if normalized_provider_home else "runtime_default"
        ),
    }


def _function_name_from_spec(spec: Any) -> str:
    if not isinstance(spec, dict):
        return ""
    function_block = spec.get("function")
    if isinstance(function_block, dict):
        function_name = str(function_block.get("name") or "").strip()
        if function_name:
            return function_name
    return str(spec.get("name") or "").strip()


def _spec_type(spec: Any) -> str:
    if not isinstance(spec, dict):
        return ""
    return str(spec.get("type") or "").strip()


def _ordered_unique(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _record_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return dict(asdict(value))
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        return {str(key): item for key, item in data.items() if not str(key).startswith("_")}
    return {}


def _web_search_mode_matrix(native_capability: Any) -> dict[str, Any]:
    return {
        "backend_id": str(getattr(native_capability, "selected_backend", "") or "").strip(),
        "configurable_modes": list(getattr(native_capability, "configurable_modes", ()) or []),
        "supported_modes": list(getattr(native_capability, "supported_modes", ()) or []),
        "default_mode": str(getattr(native_capability, "default_mode", "") or "").strip(),
        "requested_mode": str(getattr(native_capability, "requested_mode", "") or "").strip(),
        "effective_mode": str(getattr(native_capability, "effective_mode", "") or "").strip(),
        "mode_resolution": str(getattr(native_capability, "mode_resolution", "") or "").strip(),
        "mode_source": str(getattr(native_capability, "mode_source", "") or "").strip(),
        "mode_binding": str(getattr(native_capability, "mode_binding", "") or "").strip(),
        "mode_support_level": str(
            getattr(native_capability, "mode_support_level", "") or ""
        ).strip(),
        "cached_live_distinct": bool(getattr(native_capability, "cached_live_distinct", False)),
        "mode_fallback_semantics": str(
            getattr(native_capability, "mode_fallback_semantics", "") or ""
        ).strip(),
        "backend_notes": str(getattr(native_capability, "backend_notes", "") or "").strip(),
    }


def _web_search_surface_projection(specs: list[dict[str, Any]]) -> dict[str, Any]:
    for item in list(specs or []):
        if _function_name_from_spec(item) != "web_search":
            continue
        projection: dict[str, Any] = {
            "name": "web_search",
            "type": _spec_type(item),
        }
        if "external_web_access" in item:
            projection["external_web_access"] = bool(item.get("external_web_access"))
        if "max_uses" in item:
            try:
                projection["max_uses"] = int(item.get("max_uses"))
            except (TypeError, ValueError):
                projection["max_uses"] = item.get("max_uses")
        if isinstance(item.get("web_search"), dict):
            projection["web_search"] = dict(item.get("web_search") or {})
        if isinstance(item.get("function"), dict):
            projection["function_name"] = str(
                (item.get("function") or {}).get("name") or ""
            ).strip()
        if isinstance(item.get("input_schema"), dict):
            projection["input_schema_keys"] = sorted(
                str(key) for key in dict(item.get("input_schema") or {}).keys()
            )
        return projection
    return {}


def _canonical_inventory() -> list[dict[str, Any]]:
    from cli.agent_cli.providers.tool_specs import canonical_tool_registry

    rows: list[dict[str, Any]] = []
    for item in canonical_tool_registry():
        if not isinstance(item, dict):
            continue
        metadata = dict(item.get("metadata") or {})
        capability = dict(item.get("capability") or {})
        rows.append(
            {
                "name": str(item.get("name") or "").strip(),
                "label": str(metadata.get("label") or capability.get("label") or "").strip(),
                "description": str(
                    metadata.get("description") or capability.get("description") or ""
                ).strip(),
                "provider_description": str(item.get("provider_description") or "").strip(),
                "usage_text": str(metadata.get("usage_text") or "").strip(),
                "model_default_exposure": str(metadata.get("model_default_exposure") or "").strip(),
                "compatibility_alias_for": str(
                    metadata.get("compatibility_alias_for") or ""
                ).strip(),
                "provider_actions": list(item.get("provider_actions") or []),
                "command_actions": list(item.get("command_actions") or []),
            }
        )
    return rows


def _alias_exposure_snapshot(*, exposed_names: set[str]) -> dict[str, Any]:
    from cli.agent_cli.providers import tool_family_mapping_runtime as mapping

    def _group(name: str, canonical: tuple[str, ...], aliases: tuple[str, ...]) -> dict[str, Any]:
        exposed_aliases = [alias for alias in aliases if alias in exposed_names]
        return {
            "group": name,
            "canonical": list(canonical),
            "compatibility_aliases": list(aliases),
            "exposed_aliases": exposed_aliases,
            "hidden_aliases": [alias for alias in aliases if alias not in exposed_names],
            "missing_canonical": [
                tool_name for tool_name in canonical if tool_name not in exposed_names
            ],
            "alias_hidden_by_default": len(exposed_aliases) == 0,
        }

    return {
        "hidden_aliases_ordered": list(mapping.MODEL_HIDDEN_BUILTIN_COMPAT_ALIASES),
        "file_tools": _group(
            "file_tools", mapping.FILE_TOOL_CANONICAL_TRIO, mapping.FILE_TOOL_COMPAT_ALIASES
        ),
        "shell_tools": _group(
            "shell_tools", mapping.SHELL_TOOL_CANONICAL_APIS, mapping.SHELL_TOOL_COMPAT_ALIASES
        ),
        "browser_tools": _group(
            "browser_tools",
            mapping.BROWSER_TOOL_CANONICAL_PRIMARY,
            mapping.BROWSER_TOOL_COMPAT_ALIASES,
        ),
    }


def _case_snapshot(
    case: Any,
    *,
    provider_home: str,
    resolve_provider_home_dir_fn=resolve_effective_script_provider_home_dir,
) -> dict[str, Any]:
    from cli.agent_cli.host_platform import current_host_platform
    from cli.agent_cli.provider import load_provider_config
    from cli.agent_cli.providers.tool_specs import (
        merged_provider_tool_specs,
        provider_tool_names,
        responses_minimal_provider_tool_specs,
    )
    from cli.agent_cli.tools_core.tool_capabilities import (
        DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME,
        utc_now_iso,
        web_search_probe_cache_key,
    )
    from cli.agent_cli.tools_core.tool_capability_resolver import (
        WebSearchResolverInput,
        resolve_native_web_search_capability,
        resolve_web_search_capability,
    )

    payload: dict[str, Any] = {
        "case": case.label,
        "provider": case.provider,
        "model": case.model,
        "checked_at": utc_now_iso(),
        "status": "ok",
        **_provider_home_report_fields(
            provider_home,
            resolve_provider_home_dir_fn=resolve_provider_home_dir_fn,
        ),
    }
    provider_home_override = normalize_optional_provider_home_override(provider_home)

    config = load_provider_config(
        cwd=CLI_ROOT,
        env_overrides=case.env_overrides(provider_home=provider_home_override),
    )
    if config is None:
        payload["status"] = "error"
        payload["issue"] = "load_provider_config returned no config"
        return payload

    host_platform = current_host_platform()
    merged_specs = merged_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    minimal_specs = responses_minimal_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    model_tool_names = provider_tool_names(
        config,
        host_platform,
        plugin_manager_factory=lambda: None,
    )

    merged_tools = [
        {
            "name": _function_name_from_spec(item),
            "type": _spec_type(item),
        }
        for item in merged_specs
        if _function_name_from_spec(item)
    ]
    minimal_tools = _ordered_unique(
        [_function_name_from_spec(item) for item in minimal_specs if _function_name_from_spec(item)]
    )
    merged_tool_names = _ordered_unique(
        [str(item.get("name") or "").strip() for item in merged_tools]
    )
    exposed_name_set = set(merged_tool_names)
    probe_cache_default_path = (
        Path(str(payload.get("provider_home") or "")).expanduser()
        / DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME
    )

    with _temporary_env("AGENTHUB_WEB_SEARCH_PROBE_CACHE", str(probe_cache_default_path)):
        capability = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name=str(config.provider_name or "").strip(),
                model=str(config.model or "").strip(),
                wire_api=str(config.wire_api or "").strip(),
                planner_kind=str(config.planner_kind or "").strip(),
            )
        )
        native_capability = resolve_native_web_search_capability(config)
    probe_cache_key = web_search_probe_cache_key(
        provider_name=str(config.provider_name or "").strip(),
        model=str(config.model or "").strip(),
        wire_api=str(config.wire_api or "").strip(),
        planner_kind=str(config.planner_kind or "").strip(),
    )

    payload.update(
        {
            "provider_config": config.public_summary(),
            "provider_tool_names": list(model_tool_names),
            "provider_merged_tools": merged_tools,
            "provider_minimal_tools": minimal_tools,
            "capability_discovery_snapshot": {"web_search": _record_dict(capability)},
            "native_capability_snapshot": {"web_search": _record_dict(native_capability)},
            "web_search_mode_matrix": _web_search_mode_matrix(native_capability),
            "provider_web_search_surface": {
                "merged": _web_search_surface_projection(merged_specs),
                "minimal": _web_search_surface_projection(minimal_specs),
            },
            "web_search_probe_cache": {
                "cache_key": probe_cache_key.as_lookup_key(),
                "cache_default_path": str(probe_cache_default_path),
                "cache_hit": str(getattr(capability, "decision_source", "") or "").strip()
                == "probe_cache",
                "cache_status": str(getattr(capability, "cache_status", "") or "").strip(),
                "cache_expires_at": str(getattr(capability, "cache_expires_at", "") or "").strip(),
                "cache_source": str(getattr(capability, "cache_source", "") or "").strip(),
            },
            "compatibility_alias_exposure_snapshot": _alias_exposure_snapshot(
                exposed_names=exposed_name_set
            ),
        }
    )
    return payload
