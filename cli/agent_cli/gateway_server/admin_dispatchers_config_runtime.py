from __future__ import annotations

from pathlib import Path
from typing import Any


JsonMap = dict[str, Any]


def changed(current_value: Any, requested_value: Any) -> bool:
    if requested_value is None:
        return False
    return str(requested_value) != str(current_value)


def validate_workspace_root(
    *,
    current: JsonMap,
    params: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
) -> None:
    requested_workspace = params.get("workspaceRoot")
    if not changed(current.get("workspaceRoot"), requested_workspace):
        return
    changed_fields.append("workspaceRoot")
    workspace_text = str(requested_workspace or "").strip()
    workspace_path = Path(workspace_text).expanduser() if workspace_text else None
    if not workspace_text:
        blocked.append({"field": "workspaceRoot", "code": "required", "reason": "workspaceRoot 不能为空。"})
        return
    if workspace_path is None or not workspace_path.exists() or not workspace_path.is_dir():
        blocked.append(
            {
                "field": "workspaceRoot",
                "code": "not_found",
                "reason": f"workspaceRoot 不存在或不是目录：{workspace_text}",
            }
        )
        return
    applyable_fields.append("workspaceRoot")
    apply_path.append({"field": "workspaceRoot", "handler": "runtime.set_cwd"})


def validate_gui_runtime_flags(
    *,
    current: JsonMap,
    params: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    apply_path: list[JsonMap],
    restart_reasons: list[str],
    changed_fn: Any,
) -> None:
    for field in ("browserHeadless", "pluginAutoLoad"):
        if field in params and changed_fn(current.get(field), params.get(field)):
            changed_fields.append(field)
            applyable_fields.append(field)
            apply_path.append({"field": field, "handler": "gui.runtime_flags"})
            restart_reasons.append(f"{field} 变更")


def validate_runtime_policy(
    *,
    current_policy: JsonMap,
    requested_policy: JsonMap,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    apply_path: list[JsonMap],
    runtime_policy_options: dict[str, set[str]],
    changed_fn: Any,
) -> None:
    for field, options in runtime_policy_options.items():
        requested = requested_policy.get(field)
        if requested is None:
            continue
        if not changed_fn(current_policy.get(field), requested):
            continue
        changed_fields.append(field)
        normalized = str(requested).strip()
        if normalized not in options:
            blocked.append(
                {
                    "field": field,
                    "code": "invalid_value",
                    "reason": f"{field}={normalized or '-'} 不在当前支持范围。",
                }
            )
            continue
        applyable_fields.append(field)
        apply_path.append({"field": field, "handler": "runtime.configure_runtime_policy"})


def finalize_validation(
    *,
    changed_fields: list[str],
    applyable_fields: list[str],
    blocked: list[JsonMap],
    warnings: list[str],
    apply_path: list[JsonMap],
    restart_reasons: list[str],
) -> JsonMap:
    blocked_fields = {str(item.get("field") or "") for item in blocked}
    applyable_fields = [field for field in applyable_fields if field not in blocked_fields]
    changed_fields = list(dict.fromkeys(changed_fields))
    applyable_fields = list(dict.fromkeys(applyable_fields))
    apply_path = [item for item in apply_path if str(item.get("field") or "") in set(applyable_fields)]
    if changed_fields and applyable_fields:
        warnings.append(f"当前 draft 可真实应用 {len(applyable_fields)} 个字段。")
    if blocked:
        warnings.extend(str(item.get("reason") or "") for item in blocked if str(item.get("reason") or ""))
    restart = {
        "required": bool(restart_reasons),
        "reasons": list(dict.fromkeys(restart_reasons)),
        "allowed": False,
        "mode": "manual",
        "blockedReason": "runtime restart 仍需 operator 在相关运行面手动执行；当前 contract 只返回 restart report。",
    }
    if not restart["required"]:
        restart["blockedReason"] = None
    return {
        "changedFields": changed_fields,
        "applyableFields": applyable_fields,
        "blocked": blocked,
        "blockedFields": [field for field in changed_fields if field in blocked_fields],
        "warnings": list(dict.fromkeys(warnings)),
        "applyPath": apply_path,
        "restart": restart,
    }


def apply_config_changes(
    *,
    runtime: Any,
    params: JsonMap,
    validation: JsonMap,
    runtime_policy_fields: set[str],
    requested_policy: JsonMap,
    requested_reasoning_effort: Any,
    requested_delegation_models: JsonMap,
    standard_delegation_names: tuple[str, ...],
    delegation_requested_reasoning_effort_fn: Any,
) -> list[str]:
    applied_fields: list[str] = []
    if runtime_policy_fields:
        runtime.configure_runtime_policy(
            approval_policy=requested_policy.get("approval_policy") if "approval_policy" in runtime_policy_fields else None,
            sandbox_mode=requested_policy.get("sandbox_mode") if "sandbox_mode" in runtime_policy_fields else None,
            web_search_mode=requested_policy.get("web_search_mode") if "web_search_mode" in runtime_policy_fields else None,
            network_access_enabled=requested_policy.get("network_access") if "network_access" in runtime_policy_fields else None,
        )
        applied_fields.extend(sorted(runtime_policy_fields))
    if "browserHeadless" in validation["applyableFields"]:
        setattr(runtime, "_gui_browser_headless", bool(params.get("browserHeadless")))
        applied_fields.append("browserHeadless")
    if "pluginAutoLoad" in validation["applyableFields"]:
        setattr(runtime, "_gui_plugin_auto_load", bool(params.get("pluginAutoLoad")))
        applied_fields.append("pluginAutoLoad")
    if "workspaceRoot" in validation["applyableFields"]:
        runtime.set_cwd(str(params.get("workspaceRoot") or ""))
        applied_fields.append("workspaceRoot")
    if "model" in validation["applyableFields"] or "reasoningEffort" in validation["applyableFields"]:
        runtime.configure_model_selection(
            model=str(params.get("model") or "").strip() or None if "model" in validation["applyableFields"] else None,
            reasoning_effort=(
                str(requested_reasoning_effort or "").strip() or None
                if "reasoningEffort" in validation["applyableFields"]
                else None
            ),
        )
        if "model" in validation["applyableFields"]:
            applied_fields.append("model")
        if "reasoningEffort" in validation["applyableFields"]:
            applied_fields.append("reasoningEffort")
    for role_name in standard_delegation_names:
        field_name = f"delegationModels.{role_name}"
        if field_name not in validation["applyableFields"]:
            continue
        role_payload = dict(requested_delegation_models.get(role_name) or {})
        runtime.configure_delegate_selection(
            role_name,
            model=str(role_payload.get("model") or "").strip() or None if not bool(role_payload.get("clear")) else None,
            provider=(
                str(role_payload.get("provider") or "")
                if "provider" in role_payload and not bool(role_payload.get("clear"))
                else None
            ),
            reasoning_effort=(
                str(delegation_requested_reasoning_effort_fn(role_payload) or "").strip() or None
                if not bool(role_payload.get("clear"))
                else None
            ),
            timeout=role_payload.get("timeout") if not bool(role_payload.get("clear")) and "timeout" in role_payload else None,
            clear=bool(role_payload.get("clear")),
        )
        applied_fields.append(field_name)
    return applied_fields


def build_apply_result(
    *,
    applied_fields: list[str],
    validation: JsonMap,
    settings: JsonMap,
) -> JsonMap:
    blocked_fields = [str(item.get("field") or "") for item in validation["blocked"] if str(item.get("field") or "")]
    status = "blocked"
    if applied_fields and blocked_fields:
        status = "partial"
    elif applied_fields or not validation["changedFields"]:
        status = "applied"
    return {
        "applied": bool(applied_fields),
        "status": status,
        "appliedFields": applied_fields,
        "blockedFields": blocked_fields,
        "validation": validation,
        "restart": dict(validation["restart"]),
        "settings": settings,
    }
