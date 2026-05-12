from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .plugin_marketplace_commands_pure_helpers_runtime import plugin_manager


def parse_plugin_marketplace_action(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> tuple[str, list[Any], dict[str, Any]]:
    positionals, options = runtime._parse_args(arg_text)
    if name == "plugin_marketplace":
        action = str(positionals[0] if positionals else "list").strip().lower()
        action_positionals = list(positionals[1:])
    else:
        action = str(name.removeprefix("plugin_marketplace_") or "").strip().lower()
        action_positionals = list(positionals)
    return (action, action_positionals, dict(options))


def resolve_source_arg(source_value: str, *, cwd: str | None) -> str:
    source_text = str(source_value or "").strip()
    if not source_text:
        raise ValueError("plugin source path is required")
    source_path = Path(source_text).expanduser()
    if not source_path.is_absolute():
        source_path = Path(str(cwd or "")).expanduser() / source_path
    resolved = source_path.resolve()
    if not resolved.exists():
        raise ValueError(f"plugin source does not exist: {resolved}")
    return str(resolved)


def bool_option(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def marketplace_policy_hook(runtime: Any) -> tuple[Callable[..., Any] | None, str]:
    for owner in (runtime, plugin_manager(runtime)):
        if owner is None:
            continue
        for attr in ("plugin_marketplace_policy_hook", "plugin_marketplace_policy"):
            candidate = getattr(owner, attr, None)
            if callable(candidate):
                owner_name = owner.__class__.__name__
                return (candidate, f"{owner_name}.{attr}")
    return (None, "builtin.default")


def normalize_policy_decision(raw_decision: Any) -> dict[str, Any]:
    allow_tokens = {"allow", "allowed", "ok", "pass", "true", "1"}
    block_tokens = {"block", "blocked", "deny", "denied", "false", "0"}
    if raw_decision is None:
        return {"allowed": True, "reason": "", "code": "allow_default", "details": {}}
    if isinstance(raw_decision, bool):
        return {
            "allowed": raw_decision,
            "reason": "" if raw_decision else "blocked by marketplace policy",
            "code": "allow_bool" if raw_decision else "blocked_bool",
            "details": {},
        }
    if isinstance(raw_decision, str):
        token = raw_decision.strip().lower()
        if token in allow_tokens:
            return {
                "allowed": True,
                "reason": "",
                "code": "allow_string",
                "details": {"decision": token},
            }
        if token in block_tokens:
            return {
                "allowed": False,
                "reason": f"blocked by marketplace policy: {raw_decision.strip() or token}",
                "code": "blocked_string",
                "details": {"decision": token},
            }
        return {
            "allowed": False,
            "reason": f"invalid marketplace policy decision: {raw_decision}",
            "code": "invalid_policy_decision",
            "details": {"decision": raw_decision},
        }
    if isinstance(raw_decision, dict):
        decision_token = str(raw_decision.get("decision") or "").strip().lower()
        if "allow" in raw_decision:
            allow_value = raw_decision.get("allow")
            if isinstance(allow_value, str):
                allow_token = allow_value.strip().lower()
                if allow_token in allow_tokens:
                    allowed = True
                elif allow_token in block_tokens:
                    allowed = False
                else:
                    allowed = bool_option(allow_value, default=False)
            else:
                allowed = bool_option(allow_value, default=False)
        elif decision_token in allow_tokens:
            allowed = True
        elif decision_token in block_tokens:
            allowed = False
        else:
            allowed = True
        reason = str(raw_decision.get("reason") or "").strip()
        code = str(raw_decision.get("code") or "").strip()
        detail_value = raw_decision.get("details")
        details = dict(detail_value) if isinstance(detail_value, dict) else {}
        if decision_token and "decision" not in details:
            details["decision"] = decision_token
        return {
            "allowed": allowed,
            "reason": reason or ("" if allowed else "blocked by marketplace policy"),
            "code": code or ("allow_dict" if allowed else "blocked_dict"),
            "details": details,
        }
    return {
        "allowed": False,
        "reason": f"invalid marketplace policy decision type: {type(raw_decision).__name__}",
        "code": "invalid_policy_decision_type",
        "details": {"decision_type": type(raw_decision).__name__},
    }


def invoke_policy_hook(hook: Callable[..., Any], context: dict[str, Any]) -> Any:
    try:
        return hook(**context)
    except TypeError as original_exc:
        try:
            return hook(context)
        except TypeError:
            raise original_exc


def evaluate_marketplace_policy(
    runtime: Any,
    *,
    action: str,
    plugin_key: str,
    source: str | None,
    scope: str | None,
) -> dict[str, Any]:
    hook, hook_name = marketplace_policy_hook(runtime)
    if hook is None:
        return {
            "allowed": True,
            "reason": "",
            "code": "allow_default",
            "details": {},
            "hook": hook_name,
        }
    context = {
        "action": action,
        "plugin_key": plugin_key,
        "source": source,
        "scope": scope,
        "runtime": runtime,
    }
    try:
        raw_decision = invoke_policy_hook(hook, context)
    except Exception as exc:
        return {
            "allowed": False,
            "reason": f"marketplace policy hook error: {exc}",
            "code": "policy_hook_error",
            "details": {"exception_type": exc.__class__.__name__},
            "hook": hook_name,
        }
    normalized = normalize_policy_decision(raw_decision)
    normalized["hook"] = hook_name
    return normalized
