from __future__ import annotations

import json
import urllib.parse

from cli.agent_cli.providers.oauth_pkce_runtime import (
    ERROR_INVALID_STATE,
    exchange_pkce_authorization_code,
    start_pkce_authorization,
)


def test_start_pkce_authorization_builds_url_and_pkce_fields() -> None:
    result = start_pkce_authorization(
        authorization_endpoint="https://issuer.example/oauth/authorize",
        client_id="client-1",
        redirect_uri="http://127.0.0.1:8765/callback",
        scope="openid profile",
    )
    assert result["status"] == "ok"
    assert str(result.get("authorization_url") or "").startswith("https://issuer.example/oauth/authorize?")
    parsed = urllib.parse.urlparse(str(result["authorization_url"]))
    query = urllib.parse.parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-1"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/callback"]
    assert query["scope"] == ["openid profile"]
    assert query["state"] == [result["state"]]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [query["code_challenge"][0]]
    assert result["code_verifier"]


def test_exchange_pkce_authorization_code_success_and_invalid_state() -> None:
    def fake_http_client(**_kwargs):
        return {
            "status_code": 200,
            "body": json.dumps(
                {
                    "access_token": "pkce-at",
                    "refresh_token": "pkce-rt",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            ),
        }

    ok = exchange_pkce_authorization_code(
        token_endpoint="https://issuer.example/oauth/token",
        client_id="client-1",
        code="auth-code-1",
        redirect_uri="http://127.0.0.1:8765/callback",
        code_verifier="verifier-1",
        expected_state="state-1",
        returned_state="state-1",
        http_client=fake_http_client,
    )
    assert ok["status"] == "ok"
    assert ok["access_token"] == "pkce-at"
    assert ok["refresh_token"] == "pkce-rt"

    bad_state = exchange_pkce_authorization_code(
        token_endpoint="https://issuer.example/oauth/token",
        client_id="client-1",
        code="auth-code-1",
        redirect_uri="http://127.0.0.1:8765/callback",
        code_verifier="verifier-1",
        expected_state="state-1",
        returned_state="state-2",
        http_client=fake_http_client,
    )
    assert bad_state["status"] == "error"
    assert bad_state["error_code"] == ERROR_INVALID_STATE
