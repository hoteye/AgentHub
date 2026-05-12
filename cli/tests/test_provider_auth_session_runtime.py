from __future__ import annotations

import unittest

from cli.agent_cli.providers.auth_session_runtime import (
    AuthSession,
    auth_session_status,
    ensure_auth_session_status,
)


class ProviderAuthSessionRuntimeTest(unittest.TestCase):
    def test_auth_session_status_ready_when_token_and_future_expiry(self) -> None:
        session = AuthSession(
            provider_name="deepseek",
            token_ref="default",
            access_token="at-1",
            expires_at=1_800_000_100.0,
        )
        self.assertEqual(auth_session_status(session, now_ts=1_800_000_000.0), "ready")

    def test_auth_session_status_expired_by_skew_window(self) -> None:
        session = AuthSession(
            provider_name="deepseek",
            token_ref="default",
            access_token="at-1",
            expires_at=1_800_000_020.0,
        )
        self.assertEqual(
            auth_session_status(session, now_ts=1_800_000_000.0, expiry_skew_seconds=30),
            "expired",
        )

    def test_auth_session_status_missing_invalid(self) -> None:
        missing = AuthSession(provider_name="deepseek", token_ref="default")
        self.assertEqual(auth_session_status(missing), "missing")
        invalid = AuthSession(provider_name="", token_ref="default", access_token="at-1")
        self.assertEqual(auth_session_status(invalid), "invalid")

    def test_auth_session_roundtrip_and_status_normalization(self) -> None:
        original = AuthSession(
            provider_name="qwen",
            token_ref="workspace",
            access_token="at-2",
            refresh_token="rt-2",
            token_type="Bearer",
            scope="read write",
            expires_at=1_800_000_100.0,
            issued_at=1_800_000_000.0,
            metadata={"env": "test"},
        )
        rebuilt = AuthSession.from_mapping(original.to_dict())
        self.assertEqual(rebuilt, original)
        self.assertEqual(ensure_auth_session_status("READY"), "ready")
        self.assertEqual(ensure_auth_session_status("unknown"), "invalid")

