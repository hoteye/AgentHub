from __future__ import annotations

from typing import Any, Dict, Mapping


def provider_items(runtime: Any) -> list[Dict[str, Any]]:
    getter = getattr(getattr(runtime, "agent", None), "available_providers", None)
    if not callable(getter):
        return []
    try:
        items = list(getter() or [])
    except Exception:
        return []
    return [dict(item or {}) for item in items if isinstance(item, Mapping)]


def refresh_controller_surface_payload(controller: Any) -> Dict[str, Any]:
    with controller.lock:
        return {
            "provider_probe_target_count": int(controller.last_schedule_target_count or 0),
            "provider_probe_in_flight_count": len(controller.inflight_targets),
            "provider_probe_last_reason": controller.last_schedule_reason or "-",
            "provider_probe_last_started_at": controller.last_schedule_started_at or "",
            "provider_probe_last_completed_at": controller.last_completed_at or "",
            "provider_probe_last_error": controller.last_error or "",
            "provider_probe_stale_after_seconds": int(controller.stale_after_seconds or 0),
        }
