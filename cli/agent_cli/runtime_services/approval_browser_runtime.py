from __future__ import annotations

from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from workers.actions import ActionResult


def normalize_action_result(value: Any, *, default_action: str) -> ActionResult:
    if isinstance(value, ActionResult):
        return value
    if isinstance(value, dict):
        return ActionResult(
            ok=bool(value.get("ok")),
            action=str(value.get("action") or default_action),
            summary=str(value.get("summary") or value.get("message") or default_action),
            output=dict(value.get("output") or value),
            error=str(value.get("error") or "") or None,
        )
    raise TypeError("unsupported action result value")


def browser_request_from_action_payload(
    action_type: Any,
    payload: Any,
) -> Dict[str, Any]:
    payload_map = dict(payload or {})
    request = dict(payload_map.get("browser_request") or {})
    action_type = str(action_type or "").strip().lower().replace("-", "_")
    remainder = action_type.split(".", 1)[1] if "." in action_type else ""
    if "action" not in request:
        request["action"] = remainder.split(".", 1)[0] if remainder else "act"
    if request.get("action") == "act" and not request.get("kind") and "." in remainder:
        request["kind"] = remainder.split(".", 1)[1]
    return request


def browser_request_from_action_request(action_request: Any) -> Dict[str, Any]:
    return browser_request_from_action_payload(
        getattr(action_request, "action_type", ""),
        getattr(action_request, "payload", {}) or {},
    )


def browser_request_host(request: Dict[str, Any]) -> str | None:
    domain = str(request.get("domain") or "").strip().lower()
    if domain:
        return domain
    url = str(request.get("url") or "").strip()
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return str(parsed.netloc or "").strip().lower() or None


def browser_session_contract(action_type: Any, payload: Any) -> Dict[str, Any]:
    from cli.agent_cli import approval_contract_runtime

    request = browser_request_from_action_payload(action_type, payload)
    host = browser_request_host(request)
    session_cache_keys = approval_contract_runtime.browser_session_cache_keys(host=host)
    return {
        "request": request,
        "host": host,
        "session_cache_keys": session_cache_keys,
        "allow_for_session": bool(session_cache_keys),
    }


def browser_profile_prefers_local_execution(profile: Any) -> bool:
    from shared.web_automation.config import load_config
    from shared.web_automation.profiles import resolve_profiles

    config = load_config()
    profile_name = str(profile or config.default_profile or "").strip() or config.default_profile
    if not profile_name:
        return False
    try:
        profiles = resolve_profiles(config)
    except Exception:
        return False
    spec = profiles.get(profile_name)
    if spec is None:
        return False
    return str(getattr(spec, "driver", "") or "").strip().lower() == "existing-session"


def browser_artifact_refs(value: Any) -> List[str]:
    refs: List[str] = []

    def _append(candidate: Any) -> None:
        text = str(candidate or "").strip()
        if text:
            refs.append(text)

    def _walk(item: Any) -> None:
        if isinstance(item, dict):
            for key in ("path", "url", "imagePath"):
                if key in item:
                    _append(item.get(key))
            for child in item.values():
                _walk(child)
            return
        if isinstance(item, list):
            for child in item:
                _walk(child)

    _walk(value)
    return list(dict.fromkeys(refs))


def default_browser_action_executor(runtime: Any, action_request: Any) -> ActionResult:
    from shared.web_automation.client import BrowserClient
    from shared.web_automation.proxy import BrowserProxyExecutor

    request = browser_request_from_action_request(action_request)
    transport = str(request.get("transport") or "client").strip().lower() or "client"
    profile_name = str(request.get("profile") or "").strip() or None
    if transport == "proxy" and not browser_profile_prefers_local_execution(profile_name):
        result = BrowserProxyExecutor().run(
            method=str(request.get("method") or "GET"),
            path=str(request.get("path") or ""),
            query=request.get("query") if isinstance(request.get("query"), dict) else None,
            body=request.get("body"),
            timeout_ms=int(request["timeout_ms"]) if request.get("timeout_ms") is not None else None,
            profile=profile_name,
        )
        output = dict(result)
        nested = dict(output.get("result") or {}) if isinstance(output.get("result"), dict) else {}
        ok = int(output.get("status") or 500) < 400 and bool(nested.get("ok", True))
        summary = str(nested.get("message") or nested.get("action") or action_request.action_type)
        return ActionResult(
            ok=ok,
            action=str(action_request.action_type or ""),
            summary=summary,
            output=output,
            error=None if ok else str(nested.get("error") or "browser proxy action failed"),
        )

    result = BrowserClient().perform(
        action=str(request.get("action") or ""),
        profile=profile_name,
        tab_id=request.get("target_id") or request.get("tab_id"),
        url=request.get("url"),
        ref=request.get("ref"),
        start_ref=request.get("start_ref"),
        end_ref=request.get("end_ref"),
        level=request.get("level"),
        limit=request.get("limit"),
        path=request.get("path"),
        kind=request.get("kind"),
        text=request.get("text") or request.get("value"),
        key=request.get("key"),
        values=request.get("values"),
        fields=request.get("fields"),
        time_ms=request.get("time_ms"),
        width=request.get("width"),
        height=request.get("height"),
        paths=request.get("paths"),
        input_ref=request.get("input_ref"),
        accept=request.get("accept"),
        prompt_text=request.get("prompt_text"),
    )
    output = dict(result)
    ok = bool(output.get("ok"))
    return ActionResult(
        ok=ok,
        action=str(action_request.action_type or ""),
        summary=str(output.get("message") or output.get("action") or action_request.action_type),
        output=output,
        error=None if ok else str(output.get("error") or "browser action failed"),
    )


def execute_browser_gateway_action(
    runtime: Any,
    action_request: Any,
    *,
    browser_action_executor: Callable[[Any], Any] | None = None,
) -> ActionResult:
    executor = browser_action_executor or runtime.browser_action_executor or (
        lambda request: default_browser_action_executor(runtime, request)
    )
    return normalize_action_result(
        executor(action_request),
        default_action=str(action_request.action_type or ""),
    )


def action_request_details(action_request: Any) -> Dict[str, Any]:
    details = {
        "plugin_name": action_request.plugin_name,
        "connector_key": action_request.connector_key,
        "requested_by": action_request.requested_by,
    }
    if getattr(action_request, "action_family", None):
        details["action_family"] = action_request.action_family
    if getattr(action_request, "action_class", None):
        details["action_class"] = action_request.action_class
    if getattr(action_request, "approval_policy", None):
        details["approval_policy"] = action_request.approval_policy
    if getattr(action_request, "audit_stage", None):
        details["audit_stage"] = action_request.audit_stage
    browser_metadata = dict(getattr(action_request, "metadata", {}) or {}).get("browser")
    if isinstance(browser_metadata, dict) and browser_metadata:
        details["browser"] = dict(browser_metadata)
    return details
