from __future__ import annotations

import io
import json
import shlex
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.main import main
from cli.agent_cli.providers.auth_token_store_runtime import FileAuthTokenStore
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command
from cli.agent_cli.slash_parser import parse_slash_invocation


def _parse_args(arg_text: str):
    tokens = shlex.split(str(arg_text or "").strip()) if str(arg_text or "").strip() else []
    positionals: list[str] = []
    options: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key = token[2:]
            value: object = True
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                value = tokens[index + 1]
                index += 1
            options[key] = value
        else:
            positionals.append(token)
        index += 1
    return positionals, options


def _runtime_with_catalog(
    *,
    auth_path: Path,
    provider_name: str = "openai",
    auth_mode: str = "oauth",
    auth_payload: dict[str, object] | None = None,
    status_extra: dict[str, object] | None = None,
) -> SimpleNamespace:
    provider_entry = SimpleNamespace(
        auth_mode=auth_mode,
        auth=dict(auth_payload or {}),
        base_url="https://relay.example/v1",
    )
    catalog = SimpleNamespace(providers={provider_name: provider_entry})
    status_payload = {
        "provider_public_name": provider_name,
        "provider_name": provider_name,
        "provider_route_name": provider_name,
        "auth_mode": auth_mode,
        "provider_auth_path": str(auth_path),
    }
    status_payload.update(dict(status_extra or {}))
    agent = SimpleNamespace(
        provider_status=lambda: dict(status_payload),
        _load_provider_catalog=lambda **_kwargs: catalog,
        _provider_loader_kwargs=lambda: {},
        available_providers=lambda: [
            {
                "provider_name": provider_name,
                "config_provider_name": provider_name,
            }
        ],
    )
    return SimpleNamespace(
        _parse_args=_parse_args,
        cwd=str(auth_path.parent),
        agent=agent,
    )


def _switch_disabled_result(exc: Exception):
    return str(exc), []


def test_auth_status_reads_real_session_state_and_required_fields() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "device_authorization_endpoint": "https://issuer.example/device",
                "token_ref": "default",
            },
        )
        text, events = handle_provider_command(
            runtime,
            name="auth",
            arg_text="status --provider openai",
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])
    assert events == []
    assert "auth status" in text
    assert "provider_name=openai" in text
    assert "auth_mode=oauth" in text
    assert "auth_status=missing" in text
    assert "token_ref=default" in text
    assert "token_source=" in text
    assert "next_action=/auth login provider openai mode device_code" in text


def test_auth_status_reads_user_auth_store_for_project_local_provider() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        project_auth_path = root / "project" / ".config" / "auth.json"
        user_auth_path = root / "home" / ".agent_cli" / "auth.json"
        user_auth_path.parent.mkdir(parents=True, exist_ok=True)
        user_auth_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "openai::default": {
                            "provider_name": "openai",
                            "token_ref": "default",
                            "access_token": "at-user",
                            "refresh_token": "rt-user",
                            "expires_at": time.time() + 3600,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        runtime = _runtime_with_catalog(
            auth_path=project_auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "device_authorization_endpoint": "https://issuer.example/device",
                "token_ref": "default",
            },
            status_extra={"provider_config_scope": "project_local"},
        )
        with patch(
            "cli.agent_cli.runtime_core.provider_commands_auth_patchpoint_helpers_runtime.resolve_user_provider_auth_path",
            return_value=user_auth_path,
        ):
            text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="status --provider openai",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])

    assert events == []
    assert "auth_status=ready" in text
    assert f"token_source={user_auth_path}:sessions" in text


def test_auth_status_slash_invocation_native_path_does_not_require_cli_parse_args() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "device_authorization_endpoint": "https://issuer.example/device",
                "token_ref": "default",
            },
        )
        delattr(runtime, "_parse_args")
        text, events = handle_provider_command(
            runtime,
            name="auth",
            arg_text="",
            slash_invocation=parse_slash_invocation("/auth status provider openai"),
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])
    assert events == []
    assert "auth status" in text
    assert "provider_name=openai" in text
    assert "auth_status=missing" in text


def test_auth_login_device_code_start_and_poll_authorized() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "device_authorization_endpoint": "https://issuer.example/device",
                "token_ref": "default",
            },
        )
        with patch(
            "cli.agent_cli.runtime_core.provider_commands.start_device_flow",
            return_value={
                "status": "ok",
                "device_code": "dc-1",
                "verification_uri": "https://issuer.example/verify",
                "user_code": "ABCD-1234",
            },
        ):
            start_text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode device_code",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth_status=authorization_pending" in start_text
        assert "verification_uri=https://issuer.example/verify" in start_text

        with patch(
            "cli.agent_cli.runtime_core.provider_commands.poll_device_flow",
            return_value={
                "status": "authorized",
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        ):
            poll_text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode device_code --poll",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth login" in poll_text
        assert "auth_status=ready" in poll_text
        assert "next_action=/auth status provider openai" in poll_text


def test_auth_refresh_updates_existing_session() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        auth_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "openai::default": {
                            "provider_name": "openai",
                            "token_ref": "default",
                            "access_token": "old-at",
                            "refresh_token": "old-rt",
                            "metadata": {
                                "token_endpoint": "https://issuer.example/token",
                                "client_id": "client-1",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "token_ref": "default",
            },
        )
        with patch(
            "cli.agent_cli.runtime_core.provider_commands.refresh_oauth_token",
            return_value={
                "status": "ok",
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "token_type": "Bearer",
                "expires_in": 7200,
            },
        ):
            text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="refresh --provider openai",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth refresh" in text
        assert "auth_status=ready" in text
        store = FileAuthTokenStore(store_path=auth_path)
        stored = store.get("openai", "default")
        assert stored is not None
        assert stored.access_token == "new-at"
        assert stored.refresh_token == "new-rt"


def test_auth_login_browser_pkce_start_and_exchange() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_mode="wellknown",
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "authorization_endpoint": "https://issuer.example/authorize",
                "token_ref": "default",
            },
        )
        with patch(
            "cli.agent_cli.runtime_core.provider_commands.start_pkce_authorization",
            return_value={
                "status": "ok",
                "authorization_url": "https://issuer.example/authorize?x=1",
                "state": "state-1",
                "code_verifier": "verifier-1",
            },
        ):
            start_text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode browser_pkce",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth_status=authorization_url_ready" in start_text
        assert "authorization_url=https://issuer.example/authorize?x=1" in start_text

        with patch(
            "cli.agent_cli.runtime_core.provider_commands.exchange_pkce_authorization_code",
            return_value={
                "status": "ok",
                "access_token": "pkce-at",
                "refresh_token": "pkce-rt",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        ):
            exchange_text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode browser_pkce --auth-code code-1 --state state-1",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth login" in exchange_text
        assert "auth_status=ready" in exchange_text


def test_auth_login_browser_pkce_wait_callback_auto_exchange() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_mode="wellknown",
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "authorization_endpoint": "https://issuer.example/authorize",
                "token_ref": "default",
            },
        )
        with (
            patch(
                "cli.agent_cli.runtime_core.provider_commands.start_pkce_authorization",
                return_value={
                    "status": "ok",
                    "authorization_url": "https://issuer.example/authorize?x=1",
                    "state": "state-1",
                    "code_verifier": "verifier-1",
                },
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands.wait_for_pkce_callback",
                return_value={
                    "status": "ok",
                    "code": "code-from-callback",
                    "state": "state-1",
                },
            ) as wait_callback_mock,
            patch(
                "cli.agent_cli.runtime_core.provider_commands.exchange_pkce_authorization_code",
                return_value={
                    "status": "ok",
                    "access_token": "pkce-at",
                    "refresh_token": "pkce-rt",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            ) as exchange_mock,
        ):
            text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode browser_pkce --wait-callback",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth login" in text
        assert "auth_status=ready" in text
        wait_callback_mock.assert_called_once()
        assert exchange_mock.call_args is not None
        kwargs = dict(exchange_mock.call_args.kwargs)
        assert kwargs.get("code") == "code-from-callback"
        assert kwargs.get("returned_state") == "state-1"


def test_auth_login_browser_pkce_wait_callback_timeout_surface() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_mode="wellknown",
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "authorization_endpoint": "https://issuer.example/authorize",
                "token_ref": "default",
            },
        )
        with (
            patch(
                "cli.agent_cli.runtime_core.provider_commands.start_pkce_authorization",
                return_value={
                    "status": "ok",
                    "authorization_url": "https://issuer.example/authorize?x=1",
                    "state": "state-1",
                    "code_verifier": "verifier-1",
                },
            ),
            patch(
                "cli.agent_cli.runtime_core.provider_commands.wait_for_pkce_callback",
                return_value={
                    "status": "timeout",
                    "error_code": "pkce_callback_timeout",
                },
            ),
        ):
            text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="login --provider openai --mode browser_pkce --wait-callback --callback-timeout-seconds 5",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "auth_status=authorization_pending" in text
        assert "authorization_url=https://issuer.example/authorize?x=1" in text
        assert "error_code=pkce_callback_timeout" in text


def test_auth_refresh_auto_daemon_start_status_stop() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        auth_path.write_text(
            json.dumps(
                {
                    "sessions": {
                        "openai::default": {
                            "provider_name": "openai",
                            "token_ref": "default",
                            "access_token": "old-at",
                            "refresh_token": "old-rt",
                            "expires_at": 1.0,
                            "metadata": {
                                "token_endpoint": "https://issuer.example/token",
                                "client_id": "client-1",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "token_ref": "default",
            },
        )
        stop_text = ""
        try:
            with patch(
                "cli.agent_cli.runtime_core.provider_commands.refresh_oauth_token",
                return_value={
                    "status": "ok",
                    "access_token": "new-at",
                    "refresh_token": "new-rt",
                    "token_type": "Bearer",
                    "expires_in": 7200,
                },
            ):
                start_text, events = handle_provider_command(
                    runtime,
                    name="auth",
                    arg_text="refresh --provider openai --auto --daemon start --interval-seconds 3600",
                    switch_disabled_result=_switch_disabled_result,
                ) or ("", [])
                assert events == []
                assert "auth refresh" in start_text
                assert (
                    "daemon_result=started" in start_text
                    or "daemon_result=already_running" in start_text
                )
                assert "daemon_status=running" in start_text
                time.sleep(0.05)
                status_text, events = handle_provider_command(
                    runtime,
                    name="auth",
                    arg_text="refresh --provider openai --auto --daemon status",
                    switch_disabled_result=_switch_disabled_result,
                ) or ("", [])
                assert events == []
                assert "daemon_status=running" in status_text
                assert "daemon_running=true" in status_text
        finally:
            stop_text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="refresh --provider openai --auto --daemon stop",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
            assert events == []
    assert "daemon_result=stopped" in stop_text or "daemon_result=already_stopped" in stop_text
    assert "daemon_running=false" in stop_text


def test_auth_refresh_auto_managed_daemon_control_surface() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(
            auth_path=auth_path,
            auth_payload={
                "client_id": "client-1",
                "token_endpoint": "https://issuer.example/token",
                "token_ref": "default",
            },
        )
        with patch(
            "cli.agent_cli.runtime_core.provider_commands.start_managed_refresh_daemon",
            return_value={
                "result": "started",
                "daemon_mode": "managed",
                "daemon_status": "running",
                "running": True,
                "healthy": True,
                "alert_level": "ok",
                "pid": 4321,
                "interval_seconds": 60,
                "refresh_window_seconds": 300,
                "loop_count": 2,
                "contexts": 1,
                "refreshed": 1,
                "skipped": 0,
                "failed": 0,
            },
        ):
            text, events = handle_provider_command(
                runtime,
                name="auth",
                arg_text="refresh --provider openai --auto --daemon start --managed",
                switch_disabled_result=_switch_disabled_result,
            ) or ("", [])
        assert events == []
        assert "daemon_mode=managed" in text
        assert "daemon_result=started" in text
        assert "daemon_status=running" in text
        assert "healthy=true" in text
        assert "pid=4321" in text


def test_auth_login_requires_oauth_like_mode() -> None:
    with TemporaryDirectory() as temp_dir:
        auth_path = Path(temp_dir) / "auth.json"
        runtime = _runtime_with_catalog(auth_path=auth_path, auth_mode="api_key")
        text, events = handle_provider_command(
            runtime,
            name="auth",
            arg_text="login --provider openai",
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])
    assert events == []
    assert "auth_status=action_not_executed" in text
    assert "error_code=auth_mode_not_oauth" in text


def test_auth_unknown_subcommand_returns_usage_and_error_contract() -> None:
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime_with_catalog(auth_path=Path(temp_dir) / "auth.json")
        text, events = handle_provider_command(
            runtime,
            name="auth",
            arg_text="foobar",
            switch_disabled_result=_switch_disabled_result,
        ) or ("", [])
    assert events == []
    assert text.startswith("Usage: /auth <status|login|refresh|logout> [provider <name>]")
    assert "error_code=invalid_subcommand" in text
    assert "error_hint=supported subcommands: status, login, refresh, logout" in text
    assert "next_action=/auth status" in text


def test_auth_headless_json_output_keeps_required_fields() -> None:
    runtime = AgentCliRuntime()
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(
        [
            "--headless",
            "--prompt",
            "/auth status --provider openai",
            "--json",
        ],
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert "provider_name=" in payload["assistant_text"]
    assert "auth_mode=" in payload["assistant_text"]
    assert "auth_status=" in payload["assistant_text"]
    assert "next_action=" in payload["assistant_text"]
