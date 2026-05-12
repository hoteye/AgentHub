from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from cli.agent_cli.tools import ToolRegistry
from shared.web_automation.config import BrowserAutomationConfig

class _FakeBrowserProxyTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs):
        self.calls.append(dict(kwargs))
        path = str(kwargs.get("path") or "")
        method = str(kwargs.get("method") or "GET").upper()
        if method == "GET" and path == "/":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "profile": "review",
                    "running": True,
                    "active_tab": "tab-1",
                    "tabs": 1,
                },
                "files": [],
            }
        if method == "GET" and path == "/tabs":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "profile": "review",
                    "count": 1,
                    "tabs": [
                        {
                            "tab_id": "tab-1",
                            "url": "https://example.com",
                            "title": "Example",
                            "profile": "review",
                        }
                    ],
                },
                "files": [],
            }
        if method == "POST" and path == "/act":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "kind": "click",
                    "message": "Clicked ref r1",
                },
                "files": [],
            }
        if method == "POST" and path == "/screenshot":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "artifact": {
                        "path": "/remote/shot.png",
                        "content_type": "image/png",
                        "size_bytes": 8,
                        "target_id": "tab-1",
                    },
                },
                "files": [
                    {
                        "path": "/remote/shot.png",
                        "base64": "cG5nLWJ5dGVz",
                        "mime_type": "image/png",
                    }
                ],
            }
        if method == "POST" and path == "/pdf":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "artifact": {
                        "path": "/remote/report.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 12,
                        "target_id": "tab-1",
                    },
                },
                "files": [
                    {
                        "path": "/remote/report.pdf",
                        "base64": "cGRmLWJ5dGVz",
                        "mime_type": "application/pdf",
                    }
                ],
            }
        if method == "POST" and path == "/download":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "artifact": {
                        "path": "/remote/export.csv",
                        "content_type": "text/csv",
                        "size_bytes": 9,
                        "target_id": "tab-1",
                        "suggested_filename": "export.csv",
                        "ref": "r1",
                    },
                },
                "files": [
                    {
                        "path": "/remote/export.csv",
                        "base64": "YSxiCjEsMg==",
                        "mime_type": "text/csv",
                    }
                ],
            }
        if method == "POST" and path == "/upload":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "action": "upload",
                    "message": "Uploaded 1 files",
                },
                "files": [],
            }
        if method == "POST" and path == "/dialog":
            return {
                "status": 200,
                "result": {
                    "ok": True,
                    "action": "dialog",
                    "message": "Dialog handled",
                },
                "files": [],
            }
        raise AssertionError(f"unexpected proxy call: {method} {path}")

class BrowserToolProxyModeTest(unittest.TestCase):
    def test_browser_tool_uses_http_proxy_transport_for_actions(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        with (
            patch("cli.agent_cli.tools.load_browser_config", return_value=BrowserAutomationConfig(proxy_transport="http", proxy_base_url="http://127.0.0.1:8787")),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()
            tools._browser_client = None

            event = tools.browser("act", profile="review", kind="click", ref="r1")

        self.assertTrue(event.ok)
        self.assertEqual(event.name, "browser_action")
        self.assertEqual(event.payload["action"], "click")
        self.assertEqual(event.payload["target_id"], "tab-1")
        self.assertEqual(fake_transport.calls[0]["path"], "/act")
        self.assertEqual(fake_transport.calls[0]["body"]["profile"], "review")

    def test_browser_tool_surfaces_remote_proxy_files(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        with (
            patch("cli.agent_cli.tools.load_browser_config", return_value=BrowserAutomationConfig(proxy_transport="http", proxy_base_url="http://127.0.0.1:8787")),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()

            event = tools.browser("screenshot", profile="review", ref="r1")

        self.assertTrue(event.ok)
        self.assertEqual(event.name, "browser_screenshot")
        self.assertEqual(event.payload["path"], "/remote/shot.png")
        self.assertEqual(len(event.payload["files"]), 1)
        self.assertEqual(event.payload["files"][0]["mime_type"], "image/png")

    def test_browser_tool_proxy_mode_supports_pdf_and_download_artifacts(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        with (
            patch("cli.agent_cli.tools.load_browser_config", return_value=BrowserAutomationConfig(proxy_transport="http", proxy_base_url="http://127.0.0.1:8787")),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()

            pdf_event = tools.browser("pdf", profile="review")
            download_event = tools.browser("download", profile="review", ref="r1")

        self.assertTrue(pdf_event.ok)
        self.assertEqual(pdf_event.name, "browser_pdf")
        self.assertEqual(pdf_event.payload["path"], "/remote/report.pdf")
        self.assertEqual(pdf_event.payload["files"][0]["mime_type"], "application/pdf")

        self.assertTrue(download_event.ok)
        self.assertEqual(download_event.name, "browser_download")
        self.assertEqual(download_event.payload["path"], "/remote/export.csv")
        self.assertEqual(download_event.payload["files"][0]["mime_type"], "text/csv")

    def test_browser_tool_proxy_mode_supports_upload_and_dialog_actions(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        with (
            patch("cli.agent_cli.tools.load_browser_config", return_value=BrowserAutomationConfig(proxy_transport="http", proxy_base_url="http://127.0.0.1:8787")),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()

            upload_event = tools.browser("upload", profile="review", ref="r1", paths=["fixtures/invoice.pdf"])
            dialog_event = tools.browser("dialog", profile="review", accept=True, prompt_text="approved")

        self.assertTrue(upload_event.ok)
        self.assertEqual(upload_event.name, "browser_action")
        self.assertEqual(upload_event.payload["action"], "upload")
        self.assertEqual(fake_transport.calls[0]["path"], "/upload")
        self.assertEqual(fake_transport.calls[0]["body"]["paths"], ["fixtures/invoice.pdf"])

        self.assertTrue(dialog_event.ok)
        self.assertEqual(dialog_event.name, "browser_action")
        self.assertEqual(dialog_event.payload["action"], "dialog")
        self.assertEqual(fake_transport.calls[1]["path"], "/dialog")
        self.assertTrue(fake_transport.calls[1]["body"]["accept"])

    def test_existing_session_profile_stays_local_when_http_proxy_is_enabled(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        local_client = MagicMock()
        local_client.perform.return_value = {
            "ok": True,
            "action": "status",
            "profile": "user",
            "running": True,
            "active_tab": "local-tab-1",
            "tabs": 1,
            "driver": "existing-session",
            "mode": "local-existing-session",
            "transport": "existing-session",
            "attach_only": True,
        }

        with (
            patch(
                "cli.agent_cli.tools.load_browser_config",
                return_value=BrowserAutomationConfig(mode="live", proxy_transport="http", proxy_base_url="http://127.0.0.1:8787"),
            ),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()
            tools._browser_client = local_client

            event = tools.browser("status", profile="user")

        self.assertTrue(event.ok)
        self.assertEqual(event.payload["profile"], "user")
        self.assertEqual(event.payload["transport"], "existing-session")
        local_client.perform.assert_called_once()
        self.assertEqual(fake_transport.calls, [])

    def test_default_existing_session_profile_stays_local_when_http_proxy_is_enabled(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        local_client = MagicMock()
        local_client.perform.return_value = {
            "ok": True,
            "action": "status",
            "profile": "user",
            "running": False,
            "active_tab": None,
            "tabs": 0,
            "driver": "existing-session",
            "mode": "local-existing-session",
            "transport": "existing-session",
            "attach_only": True,
        }

        with (
            patch(
                "cli.agent_cli.tools.load_browser_config",
                return_value=BrowserAutomationConfig(
                    mode="live",
                    default_profile="user",
                    proxy_transport="http",
                    proxy_base_url="http://127.0.0.1:8787",
                ),
            ),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()
            tools._browser_client = local_client

            event = tools.browser("status")

        self.assertTrue(event.ok)
        self.assertEqual(event.payload["profile"], "user")
        local_client.perform.assert_called_once()
        self.assertEqual(fake_transport.calls, [])

    def test_explicit_proxy_transport_uses_proxy_even_when_default_config_is_local(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        with (
            patch(
                "cli.agent_cli.tools.load_browser_config",
                return_value=BrowserAutomationConfig(proxy_transport="local"),
            ),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()

            event = tools.browser("status", profile="review", transport="proxy")

        self.assertTrue(event.ok)
        self.assertEqual(event.payload["requested_transport"], "proxy")
        self.assertEqual(fake_transport.calls[0]["path"], "/")

    def test_explicit_proxy_transport_still_keeps_existing_session_local(self) -> None:
        fake_transport = _FakeBrowserProxyTransport()
        local_client = MagicMock()
        local_client.perform.return_value = {
            "ok": True,
            "action": "status",
            "profile": "user",
            "running": True,
            "driver": "existing-session",
            "mode": "local-existing-session",
            "transport": "existing-session",
            "attach_only": True,
        }

        with (
            patch(
                "cli.agent_cli.tools.load_browser_config",
                return_value=BrowserAutomationConfig(mode="live", proxy_transport="local"),
            ),
            patch("cli.agent_cli.tools.create_browser_proxy_transport", return_value=fake_transport),
        ):
            tools = ToolRegistry()
            tools._browser_client = local_client

            event = tools.browser("status", profile="user", transport="proxy")

        self.assertTrue(event.ok)
        self.assertEqual(event.payload["requested_transport"], "proxy")
        local_client.perform.assert_called_once()
        self.assertEqual(fake_transport.calls, [])
