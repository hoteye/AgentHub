from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping


def normalized_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_key(value: Any) -> str:
    return normalized_text(value).lower()


def planner_signature(planner: Any) -> tuple[str, str, str, str, str]:
    if planner is None:
        return ("", "", "", "", "")
    public_summary = getattr(planner, "public_summary", None)
    if not callable(public_summary):
        return ("", "", "", "", "")
    try:
        summary = dict(public_summary() or {})
    except Exception:
        return ("", "", "", "", "")
    return (
        normalized_text(summary.get("provider_name")),
        normalized_text(summary.get("model")),
        normalized_text(summary.get("model_key")),
        normalized_text(summary.get("planner_kind")),
        normalized_text(summary.get("base_url")),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_target_from_item(item: Mapping[str, Any]) -> Dict[str, Any] | None:
    provider_name = normalized_text(item.get("config_provider_name") or item.get("provider_name"))
    model = normalized_text(item.get("provider_default_model_id") or item.get("default_model"))
    if not provider_name or not model:
        return None
    return {
        "provider_name": provider_name,
        "model": model,
        "provider_public_name": normalized_text(item.get("provider_name")),
        "provider_auth_ready": bool(item.get("provider_auth_ready")),
        "provider_base_eligible": bool(item.get("provider_base_eligible")),
        "availability_status": normalized_key(item.get("availability_status")),
        "provider_status_state": normalized_key(item.get("provider_status_state")),
    }


def deduped_probe_targets(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    deduped: dict[tuple[str, str], Dict[str, Any]] = {}
    for item in items:
        probe_target = probe_target_from_item(item)
        if probe_target is None:
            continue
        if not probe_target["provider_auth_ready"] or not probe_target["provider_base_eligible"]:
            continue
        key = (normalized_key(probe_target["provider_name"]), normalized_key(probe_target["model"]))
        if key not in deduped:
            deduped[key] = probe_target
    return list(deduped.values())


def target_key(target: Mapping[str, Any]) -> tuple[str, str]:
    return (normalized_key(target.get("provider_name")), normalized_key(target.get("model")))
