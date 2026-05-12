from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping, MutableMapping, Sequence

ERROR_NETWORK = "oauth_network_error"
ERROR_HTTP = "oauth_http_error"
ERROR_INVALID_RESPONSE = "oauth_invalid_response"
ERROR_AUTHORIZATION_PENDING = "authorization_pending"
ERROR_SLOW_DOWN = "slow_down"
ERROR_EXPIRED_TOKEN = "expired_token"
ERROR_INVALID_GRANT = "invalid_grant"

HttpClient = Callable[..., Mapping[str, Any]]


def _normalize_scope(scope: str | Sequence[str] | None) -> str:
    if scope is None:
        return ""
    if isinstance(scope, str):
        return scope.strip()
    return " ".join(str(item).strip() for item in scope if str(item).strip()).strip()


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _json_object_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return None


def _default_http_client(
    *,
    method: str,
    url: str,
    data: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    encoded = None
    request_headers: MutableMapping[str, str] = {
        "Accept": "application/json",
    }
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items()})
    if data is not None:
        encoded = urllib.parse.urlencode(
            {k: v for k, v in data.items() if v is not None},
            doseq=True,
        ).encode("utf-8")
        request_headers.setdefault(
            "Content-Type",
            "application/x-www-form-urlencoded",
        )
    request = urllib.request.Request(
        url,
        data=encoded,
        headers=dict(request_headers),
        method=method.upper(),
    )
    timeout = max(1, int(timeout_seconds or 10))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "status_code": int(getattr(resp, "status", 200) or 200),
                "body": body,
                "headers": dict(resp.headers.items()),
            }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "status_code": int(getattr(exc, "code", 0) or 0),
            "body": body,
            "headers": dict(getattr(exc, "headers", {}).items()) if getattr(exc, "headers", None) else {},
        }
    except Exception as exc:
        return {"error": ERROR_NETWORK, "error_detail": str(exc)}


def _request_json(
    *,
    endpoint: str,
    form_data: Mapping[str, Any],
    timeout_seconds: int,
    http_client: HttpClient | None,
) -> dict[str, Any]:
    client = http_client or _default_http_client
    response = client(
        method="POST",
        url=endpoint,
        data=form_data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(response, Mapping):
        return {"status": "error", "error_code": ERROR_INVALID_RESPONSE}
    error_code = str(response.get("error") or "").strip()
    if error_code:
        return {
            "status": "error",
            "error_code": error_code,
            "error_description": str(response.get("error_detail") or "").strip(),
        }
    status_code = _to_int(response.get("status_code"), 0)
    payload = _json_object_or_none(response.get("body"))
    if payload is None:
        return {
            "status": "error",
            "error_code": ERROR_INVALID_RESPONSE,
            "http_status": status_code,
        }
    return {
        "status": "ok",
        "http_status": status_code,
        "payload": payload,
    }


def start_device_flow(
    *,
    device_authorization_endpoint: str,
    client_id: str,
    scope: str | Sequence[str] | None = None,
    audience: str | None = None,
    extra_fields: Mapping[str, Any] | None = None,
    http_client: HttpClient | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    form_data: dict[str, Any] = {"client_id": client_id}
    joined_scope = _normalize_scope(scope)
    if joined_scope:
        form_data["scope"] = joined_scope
    if str(audience or "").strip():
        form_data["audience"] = str(audience).strip()
    if extra_fields:
        form_data.update(dict(extra_fields))
    result = _request_json(
        endpoint=device_authorization_endpoint,
        form_data=form_data,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )
    if result.get("status") != "ok":
        return result
    payload = dict(result.get("payload") or {})
    status_code = _to_int(result.get("http_status"), 0)
    if status_code >= 400:
        return {
            "status": "error",
            "error_code": str(payload.get("error") or ERROR_HTTP),
            "error_description": str(payload.get("error_description") or "").strip(),
            "http_status": status_code,
        }
    verification_uri = str(payload.get("verification_uri") or "").strip()
    user_code = str(payload.get("user_code") or "").strip()
    device_code = str(payload.get("device_code") or "").strip()
    if not verification_uri or not user_code or not device_code:
        return {
            "status": "error",
            "error_code": ERROR_INVALID_RESPONSE,
            "http_status": status_code,
        }
    return {
        "status": "ok",
        "device_code": device_code,
        "verification_uri": verification_uri,
        "verification_uri_complete": str(payload.get("verification_uri_complete") or "").strip(),
        "user_code": user_code,
        "interval": _to_int(payload.get("interval"), 5),
        "expires_in": _to_int(payload.get("expires_in"), 0),
    }


def poll_device_flow(
    *,
    token_endpoint: str,
    client_id: str,
    device_code: str,
    client_secret: str | None = None,
    scope: str | Sequence[str] | None = None,
    http_client: HttpClient | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    form_data: dict[str, Any] = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": client_id,
    }
    if str(client_secret or "").strip():
        form_data["client_secret"] = str(client_secret).strip()
    joined_scope = _normalize_scope(scope)
    if joined_scope:
        form_data["scope"] = joined_scope
    result = _request_json(
        endpoint=token_endpoint,
        form_data=form_data,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )
    if result.get("status") != "ok":
        return result
    payload = dict(result.get("payload") or {})
    status_code = _to_int(result.get("http_status"), 0)
    if str(payload.get("access_token") or "").strip():
        return {
            "status": "authorized",
            "access_token": str(payload.get("access_token") or "").strip(),
            "refresh_token": str(payload.get("refresh_token") or "").strip(),
            "token_type": str(payload.get("token_type") or "").strip(),
            "scope": str(payload.get("scope") or "").strip(),
            "expires_in": _to_int(payload.get("expires_in"), 0),
        }
    provider_error = str(payload.get("error") or "").strip()
    if provider_error == ERROR_AUTHORIZATION_PENDING:
        return {
            "status": "pending",
            "error_code": ERROR_AUTHORIZATION_PENDING,
            "retry_after_seconds": _to_int(payload.get("interval"), 0),
        }
    if provider_error == ERROR_SLOW_DOWN:
        return {
            "status": "slow_down",
            "error_code": ERROR_SLOW_DOWN,
            "retry_after_seconds": max(1, _to_int(payload.get("interval"), 5)),
        }
    if provider_error == ERROR_EXPIRED_TOKEN:
        return {
            "status": "expired",
            "error_code": ERROR_EXPIRED_TOKEN,
        }
    if provider_error:
        return {
            "status": "error",
            "error_code": provider_error,
            "error_description": str(payload.get("error_description") or "").strip(),
            "http_status": status_code,
        }
    return {
        "status": "error",
        "error_code": ERROR_INVALID_RESPONSE,
        "http_status": status_code,
    }


def refresh_oauth_token(
    *,
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
    scope: str | Sequence[str] | None = None,
    http_client: HttpClient | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    form_data: dict[str, Any] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if str(client_secret or "").strip():
        form_data["client_secret"] = str(client_secret).strip()
    joined_scope = _normalize_scope(scope)
    if joined_scope:
        form_data["scope"] = joined_scope
    result = _request_json(
        endpoint=token_endpoint,
        form_data=form_data,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )
    if result.get("status") != "ok":
        return result
    payload = dict(result.get("payload") or {})
    status_code = _to_int(result.get("http_status"), 0)
    access_token = str(payload.get("access_token") or "").strip()
    if access_token:
        return {
            "status": "ok",
            "access_token": access_token,
            "refresh_token": str(payload.get("refresh_token") or refresh_token).strip(),
            "token_type": str(payload.get("token_type") or "").strip(),
            "scope": str(payload.get("scope") or "").strip(),
            "expires_in": _to_int(payload.get("expires_in"), 0),
        }
    provider_error = str(payload.get("error") or "").strip()
    if provider_error:
        return {
            "status": "error",
            "error_code": provider_error,
            "error_description": str(payload.get("error_description") or "").strip(),
            "http_status": status_code,
        }
    if status_code >= 400:
        return {
            "status": "error",
            "error_code": ERROR_HTTP,
            "http_status": status_code,
        }
    return {"status": "error", "error_code": ERROR_INVALID_RESPONSE}

