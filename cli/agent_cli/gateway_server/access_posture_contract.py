from __future__ import annotations

from typing import Any

from cli.agent_cli.gateway_protocol.auth_context import GatewayAuthContext, anonymous_auth_context


def build_access_posture_summary(
    runtime: Any,
    *,
    auth: GatewayAuthContext | None = None,
) -> dict[str, Any]:
    resolved_auth = auth or anonymous_auth_context(client_type="gateway")
    auth_origin = _auth_origin_posture(resolved_auth)
    auth_mode = _auth_mode_posture(resolved_auth, origin=auth_origin)

    local_enabled = True
    remote_enabled = auth_origin == "remote"
    posture = "unknown"
    if local_enabled and remote_enabled:
        posture = "local+remote"
    elif local_enabled:
        posture = "local-only"
    elif remote_enabled:
        posture = "remote-only"

    pairing = _pairing_summary(runtime)
    roles = [str(item).strip() for item in list(resolved_auth.roles or []) if str(item).strip()]
    if not roles and str(resolved_auth.role or "").strip():
        roles = [str(resolved_auth.role).strip()]

    return {
        "access": {
            "posture": posture,
            "local": {
                "enabled": local_enabled,
                "channel": "local-app-server",
                "origin": "localhost",
            },
            "remote": {
                "enabled": remote_enabled,
                "channel": "gateway",
                "origin": "network" if remote_enabled else None,
            },
        },
        "auth": {
            "mode": auth_mode,
            "origin": auth_origin,
            "authenticated": bool(resolved_auth.authenticated),
            "authSource": str(resolved_auth.auth_source or "unknown"),
            "trustLevel": str(resolved_auth.trust_level or "unknown"),
            "actorId": str(resolved_auth.actor_id or ""),
            "clientType": str(resolved_auth.client_type or ""),
            "roles": roles,
            "scopes": [str(item).strip() for item in list(resolved_auth.scopes or []) if str(item).strip()],
        },
        "pairing": pairing,
        "summary": {
            "pendingPairingRequestCount": int(pairing["pendingRequestCount"]),
            "pendingApprovalCount": int(pairing["pendingApprovalCount"]),
            "accessPosture": posture,
            "authMode": auth_mode,
            "authOrigin": auth_origin,
        },
    }


def _auth_origin_posture(auth: GatewayAuthContext) -> str:
    source = str(auth.auth_source or "").strip().lower()
    client_type = str(auth.client_type or "").strip().lower()
    if source == "anonymous":
        return "unknown"
    if source in {"local-app-server", "app_server"} or client_type in {"gui", "app_server"}:
        return "local"
    if source in {"gateway", "shared-secret", "token", "api-key"} or client_type in {
        "remote",
        "gateway",
        "web",
        "websocket",
    }:
        return "remote"
    return "unknown"


def _auth_mode_posture(auth: GatewayAuthContext, *, origin: str) -> str:
    if not auth.authenticated:
        return "anonymous"
    source = str(auth.auth_source or "").strip().lower()
    trust = str(auth.trust_level or "").strip().lower()
    if origin == "local" and (source in {"local-app-server", "app_server"} or trust in {"trusted", "local"}):
        return "trusted_local"
    if origin == "remote" or source in {"gateway", "shared-secret", "token", "api-key"}:
        return "remote_authenticated"
    return "authenticated"


def _pairing_summary(runtime: Any) -> dict[str, Any]:
    tickets = _pending_approval_tickets(runtime, limit=200)
    pending_refs: list[dict[str, Any]] = []
    for item in tickets:
        if _is_pairing_ticket(item):
            pending_refs.append(_pairing_pending_ref(item))
    pairing_count = len(pending_refs)
    return {
        "pendingRequestCount": pairing_count,
        "pendingApprovalCount": len(tickets),
        "pendingRefs": pending_refs,
        "source": "approvals.pending_heuristic",
        "hasNativeContract": False,
        "summary": (
            "derived from pending approval tickets via pairing/device keywords"
            if tickets
            else "no pending approvals available for pairing heuristic"
        ),
    }


def _pending_approval_tickets(runtime: Any, *, limit: int) -> list[dict[str, Any]]:
    getter = getattr(runtime, "list_approval_tickets", None)
    if not callable(getter):
        return []
    try:
        items = getter(limit=limit, status="pending")
    except TypeError:
        try:
            items = getter(limit=limit)
        except Exception:
            return []
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for item in list(items or []):
        result.append(_item_to_dict(item))
    return result


def _item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return dict(value)
    payload = getattr(item, "payload", None)
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _is_pairing_ticket(item: dict[str, Any]) -> bool:
    fields = (
        item.get("title"),
        item.get("summary"),
        item.get("reason"),
        item.get("action_type"),
        item.get("actionType"),
    )
    haystack = " ".join(str(value or "").strip().lower() for value in fields if str(value or "").strip())
    if not haystack:
        return False
    keywords = (
        "pair",
        "pairing",
        "device",
        "trust",
        "remote access",
        "remote_access",
    )
    return any(keyword in haystack for keyword in keywords)


def _pairing_pending_ref(item: dict[str, Any]) -> dict[str, Any]:
    approval_id = _first_text(item, "approval_id", "approvalId", "id")
    trace_id = _first_text(item, "trace_id", "traceId")
    title = _first_text(item, "title", "summary", "reason") or "pending pairing request"
    action_type = _first_text(item, "action_type", "actionType") or "unknown"
    requested_at = _first_text(item, "requested_at", "requestedAt", "created_at", "createdAt")
    ref = {
        "approvalId": approval_id,
        "traceId": trace_id,
        "title": title,
        "actionType": action_type,
    }
    if requested_at:
        ref["requestedAt"] = requested_at
    return ref


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""
