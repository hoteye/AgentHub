from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.gateway_server import admin_dispatchers_config_runtime as admin_dispatchers_config_runtime_service
from cli.agent_cli.gateway_server import admin_dispatchers_runtime_validation_helpers as validation_helpers


JsonMap = dict[str, Any]

_REASONING_EFFORT_OPTIONS = validation_helpers.REASONING_EFFORT_OPTIONS
_RUNTIME_POLICY_OPTIONS = validation_helpers.RUNTIME_POLICY_OPTIONS
_RUNTIME_POLICY_FIELDS = validation_helpers.RUNTIME_POLICY_FIELDS


def _changed(current_value: Any, requested_value: Any) -> bool:
    return admin_dispatchers_config_runtime_service.changed(current_value, requested_value)


def _validate_model_field(
    *,
    current: JsonMap,
    params: JsonMap,
    known_selectors: set[str],
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    validation_helpers.validate_model_field(
        current=current,
        params=params,
        known_selectors=known_selectors,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
        changed_fn=_changed,
    )


def _validate_reasoning_effort_field(
    *,
    current: JsonMap,
    requested_reasoning_effort: Any,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    validation_helpers.validate_reasoning_effort_field(
        current=current,
        requested_reasoning_effort=requested_reasoning_effort,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
        changed_fn=_changed,
        reasoning_effort_options=_REASONING_EFFORT_OPTIONS,
    )


def _validate_delegation_models(
    *,
    current: JsonMap,
    known_selectors: set[str],
    standard_delegation_names: tuple[str, ...],
    requested_delegation_models: JsonMap,
    normalized_delegation_signature_fn: Callable[[JsonMap], Any],
    current_delegation_signature_fn: Callable[[JsonMap], Any],
    delegation_requested_reasoning_effort_fn: Callable[[JsonMap], Any],
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    validation_helpers.validate_delegation_models(
        current=current,
        known_selectors=known_selectors,
        standard_delegation_names=standard_delegation_names,
        requested_delegation_models=requested_delegation_models,
        normalized_delegation_signature_fn=normalized_delegation_signature_fn,
        current_delegation_signature_fn=current_delegation_signature_fn,
        delegation_requested_reasoning_effort_fn=delegation_requested_reasoning_effort_fn,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
        reasoning_effort_options=_REASONING_EFFORT_OPTIONS,
    )


def _validate_workspace_root(
    *,
    current: JsonMap,
    params: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    admin_dispatchers_config_runtime_service.validate_workspace_root(
        current=current,
        params=params,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )


def _validate_gui_runtime_flags(
    *,
    current: JsonMap,
    params: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    apply_path: list[JsonMap],
    restart_reasons: list[str],
) -> None:
    admin_dispatchers_config_runtime_service.validate_gui_runtime_flags(
        current=current,
        params=params,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        apply_path=apply_path,
        restart_reasons=restart_reasons,
        changed_fn=_changed,
    )


def _validate_runtime_policy(
    *,
    current_policy: JsonMap,
    requested_policy: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    admin_dispatchers_config_runtime_service.validate_runtime_policy(
        current_policy=current_policy,
        requested_policy=requested_policy,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
        runtime_policy_options=_RUNTIME_POLICY_OPTIONS,
        changed_fn=_changed,
    )


def _finalize_validation(
    *,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    warnings: list[str],
    apply_path: list[JsonMap],
    restart_reasons: list[str],
) -> JsonMap:
    return admin_dispatchers_config_runtime_service.finalize_validation(
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        warnings=warnings,
        apply_path=apply_path,
        restart_reasons=restart_reasons,
    )


def config_validation_payload(
    *,
    current: JsonMap,
    params: JsonMap,
    known_selectors: set[str],
    standard_delegation_names: tuple[str, ...],
    requested_policy: JsonMap,
    requested_reasoning_effort: Any,
    requested_delegation_models: JsonMap,
    normalized_delegation_signature_fn: Callable[[JsonMap], Any],
    current_delegation_signature_fn: Callable[[JsonMap], Any],
    delegation_requested_reasoning_effort_fn: Callable[[JsonMap], Any],
) -> JsonMap:
    current_policy = dict(current.get("runtimePolicy") or {})
    changed_fields: list[str] = []
    applyable_fields: list[str] = []
    blocked: list[JsonMap] = []
    warnings: list[str] = []
    apply_path: list[JsonMap] = []
    restart_reasons: list[str] = []

    _validate_model_field(
        current=current,
        params=params,
        known_selectors=known_selectors,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )
    _validate_reasoning_effort_field(
        current=current,
        requested_reasoning_effort=requested_reasoning_effort,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )
    _validate_delegation_models(
        current=current,
        known_selectors=known_selectors,
        standard_delegation_names=standard_delegation_names,
        requested_delegation_models=requested_delegation_models,
        normalized_delegation_signature_fn=normalized_delegation_signature_fn,
        current_delegation_signature_fn=current_delegation_signature_fn,
        delegation_requested_reasoning_effort_fn=delegation_requested_reasoning_effort_fn,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )
    _validate_workspace_root(
        current=current,
        params=params,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )
    _validate_gui_runtime_flags(
        current=current,
        params=params,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        apply_path=apply_path,
        restart_reasons=restart_reasons,
    )
    _validate_runtime_policy(
        current_policy=current_policy,
        requested_policy=requested_policy,
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        apply_path=apply_path,
    )
    return _finalize_validation(
        changed_fields=changed_fields,
        applyable_fields=applyable_fields,
        blocked=blocked,
        warnings=warnings,
        apply_path=apply_path,
        restart_reasons=restart_reasons,
    )


def config_apply_result(
    *,
    runtime: Any,
    params: JsonMap,
    validation: JsonMap,
    standard_delegation_names: tuple[str, ...],
    requested_policy: JsonMap,
    requested_reasoning_effort: Any,
    requested_delegation_models: JsonMap,
    delegation_requested_reasoning_effort_fn: Callable[[JsonMap], Any],
    config_settings_snapshot_fn: Callable[..., JsonMap],
    runtime_registry_payload_fn: Callable[[Any], JsonMap],
) -> JsonMap:
    runtime_policy_fields = {
        field for field in validation["applyableFields"] if field in _RUNTIME_POLICY_FIELDS
    }
    applied_fields = admin_dispatchers_config_runtime_service.apply_config_changes(
        runtime=runtime,
        params=params,
        validation=validation,
        runtime_policy_fields=runtime_policy_fields,
        requested_policy=requested_policy,
        requested_reasoning_effort=requested_reasoning_effort,
        requested_delegation_models=requested_delegation_models,
        standard_delegation_names=standard_delegation_names,
        delegation_requested_reasoning_effort_fn=delegation_requested_reasoning_effort_fn,
    )

    return admin_dispatchers_config_runtime_service.build_apply_result(
        applied_fields=applied_fields,
        validation=validation,
        settings=config_settings_snapshot_fn(runtime, runtime_registry_payload_fn=runtime_registry_payload_fn),
    )


def config_restart_report(*, validation: JsonMap) -> JsonMap:
    return {
        "required": bool(validation["restart"].get("required")),
        "reasons": list(validation["restart"].get("reasons") or []),
        "allowed": bool(validation["restart"].get("allowed")),
        "mode": str(validation["restart"].get("mode") or "manual"),
        "blockedReason": validation["restart"].get("blockedReason"),
    }
