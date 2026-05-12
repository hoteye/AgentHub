from __future__ import annotations

from typing import Any, Callable


JsonMap = dict[str, Any]

REASONING_EFFORT_OPTIONS = {"default", "auto", "inherit", "low", "medium", "high", "xhigh"}
RUNTIME_POLICY_OPTIONS = {
    "approval_policy": {"never", "on-request", "on-failure", "untrusted"},
    "sandbox_mode": {"read-only", "workspace-write", "danger-full-access"},
    "web_search_mode": {"disabled", "cached", "live"},
    "network_access": {"enabled", "disabled"},
}
RUNTIME_POLICY_FIELDS = frozenset(RUNTIME_POLICY_OPTIONS)


def validate_model_field(
    *,
    current: JsonMap,
    params: JsonMap,
    known_selectors: set[str],
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
    changed_fn: Callable[[Any, Any], bool],
) -> None:
    requested_model = params.get("model")
    if not changed_fn(current.get("model"), requested_model):
        return
    changed_fields.append("model")
    model_text = str(requested_model or "").strip()
    if not model_text:
        blocked.append({"field": "model", "code": "required", "reason": "model 不能为空。"})
        return
    if model_text.lower() in {"default", "auto", "inherit"} or model_text in known_selectors:
        applyable_fields.append("model")
        apply_path.append({"field": "model", "handler": "runtime.configure_model_selection.model"})
        return
    blocked.append(
        {
            "field": "model",
            "code": "not_found",
            "reason": f"未知 model selector：{model_text}",
        }
    )


def validate_reasoning_effort_field(
    *,
    current: JsonMap,
    requested_reasoning_effort: Any,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
    changed_fn: Callable[[Any, Any], bool],
    reasoning_effort_options: set[str],
) -> None:
    if not changed_fn(current.get("reasoningEffort"), requested_reasoning_effort):
        return
    changed_fields.append("reasoningEffort")
    normalized_effort = str(requested_reasoning_effort or "").strip().lower()
    if not normalized_effort:
        blocked.append({"field": "reasoningEffort", "code": "required", "reason": "reasoningEffort 不能为空。"})
        return
    if normalized_effort in reasoning_effort_options:
        applyable_fields.append("reasoningEffort")
        apply_path.append({"field": "reasoningEffort", "handler": "runtime.configure_model_selection.reasoning_effort"})
        return
    blocked.append(
        {
            "field": "reasoningEffort",
            "code": "invalid_enum",
            "reason": "reasoningEffort 必须是 low、medium、high、xhigh 或 default。",
        }
    )


def validate_delegation_models(
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
    reasoning_effort_options: set[str],
) -> None:
    current_delegation_models = dict(current.get("delegationModels") or {})
    for role_name, raw_payload in requested_delegation_models.items():
        field_name = f"delegationModels.{role_name}"
        if role_name not in standard_delegation_names:
            changed_fields.append(field_name)
            blocked.append(
                {
                    "field": field_name,
                    "code": "invalid_key",
                    "reason": f"未知 delegation role：{role_name}",
                }
            )
            continue
        if not isinstance(raw_payload, dict):
            changed_fields.append(field_name)
            blocked.append(
                {
                    "field": field_name,
                    "code": "invalid_type",
                    "reason": "delegation role payload 必须是对象。",
                }
            )
            continue
        requested_signature = normalized_delegation_signature_fn(raw_payload)
        current_signature = current_delegation_signature_fn(dict(current_delegation_models.get(role_name) or {}))
        if requested_signature == current_signature:
            continue
        changed_fields.append(field_name)
        if bool(raw_payload.get("clear")):
            applyable_fields.append(field_name)
            apply_path.append({"field": field_name, "handler": f"runtime.configure_delegate_selection.{role_name}"})
            continue
        requested_model_text = str(raw_payload.get("model") or "").strip() if "model" in raw_payload else None
        requested_provider_text = str(raw_payload.get("provider") or "").strip() if "provider" in raw_payload else None
        requested_reasoning_text = delegation_requested_reasoning_effort_fn(raw_payload)
        requested_reasoning_text = (
            str(requested_reasoning_text or "").strip().lower()
            if requested_reasoning_text is not None
            else None
        )
        requested_timeout = raw_payload.get("timeout") if "timeout" in raw_payload else None
        if (
            requested_model_text is None
            and requested_provider_text is None
            and requested_reasoning_text is None
            and requested_timeout is None
        ):
            blocked.append(
                {
                    "field": field_name,
                    "code": "required",
                    "reason": "delegation role 至少需要一个变更字段，或显式 clear=true。",
                }
            )
            continue
        invalid = False
        if requested_model_text is not None:
            if not requested_model_text:
                blocked.append({"field": field_name, "code": "required", "reason": "delegation model 不能为空。"})
                invalid = True
            elif requested_model_text.lower() not in {"default", "auto", "inherit"} and requested_model_text not in known_selectors:
                blocked.append(
                    {
                        "field": field_name,
                        "code": "not_found",
                        "reason": f"未知 delegation model selector：{requested_model_text}",
                    }
                )
                invalid = True
        if requested_reasoning_text is not None:
            if not requested_reasoning_text:
                blocked.append({"field": field_name, "code": "required", "reason": "delegation reasoningEffort 不能为空。"})
                invalid = True
            elif requested_reasoning_text not in reasoning_effort_options:
                blocked.append(
                    {
                        "field": field_name,
                        "code": "invalid_enum",
                        "reason": "delegation reasoningEffort 必须是 low、medium、high、xhigh 或 default。",
                    }
                )
                invalid = True
        if requested_timeout is not None:
            try:
                timeout_value = int(str(requested_timeout).strip())
                if timeout_value <= 0:
                    raise ValueError("timeout")
            except (TypeError, ValueError):
                blocked.append(
                    {
                        "field": field_name,
                        "code": "invalid_timeout",
                        "reason": "delegation timeout 必须是正整数。",
                    }
                )
                invalid = True
        if invalid:
            continue
        applyable_fields.append(field_name)
        apply_path.append({"field": field_name, "handler": f"runtime.configure_delegate_selection.{role_name}"})
