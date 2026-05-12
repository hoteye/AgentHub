from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import threading
from typing import Any, Dict

from cli.agent_cli.providers.availability_models import (
    DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
)
from cli.agent_cli.providers.availability_feature_config_runtime import provider_availability_feature_settings
from cli.agent_cli.runtime_services.provider_availability_refresh_decision_helpers_runtime import (
    probe_target,
    select_probe_targets,
    start_schedule,
)
from cli.agent_cli.runtime_services.provider_availability_refresh_projection_helpers_runtime import (
    provider_items,
    refresh_controller_surface_payload,
)
from cli.agent_cli.runtime_services.provider_availability_refresh_pure_helpers_runtime import (
    now_iso,
    planner_signature,
    target_key,
)


_REFRESH_CONTROLLER_ATTRS = (
    "_provider_availability_refresh_controller",
    "provider_availability_refresh_controller",
)


@dataclass(slots=True)
class ProviderAvailabilityRefreshController:
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    inflight_targets: set[tuple[str, str]] = field(default_factory=set, repr=False)
    last_schedule_reason: str = ""
    last_schedule_target_count: int = 0
    last_schedule_started_count: int = 0
    last_schedule_skipped_inflight_count: int = 0
    last_schedule_started_at: str = ""
    last_completed_at: str = ""
    last_error: str = ""

    @property
    def stale_after(self) -> timedelta:
        return timedelta(seconds=max(0, int(self.stale_after_seconds or 0)))


def get_refresh_controller(owner: Any) -> ProviderAvailabilityRefreshController | None:
    for attr_name in _REFRESH_CONTROLLER_ATTRS:
        controller = getattr(owner, attr_name, None)
        if controller is not None:
            return controller
    return None


def attach_refresh_controller(owner: Any, controller: ProviderAvailabilityRefreshController | None) -> None:
    for attr_name in _REFRESH_CONTROLLER_ATTRS:
        setattr(owner, attr_name, controller)


def build_refresh_controller(
    *,
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
) -> ProviderAvailabilityRefreshController:
    return ProviderAvailabilityRefreshController(
        stale_after_seconds=max(0, int(stale_after_seconds or DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS))
    )


def _refresh_config_owner(owner: Any) -> Any:
    agent = getattr(owner, "agent", None)
    return agent if agent is not None else owner


def _sync_controller_stale_after_seconds(owner: Any, controller: ProviderAvailabilityRefreshController) -> int:
    settings = provider_availability_feature_settings(_refresh_config_owner(owner))
    stale_after_seconds = max(
        1,
        int(settings.get("stale_after_seconds") or DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS),
    )
    with controller.lock:
        controller.stale_after_seconds = stale_after_seconds
    return stale_after_seconds


def refresh_controller_surface_fields(owner: Any) -> Dict[str, Any]:
    controller = get_refresh_controller(owner)
    if controller is None:
        return {}
    _sync_controller_stale_after_seconds(owner, controller)
    return refresh_controller_surface_payload(controller)


def _run_probe_worker(
    runtime: Any,
    controller: ProviderAvailabilityRefreshController,
    target: Dict[str, Any],
    *,
    retry_soft_failures: bool,
) -> None:
    try:
        probe_target(runtime, target, retry_soft_failures=retry_soft_failures)
    except Exception as exc:
        with controller.lock:
            controller.last_error = str(exc)
    finally:
        with controller.lock:
            controller.inflight_targets.discard(target_key(target))
            controller.last_completed_at = now_iso()


def schedule_refresh(
    runtime: Any,
    *,
    reason: str,
    only_stale: bool,
    background: bool = True,
    retry_soft_failures: bool = True,
) -> Dict[str, Any]:
    controller = get_refresh_controller(runtime)
    if controller is None:
        return {
            "scheduled": False,
            "reason": reason,
            "target_count": 0,
            "started_count": 0,
            "skipped_inflight_count": 0,
        }
    _sync_controller_stale_after_seconds(runtime, controller)

    probe_targets = select_probe_targets(
        runtime,
        controller,
        provider_items=provider_items(runtime),
        only_stale=only_stale,
    )
    scheduling = start_schedule(
        controller,
        probe_targets,
        reason=reason,
        now_iso_fn=now_iso,
    )
    started = scheduling["started"]
    skipped_inflight = int(scheduling["skipped_inflight_count"] or 0)

    if not started:
        return {
            "scheduled": False,
            "reason": reason,
            "target_count": len(probe_targets),
            "started_count": 0,
            "skipped_inflight_count": skipped_inflight,
        }

    if background:
        for target in started:
            worker = threading.Thread(
                target=_run_probe_worker,
                kwargs={
                    "runtime": runtime,
                    "controller": controller,
                    "target": target,
                    "retry_soft_failures": retry_soft_failures,
                },
                name=f"provider-probe-{target_key(target)[0] or 'unknown'}",
                daemon=True,
            )
            try:
                worker.start()
            except Exception as exc:
                with controller.lock:
                    controller.inflight_targets.discard(target_key(target))
                    controller.last_error = str(exc)
    else:
        for target in started:
            _run_probe_worker(
                runtime,
                controller,
                target,
                retry_soft_failures=retry_soft_failures,
            )

    return {
        "scheduled": True,
        "reason": reason,
        "target_count": len(probe_targets),
        "started_count": len(started),
        "skipped_inflight_count": skipped_inflight,
    }


def schedule_startup_warmup(runtime: Any, *, background: bool = True) -> Dict[str, Any]:
    return schedule_refresh(
        runtime,
        reason="startup_warmup",
        only_stale=False,
        background=background,
        retry_soft_failures=True,
    )


def schedule_stale_on_use_refresh(
    runtime: Any,
    *,
    reason: str,
    background: bool = True,
) -> Dict[str, Any]:
    return schedule_refresh(
        runtime,
        reason=reason,
        only_stale=True,
        background=background,
        retry_soft_failures=True,
    )


def maybe_reload_planner_for_provider_gate_update(agent: Any) -> bool:
    planner = getattr(agent, "_planner", None)
    if planner is None:
        return False
    if not bool(getattr(agent, "_planner_managed", False)):
        return False
    planner_config = getattr(planner, "config", None)
    raw_provider = dict(getattr(planner_config, "raw_provider", {}) or {}) if planner_config is not None else {}
    current_snapshot = dict(raw_provider.get("expert_review_gate_snapshot") or {})
    provider_review_gate_fn = getattr(agent, "provider_review_gate", None)
    if not callable(provider_review_gate_fn):
        return False
    try:
        live_snapshot = dict(provider_review_gate_fn() or {})
    except Exception:
        return False
    if live_snapshot == current_snapshot:
        return False
    reload_planner = getattr(agent, "_reload_planner", None)
    if callable(reload_planner):
        previous_signature = planner_signature(planner)
        previous_runtime_error = getattr(agent, "_planner_runtime_error", None)
        previous_runtime_error_diagnostics = getattr(agent, "_planner_runtime_error_diagnostics", None)
        reload_planner()
        current_planner = getattr(agent, "_planner", None)
        if (
            previous_runtime_error
            and not getattr(agent, "_planner_error", None)
            and not getattr(agent, "_planner_runtime_error", None)
            and previous_signature == planner_signature(current_planner)
        ):
            # Gate snapshot refresh should not erase the last observed provider failure
            # when the active provider/model did not actually change.
            agent._planner_runtime_error = previous_runtime_error
            agent._planner_runtime_error_diagnostics = previous_runtime_error_diagnostics
        return True
    return False


__all__ = [
    "ProviderAvailabilityRefreshController",
    "attach_refresh_controller",
    "build_refresh_controller",
    "get_refresh_controller",
    "maybe_reload_planner_for_provider_gate_update",
    "refresh_controller_surface_fields",
    "schedule_refresh",
    "schedule_stale_on_use_refresh",
    "schedule_startup_warmup",
]
