from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

from cli.agent_cli.providers.availability_projection import get_availability_registry
from cli.agent_cli.providers.provider_status_management_runtime import failure_code_is_soft
from cli.agent_cli.runtime_services.provider_availability_refresh_pure_helpers_runtime import (
    deduped_probe_targets,
    normalized_key,
    normalized_text,
    target_key,
)


def target_is_stale(runtime: Any, controller: Any, target: Mapping[str, Any]) -> bool:
    registry = get_availability_registry(runtime)
    if registry is None:
        return False
    is_stale = getattr(registry, "is_stale", None)
    if not callable(is_stale):
        return False
    try:
        return bool(
            is_stale(
                str(target.get("provider_name") or ""),
                str(target.get("model") or ""),
                ttl=controller.stale_after,
            )
        )
    except Exception:
        return False


def select_probe_targets(
    runtime: Any,
    controller: Any,
    *,
    provider_items: list[Mapping[str, Any]],
    only_stale: bool,
) -> list[Dict[str, Any]]:
    probe_targets = deduped_probe_targets(provider_items)
    if not only_stale:
        return probe_targets
    return [target for target in probe_targets if target_is_stale(runtime, controller, target)]


def start_schedule(
    controller: Any,
    probe_targets: list[Mapping[str, Any]],
    *,
    reason: str,
    now_iso_fn: Callable[[], str],
) -> Dict[str, Any]:
    started: list[Dict[str, Any]] = []
    skipped_inflight = 0
    with controller.lock:
        controller.last_schedule_reason = normalized_text(reason) or "-"
        controller.last_schedule_target_count = len(probe_targets)
        controller.last_schedule_started_at = now_iso_fn()
        controller.last_schedule_started_count = 0
        controller.last_schedule_skipped_inflight_count = 0
        controller.last_error = ""
        for target in probe_targets:
            key = target_key(target)
            if key in controller.inflight_targets:
                skipped_inflight += 1
                continue
            controller.inflight_targets.add(key)
            started.append(dict(target))
        controller.last_schedule_started_count = len(started)
        controller.last_schedule_skipped_inflight_count = skipped_inflight
    return {
        "started": started,
        "skipped_inflight_count": skipped_inflight,
    }


def probe_target(runtime: Any, target: Mapping[str, Any], *, retry_soft_failures: bool) -> Dict[str, Any]:
    probe_fn = getattr(getattr(runtime, "agent", None), "probe_provider", None)
    if not callable(probe_fn):
        return {"probe_status": "unavailable", "probe_failure_code": "probe_not_supported"}

    result = dict(
        probe_fn(
            provider_name=str(target.get("provider_name") or "") or None,
            model=str(target.get("model") or "") or None,
            writeback_availability=True,
        )
        or {}
    )
    failure_code = normalized_key(result.get("probe_failure_code"))
    if (
        retry_soft_failures
        and str(result.get("probe_status") or "").strip().lower() != "available"
        and failure_code_is_soft(failure_code)
    ):
        result = dict(
            probe_fn(
                provider_name=str(target.get("provider_name") or "") or None,
                model=str(target.get("model") or "") or None,
                writeback_availability=True,
            )
            or {}
        )
    return result
