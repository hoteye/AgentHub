from __future__ import annotations

from cli.agent_cli.gateway_protocol import ErrorCodes, GatewayProtocolError, error_shape

def test_gateway_protocol_error_shape_uses_known_codes_only() -> None:
    shaped = error_shape(
        ErrorCodes.UNAVAILABLE,
        "gateway unavailable",
        retryable=True,
        retry_after_ms=500,
    )

    assert shaped.code == ErrorCodes.UNAVAILABLE
    assert shaped.retryable is True
    assert shaped.retry_after_ms == 500
    assert shaped.to_dict()["code"] == ErrorCodes.UNAVAILABLE

def test_gateway_protocol_error_exception_exposes_error_payload() -> None:
    exc = GatewayProtocolError(
        ErrorCodes.FORBIDDEN,
        "scope missing",
        details={"required_scope": "gateway:write"},
    )

    assert exc.code == ErrorCodes.FORBIDDEN
    assert exc.to_dict()["details"]["required_scope"] == "gateway:write"

def test_gateway_protocol_error_shape_rejects_unknown_code() -> None:
    try:
        error_shape("bad_code", "invalid")
    except ValueError as exc:
        assert "unknown gateway error code" in str(exc)
    else:
        raise AssertionError("expected ValueError")
