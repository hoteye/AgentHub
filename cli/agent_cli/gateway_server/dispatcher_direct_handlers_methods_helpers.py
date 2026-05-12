from __future__ import annotations

from typing import Any, Callable

JsonMap = dict[str, Any]


def handle_nodes_list(
    kwargs: dict[str, Any],
    *,
    resolve_gateway_auth_context_fn: Callable[..., Any],
    first_int_fn: Callable[..., int],
    build_access_posture_summary_fn: Callable[..., dict[str, Any]],
    runtime_registry_payload_fn: Callable[..., dict[str, Any]],
    nodes_inventory_payload_fn: Callable[..., dict[str, Any]],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    runtime = kwargs["runtime"]
    params = kwargs["params"]
    auth = resolve_gateway_auth_context_fn(kwargs.get("client_info"))
    limit = first_int_fn(params, "limit", default=20, minimum=1, maximum=200)
    snapshot = dict(runtime.gateway_state_snapshot(limit=limit) or {})
    access_posture = build_access_posture_summary_fn(runtime, auth=auth)
    runtime_registry = runtime_registry_payload_fn(runtime)
    return success_fn(
        nodes_inventory_payload_fn(
            snapshot=snapshot,
            access_posture=access_posture,
            runtime_registry=runtime_registry,
            limit=limit,
        )
    )


def handle_logs_tail(
    kwargs: dict[str, Any],
    *,
    available_log_sources_fn: Callable[..., list[dict[str, Any]]],
    normalized_logs_tail_request_fn: Callable[..., dict[str, Any]],
    first_int_fn: Callable[..., int],
    first_text_fn: Callable[..., str],
    failure_fn: Callable[..., JsonMap],
    success_fn: Callable[..., JsonMap],
    empty_logs_tail_payload_fn: Callable[..., dict[str, Any]],
    tail_text_lines_fn: Callable[..., tuple[list[str], bool]],
    logs_tail_payload_fn: Callable[..., dict[str, Any]],
    log_sources_payload_fn: Callable[..., list[dict[str, Any]]],
) -> JsonMap:
    runtime = kwargs["runtime"]
    params = kwargs["params"]
    sources = available_log_sources_fn(runtime)
    try:
        request = normalized_logs_tail_request_fn(
            params,
            sources=sources,
            first_int_fn=first_int_fn,
            first_text_fn=first_text_fn,
        )
    except ValueError as exc:
        return failure_fn(-32602, "Invalid params", detail=str(exc))
    source_meta = request["source_meta"]
    if source_meta is None:
        return success_fn(empty_logs_tail_payload_fn())
    lines = []
    truncated = False
    try:
        lines, truncated = tail_text_lines_fn(source_meta["path"], limit=request["safe_lines"])
    except OSError as exc:
        return failure_fn(-32034, "Log tail failed", detail=str(exc))
    return success_fn(
        logs_tail_payload_fn(
            selected_source=request["selected_source"],
            source_meta=source_meta,
            lines=lines,
            truncated=truncated,
            available_sources=log_sources_payload_fn(sources),
        )
    )


def handle_gateway_dispatch(
    kwargs: dict[str, Any],
    *,
    validated_gateway_dispatch_event_kwargs_fn: Callable[..., dict[str, Any]],
    first_text_fn: Callable[..., str],
    gateway_event_kwargs_fn: Callable[..., dict[str, Any]],
    create_gateway_event_fn: Callable[..., Any],
    gateway_dispatch_result_payload_fn: Callable[..., dict[str, Any]],
    failure_fn: Callable[..., JsonMap],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    params = kwargs["params"]
    runtime = kwargs["runtime"]
    try:
        event_kwargs = validated_gateway_dispatch_event_kwargs_fn(
            params,
            first_text_fn=first_text_fn,
            gateway_event_kwargs_fn=gateway_event_kwargs_fn,
        )
    except ValueError as exc:
        return failure_fn(-32602, "Invalid params", detail=str(exc))
    event = create_gateway_event_fn(**event_kwargs)
    return success_fn(gateway_dispatch_result_payload_fn(runtime.dispatch_gateway_event(event)))


def handle_gateway_webhook(
    kwargs: dict[str, Any],
    *,
    validated_gateway_webhook_request_fn: Callable[..., dict[str, Any]],
    first_text_fn: Callable[..., str],
    verify_webhook_request_fn: Callable[..., dict[str, Any] | None],
    verify_webhook_signature_fn: Callable[..., Any],
    verification_payload_fn: Callable[..., dict[str, Any]],
    webhook_event_payload_fn: Callable[..., dict[str, Any]],
    parse_webhook_body_fn: Callable[..., dict[str, Any]],
    build_webhook_event_fn: Callable[..., Any],
    gateway_dispatch_response_fn: Callable[..., dict[str, Any]],
    gateway_dispatch_result_payload_fn: Callable[..., dict[str, Any]],
    failure_fn: Callable[..., JsonMap],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    params = kwargs["params"]
    runtime = kwargs["runtime"]
    try:
        request = validated_gateway_webhook_request_fn(
            params,
            first_text_fn=first_text_fn,
        )
        verification_payload = verify_webhook_request_fn(
            request["verification"],
            headers=request["headers"],
            raw_body=request["raw_body"],
            verify_signature_fn=verify_webhook_signature_fn,
            verification_payload_fn=verification_payload_fn,
        )
        if verification_payload is not None and "error_code" in verification_payload:
            return failure_fn(
                verification_payload["error_code"],
                verification_payload["error_message"],
                detail=verification_payload["error_detail"],
            )
        event_payload = webhook_event_payload_fn(
            raw_body=request["raw_body"],
            payload=request["payload"],
            parse_webhook_body_fn=parse_webhook_body_fn,
        )
    except ValueError as exc:
        return failure_fn(-32602, "Invalid params", detail=str(exc))

    event = build_webhook_event_fn(
        connector_key=request["connector_key"],
        event_type=request["event_type"],
        payload=event_payload,
        headers=request["headers"],
        source_id=request["source_id"],
    )
    response_payload = gateway_dispatch_response_fn(
        gateway_dispatch_result_payload_fn(runtime.dispatch_gateway_event(event)),
        verification_payload=verification_payload,
    )
    return success_fn(response_payload)


def handle_gateway_state_get(
    kwargs: dict[str, Any],
    *,
    gateway_state_payload_fn: Callable[..., dict[str, Any]],
    gateway_item_to_dict_fn: Callable[..., dict[str, Any]],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    params = kwargs["params"]
    runtime = kwargs["runtime"]
    limit = int(params.get("limit") or 20)
    snapshot = runtime.gateway_state_snapshot(limit=limit)
    return success_fn(
        gateway_state_payload_fn(
            snapshot,
            gateway_item_to_dict_fn=gateway_item_to_dict_fn,
        )
    )


def handle_gateway_events_list(
    kwargs: dict[str, Any],
    *,
    handle_gateway_state_get_fn: Callable[..., JsonMap],
    gateway_events_list_payload_fn: Callable[..., dict[str, Any]],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    state = handle_gateway_state_get_fn(**kwargs)
    if not state.ok:
        return state
    result = dict(state.result or {})
    return success_fn(gateway_events_list_payload_fn(result))


def handle_gateway_workflows_list(
    kwargs: dict[str, Any],
    *,
    handle_gateway_state_get_fn: Callable[..., JsonMap],
    gateway_workflows_list_payload_fn: Callable[..., dict[str, Any]],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    state = handle_gateway_state_get_fn(**kwargs)
    if not state.ok:
        return state
    result = dict(state.result or {})
    return success_fn(gateway_workflows_list_payload_fn(result))


def handle_approvals_resolve(
    kwargs: dict[str, Any],
    *,
    approvals_resolve_request_fn: Callable[..., dict[str, Any]],
    first_text_fn: Callable[..., str],
    normalize_approval_decision_fn: Callable[..., str],
    failure_fn: Callable[..., JsonMap],
    approval_decision_result_to_camel_case_fn: Callable[..., dict[str, Any]],
    gateway_dispatch_result_cls: type,
    resume_after_approval_fn: Callable[..., Any] | None = None,
    persist_continuation_result_fn: Callable[..., Any] | None = None,
) -> JsonMap:
    params = kwargs["params"]
    runtime = kwargs["runtime"]
    try:
        request = approvals_resolve_request_fn(
            params,
            first_text_fn=first_text_fn,
            normalize_decision_fn=normalize_approval_decision_fn,
        )
    except ValueError as exc:
        return failure_fn(-32602, "Invalid params", detail=str(exc))
    try:
        result = runtime.decide_approval(
            request["approval_id"],
            decision=request["decision"],
            decided_by=request["decided_by"],
            decision_note=request["decision_note"],
        )
    except ValueError as exc:
        return failure_fn(-32040, "Approval decision failed", detail=str(exc))
    if callable(resume_after_approval_fn):
        continuation = result.get("continuation")
        if isinstance(continuation, dict):
            resumed_intent = resume_after_approval_fn(
                runtime,
                continuation_result=continuation,
            )
            if resumed_intent is not None:
                result["resumed_intent"] = resumed_intent
                assistant_text = str(getattr(resumed_intent, "assistant_text", "") or "").strip()
                if assistant_text:
                    continuation["assistant_text"] = assistant_text
                tool_events = [
                    item
                    for item in list(result.get("tool_events") or [])
                    if item is not None
                ]
                tool_events.extend(
                    [
                        item
                        for item in list(getattr(resumed_intent, "tool_events", []) or [])
                        if item is not None
                    ]
                )
                result["tool_events"] = tool_events
                item_events = [
                    dict(item)
                    for item in list(result.get("item_events") or [])
                    if isinstance(item, dict)
                ]
                item_events.extend(
                    [
                        dict(item)
                        for item in list(getattr(resumed_intent, "item_events", []) or [])
                        if isinstance(item, dict)
                    ]
                )
                result["item_events"] = item_events
                turn_events = [
                    dict(item)
                    for item in list(result.get("turn_events") or [])
                    if isinstance(item, dict)
                ]
                turn_events.extend(
                    [
                        dict(item)
                        for item in list(getattr(resumed_intent, "turn_events", []) or [])
                        if isinstance(item, dict)
                    ]
                )
                result["turn_events"] = turn_events
            for event in list(result.get("tool_events") or []):
                payload = getattr(event, "payload", None)
                if isinstance(payload, dict):
                    payload["continuation"] = dict(continuation)
            if callable(persist_continuation_result_fn):
                persist_continuation_result_fn(
                    runtime,
                    str(continuation.get("approval_id") or request["approval_id"] or ""),
                    continuation,
                )
    return gateway_dispatch_result_cls(
        ok=True,
        result=approval_decision_result_to_camel_case_fn(result),
        transport_context={"approval_decision_result": result},
    )


def handle_browser_proxy(
    kwargs: dict[str, Any],
    *,
    browser_proxy_request_json_fn: Callable[..., dict[str, Any]],
    run_browser_proxy_command_fn: Callable[..., dict[str, Any]],
    browser_proxy_result_fn: Callable[..., dict[str, Any]],
    failure_fn: Callable[..., JsonMap],
    success_fn: Callable[..., JsonMap],
) -> JsonMap:
    params = kwargs["params"]
    try:
        request_json = browser_proxy_request_json_fn(params)
    except ValueError as exc:
        return failure_fn(-32602, "Invalid params", detail=str(exc))
    try:
        result = browser_proxy_result_fn(run_browser_proxy_command_fn(request_json))
    except Exception as exc:
        return failure_fn(-32032, "Browser proxy failed", detail=str(exc))
    return success_fn(result)
