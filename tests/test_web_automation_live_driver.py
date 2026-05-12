from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from shared.web_automation.config import BrowserAutomationConfig
from shared.web_automation.live_driver import LiveBrowserDriver
from shared.web_automation.navigation_guard import InvalidBrowserNavigationUrlError
from shared.web_automation.types import BrowserPageRef, BrowserProfileSpec, BrowserTab, ProfileState

class _FakeLocator:
    def __init__(self) -> None:
        self.click = Mock()
        self.fill = Mock()
        self.hover = Mock()
        self.focus = Mock()
        self.check = Mock()
        self.uncheck = Mock()
        self.dblclick = Mock()
        self.press = Mock()
        self.type = Mock()
        self.select_option = Mock()
        self.screenshot = Mock()

class _FakePage:
    def __init__(self) -> None:
        self.goto = Mock()
        self.url = "about:blank"
        self.locator = Mock()
        self.screenshot = Mock()
        self.expect_download = Mock()
        self.wait_for_function = Mock()
        self.wait_for_load_state = Mock()
        self.wait_for_timeout = Mock()
        self.title = Mock(return_value="Title")

class _FakeDownloadWaiter:
    def __init__(self, value) -> None:
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class _FakeBrowserContext:
    def __init__(self) -> None:
        self.close = Mock()
        self.new_page = Mock()
        self.pages = []

class _FakeBrowser:
    def __init__(self, context: _FakeBrowserContext) -> None:
        self.new_context = Mock(return_value=context)
        self.close = Mock()
        self.contexts = [context]

class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.launch = Mock(return_value=browser)
        self.connect_over_cdp = Mock(return_value=browser)

class _FakePlaywrightRuntime:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium
        self.stop = Mock()

class _FakePlaywrightFactory:
    def __init__(self, runtime: _FakePlaywrightRuntime) -> None:
        self._runtime = runtime

    def start(self) -> _FakePlaywrightRuntime:
        return self._runtime

class _FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class LiveBrowserDriverNavigationTest(unittest.TestCase):
    def test_goto_blocks_unsupported_protocol_before_page_navigation(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()

        with self.assertRaises(InvalidBrowserNavigationUrlError):
            driver._goto(page, "javascript:alert(1)")

        page.goto.assert_not_called()

    def test_goto_rechecks_final_url_against_navigation_policy(self) -> None:
        driver = LiveBrowserDriver(
            BrowserAutomationConfig(
                mode="live",
                allow_hosts=["example.com"],
                navigation_timeout_ms=1000,
            )
        )
        page = _FakePage()
        page.goto.side_effect = lambda url, wait_until, timeout: setattr(page, "url", "https://blocked.example.org/final")

        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, "is not in allow_hosts"):
            driver._goto(page, "https://example.com/start")

        page.goto.assert_called()

    def test_start_profile_uses_remote_cdp_for_attach_only_profile(self) -> None:
        config = BrowserAutomationConfig(
            mode="live",
            launch_timeout_ms=3456,
            profiles={
                "review": {
                    "driver": "remote-cdp",
                    "cdp_url": "http://127.0.0.1:9222",
                    "attach_only": True,
                }
            },
        )
        driver = LiveBrowserDriver(config)
        context = _FakeBrowserContext()
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)
        runtime = _FakePlaywrightRuntime(chromium)
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="review",
                color="#228B22",
                driver="remote-cdp",
                attach_only=True,
                cdp_url="http://127.0.0.1:9222",
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            self.assertTrue(driver.start_profile(profile_state))

        chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222", timeout=3456)
        chromium.launch.assert_not_called()

    def test_start_profile_blocks_private_remote_cdp_without_allow_private_network(self) -> None:
        config = BrowserAutomationConfig(mode="live", launch_timeout_ms=3456)
        driver = LiveBrowserDriver(config)
        runtime = _FakePlaywrightRuntime(_FakeChromium(_FakeBrowser(_FakeBrowserContext())))
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="review",
                color="#228B22",
                driver="remote-cdp",
                attach_only=True,
                cdp_url="http://10.0.0.42:9222",
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'private network host "10.0.0.42"'):
                driver.start_profile(profile_state)

    def test_start_profile_allows_private_remote_cdp_when_configured(self) -> None:
        config = BrowserAutomationConfig(mode="live", launch_timeout_ms=3456, allow_private_network=True)
        driver = LiveBrowserDriver(config)
        context = _FakeBrowserContext()
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)
        runtime = _FakePlaywrightRuntime(chromium)
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="review",
                color="#228B22",
                driver="remote-cdp",
                attach_only=True,
                cdp_url="ws://10.0.0.42:9222/devtools/browser/abc",
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            self.assertTrue(driver.start_profile(profile_state))

        chromium.connect_over_cdp.assert_called_once_with("ws://10.0.0.42:9222/devtools/browser/abc", timeout=3456)

    def test_start_profile_uses_profile_specific_launch_overrides(self) -> None:
        config = BrowserAutomationConfig(
            mode="live",
            executable_path="/opt/browser/default",
            headless=True,
            launch_timeout_ms=4567,
            profiles={
                "review": {
                    "driver": "live",
                    "headless": False,
                    "executable_path": "/opt/browser/review",
                }
            },
        )
        driver = LiveBrowserDriver(config)
        context = _FakeBrowserContext()
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)
        runtime = _FakePlaywrightRuntime(chromium)
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="review",
                color="#228B22",
                driver="live",
                executable_path="/opt/browser/review",
                headless=False,
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            with patch.object(driver, "_resolve_executable_path", return_value="/opt/browser/review"):
                self.assertTrue(driver.start_profile(profile_state))

        chromium.launch.assert_called_once_with(
            executable_path="/opt/browser/review",
            headless=False,
            timeout=4567,
            args=["--disable-dev-shm-usage"],
        )

    def test_start_profile_existing_session_discovers_loopback_cdp(self) -> None:
        config = BrowserAutomationConfig(mode="live")
        driver = LiveBrowserDriver(config)
        context = _FakeBrowserContext()
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)
        runtime = _FakePlaywrightRuntime(chromium)
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="user",
                color="#00AA00",
                driver="existing-session",
                attach_only=True,
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            with patch(
                "shared.web_automation.live_driver.urlopen",
                return_value=_FakeHttpResponse(
                    b'{"Browser":"Chrome/123.0","webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/test"}'
                ),
            ) as mocked_urlopen:
                self.assertTrue(driver.start_profile(profile_state))

        chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222", timeout=20000)
        mocked_urlopen.assert_called_once()

    def test_start_profile_existing_session_uses_configured_discovery_base(self) -> None:
        config = BrowserAutomationConfig(
            mode="live",
            existing_session_discovery_bases=["http://127.0.0.1:9333", "http://localhost:9222"],
        )
        driver = LiveBrowserDriver(config)
        context = _FakeBrowserContext()
        browser = _FakeBrowser(context)
        chromium = _FakeChromium(browser)
        runtime = _FakePlaywrightRuntime(chromium)
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="user",
                color="#00AA00",
                driver="existing-session",
                attach_only=True,
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            with patch(
                "shared.web_automation.live_driver.urlopen",
                return_value=_FakeHttpResponse(
                    b'{"Browser":"Chrome/123.0","webSocketDebuggerUrl":"ws://127.0.0.1:9333/devtools/browser/test"}'
                ),
            ) as mocked_urlopen:
                self.assertTrue(driver.start_profile(profile_state))

        chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9333", timeout=20000)
        first_request = mocked_urlopen.call_args.args[0]
        self.assertEqual(first_request.full_url, "http://127.0.0.1:9333/json/version")

    def test_start_profile_existing_session_without_cdp_raises_clear_error(self) -> None:
        config = BrowserAutomationConfig(mode="live")
        driver = LiveBrowserDriver(config)
        runtime = _FakePlaywrightRuntime(_FakeChromium(_FakeBrowser(_FakeBrowserContext())))
        profile_state = ProfileState(
            spec=BrowserProfileSpec(
                name="user",
                color="#00AA00",
                driver="existing-session",
                attach_only=True,
            )
        )

        with patch("shared.web_automation.live_driver.sync_playwright", return_value=_FakePlaywrightFactory(runtime)):
            with patch("shared.web_automation.live_driver.urlopen", side_effect=OSError("refused")):
                with self.assertRaisesRegex(RuntimeError, "Attempted discovery URLs:"):
                    driver.start_profile(profile_state)

    def test_discover_existing_session_cdp_url_falls_back_to_localhost(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))

        responses = [
            OSError("refused"),
            _FakeHttpResponse(
                b'{"Browser":"Chrome/123.0","webSocketDebuggerUrl":"ws://localhost:9222/devtools/browser/test"}'
            ),
        ]

        def _fake_urlopen(_request, timeout):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            self.assertLessEqual(timeout, 1.5)
            return result

        with patch("shared.web_automation.live_driver.urlopen", side_effect=_fake_urlopen) as mocked_urlopen:
            discovered = driver._discover_existing_session_cdp_url()

        self.assertEqual(discovered, "http://localhost:9222")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_discover_existing_session_cdp_url_uses_configured_path(self) -> None:
        driver = LiveBrowserDriver(
            BrowserAutomationConfig(
                mode="live",
                existing_session_discovery_bases=["http://127.0.0.1:9444"],
                existing_session_discovery_path="/json/version?profile=user",
            )
        )

        with patch(
            "shared.web_automation.live_driver.urlopen",
            return_value=_FakeHttpResponse(
                b'{"Browser":"Chrome/123.0","webSocketDebuggerUrl":"ws://127.0.0.1:9444/devtools/browser/test"}'
            ),
        ) as mocked_urlopen:
            discovered = driver._discover_existing_session_cdp_url()

        self.assertEqual(discovered, "http://127.0.0.1:9444")
        first_request = mocked_urlopen.call_args.args[0]
        self.assertEqual(first_request.full_url, "http://127.0.0.1:9444/json/version?profile=user")

    def test_discover_existing_session_cdp_url_reports_attempts(self) -> None:
        driver = LiveBrowserDriver(
            BrowserAutomationConfig(
                mode="live",
                existing_session_discovery_bases=["http://127.0.0.1:9223", "http://localhost:9222"],
            )
        )

        with patch("shared.web_automation.live_driver.urlopen", side_effect=OSError("refused")):
            with self.assertRaisesRegex(
                RuntimeError,
                "http://127.0.0.1:9223/json/version, http://localhost:9222/json/version",
            ):
                driver._discover_existing_session_cdp_url()

    def test_discover_existing_session_cdp_url_rejects_disallowed_private_base(self) -> None:
        driver = LiveBrowserDriver(
            BrowserAutomationConfig(
                mode="live",
                existing_session_discovery_bases=["http://10.0.0.42:9222"],
            )
        )

        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'private network host "10.0.0.42"'):
            driver._discover_existing_session_cdp_url()

class LiveBrowserDriverRefRetryTest(unittest.TestCase):
    def test_ref_action_refreshes_refs_and_retries_once(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()
        first_locator = _FakeLocator()
        second_locator = _FakeLocator()
        first_locator.click.side_effect = RuntimeError("Timeout 5000ms exceeded waiting for locator")
        page.locator.side_effect = [
            Mock(first=first_locator),
            Mock(first=second_locator),
        ]

        tab = BrowserTab(
            tab_id="tab-1",
            url="https://example.com",
            title="Example",
            profile="openclaw",
            refs=[BrowserPageRef(ref="e1", role="button", name="Save", selector='[data-agenthub-ref="e1"]')],
        )
        driver._pages[tab.tab_id] = page

        refreshed = {"done": False}

        def _refresh_refs(bound_tab: BrowserTab) -> None:
            refreshed["done"] = True
            bound_tab.refs = [BrowserPageRef(ref="e1", role="button", name="Save", selector='[data-agenthub-ref="e1"]')]

        driver._refresh_refs_for_tab = _refresh_refs  # type: ignore[method-assign]

        driver.click(tab, ref="e1")

        self.assertTrue(refreshed["done"])
        self.assertEqual(first_locator.click.call_count, 1)
        self.assertEqual(second_locator.click.call_count, 1)

    def test_screenshot_tab_uses_ref_locator_when_ref_is_provided(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()
        locator = _FakeLocator()

        def _write_screenshot(*, path: str, **_kwargs) -> None:
            Path(path).write_bytes(b"ref-shot")

        locator.screenshot.side_effect = _write_screenshot
        page.locator.return_value = Mock(first=locator)

        tab = BrowserTab(
            tab_id="tab-shot",
            url="https://example.com",
            title="Example",
            profile="openclaw",
            refs=[BrowserPageRef(ref="e1", role="button", name="Save", selector='[data-agenthub-ref="e1"]')],
        )
        driver._pages[tab.tab_id] = page

        artifact = driver.screenshot_tab(tab, ref="e1")

        page.screenshot.assert_not_called()
        locator.screenshot.assert_called_once()
        self.assertEqual(artifact.ref, "e1")

    def test_download_ref_clicks_ref_and_records_download_artifact(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()
        locator = _FakeLocator()

        class _FakeDownload:
            suggested_filename = "../report.csv"
            url = "https://example.com/files/report.csv"

            @staticmethod
            def save_as(path: str) -> None:
                Path(path).write_bytes(b"download-content")

        page.expect_download.return_value = _FakeDownloadWaiter(_FakeDownload())
        page.locator.return_value = Mock(first=locator)

        tab = BrowserTab(
            tab_id="tab-download",
            url="https://example.com",
            title="Example",
            profile="openclaw",
            refs=[BrowserPageRef(ref="e1", role="link", name="Download", selector='[data-agenthub-ref="e1"]')],
        )
        driver._pages[tab.tab_id] = page

        artifact = driver.download_ref(tab, ref="e1")

        page.expect_download.assert_called_once()
        locator.click.assert_called_once()
        self.assertEqual(artifact.kind, "download")
        self.assertEqual(artifact.ref, "e1")
        self.assertEqual(artifact.suggested_filename, "report.csv")
        self.assertEqual(artifact.url, "https://example.com/files/report.csv")

    def test_wait_for_download_honors_requested_relative_output_path(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()

        class _FakeDownload:
            suggested_filename = "delayed.csv"
            url = "https://example.com/files/delayed.csv"

            @staticmethod
            def save_as(path: str) -> None:
                Path(path).write_bytes(b"download-content")

        page.expect_download.return_value = _FakeDownloadWaiter(_FakeDownload())

        tab = BrowserTab(
            tab_id="tab-wait",
            url="https://example.com",
            title="Example",
            profile="openclaw",
        )
        driver._pages[tab.tab_id] = page

        artifact = driver.wait_for_download(tab, timeout_ms=250, requested_path="safe/delayed.csv")

        page.expect_download.assert_called_once()
        self.assertGreaterEqual(page.wait_for_timeout.call_count, 1)
        self.assertTrue(artifact.path.endswith("safe/delayed.csv"))
        self.assertEqual(artifact.suggested_filename, "delayed.csv")

    def test_download_ref_rejects_escape_output_path(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()
        locator = _FakeLocator()

        class _FakeDownload:
            suggested_filename = "report.csv"
            url = "https://example.com/files/report.csv"

            @staticmethod
            def save_as(path: str) -> None:
                Path(path).write_bytes(b"download-content")

        page.expect_download.return_value = _FakeDownloadWaiter(_FakeDownload())
        page.locator.return_value = Mock(first=locator)

        tab = BrowserTab(
            tab_id="tab-download-escape",
            url="https://example.com",
            title="Example",
            profile="openclaw",
            refs=[BrowserPageRef(ref="e1", role="link", name="Download", selector='[data-agenthub-ref="e1"]')],
        )
        driver._pages[tab.tab_id] = page

        with self.assertRaisesRegex(ValueError, "escaped runtime directory"):
            driver.download_ref(tab, ref="e1", requested_path="../escape.csv")

    @unittest.skipIf(os.name == "nt", "symlink escape test requires POSIX-style symlink support")
    def test_wait_for_download_rejects_symlink_escape_path(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        page = _FakePage()

        class _FakeDownload:
            suggested_filename = "delayed.csv"
            url = "https://example.com/files/delayed.csv"

            @staticmethod
            def save_as(path: str) -> None:
                Path(path).write_bytes(b"download-content")

        page.expect_download.return_value = _FakeDownloadWaiter(_FakeDownload())

        tab = BrowserTab(
            tab_id="tab-wait-symlink",
            url="https://example.com",
            title="Example",
            profile="openclaw",
        )
        driver._pages[tab.tab_id] = page

        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                downloads_root = Path(".web_automation_state/artifacts/downloads")
                downloads_root.mkdir(parents=True, exist_ok=True)
                outside = Path(temp_dir) / "outside"
                outside.mkdir()
                symlink_dir = downloads_root / "link-out"
                symlink_dir.symlink_to(outside, target_is_directory=True)

                with self.assertRaisesRegex(ValueError, "escaped runtime directory"):
                    driver.wait_for_download(tab, timeout_ms=250, requested_path="link-out/escape.csv")
            finally:
                os.chdir(old_cwd)

class LiveBrowserDriverObservationHooksTest(unittest.TestCase):
    def test_page_error_and_network_events_append_debug_entries(self) -> None:
        driver = LiveBrowserDriver(BrowserAutomationConfig(mode="live"))
        tab = BrowserTab(
            tab_id="tab-observe",
            url="https://example.com/app",
            title="Example",
            profile="openclaw",
        )

        response_request = Mock()
        response_request.method = "GET"
        response_request.resource_type = "xhr"

        response = Mock()
        response.request = response_request
        response.status = 503
        response.url = "https://example.com/api/profile"

        failed_request = Mock()
        failed_request.method = "POST"
        failed_request.resource_type = "fetch"
        failed_request.url = "https://example.com/api/login"
        failed_request.failure = {"errorText": "net::ERR_CONNECTION_RESET"}

        driver._handle_page_error(tab, RuntimeError("Unhandled promise rejection"))
        driver._handle_response(tab, response)
        driver._handle_request_failed(tab, failed_request)

        self.assertEqual(tab.console[0].type, "error")
        self.assertEqual(tab.console[0].location["severity"], "error")
        self.assertIn("Unhandled promise rejection", tab.console[0].text)

        self.assertEqual(tab.console[1].type, "request")
        self.assertEqual(tab.console[1].location["method"], "GET")
        self.assertEqual(tab.console[1].location["status"], 503)
        self.assertEqual(tab.console[1].location["outcome"], "failed")
        self.assertEqual(tab.console[1].location["resource_type"], "xhr")

        self.assertEqual(tab.console[2].type, "request")
        self.assertEqual(tab.console[2].location["method"], "POST")
        self.assertEqual(tab.console[2].location["outcome"], "failed")
        self.assertEqual(tab.console[2].location["resource_type"], "fetch")
        self.assertIn("ERR_CONNECTION_RESET", tab.console[2].text)
