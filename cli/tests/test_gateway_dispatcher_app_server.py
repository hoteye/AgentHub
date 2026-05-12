from __future__ import annotations

import io
import json
from unittest.mock import Mock, patch

from cli.agent_cli.app_server import AgentCliAppServer
from cli.agent_cli.app_server_protocol_runtime import (
    APP_SERVER_BASE_METHODS,
    APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
    APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED,
    APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT,
    APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
    APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
    APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED,
    REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS,
    app_server_gateway_extension_methods,
)
from cli.agent_cli.gateway_server.dispatcher import GatewayDispatchResult

class _Runtime:
    def __init__(self) -> None:
        self.agent = type(
            "Agent",
            (),
            {
                "provider_status": staticmethod(
                    lambda: {
                        "platform_family": "linux",
                        "platform_os": "linux",
                        "shell_kind": "bash",
                        "provider_label": "test-provider",
                    }
                )
            },
        )()

    @staticmethod
    def has_active_run() -> bool:
        return False

def _server() -> tuple[AgentCliAppServer, io.StringIO]:
    stdout = io.StringIO()
    server = AgentCliAppServer(runtime=_Runtime(), action_worker=object(), stdin=io.StringIO(), stdout=stdout)
    server.state.initialized = True
    server.state.initialized_notification_received = True
    server.state.client_info = {"name": "dispatcher-test-client"}
    return server, stdout


def _uninitialized_server() -> tuple[AgentCliAppServer, io.StringIO]:
    stdout = io.StringIO()
    server = AgentCliAppServer(runtime=_Runtime(), action_worker=object(), stdin=io.StringIO(), stdout=stdout)
    server.state.initialized = False
    server.state.client_info = {"name": "dispatcher-test-client"}
    return server, stdout

def test_app_server_routes_gateway_methods_through_dispatcher() -> None:
    server, stdout = _server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = GatewayDispatchResult(
            ok=True,
            result={"workflowRuns": [], "source": "dispatcher"},
        )
        server._handle_line(json.dumps({"id": "gw-1", "method": "gateway.state.get", "params": {"limit": 5}}))

    dispatch_mock.assert_called_once()
    call = dispatch_mock.call_args.kwargs
    assert call["method"] == "gateway.state.get"
    assert call["params"] == {"limit": 5}
    assert call["client_info"]["name"] == "dispatcher-test-client"
    assert call["client_info"]["connId"].startswith("conn_")

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [{"id": "gw-1", "result": {"workflowRuns": [], "source": "dispatcher"}}]

def test_app_server_preserves_explicit_conn_id_in_gateway_client_info() -> None:
    server, _ = _server()
    server.state.client_info = {"name": "dispatcher-test-client", "connId": "client-conn-fixed"}

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = GatewayDispatchResult(
            ok=True,
            result={"ok": True},
        )
        server._handle_line(json.dumps({"id": "gw-conn", "method": "gateway.state.get", "params": {"limit": 1}}))

    call = dispatch_mock.call_args.kwargs
    assert call["client_info"]["connId"] == "client-conn-fixed"

def test_app_server_preserves_transport_followup_for_approval_results() -> None:
    server, stdout = _server()
    register_mock = Mock()
    server._register_approved_shell_session = register_mock  # type: ignore[method-assign]

    approval_result = {
        "approval_ticket": {"approval_id": "approval_1"},
        "action_request": {"action_id": "action_1"},
        "action_result": {"result_id": "result_1"},
        "audit_records": [],
    }
    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = GatewayDispatchResult(
            ok=True,
            result={"approvalTicket": {"approval_id": "approval_1"}},
            transport_context={"approval_decision_result": approval_result},
        )
        server._handle_line(
            json.dumps(
                {
                    "id": "approve-1",
                    "method": "approvals.resolve",
                    "params": {"approvalId": "approval_1", "decision": "approved"},
                }
            )
        )

    register_mock.assert_called_once_with(request_id="approve-1", result=approval_result)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [{"id": "approve-1", "result": {"approvalTicket": {"approval_id": "approval_1"}}}]

def test_app_server_emits_dispatcher_errors_as_transport_errors() -> None:
    server, stdout = _server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = GatewayDispatchResult(
            ok=False,
            error_code=-32601,
            error_message=APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
            error_data={"detail": "gateway.unknown"},
        )
        server._handle_line(json.dumps({"id": "gw-404", "method": "gateway.unknown", "params": {}}))

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [
        {
            "id": "gw-404",
            "error": {
                "code": -32601,
                "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
                "data": {"detail": "gateway.unknown"},
            },
        }
    ]


def test_app_server_emits_dispatcher_invalid_params_error_as_transport_error_with_stable_detail() -> None:
    server, stdout = _server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        dispatch_mock.return_value = GatewayDispatchResult(
            ok=False,
            error_code=-32602,
            error_message=APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
            error_data={"detail": APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT},
        )
        server._handle_line(json.dumps({"id": "gw-params-1", "method": "gateway.state.get", "params": {"limit": 5}}))

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [
        {
            "id": "gw-params-1",
            "error": {
                "code": -32602,
                "message": APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
                "data": {"detail": APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT},
            },
        }
    ]


def test_app_server_unsupported_matrix_contract_not_initialized_invalid_params_and_method_not_found() -> None:
    server, stdout = _uninitialized_server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        server._handle_line(json.dumps({"id": "pre-init", "method": "skills/list", "params": {}}))
    dispatch_mock.assert_not_called()

    pre_init_lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert pre_init_lines == [
        {
            "id": "pre-init",
            "error": {
                "code": -32002,
                "message": APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED,
                "data": {"detail": APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED},
            },
        }
    ]

    initialized_server, initialized_stdout = _server()
    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        initialized_server._handle_line(json.dumps({"id": "invalid-params", "method": "skills/list", "params": []}))
        initialized_server._handle_line(json.dumps({"id": "unsupported", "method": "skills/list", "params": {}}))
        initialized_server._handle_line(json.dumps({"id": "unknown-method", "method": "missing/method", "params": {}}))
    dispatch_mock.assert_not_called()

    lines = [json.loads(line) for line in initialized_stdout.getvalue().splitlines() if line.strip()]
    errors = {item["id"]: item["error"] for item in lines}
    assert errors["invalid-params"] == {
        "code": -32602,
        "message": APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
        "data": {"detail": APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT},
    }
    assert errors["unsupported"] == {
        "code": -32601,
        "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
        "data": {
            "detail": "skills/list",
            "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            "replacement": str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"]),
        },
    }
    assert errors["unknown-method"] == {
        "code": -32601,
        "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
        "data": {"detail": "missing/method"},
    }


def test_app_server_unsupported_reference_method_does_not_route_to_gateway_dispatcher() -> None:
    server, stdout = _server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        server._handle_line(json.dumps({"id": "unsupported-1", "method": "skills/list", "params": {}}))

    dispatch_mock.assert_not_called()
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [
        {
            "id": "unsupported-1",
            "error": {
                "code": -32601,
                "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
                "data": {
                    "detail": "skills/list",
                    "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
                    "replacement": "tools/list",
                },
            },
        }
    ]


def test_app_server_unsupported_reference_replacement_paths_bypass_gateway_dispatcher() -> None:
    server, stdout = _server()

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        server._handle_line(json.dumps({"id": "unsupported-turn-interrupt", "method": "turn/interrupt", "params": {"threadId": "thr_1", "turnId": "turn_1"}}))
        server._handle_line(json.dumps({"id": "unsupported-config-read", "method": "config/read", "params": {}}))

    dispatch_mock.assert_not_called()
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    errors = {item["id"]: item["error"] for item in lines}

    assert errors["unsupported-turn-interrupt"]["data"] == {
        "detail": "turn/interrupt",
        "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
        "replacement": "session/interrupt",
    }
    assert errors["unsupported-config-read"]["data"] == {
        "detail": "config/read",
        "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
        "replacement": "session/providerStatus",
    }

    for request_id in ("unsupported-turn-interrupt", "unsupported-config-read"):
        data = errors[request_id]["data"]
        replacement = data["replacement"]
        detail = data["detail"]
        assert isinstance(replacement, str)
        assert replacement.strip()
        assert replacement != detail
        assert "unsupported" not in replacement.casefold()
        assert "unknown" not in replacement.casefold()


def test_gateway_unsupported_replacements_are_reachable_from_app_server_surface() -> None:
    server, stdout = _server()
    reachable = set(APP_SERVER_BASE_METHODS) | set(app_server_gateway_extension_methods())
    unsupported_requests = [
        {"id": "unsupported-turn-interrupt", "method": "turn/interrupt", "params": {"threadId": "thr_1", "turnId": "turn_1"}},
        {"id": "unsupported-skills-list", "method": "skills/list", "params": {}},
        {"id": "unsupported-config-read", "method": "config/read", "params": {}},
    ]

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        for request in unsupported_requests:
            server._handle_line(json.dumps(request))
    dispatch_mock.assert_not_called()

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    for line in lines:
        error = dict(line.get("error") or {})
        data = dict(error.get("data") or {})
        replacement = str(data.get("replacement") or "").strip()
        assert replacement in reachable, f"gateway replacement unreachable: {line.get('id')} -> {replacement}"


def test_gateway_unsupported_replacement_consistency_guard() -> None:
    server, stdout = _server()
    requests = [
        {"id": "turn-a", "method": "turn/interrupt", "params": {"threadId": "thr_1", "turnId": "turn_1"}},
        {"id": "turn-b", "method": "turn/interrupt", "params": {"threadId": "thr_2", "turnId": "turn_2"}},
        {"id": "skills-a", "method": "skills/list", "params": {}},
        {"id": "skills-b", "method": "skills/list", "params": {"limit": 5}},
    ]

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        for request in requests:
            server._handle_line(json.dumps(request))
    dispatch_mock.assert_not_called()

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    replacements_by_method: dict[str, set[str]] = {}
    for line in lines:
        error = dict(line.get("error") or {})
        data = dict(error.get("data") or {})
        method = str(data.get("detail") or "").strip()
        replacement = str(data.get("replacement") or "").strip()
        replacements_by_method.setdefault(method, set()).add(replacement)

    assert replacements_by_method["turn/interrupt"] == {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["turn/interrupt"])}
    assert replacements_by_method["skills/list"] == {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"])}


def test_gateway_unsupported_replacement_field_guard_for_two_methods_with_param_variants() -> None:
    server, stdout = _server()
    requests = [
        {"id": "turn-a", "method": "turn/interrupt", "params": {"threadId": "thr_1", "turnId": "turn_1"}},
        {"id": "turn-b", "method": "turn/interrupt", "params": {"threadId": "thr_2", "turnId": "turn_2"}},
        {"id": "skills-a", "method": "skills/list", "params": {}},
        {"id": "skills-b", "method": "skills/list", "params": {"limit": 5}},
    ]

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        for request in requests:
            server._handle_line(json.dumps(request))
    dispatch_mock.assert_not_called()

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    request_matrix = [
        ("turn-a", "turn/interrupt"),
        ("turn-b", "turn/interrupt"),
        ("skills-a", "skills/list"),
        ("skills-b", "skills/list"),
    ]
    replacements_by_method: dict[str, set[str]] = {}
    for request_id, method in request_matrix:
        payload = next(item for item in lines if item.get("id") == request_id)
        error = dict(payload.get("error") or {})
        assert error.get("code") == -32601
        assert error.get("message") == APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND
        data = dict(error.get("data") or {})
        assert data.get("detail") == method
        assert data.get("compatibility") == APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD
        assert "replacement" in data
        replacement = str(data.get("replacement") or "").strip()
        assert replacement
        replacements_by_method.setdefault(method, set()).add(replacement)

    assert replacements_by_method["turn/interrupt"] == {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["turn/interrupt"])}
    assert replacements_by_method["skills/list"] == {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"])}


def test_gateway_unsupported_observation_snapshot_guard() -> None:
    server, stdout = _server()
    requests = [
        {"id": "obs-turn-interrupt", "method": "turn/interrupt", "params": {"threadId": "thr_1", "turnId": "turn_1"}},
        {"id": "obs-skills", "method": "skills/list", "params": {}},
        {"id": "obs-config-read", "method": "config/read", "params": {}},
    ]

    with patch("cli.agent_cli.app_server.dispatch_gateway_method") as dispatch_mock:
        for request in requests:
            server._handle_line(json.dumps(request))
    dispatch_mock.assert_not_called()

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    observations: list[dict[str, str | int]] = []
    for line in lines:
        assert list(line.keys()) == ["id", "error"]
        error = dict(line.get("error") or {})
        assert list(error.keys()) == ["code", "message", "data"]
        data = dict(error.get("data") or {})
        assert list(data.keys()) == ["detail", "compatibility", "replacement"]
        observations.append(
            {
                "id": str(line["id"]),
                "code": int(error["code"]),
                "message": str(error["message"]),
                "detail": str(data["detail"]),
                "compatibility": str(data["compatibility"]),
                "replacement": str(data["replacement"]),
            }
        )

    assert observations == [
        {
            "id": "obs-turn-interrupt",
            "code": -32601,
            "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
            "detail": "turn/interrupt",
            "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            "replacement": str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["turn/interrupt"]),
        },
        {
            "id": "obs-skills",
            "code": -32601,
            "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
            "detail": "skills/list",
            "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            "replacement": str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"]),
        },
        {
            "id": "obs-config-read",
            "code": -32601,
            "message": APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
            "detail": "config/read",
            "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            "replacement": str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["config/read"]),
        },
    ]


def test_app_server_rejects_gateway_method_when_client_auth_is_explicitly_unauthenticated() -> None:
    server, stdout = _server()
    server.state.client_info = {"role": "operator", "actorId": "operator-1", "authenticated": False}

    server._handle_line(json.dumps({"id": "gw-auth-1", "method": "gateway.state.get", "params": {"limit": 5}}))

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines == [
        {
            "id": "gw-auth-1",
            "error": {
                "code": -32041,
                "message": "authenticated gateway auth context is required",
                "data": {
                    "gatewayCode": "UNAUTHORIZED",
                    "details": {
                        "method": "gateway.state.get",
                        "required_scopes": ["gateway.read"],
                        "missing_scopes": [],
                        "allowed_roles": ["operator", "system"],
                        "control_plane_write": False,
                    },
                },
            },
        }
    ]
