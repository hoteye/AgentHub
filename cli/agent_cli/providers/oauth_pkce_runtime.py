from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping, MutableMapping

ERROR_NETWORK = "oauth_network_error"
ERROR_HTTP = "oauth_http_error"
ERROR_INVALID_RESPONSE = "oauth_invalid_response"
ERROR_INVALID_STATE = "invalid_state"

HttpClient = Callable[..., Mapping[str, Any]]


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _random_urlsafe(length: int = 64) -> str:
    # PKCE verifier must be high-entropy ASCII. urlsafe token without '=' fits.
    return secrets.token_urlsafe(max(32, int(length))).rstrip("=")


def _pkce_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _json_object_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    text = _as_str(value)
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
        encoded = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}, doseq=True).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(
        url=url,
        data=encoded,
        headers=dict(request_headers),
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds or 10))) as response:
            return {
                "status_code": int(getattr(response, "status", 200) or 200),
                "body": response.read().decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {"status_code": int(getattr(exc, "code", 0) or 0), "body": body}
    except Exception as exc:
        return {"error": ERROR_NETWORK, "error_detail": str(exc)}


def start_pkce_authorization(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str | None = None,
    code_verifier: str | None = None,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = _as_str(authorization_endpoint)
    client = _as_str(client_id)
    redirect = _as_str(redirect_uri)
    if not endpoint or not client or not redirect:
        return {"status": "error", "error_code": ERROR_INVALID_RESPONSE, "error_hint": "missing_authorization_parameters"}
    verifier = _as_str(code_verifier) or _random_urlsafe(64)
    request_state = _as_str(state) or _random_urlsafe(32)
    params: dict[str, Any] = {
        "response_type": "code",
        "client_id": client,
        "redirect_uri": redirect,
        "scope": _as_str(scope),
        "state": request_state,
        "code_challenge_method": "S256",
        "code_challenge": _pkce_code_challenge(verifier),
    }
    if extra_params:
        for key, value in dict(extra_params).items():
            text_key = _as_str(key)
            if not text_key:
                continue
            params[text_key] = value
    query = urllib.parse.urlencode(params, doseq=True)
    return {
        "status": "ok",
        "authorization_url": f"{endpoint}?{query}",
        "state": request_state,
        "code_verifier": verifier,
    }


def exchange_pkce_authorization_code(
    *,
    token_endpoint: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    expected_state: str | None = None,
    returned_state: str | None = None,
    client_secret: str | None = None,
    http_client: HttpClient | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    if _as_str(expected_state) and _as_str(returned_state) and _as_str(expected_state) != _as_str(returned_state):
        return {"status": "error", "error_code": ERROR_INVALID_STATE}
    endpoint = _as_str(token_endpoint)
    if not endpoint or not _as_str(client_id) or not _as_str(code) or not _as_str(redirect_uri) or not _as_str(code_verifier):
        return {"status": "error", "error_code": ERROR_INVALID_RESPONSE, "error_hint": "missing_token_exchange_parameters"}
    client = http_client or _default_http_client
    response = client(
        method="POST",
        url=endpoint,
        data={
            "grant_type": "authorization_code",
            "client_id": _as_str(client_id),
            "code": _as_str(code),
            "redirect_uri": _as_str(redirect_uri),
            "code_verifier": _as_str(code_verifier),
            "client_secret": _as_str(client_secret) or None,
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(response, Mapping):
        return {"status": "error", "error_code": ERROR_INVALID_RESPONSE}
    response_error = _as_str(response.get("error"))
    if response_error:
        return {
            "status": "error",
            "error_code": response_error,
            "error_description": _as_str(response.get("error_detail")),
        }
    status_code = _to_int(response.get("status_code"), 0)
    payload = _json_object_or_none(response.get("body"))
    if payload is None:
        return {"status": "error", "error_code": ERROR_INVALID_RESPONSE, "http_status": status_code}
    access_token = _as_str(payload.get("access_token"))
    if access_token:
        return {
            "status": "ok",
            "access_token": access_token,
            "refresh_token": _as_str(payload.get("refresh_token")),
            "token_type": _as_str(payload.get("token_type")),
            "scope": _as_str(payload.get("scope")),
            "expires_in": _to_int(payload.get("expires_in"), 0),
        }
    provider_error = _as_str(payload.get("error"))
    if provider_error:
        return {
            "status": "error",
            "error_code": provider_error,
            "error_description": _as_str(payload.get("error_description")),
            "http_status": status_code,
        }
    if status_code >= 400:
        return {"status": "error", "error_code": ERROR_HTTP, "http_status": status_code}
    return {"status": "error", "error_code": ERROR_INVALID_RESPONSE, "http_status": status_code}
