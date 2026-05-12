from __future__ import annotations

from typing import Any, Dict, Mapping

from cli.agent_cli.providers.config.catalog import (
    default_reasoning_effort_for_model,
    default_supports_reasoning_for_model,
    supported_reasoning_efforts_for_model,
)


def booleanish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def aliased_mapping_value(mapping: Mapping[str, Any], snake_key: str, camel_key: str) -> Any:
    if snake_key in mapping:
        return mapping.get(snake_key)
    if camel_key in mapping:
        return mapping.get(camel_key)
    return None


def model_hidden(item: Dict[str, Any]) -> bool:
    if "hidden" in item:
        return booleanish(item.get("hidden"))
    if "show_in_picker" in item:
        return not booleanish(item.get("show_in_picker"), default=True)
    return False


def default_model_key(
    provider_name: str,
    *,
    catalog: Any,
    default_model_entry_fn,
) -> str:
    default_model_entry = default_model_entry_fn(provider_name, catalog)
    if default_model_entry is not None:
        return str(getattr(default_model_entry, "key", "") or "").strip()
    provider_entry = getattr(catalog, "providers", {}).get(provider_name)
    return str(getattr(provider_entry, "default_model", "") or "").strip()


def public_provider_name_for_entry(
    provider_name: str,
    *,
    catalog: Any,
    provider_entry: Any,
    public_provider_name_fn,
    default_model_entry_fn,
) -> str:
    default_model_entry = default_model_entry_fn(provider_name, catalog)
    return (
        public_provider_name_fn(
            provider_name=provider_name,
            model=(default_model_entry.model_id if default_model_entry is not None else provider_entry.default_model),
            base_url=str(provider_entry.base_url or ""),
            planner_kind=str(provider_entry.planner_kind or ""),
        )
        or provider_name
    )


def normalized_local_model_item(
    *,
    catalog: Any,
    entry: Any,
    public_provider_name_fn,
    default_model_entry_fn,
) -> Dict[str, Any]:
    provider_entry = getattr(catalog, "providers", {}).get(entry.provider_name)
    public_name = (
        public_provider_name_fn(
            provider_name=entry.provider_name,
            model=entry.model_id,
            base_url=str(getattr(provider_entry, "base_url", "") or ""),
            planner_kind=str(entry.planner_kind or getattr(provider_entry, "planner_kind", "") or ""),
        )
        or entry.provider_name
    )
    raw_model = dict(getattr(entry, "raw_model", {}) or {})
    explicit_hidden = "hidden" in raw_model or "show_in_picker" in raw_model
    hidden = model_hidden(raw_model)
    if not explicit_hidden and public_name != entry.provider_name:
        hidden = True
    if not explicit_hidden and isinstance(raw_model.get("routes"), dict) and raw_model.get("routes"):
        hidden = True
    supported_reasoning_efforts = tuple(getattr(entry, "supported_reasoning_efforts", ()) or ())
    return {
        "model_key": entry.key,
        "provider_name": public_name,
        "config_provider_name": entry.provider_name,
        "model_id": entry.model_id,
        "display_name": entry.display_name or entry.model_id,
        "planner_kind": entry.planner_kind or "-",
        "wire_api": entry.wire_api or "-",
        "supports_tools": str(entry.supports_tools).lower(),
        "supports_reasoning": str(entry.supports_reasoning).lower(),
        "supported_reasoning_efforts": list(supported_reasoning_efforts),
        "default_reasoning_effort": str(getattr(entry, "default_reasoning_effort", "") or "").strip(),
        "hidden": hidden,
        "_source": "local",
        "_default_model": entry.key == default_model_key(
            entry.provider_name,
            catalog=catalog,
            default_model_entry_fn=default_model_entry_fn,
        ),
        "_public_provider_exact": public_name == entry.provider_name,
        "_explicit_show_in_picker": "show_in_picker" in raw_model
        and booleanish(raw_model.get("show_in_picker"), default=True),
    }


def normalized_remote_model_item(
    *,
    catalog: Any,
    provider_name: str,
    remote_item: Dict[str, Any],
    public_provider_name_fn,
    default_model_entry_fn,
) -> Dict[str, Any] | None:
    model_key = str(remote_item.get("model_key") or remote_item.get("key") or "").strip()
    model_id = str(remote_item.get("model_id") or remote_item.get("model") or "").strip()
    if not model_key or not model_id:
        return None
    provider_entry = getattr(catalog, "providers", {}).get(provider_name)
    public_name = (
        public_provider_name_fn(
            provider_name=provider_name,
            model=model_id,
            base_url=str(getattr(provider_entry, "base_url", "") or ""),
            planner_kind=str(
                remote_item.get("planner_kind")
                or getattr(provider_entry, "planner_kind", "")
                or "-"
            ),
        )
        or provider_name
    )
    explicit_hidden = "hidden" in remote_item or "show_in_picker" in remote_item
    hidden = model_hidden(remote_item)
    if not explicit_hidden and public_name != provider_name:
        hidden = True
    if not explicit_hidden and isinstance(remote_item.get("routes"), dict) and remote_item.get("routes"):
        hidden = True
    supports_reasoning = default_supports_reasoning_for_model(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=remote_item.get("supports_reasoning"),
        supported_reasoning_efforts=aliased_mapping_value(
            remote_item, "supported_reasoning_efforts", "supportedReasoningEfforts"
        ),
        default_reasoning_effort=aliased_mapping_value(
            remote_item, "default_reasoning_effort", "defaultReasoningEffort"
        ),
    )
    supported_reasoning_efforts = supported_reasoning_efforts_for_model(
        provider_name=provider_name,
        model_id=model_id,
        supports_reasoning=remote_item.get("supports_reasoning"),
        supported_reasoning_efforts=aliased_mapping_value(
            remote_item, "supported_reasoning_efforts", "supportedReasoningEfforts"
        ),
        default_reasoning_effort=aliased_mapping_value(
            remote_item, "default_reasoning_effort", "defaultReasoningEffort"
        ),
    )
    default_reasoning_effort = default_reasoning_effort_for_model(
        provider_name=provider_name,
        model_id=model_id,
        planner_kind=str(remote_item.get("planner_kind") or ""),
        wire_api=str(remote_item.get("wire_api") or ""),
        supports_reasoning=remote_item.get("supports_reasoning"),
        supported_reasoning_efforts=supported_reasoning_efforts,
        default_reasoning_effort=aliased_mapping_value(
            remote_item, "default_reasoning_effort", "defaultReasoningEffort"
        ),
    )
    return {
        "model_key": model_key,
        "provider_name": public_name,
        "config_provider_name": provider_name,
        "model_id": model_id,
        "display_name": str(remote_item.get("display_name") or model_id),
        "planner_kind": str(remote_item.get("planner_kind") or "-"),
        "wire_api": str(remote_item.get("wire_api") or "-"),
        "supports_tools": str(remote_item.get("supports_tools", True)).lower(),
        "supports_reasoning": str(bool(supports_reasoning)).lower(),
        "supported_reasoning_efforts": list(supported_reasoning_efforts),
        "default_reasoning_effort": default_reasoning_effort,
        "hidden": hidden,
        "_source": "remote",
        "_default_model": model_key == default_model_key(
            provider_name,
            catalog=catalog,
            default_model_entry_fn=default_model_entry_fn,
        ),
        "_public_provider_exact": public_name == provider_name,
        "_explicit_show_in_picker": "show_in_picker" in remote_item
        and booleanish(remote_item.get("show_in_picker"), default=True),
    }


def picker_priority(item: Dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    return (
        1 if bool(item.get("_explicit_show_in_picker")) else 0,
        1 if bool(item.get("_default_model")) else 0,
        1 if bool(item.get("_public_provider_exact")) else 0,
        1 if str(item.get("_source") or "") == "local" else 0,
        -len(str(item.get("model_key") or "")),
        str(item.get("model_key") or ""),
    )


def strip_private_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if not str(key).startswith("_")}
