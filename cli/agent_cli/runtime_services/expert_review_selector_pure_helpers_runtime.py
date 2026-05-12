from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def boolish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def normalized_provider_key(value: Any) -> str:
    return str(value or "").strip().lower()


def first_present(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        return value
    return default


def provider_identity_fields(item: Mapping[str, Any]) -> Dict[str, str]:
    config_name = str(item.get("config_provider_name") or item.get("provider_name") or "").strip()
    public_name = str(item.get("provider_name") or item.get("display_name") or config_name).strip()
    return {
        "config_provider_name": config_name,
        "provider_name": public_name,
        "_config_provider_key": normalized_provider_key(config_name),
        "_provider_key": normalized_provider_key(public_name),
    }


def deduped_provider_items(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    deduped: dict[tuple[str, str], Dict[str, Any]] = {}
    for raw_item in items:
        item = dict(raw_item or {})
        identity = provider_identity_fields(item)
        item.update(identity)
        dedupe_key = (
            identity["_config_provider_key"] or identity["_provider_key"],
            identity["_provider_key"] or identity["_config_provider_key"],
        )
        if dedupe_key not in deduped:
            deduped[dedupe_key] = item
    return list(deduped.values())


def resolved_vendor_name(
    candidate_names: Iterable[Any],
    *,
    vendor_for_name_fn: Callable[[str], Any] | None,
) -> str:
    if vendor_for_name_fn is None:
        return ""
    for candidate in candidate_names:
        candidate_name = str(candidate or "").strip()
        if not candidate_name:
            continue
        try:
            vendor = vendor_for_name_fn(candidate_name)
        except Exception:
            vendor = None
        vendor_name = str(getattr(vendor, "name", "") or "").strip().lower()
        if vendor_name:
            return vendor_name
    return ""


def available_reviewer_candidate(item: Mapping[str, Any]) -> bool:
    return boolish(item.get("provider_base_eligible"))
