from __future__ import annotations

from typing import Any, Callable


def gateway_dispatcher_methods(
    *,
    legacy_only_methods: set[str],
    legacy_method_aliases: dict[str, str],
    method_registry: Any,
    gateway_method_handlers: dict[str, Any],
) -> tuple[str, ...]:
    methods = set(legacy_only_methods)
    methods.update(legacy_method_aliases)
    methods.update(item.metadata.method for item in method_registry.list())
    methods.update(gateway_method_handlers)
    return tuple(sorted(methods))


def gateway_dispatcher_supports_method(method: str, *, gateway_dispatcher_methods_fn: Callable[[], tuple[str, ...]]) -> bool:
    return str(method or "").strip() in gateway_dispatcher_methods_fn()


def protocol_error_failure(
    error: Any,
    *,
    error_codes: Any,
    result_type: type,
) -> Any:
    code = {
        error_codes.INVALID_REQUEST: -32600,
        error_codes.METHOD_NOT_FOUND: -32601,
        error_codes.UNAUTHORIZED: -32041,
        error_codes.FORBIDDEN: -32043,
        error_codes.UNAVAILABLE: -32029,
        error_codes.INTERNAL_ERROR: -32000,
    }.get(error.code, -32000)
    error_data: dict[str, Any] = {"gatewayCode": error.code}
    if error.details is not None:
        error_data["details"] = error.details
    retry_after_ms = error.error.retry_after_ms
    if retry_after_ms is not None:
        error_data["retryAfterMs"] = retry_after_ms
    if error.error.retryable:
        error_data["retryable"] = True
    return result_type(
        ok=False,
        error_code=code,
        error_message=error.error.message,
        error_data=error_data,
    )


def dispatch_gateway_method(
    *,
    method: str,
    params: dict[str, Any],
    runtime: Any,
    action_worker: Any | None,
    request_id: Any,
    client_info: dict[str, Any] | None,
    legacy_method_aliases: dict[str, str],
    method_registry: Any,
    resolve_gateway_auth_context_fn: Any,
    require_gateway_authorized_fn: Any,
    consume_control_plane_write_budget_fn: Any,
    gateway_protocol_error_type: type[Exception],
    error_codes: Any,
    protocol_error_failure_fn: Any,
    build_gateway_request_scope_fn: Any,
    direct_method_handlers: dict[str, Callable[..., Any]],
    run_browser_proxy_command: Any,
    dispatcher_direct_handlers_module: Any,
    with_gateway_request_scope_fn: Any,
    gateway_method_handlers: dict[str, Callable[..., Any]],
    success_fn: Any,
    failure_fn: Any,
) -> Any:
    normalized_method = str(method or "").strip()
    if not normalized_method:
        return failure_fn(-32600, "Invalid Request", detail="method is required")
    if not isinstance(params, dict):
        return failure_fn(-32602, "Invalid params", detail="params must be an object")

    canonical_method = legacy_method_aliases.get(normalized_method, normalized_method)
    registration = method_registry.get(canonical_method)
    auth = resolve_gateway_auth_context_fn(client_info)
    if registration is not None:
        try:
            decision = require_gateway_authorized_fn(
                method=canonical_method,
                auth=auth,
                metadata=registration.metadata,
            )
            if decision.control_plane_write and canonical_method != "browser.proxy":
                budget = consume_control_plane_write_budget_fn(client=client_info)
                if not budget.allowed:
                    raise gateway_protocol_error_type(
                        error_codes.UNAVAILABLE,
                        f"rate limit exceeded for {canonical_method}; retry after {max(1, budget.retry_after_ms // 1000)}s",
                        details={
                            "method": canonical_method,
                            "limit": f"{budget.limit} per {budget.window_ms // 1000}s",
                            "budget_key": budget.key,
                            "remaining": budget.remaining,
                        },
                        retryable=True,
                        retry_after_ms=budget.retry_after_ms,
                    )
        except gateway_protocol_error_type as exc:
            return protocol_error_failure_fn(exc)
    request_scope = build_gateway_request_scope_fn(
        method=canonical_method,
        params=params,
        request_id=request_id,
        client_info=client_info,
        auth=auth,
    )

    handler = direct_method_handlers.get(canonical_method)
    if handler is not None:
        try:
            if canonical_method == "browser.proxy":
                dispatcher_direct_handlers_module.run_browser_proxy_command = run_browser_proxy_command
            return with_gateway_request_scope_fn(
                request_scope,
                lambda: handler(
                    params=dict(params),
                    runtime=runtime,
                    action_worker=action_worker,
                    request_id=request_id,
                    client_info=dict(client_info or {}),
                    method=canonical_method,
                ),
            )
        except ValueError as exc:
            return failure_fn(-32602, "Invalid params", detail=str(exc))
        except Exception as exc:
            return failure_fn(-32000, "Gateway handler failed", detail=f"{type(exc).__name__}: {exc}")

    stub_handler = gateway_method_handlers.get(canonical_method)
    if stub_handler is not None:
        try:
            return with_gateway_request_scope_fn(
                request_scope,
                lambda: success_fn(
                    stub_handler(
                        params=dict(params),
                        runtime=runtime,
                        action_worker=action_worker,
                        request_id=request_id,
                        client_info=dict(client_info or {}),
                    )
                ),
            )
        except ValueError as exc:
            return failure_fn(-32602, "Invalid params", detail=str(exc))
        except Exception as exc:
            return failure_fn(-32000, "Gateway handler failed", detail=f"{type(exc).__name__}: {exc}")

    return failure_fn(-32601, "Method not found", detail=normalized_method)
