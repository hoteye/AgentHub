from __future__ import annotations

import json
from typing import Any


JsonMap = dict[str, Any]


def capabilities_inputs(
    *,
    registry_items: list[Any],
    legacy_methods: list[str],
) -> JsonMap:
    return {
        "method_entries": [item.metadata.to_dict() for item in registry_items],
        "legacy_methods": legacy_methods,
    }


def normalized_logs_tail_request(
    params: JsonMap,
    *,
    sources: JsonMap,
    first_int_fn: Any,
    first_text_fn: Any,
) -> JsonMap:
    safe_lines = first_int_fn(params, "lines", "limit", default=40, minimum=1, maximum=200)
    requested_source = first_text_fn(params, "source", "logSource", "log_source")
    if requested_source and requested_source not in sources:
        choices = ", ".join(sorted(sources)) or "none"
        raise ValueError(f"params.source must be one of: {choices}")
    selected_source = requested_source or (
        "thread.active_rollout" if "thread.active_rollout" in sources else next(iter(sources), "")
    )
    return {
        "safe_lines": safe_lines,
        "selected_source": selected_source,
        "source_meta": sources.get(selected_source),
    }


def validated_gateway_dispatch_event_kwargs(
    params: JsonMap,
    *,
    first_text_fn: Any,
    gateway_event_kwargs_fn: Any,
) -> JsonMap:
    event_kwargs = gateway_event_kwargs_fn(params, first_text_fn=first_text_fn)
    if not event_kwargs["event_type"]:
        raise ValueError("params.eventType must be a non-empty string")
    if not event_kwargs["source_kind"]:
        raise ValueError("params.sourceKind must be a non-empty string")
    if not event_kwargs["source_id"]:
        raise ValueError("params.sourceId must be a non-empty string")
    payload = params.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("params.payload must be an object when provided")
    metadata = params.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("params.metadata must be an object when provided")
    return event_kwargs


def validated_gateway_webhook_request(params: JsonMap, *, first_text_fn: Any) -> JsonMap:
    connector_key = first_text_fn(params, "connectorKey", "connector_key")
    event_type = first_text_fn(params, "eventType", "event_type")
    if not connector_key:
        raise ValueError("params.connectorKey must be a non-empty string")
    if not event_type:
        raise ValueError("params.eventType must be a non-empty string")
    raw_body = params.get("rawBody")
    if raw_body is not None and not isinstance(raw_body, str):
        raise ValueError("params.rawBody must be a string when provided")
    payload = params.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("params.payload must be an object when provided")
    if raw_body is not None and payload is not None:
        raise ValueError("params.payload must not be provided when params.rawBody is present")
    headers = params.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise ValueError("params.headers must be an object when provided")
    verification = params.get("verifySignature") or params.get("verify_signature")
    return {
        "connector_key": connector_key,
        "event_type": event_type,
        "raw_body": raw_body,
        "payload": payload,
        "headers": headers,
        "verification": verification,
        "source_id": first_text_fn(params, "sourceId", "source_id") or "webhook",
    }


def verify_webhook_request(
    verification: Any,
    *,
    headers: JsonMap | None,
    raw_body: str | None,
    verify_signature_fn: Any,
    verification_payload_fn: Any,
) -> JsonMap | None:
    if verification is None:
        return None
    if not isinstance(verification, dict):
        raise ValueError("params.verifySignature must be an object when provided")
    if raw_body is None:
        raise ValueError("params.rawBody is required when verifySignature is provided")
    secret = str(verification.get("secret") or "").strip()
    if not secret:
        raise ValueError("params.verifySignature.secret must be a non-empty string")
    header_name = str(verification.get("headerName") or "X-Hub-Signature-256").strip()
    prefix = str(verification.get("prefix") or "sha256=")
    verified = verify_signature_fn(
        headers=headers,
        raw_body=raw_body,
        secret=secret,
        header_name=header_name,
        prefix=prefix,
    )
    if not verified:
        return {
            "error_code": -32020,
            "error_message": "Webhook signature verification failed",
            "error_detail": f"signature header {header_name} missing or invalid",
        }
    return verification_payload_fn(header_name=header_name, prefix=prefix)


def webhook_event_payload(
    *,
    raw_body: str | None,
    payload: JsonMap | None,
    parse_webhook_body_fn: Any,
) -> JsonMap:
    if raw_body is None:
        return dict(payload or {})
    try:
        return parse_webhook_body_fn(raw_body)
    except ValueError as exc:
        raise ValueError(f"params.{exc}") from exc


def gateway_dispatch_response(
    response_payload: JsonMap,
    *,
    verification_payload: JsonMap | None,
) -> JsonMap:
    result = dict(response_payload)
    if verification_payload is not None:
        result["verification"] = verification_payload
    return result


def approvals_resolve_request(
    params: JsonMap,
    *,
    first_text_fn: Any,
    normalize_decision_fn: Any,
) -> JsonMap:
    approval_id = first_text_fn(params, "approvalId", "approval_id")
    if not approval_id:
        raise ValueError("params.approvalId must be a non-empty string")
    normalized_decision = normalize_decision_fn(first_text_fn(params, "decision"))
    if not normalized_decision:
        raise ValueError("params.decision is unsupported")
    return {
        "approval_id": approval_id,
        "decision": normalized_decision,
        "decided_by": first_text_fn(params, "decidedBy", "decided_by") or "app_server",
        "decision_note": first_text_fn(params, "decisionNote", "decision_note"),
    }


def browser_proxy_request_json(params: JsonMap) -> str:
    path = params.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("params.path must be a non-empty string")
    return json.dumps(params, ensure_ascii=False)


def browser_proxy_result(raw_result: str) -> JsonMap:
    return json.loads(raw_result)
