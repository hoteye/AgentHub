from __future__ import annotations

from cli.agent_cli.gateway_protocol import (
    ErrorCodes,
    error_frame,
    error_shape,
    event_frame,
    parse_gateway_frame,
    request_frame,
    success_frame,
)

def test_gateway_protocol_request_success_error_and_event_frames_roundtrip() -> None:
    request = request_frame(request_id="req-1", method="gateway.state", params={"limit": 5})
    success = success_frame(request_id="req-1", result={"ok": True, "count": 1})
    failure = error_frame(
        request_id="req-1",
        error=error_shape(ErrorCodes.INVALID_REQUEST, "invalid params", details={"field": "limit"}),
    )
    event = event_frame(event_type="gateway.audit.appended", data={"audit_id": "audit-1"})

    assert request.to_dict()["method"] == "gateway.state"
    assert success.to_dict()["ok"] is True
    assert failure.to_dict()["error"]["code"] == ErrorCodes.INVALID_REQUEST
    assert event.to_dict()["event_type"] == "gateway.audit.appended"

    assert parse_gateway_frame(request.to_dict()) == request
    assert parse_gateway_frame(success.to_dict()) == success
    assert parse_gateway_frame(failure.to_dict()) == failure
    assert parse_gateway_frame(event.to_dict()) == event

def test_gateway_protocol_rejects_unknown_frame_shape() -> None:
    try:
        parse_gateway_frame({"protocol_version": "v1", "request_id": "req-1"})
    except ValueError as exc:
        assert "unrecognized gateway frame shape" in str(exc)
    else:
        raise AssertionError("expected ValueError")

def test_gateway_protocol_validates_required_request_fields() -> None:
    try:
        request_frame(request_id="", method="gateway.state")
    except ValueError as exc:
        assert "request_id is required" in str(exc)
    else:
        raise AssertionError("expected ValueError")
