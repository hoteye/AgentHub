from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.providers.auth_session_runtime import AuthSession
from cli.agent_cli.providers.auth_token_encryption_runtime import (
    token_encryption_supported,
    token_keyring_path_for_store,
)
from cli.agent_cli.providers.auth_token_store_runtime import (
    FileAuthTokenStore,
    token_store_key,
)


class ProviderAuthTokenStoreRuntimeTest(unittest.TestCase):
    def test_file_store_put_get_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "auth" / "tokens.json"
            store = FileAuthTokenStore(store_path=store_path)

            session = AuthSession(
                provider_name="deepseek",
                token_ref="default",
                access_token="at-1",
                refresh_token="rt-1",
                expires_at=1_800_000_100.0,
            )
            store.put(session)

            loaded = store.get("deepseek", "default")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.access_token, "at-1")
            self.assertTrue(store.delete("deepseek", "default"))
            self.assertFalse(store.delete("deepseek", "default"))
            self.assertIsNone(store.get("deepseek", "default"))

    def test_file_store_tolerates_invalid_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "tokens.json"
            store_path.write_text("{not-json", encoding="utf-8")
            store = FileAuthTokenStore(store_path=store_path)
            self.assertIsNone(store.get("deepseek", "default"))

            session = AuthSession(provider_name="deepseek", token_ref="default", access_token="at-2")
            store.put(session)
            loaded = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["version"], 1)
            self.assertIn(token_store_key("deepseek", "default"), loaded["sessions"])

    def test_put_requires_provider_and_token_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAuthTokenStore(store_path=Path(temp_dir) / "tokens.json")
            with self.assertRaises(ValueError):
                store.put(AuthSession(provider_name="", token_ref="x", access_token="token"))
            with self.assertRaises(ValueError):
                store.put(AuthSession(provider_name="deepseek", token_ref="", access_token="token"))

    def test_file_store_encrypts_session_tokens_when_enabled(self) -> None:
        if not token_encryption_supported():
            self.skipTest("cryptography is not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "auth.json"
            with patch.dict(os.environ, {"AGENTHUB_AUTH_TOKEN_ENCRYPTION": "on"}, clear=False):
                store = FileAuthTokenStore(store_path=store_path)
                session = AuthSession(
                    provider_name="deepseek",
                    token_ref="default",
                    access_token="at-enc-1",
                    refresh_token="rt-enc-1",
                )
                store.put(session)
                raw = json.loads(store_path.read_text(encoding="utf-8"))
                stored_payload = dict(raw["sessions"][token_store_key("deepseek", "default")] or {})
                self.assertIn("_enc", stored_payload)
                self.assertNotIn("access_token", stored_payload)
                loaded = store.get("deepseek", "default")
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded.access_token, "at-enc-1")
                self.assertEqual(loaded.refresh_token, "rt-enc-1")

    def test_file_store_rotates_encryption_key_by_policy(self) -> None:
        if not token_encryption_supported():
            self.skipTest("cryptography is not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "auth.json"
            with patch.dict(
                os.environ,
                {
                    "AGENTHUB_AUTH_TOKEN_ENCRYPTION": "on",
                    "AGENTHUB_AUTH_TOKEN_ROTATE_DAYS": "1",
                },
                clear=False,
            ):
                store = FileAuthTokenStore(store_path=store_path)
                store.put(AuthSession(provider_name="deepseek", token_ref="default", access_token="a1"))
                keyring_path = token_keyring_path_for_store(store_path=store_path)
                first = json.loads(keyring_path.read_text(encoding="utf-8"))
                self.assertEqual(first["version"], 1)
                with patch(
                    "cli.agent_cli.providers.auth_token_encryption_runtime.time.time",
                    return_value=10_000_000_000.0,
                ):
                    store.put(AuthSession(provider_name="deepseek", token_ref="second", access_token="a2"))
                second = json.loads(keyring_path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(second.get("keys", {})), 2)
