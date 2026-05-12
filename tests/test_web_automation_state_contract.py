from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from shared.web_automation.service import BrowserService

def _service_state_contract_available() -> bool:
    required = (
        "get_cookies",
        "set_cookies",
        "clear_cookies",
        "get_storage",
        "set_storage",
        "clear_storage",
    )
    return all(hasattr(BrowserService, name) for name in required)

def _sample_cookie() -> dict[str, object]:
    return {
        "name": "session_id",
        "value": "abc123",
        "domain": "example.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }

@unittest.skipUnless(
    _service_state_contract_available(),
    "browser state service contract not implemented yet",
)
class BrowserStateServiceContractTest(unittest.TestCase):
    def test_cookie_roundtrip_and_clear_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    service = BrowserService()
                    self.assertTrue(service.start())
                    tab = service.open_tab("https://example.com/app")
                    self.assertIsNotNone(tab)

                    service.set_cookies(  # type: ignore[attr-defined]
                        target_id=tab.tab_id,
                        cookies=[_sample_cookie()],
                    )

                    cookies = service.get_cookies(target_id=tab.tab_id)  # type: ignore[attr-defined]
                    self.assertEqual(len(cookies), 1)
                    self.assertEqual(cookies[0]["name"], "session_id")
                    self.assertEqual(cookies[0]["value"], "abc123")
                    self.assertEqual(cookies[0]["domain"], "example.com")

                    cleared = service.clear_cookies(target_id=tab.tab_id)  # type: ignore[attr-defined]
                    self.assertEqual(cleared["cleared"], 1)
                    self.assertEqual(service.get_cookies(target_id=tab.tab_id), [])  # type: ignore[attr-defined]
            finally:
                os.chdir(old_cwd)

    def test_storage_roundtrip_for_local_and_session_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    service = BrowserService()
                    self.assertTrue(service.start())
                    tab = service.open_tab("https://example.com/app")
                    self.assertIsNotNone(tab)

                    service.set_storage(  # type: ignore[attr-defined]
                        target_id=tab.tab_id,
                        storage_kind="local",
                        items={"token": "t-1", "theme": "light"},
                    )
                    service.set_storage(  # type: ignore[attr-defined]
                        target_id=tab.tab_id,
                        storage_kind="session",
                        items={"wizard_step": "2"},
                    )

                    local_items = service.get_storage(target_id=tab.tab_id, storage_kind="local")  # type: ignore[attr-defined]
                    session_items = service.get_storage(target_id=tab.tab_id, storage_kind="session")  # type: ignore[attr-defined]
                    self.assertEqual(local_items, {"token": "t-1", "theme": "light"})
                    self.assertEqual(session_items, {"wizard_step": "2"})

                    local_cleared = service.clear_storage(target_id=tab.tab_id, storage_kind="local")  # type: ignore[attr-defined]
                    session_cleared = service.clear_storage(target_id=tab.tab_id, storage_kind="session")  # type: ignore[attr-defined]
                    self.assertEqual(local_cleared["cleared"], 2)
                    self.assertEqual(session_cleared["cleared"], 1)
                    self.assertEqual(service.get_storage(target_id=tab.tab_id, storage_kind="local"), {})  # type: ignore[attr-defined]
                    self.assertEqual(service.get_storage(target_id=tab.tab_id, storage_kind="session"), {})  # type: ignore[attr-defined]
            finally:
                os.chdir(old_cwd)

    def test_state_contract_errors_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {"AGENTHUB_BROWSER_MODE": "synthetic"}, clear=False):
                    service = BrowserService()
                    self.assertTrue(service.start())
                    tab = service.open_tab("https://example.com/app")
                    self.assertIsNotNone(tab)

                    with self.assertRaisesRegex(ValueError, "storage_kind"):
                        service.get_storage(target_id=tab.tab_id, storage_kind="invalid")  # type: ignore[attr-defined]

                    with self.assertRaisesRegex(ValueError, "cookies"):
                        service.set_cookies(target_id=tab.tab_id, cookies=[])  # type: ignore[attr-defined]

                    with self.assertRaisesRegex(ValueError, "items"):
                        service.set_storage(target_id=tab.tab_id, storage_kind="local", items={})  # type: ignore[attr-defined]
            finally:
                os.chdir(old_cwd)
