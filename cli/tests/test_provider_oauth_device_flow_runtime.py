from __future__ import annotations

import json

from cli.agent_cli.providers.oauth_device_flow_runtime import (
    ERROR_AUTHORIZATION_PENDING,
    ERROR_EXPIRED_TOKEN,
    ERROR_INVALID_GRANT,
    ERROR_NETWORK,
    ERROR_SLOW_DOWN,
    poll_device_flow,
    refresh_oauth_token,
    start_device_flow,
)


def test_start_device_flow_returns_required_fields_and_normalized_scope() -> None:
    seen: dict[str, object] = {}

    def fake_http_client(**kwargs):
        seen.update(kwargs)
        return {
            "status_code": 200,
            "body": json.dumps(
                {
                    "device_code": "dc-1",
                    "verification_uri": "https://verify.example/device",
                    "verification_uri_complete": "https://verify.example/device?code=ABCD",
                    "user_code": "ABCD-1234",
                    "interval": 7,
                    "expires_in": 1800,
                }
            ),
        }

    result = start_device_flow(
        device_authorization_endpoint="https://issuer.example/device_authorization",
        client_id="client-1",
        scope=["openid", "profile"],
        http_client=fake_http_client,
    )

    assert result["status"] == "ok"
    assert result["verification_uri"] == "https://verify.example/device"
    assert result["user_code"] == "ABCD-1234"
    assert result["interval"] == 7
    assert seen["url"] == "https://issuer.example/device_authorization"
    assert seen["data"]["scope"] == "openid profile"
    assert seen["data"]["client_id"] == "client-1"


def test_poll_device_flow_pending_slow_down_expired_and_authorized() -> None:
    responses = [
        {"status_code": 400, "body": json.dumps({"error": ERROR_AUTHORIZATION_PENDING})},
        {"status_code": 400, "body": json.dumps({"error": ERROR_SLOW_DOWN, "interval": 9})},
        {"status_code": 400, "body": json.dumps({"error": ERROR_EXPIRED_TOKEN})},
        {
            "status_code": 200,
            "body": json.dumps(
                {
                    "access_token": "at-1",
                    "refresh_token": "rt-1",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid profile",
                }
            ),
        },
    ]

    def fake_http_client(**_kwargs):
        return responses.pop(0)

    pending = poll_device_flow(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        device_code="dc-1",
        http_client=fake_http_client,
    )
    assert pending == {
        "status": "pending",
        "error_code": ERROR_AUTHORIZATION_PENDING,
        "retry_after_seconds": 0,
    }

    slow_down = poll_device_flow(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        device_code="dc-1",
        http_client=fake_http_client,
    )
    assert slow_down["status"] == "slow_down"
    assert slow_down["error_code"] == ERROR_SLOW_DOWN
    assert slow_down["retry_after_seconds"] == 9

    expired = poll_device_flow(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        device_code="dc-1",
        http_client=fake_http_client,
    )
    assert expired == {"status": "expired", "error_code": ERROR_EXPIRED_TOKEN}

    authorized = poll_device_flow(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        device_code="dc-1",
        http_client=fake_http_client,
    )
    assert authorized["status"] == "authorized"
    assert authorized["access_token"] == "at-1"
    assert authorized["refresh_token"] == "rt-1"


def test_refresh_oauth_token_success_and_invalid_grant() -> None:
    responses = [
        {
            "status_code": 200,
            "body": json.dumps(
                {
                    "access_token": "at-refresh",
                    "refresh_token": "rt-new",
                    "token_type": "Bearer",
                    "expires_in": 7200,
                }
            ),
        },
        {
            "status_code": 400,
            "body": json.dumps(
                {
                    "error": ERROR_INVALID_GRANT,
                    "error_description": "refresh token revoked",
                }
            ),
        },
    ]

    def fake_http_client(**_kwargs):
        return responses.pop(0)

    ok_result = refresh_oauth_token(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        refresh_token="rt-old",
        http_client=fake_http_client,
    )
    assert ok_result["status"] == "ok"
    assert ok_result["access_token"] == "at-refresh"
    assert ok_result["refresh_token"] == "rt-new"

    invalid_grant = refresh_oauth_token(
        token_endpoint="https://issuer.example/token",
        client_id="client-1",
        refresh_token="rt-old",
        http_client=fake_http_client,
    )
    assert invalid_grant["status"] == "error"
    assert invalid_grant["error_code"] == ERROR_INVALID_GRANT
    assert "revoked" in invalid_grant["error_description"]


def test_start_device_flow_returns_network_error_code_from_http_client() -> None:
    def fake_http_client(**_kwargs):
        return {"error": ERROR_NETWORK, "error_detail": "dial tcp timeout"}

    result = start_device_flow(
        device_authorization_endpoint="https://issuer.example/device_authorization",
        client_id="client-1",
        http_client=fake_http_client,
    )

    assert result["status"] == "error"
    assert result["error_code"] == ERROR_NETWORK
