from __future__ import annotations

import time
from pathlib import Path

from cli.agent_cli.providers.auth_refresh_scheduler_runtime import (
    RefreshDaemonHandle,
    RefreshProviderContext,
    refresh_due_sessions,
    refresh_daemon_status,
    session_refresh_due,
    start_refresh_daemon,
    stop_refresh_daemon,
)
from cli.agent_cli.providers.auth_session_runtime import AuthSession
from cli.agent_cli.providers.auth_token_store_runtime import FileAuthTokenStore


def test_session_refresh_due_window() -> None:
    session = AuthSession(
        provider_name="openai",
        token_ref="default",
        access_token="at",
        refresh_token="rt",
        expires_at=1_800_000_250.0,
    )
    assert session_refresh_due(session, now_ts=1_800_000_000.0, refresh_window_seconds=300) is True
    assert session_refresh_due(session, now_ts=1_800_000_000.0, refresh_window_seconds=120) is False


def test_refresh_due_sessions_refreshes_only_due_items(tmp_path: Path) -> None:
    store = FileAuthTokenStore(store_path=tmp_path / "auth.json")
    store.put(
        AuthSession(
            provider_name="openai",
            token_ref="default",
            access_token="old-at",
            refresh_token="old-rt",
            expires_at=1_800_000_010.0,
            metadata={"token_endpoint": "https://issuer.example/token", "client_id": "client-1"},
        )
    )
    store.put(
        AuthSession(
            provider_name="wk",
            token_ref="default",
            access_token="wk-at",
            refresh_token="wk-rt",
            expires_at=1_800_010_000.0,
        )
    )

    def fake_refresh(**kwargs):
        if str(kwargs.get("client_id")) == "client-1":
            return {
                "status": "ok",
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expires_in": 7200,
                "token_type": "Bearer",
            }
        return {"status": "error", "error_code": "unexpected"}

    summary = refresh_due_sessions(
        store=store,
        contexts=[
            RefreshProviderContext(
                provider_name="openai",
                token_ref="default",
                token_endpoint="https://issuer.example/token",
                client_id="client-1",
            ),
            RefreshProviderContext(
                provider_name="wk",
                token_ref="default",
                token_endpoint="https://issuer.example/token",
                client_id="client-2",
            ),
        ],
        now_ts=1_800_000_000.0,
        refresh_window_seconds=300,
        refresh_fn=fake_refresh,
    )
    assert summary["status"] == "ok"
    assert summary["refreshed"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 0

    refreshed = store.get("openai", "default")
    assert refreshed is not None
    assert refreshed.access_token == "new-at"
    assert refreshed.refresh_token == "new-rt"


def test_refresh_daemon_start_status_stop_runs_loop(tmp_path: Path) -> None:
    store = FileAuthTokenStore(store_path=tmp_path / "auth.json")
    store.put(
        AuthSession(
            provider_name="openai",
            token_ref="default",
            access_token="old-at",
            refresh_token="old-rt",
            expires_at=1.0,
        )
    )

    def contexts_provider() -> list[RefreshProviderContext]:
        return [
            RefreshProviderContext(
                provider_name="openai",
                token_ref="default",
                token_endpoint="https://issuer.example/token",
                client_id="client-1",
            )
        ]

    def fake_refresh(**_kwargs):
        return {
            "status": "ok",
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "token_type": "Bearer",
            "expires_in": 1800,
        }

    handle = RefreshDaemonHandle()
    started = start_refresh_daemon(
        handle=handle,
        store=store,
        contexts_provider=contexts_provider,
        interval_seconds=3600,
        refresh_window_seconds=300,
        refresh_fn=fake_refresh,
    )
    assert started["status"] in {"started", "already_running"}

    deadline = time.time() + 1.5
    snapshot = refresh_daemon_status(handle=handle)
    while snapshot.get("loop_count", 0) == 0 and time.time() < deadline:
        time.sleep(0.05)
        snapshot = refresh_daemon_status(handle=handle)
    assert snapshot.get("running") is True
    assert int(snapshot.get("loop_count") or 0) >= 1

    stopped = stop_refresh_daemon(handle=handle, timeout_seconds=2.0)
    assert stopped["status"] in {"stopped", "already_stopped"}
    assert stopped.get("running") is False
