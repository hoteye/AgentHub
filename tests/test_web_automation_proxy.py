import base64
import json
import time
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.config import load_config
from shared.web_automation.proxy import BrowserProxyExecutor, run_browser_proxy_command
from shared.web_automation.routes import BrowserRouteResponse

class _FakeDispatcher:
    def __init__(self, response: BrowserRouteResponse | None = None) -> None:
        self.response = response or BrowserRouteResponse(status=200, body={"ok": True})
        self.calls: list[dict[str, object]] = []

    def dispatch(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response

class _SlowDispatcher(_FakeDispatcher):
    def dispatch(self, **kwargs):
        self.calls.append(dict(kwargs))
        if kwargs.get("path") == "/":
            return BrowserRouteResponse(
                status=200,
                body={
                    "running": True,
                    "profile": "openclaw",
                    "tabs": 1,
                    "cdp_http": False,
                    "cdp_ready": False,
                },
            )
        time.sleep(0.05)
        return self.response

class BrowserProxyConfigTest(unittest.TestCase):
    def test_load_config_reads_proxy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "browser_automation.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "enabled = true",
                        'mode = "live"',
                        "",
                        "[proxy]",
                        "enabled = false",
                        'allow_profiles = ["openclaw", "review"]',
                        "max_file_bytes = 2048",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertFalse(config.proxy_enabled)
        self.assertEqual(config.proxy_allow_profiles, ["openclaw", "review"])
        self.assertEqual(config.proxy_max_file_bytes, 2048)

class BrowserProxyExecutorTest(unittest.TestCase):
    def test_run_rejects_when_proxy_disabled(self) -> None:
        config_path = ROOT / "config" / "browser_automation.toml"
        del config_path
        from shared.web_automation.config import BrowserAutomationConfig

        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(proxy_enabled=False),
            dispatcher=_FakeDispatcher(),
        )

        with self.assertRaisesRegex(RuntimeError, "browser proxy disabled"):
            executor.run(path="/profiles")

    def test_run_enforces_profile_allowlist(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        dispatcher = _FakeDispatcher()
        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(proxy_allow_profiles=["openclaw"]),
            dispatcher=dispatcher,
        )

        with self.assertRaisesRegex(ValueError, "browser profile not allowed"):
            executor.run(method="GET", path="/tabs", query={"profile": "review"})

        self.assertEqual(dispatcher.calls, [])

    def test_run_blocks_persistent_profile_mutation_when_allowlist_is_set(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(proxy_allow_profiles=["openclaw"]),
            dispatcher=_FakeDispatcher(),
        )

        with self.assertRaisesRegex(ValueError, "cannot mutate persistent browser profiles"):
            executor.run(method="POST", path="/profiles/create", body={"name": "review"})

        with self.assertRaisesRegex(ValueError, "cannot mutate persistent browser profiles"):
            executor.run(method="POST", path="/reset-profile", body={"profile": "openclaw"})

    def test_run_returns_result_and_collects_files(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "shot.png"
            artifact.write_bytes(b"png-bytes")
            dispatcher = _FakeDispatcher(
                BrowserRouteResponse(
                    status=200,
                    body={
                        "ok": True,
                        "artifact": {
                            "path": str(artifact),
                        },
                    },
                )
            )
            executor = BrowserProxyExecutor(
                BrowserAutomationConfig(proxy_allow_profiles=["openclaw"], proxy_max_file_bytes=1024),
                dispatcher=dispatcher,
            )

            result = executor.run(method="GET", path="/snapshot", query={"profile": "openclaw"})

        self.assertEqual(result["status"], 200)
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(
            base64.b64decode(result["files"][0]["base64"]),
            b"png-bytes",
        )

    def test_run_rejects_oversized_proxy_file(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "large.bin"
            artifact.write_bytes(b"x" * 8)
            executor = BrowserProxyExecutor(
                BrowserAutomationConfig(proxy_max_file_bytes=4),
                dispatcher=_FakeDispatcher(
                    BrowserRouteResponse(status=200, body={"path": str(artifact)}),
                ),
            )

            with self.assertRaisesRegex(ValueError, "browser proxy file exceeds 4 bytes"):
                executor.run(method="GET", path="/snapshot")

    def test_run_browser_proxy_command_returns_json_payload(self) -> None:
        payload = run_browser_proxy_command(
            json.dumps({"method": "GET", "path": "/profiles"}),
            executor=BrowserProxyExecutor(dispatcher=_FakeDispatcher(BrowserRouteResponse(status=200, body={"ok": True}))),
        )

        decoded = json.loads(payload)
        self.assertEqual(decoded["status"], 200)
        self.assertTrue(decoded["result"]["ok"])

    def test_run_browser_proxy_command_rejects_missing_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "path is required"):
            run_browser_proxy_command(json.dumps({"method": "GET"}), executor=BrowserProxyExecutor(dispatcher=_FakeDispatcher()))

    def test_run_honors_timeout_and_formats_status(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(),
            dispatcher=_SlowDispatcher(BrowserRouteResponse(status=200, body={"ok": True})),
        )

        with self.assertRaisesRegex(
            TimeoutError,
            "browser proxy timed out for GET /snapshot after 1ms; ws-backed browser action; profile=openclaw; status\\(running=True, profile=openclaw, tabs=1, cdp_http=False, cdp_ready=False\\)",
        ):
            executor.run(method="GET", path="/snapshot", profile="openclaw", timeout_ms=1)

    def test_run_timeout_redacts_cdp_url_secrets(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        class _CdpSlowDispatcher(_FakeDispatcher):
            def dispatch(self, **kwargs):
                self.calls.append(dict(kwargs))
                if kwargs.get("path") == "/":
                    return BrowserRouteResponse(
                        status=200,
                        body={
                            "running": True,
                            "profile": "review",
                            "transport": "cdp",
                            "cdp_http": True,
                            "cdp_ready": False,
                            "cdp_url": "https://browserless.example/chrome?token=secret-token&foo=bar",
                        },
                    )
                time.sleep(0.05)
                return self.response

        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(),
            dispatcher=_CdpSlowDispatcher(BrowserRouteResponse(status=200, body={"ok": True})),
        )

        with self.assertRaisesRegex(
            TimeoutError,
            r"cdp_http=True, cdp_ready=False, cdp_url=https://browserless\.example/chrome\?token=\*\*\*&foo=bar",
        ):
            executor.run(method="POST", path="/navigate", profile="review", timeout_ms=1)

    def test_run_filters_profiles_result_when_allowlist_is_set(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        dispatcher = _FakeDispatcher(
            BrowserRouteResponse(
                status=200,
                body={
                    "profiles": [
                        {"name": "openclaw", "mode": "local-managed"},
                        {"name": "review", "mode": "remote-cdp"},
                    ],
                    "count": 2,
                },
            )
        )
        executor = BrowserProxyExecutor(
            BrowserAutomationConfig(proxy_allow_profiles=["openclaw"]),
            dispatcher=dispatcher,
        )

        result = executor.run(method="GET", path="/profiles")

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["result"]["count"], 1)
        self.assertEqual(result["result"]["profile_names"], ["openclaw"])
