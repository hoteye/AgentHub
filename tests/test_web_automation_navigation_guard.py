import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.config import load_config
from shared.web_automation.navigation_guard import (
    BrowserNavigationPolicy,
    InvalidBrowserNavigationUrlError,
    assert_browser_endpoint_allowed,
    assert_browser_navigation_allowed,
    assert_browser_navigation_result_allowed,
    navigation_policy_from_config,
)

class BrowserNavigationGuardTest(unittest.TestCase):
    def test_allows_safe_default_protocols(self) -> None:
        assert_browser_navigation_allowed("https://example.com")
        assert_browser_navigation_allowed("http://example.com")
        assert_browser_navigation_allowed("about:blank")
        assert_browser_navigation_allowed("file:///tmp/report.txt")
        assert_browser_navigation_allowed("data:text/plain,hello")

    def test_blocks_unsupported_protocols(self) -> None:
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'unsupported protocol "javascript:"'):
            assert_browser_navigation_allowed("javascript:alert(1)")
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'unsupported protocol "chrome:"'):
            assert_browser_navigation_allowed("chrome://settings")

    def test_blocks_private_network_hosts_by_default(self) -> None:
        for url in (
            "http://localhost:8787/",
            "http://127.0.0.1:8787/",
            "http://10.0.0.8/admin",
            "http://172.16.0.10/app",
            "http://192.168.1.9/ui",
            "http://[::1]/",
        ):
            with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, "private network host"):
                assert_browser_navigation_allowed(url)

    def test_allows_private_network_when_policy_enables_it(self) -> None:
        policy = BrowserNavigationPolicy(allow_private_network=True)
        assert_browser_navigation_allowed("http://localhost:8787/", policy=policy)
        assert_browser_navigation_allowed("http://127.0.0.1:8787/", policy=policy)
        assert_browser_navigation_allowed("http://192.168.1.9/ui", policy=policy)

    def test_applies_block_hosts_before_navigation(self) -> None:
        policy = BrowserNavigationPolicy(block_hosts=("blocked.example.com", "*.forbidden.internal"))
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'matches block_hosts rule "blocked.example.com"'):
            assert_browser_navigation_allowed("https://blocked.example.com/path", policy=policy)
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'matches block_hosts rule "\\*\\.forbidden\\.internal"'):
            assert_browser_navigation_allowed("https://api.forbidden.internal/path", policy=policy)

    def test_applies_allow_hosts_when_present(self) -> None:
        policy = BrowserNavigationPolicy(allow_hosts=("example.com", "*.allowed.example"))
        assert_browser_navigation_allowed("https://example.com/docs", policy=policy)
        assert_browser_navigation_allowed("https://api.allowed.example/v1", policy=policy)
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'is not in allow_hosts'):
            assert_browser_navigation_allowed("https://denied.example.org", policy=policy)

    def test_resolver_detects_private_addresses_for_hostnames(self) -> None:
        policy = BrowserNavigationPolicy()

        def _resolver(hostname: str) -> list[str]:
            if hostname == "intranet.example.com":
                return ["10.10.1.8"]
            return []

        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'private network host "intranet.example.com"'):
            assert_browser_navigation_allowed(
                "https://intranet.example.com/dashboard",
                policy=policy,
                resolver=_resolver,
            )

    def test_result_guard_ignores_empty_and_rechecks_network_urls(self) -> None:
        assert_browser_navigation_result_allowed("")
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, "private network host"):
            assert_browser_navigation_result_allowed("http://127.0.0.1/final")

    def test_endpoint_guard_allows_loopback_and_ws_protocols(self) -> None:
        assert_browser_endpoint_allowed("http://127.0.0.1:9222")
        assert_browser_endpoint_allowed("ws://localhost:9222/devtools/browser/abc")

    def test_endpoint_guard_blocks_private_non_loopback_by_default(self) -> None:
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'private network host "10.0.0.42"'):
            assert_browser_endpoint_allowed("http://10.0.0.42:9222")

    def test_endpoint_guard_applies_host_allow_rules(self) -> None:
        policy = BrowserNavigationPolicy(allow_hosts=("browserless.example.com",))
        assert_browser_endpoint_allowed("https://browserless.example.com?token=test", policy=policy)
        with self.assertRaisesRegex(InvalidBrowserNavigationUrlError, 'is not in allow_hosts'):
            assert_browser_endpoint_allowed("https://cdp.example.net", policy=policy)

class BrowserNavigationConfigTest(unittest.TestCase):
    def test_load_config_reads_navigation_policy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "browser_automation.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "enabled = true",
                        'mode = "live"',
                        "allow_hosts = [\"example.com\", \"*.allowed.example\"]",
                        "block_hosts = [\"blocked.example.com\"]",
                        "allow_private_network = true",
                        "",
                        "[existing_session]",
                        'discovery_bases = ["http://127.0.0.1:9333"]',
                        'discovery_path = "/json/version?profile=user"',
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)
            policy = navigation_policy_from_config(config)

        self.assertEqual(config.allow_hosts, ["example.com", "*.allowed.example"])
        self.assertEqual(config.block_hosts, ["blocked.example.com"])
        self.assertTrue(config.allow_private_network)
        self.assertEqual(config.existing_session_discovery_bases, ["http://127.0.0.1:9333"])
        self.assertEqual(config.existing_session_discovery_path, "/json/version?profile=user")
        self.assertEqual(policy.allow_hosts, ("example.com", "*.allowed.example"))
        self.assertEqual(policy.block_hosts, ("blocked.example.com",))
        self.assertTrue(policy.allow_private_network)
