import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.routes import BrowserRouteDispatcher

class _FakeBrowserClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def perform(self, **kwargs):
        self.calls.append(dict(kwargs))
        action = str(kwargs.get("action") or "")
        if action == "snapshot" and kwargs.get("tab_id") == "bad-int":
            raise ValueError("bad snapshot request")
        return {"ok": True, "action": action, "echo": dict(kwargs)}

class _FakeStatusBrowserClient(_FakeBrowserClient):
    def perform(self, **kwargs):
        if str(kwargs.get("action") or "") == "status":
            profile = str(kwargs.get("profile") or "openclaw")
            return {
                "ok": True,
                "action": "status",
                "profile": profile,
                "running": profile == "review",
                "active_tab": "tab-review" if profile == "review" else None,
                "tabs": 1 if profile == "review" else 0,
                "driver": "remote-cdp" if profile == "review" else "live",
                "mode": "remote-cdp" if profile == "review" else "local-managed",
                "transport": "cdp" if profile == "review" else "managed",
                "cdp_http": profile == "review",
                "cdp_ready": False,
                "cdp_url": "http://127.0.0.1:9222" if profile == "review" else "",
                "attach_only": profile == "review",
            }
        return super().perform(**kwargs)

class BrowserRouteDispatcherTest(unittest.TestCase):
    def test_dispatches_basic_routes(self) -> None:
        client = _FakeBrowserClient()
        dispatcher = BrowserRouteDispatcher(client=client)

        status = dispatcher.dispatch(method="GET", path="/", query={"profile": "review"})
        profiles = dispatcher.dispatch(method="GET", path="/profiles")
        created = dispatcher.dispatch(
            method="POST",
            path="/profiles/create",
            body={"name": "review", "driver": "openclaw"},
        )
        start = dispatcher.dispatch(method="POST", path="/start", body={"profile": "review"})
        reset = dispatcher.dispatch(method="POST", path="/reset-profile", body={"profile": "review"})
        deleted = dispatcher.dispatch(method="DELETE", path="/profiles/review")

        self.assertEqual(status.status, 200)
        self.assertEqual(status.body["action"], "status")
        self.assertEqual(status.body["echo"]["profile"], "review")

        self.assertEqual(profiles.status, 200)
        self.assertEqual(profiles.body["action"], "profiles")

        self.assertEqual(created.status, 200)
        self.assertEqual(created.body["action"], "create_profile")
        self.assertEqual(created.body["echo"]["name"], "review")

        self.assertEqual(start.status, 200)
        self.assertEqual(start.body["echo"]["profile"], "review")

        self.assertEqual(reset.status, 200)
        self.assertEqual(reset.body["action"], "reset_profile")
        self.assertEqual(reset.body["echo"]["profile"], "review")

        self.assertEqual(deleted.status, 200)
        self.assertEqual(deleted.body["action"], "delete_profile")
        self.assertEqual(deleted.body["echo"]["name"], "review")

    def test_dispatches_tabs_snapshot_and_act_routes(self) -> None:
        client = _FakeBrowserClient()
        dispatcher = BrowserRouteDispatcher(client=client)

        opened = dispatcher.dispatch(
            method="POST",
            path="/tabs/open",
            body={"url": "https://example.com", "profile": "openclaw"},
        )
        focused = dispatcher.dispatch(
            method="POST",
            path="/tabs/focus",
            body={"targetId": "tab-1", "profile": "openclaw"},
        )
        snapshot = dispatcher.dispatch(
            method="GET",
            path="/snapshot",
            query={"targetId": "tab-1", "maxChars": "400", "maxRefs": "8", "profile": "openclaw"},
        )
        act = dispatcher.dispatch(
            method="POST",
            path="/act",
            body={"kind": "click", "ref": "e1", "targetId": "tab-1", "profile": "openclaw"},
        )
        closed = dispatcher.dispatch(
            method="DELETE",
            path="/tabs/tab-1",
            query={"profile": "openclaw"},
        )

        self.assertEqual(opened.status, 200)
        self.assertEqual(opened.body["echo"]["action"], "open")
        self.assertEqual(opened.body["echo"]["url"], "https://example.com")

        self.assertEqual(focused.status, 200)
        self.assertEqual(focused.body["echo"]["action"], "focus")
        self.assertEqual(focused.body["echo"]["tab_id"], "tab-1")

        self.assertEqual(snapshot.status, 200)
        self.assertEqual(snapshot.body["echo"]["max_chars"], 400)
        self.assertEqual(snapshot.body["echo"]["max_refs"], 8)

        self.assertEqual(act.status, 200)
        self.assertEqual(act.body["echo"]["kind"], "click")
        self.assertEqual(act.body["echo"]["ref"], "e1")

        self.assertEqual(closed.status, 200)
        self.assertEqual(closed.body["echo"]["action"], "close")

    def test_dispatches_extended_proxy_parity_routes(self) -> None:
        client = _FakeBrowserClient()
        dispatcher = BrowserRouteDispatcher(client=client)

        navigate = dispatcher.dispatch(
            method="POST",
            path="/navigate",
            body={"targetId": "tab-1", "url": "https://example.com/next", "profile": "openclaw"},
        )
        screenshot = dispatcher.dispatch(
            method="POST",
            path="/screenshot",
            body={"targetId": "tab-1", "ref": "e1", "profile": "openclaw"},
        )
        pdf = dispatcher.dispatch(
            method="POST",
            path="/pdf",
            body={"targetId": "tab-1", "profile": "openclaw"},
        )
        download = dispatcher.dispatch(
            method="POST",
            path="/download",
            body={"targetId": "tab-1", "ref": "e9", "path": "safe/report.csv", "profile": "openclaw"},
        )
        wait_download = dispatcher.dispatch(
            method="POST",
            path="/wait-download",
            body={"targetId": "tab-1", "path": "safe/later.csv", "timeoutMs": 200, "profile": "openclaw"},
        )
        highlight = dispatcher.dispatch(
            method="POST",
            path="/highlight",
            body={"targetId": "tab-1", "ref": "e2", "timeMs": 50, "profile": "openclaw"},
        )
        trace_start = dispatcher.dispatch(
            method="POST",
            path="/trace/start",
            body={"targetId": "tab-1", "profile": "openclaw"},
        )
        trace_stop = dispatcher.dispatch(
            method="POST",
            path="/trace/stop",
            body={"targetId": "tab-1", "path": "safe/trace.zip", "profile": "openclaw"},
        )
        cookies_set = dispatcher.dispatch(
            method="POST",
            path="/cookies/set",
            body={"targetId": "tab-1", "profile": "openclaw", "cookies": [{"name": "sid", "value": "1"}]},
        )
        storage_set = dispatcher.dispatch(
            method="POST",
            path="/storage/set",
            body={"targetId": "tab-1", "profile": "openclaw", "storageKind": "local", "items": {"token": "x"}},
        )
        upload = dispatcher.dispatch(
            method="POST",
            path="/upload",
            body={"targetId": "tab-1", "ref": "e7", "paths": ["fixtures/invoice.pdf"], "timeoutMs": 1000, "profile": "openclaw"},
        )
        dialog = dispatcher.dispatch(
            method="POST",
            path="/dialog",
            body={"targetId": "tab-1", "accept": True, "promptText": "approved", "timeoutMs": 100, "profile": "openclaw"},
        )

        self.assertEqual(navigate.status, 200)
        self.assertEqual(navigate.body["echo"]["action"], "navigate")
        self.assertEqual(navigate.body["echo"]["url"], "https://example.com/next")

        self.assertEqual(screenshot.body["echo"]["action"], "screenshot")
        self.assertEqual(screenshot.body["echo"]["ref"], "e1")
        self.assertEqual(pdf.body["echo"]["action"], "pdf")
        self.assertEqual(download.body["echo"]["action"], "download")
        self.assertEqual(download.body["echo"]["path"], "safe/report.csv")
        self.assertEqual(wait_download.body["echo"]["action"], "wait_download")
        self.assertEqual(wait_download.body["echo"]["time_ms"], 200)
        self.assertEqual(highlight.body["echo"]["action"], "highlight")
        self.assertEqual(trace_start.body["echo"]["action"], "trace_start")
        self.assertEqual(trace_stop.body["echo"]["action"], "trace_stop")
        self.assertEqual(cookies_set.body["echo"]["action"], "cookies_set")
        self.assertEqual(cookies_set.body["echo"]["cookies"][0]["name"], "sid")
        self.assertEqual(storage_set.body["echo"]["action"], "storage_set")
        self.assertEqual(storage_set.body["echo"]["storage_kind"], "local")
        self.assertEqual(upload.body["echo"]["action"], "upload")
        self.assertEqual(upload.body["echo"]["paths"], ["fixtures/invoice.pdf"])
        self.assertEqual(dialog.body["echo"]["action"], "dialog")
        self.assertTrue(dialog.body["echo"]["accept"])

    def test_dispatches_cookie_storage_read_routes(self) -> None:
        client = _FakeBrowserClient()
        dispatcher = BrowserRouteDispatcher(client=client)

        cookies = dispatcher.dispatch(method="GET", path="/cookies", query={"targetId": "tab-1", "profile": "openclaw"})
        cookies_get = dispatcher.dispatch(method="GET", path="/cookies/get", query={"targetId": "tab-1", "profile": "openclaw"})
        storage_state = dispatcher.dispatch(method="GET", path="/storage/state", query={"targetId": "tab-1", "profile": "openclaw"})
        storage_get = dispatcher.dispatch(
            method="GET",
            path="/storage/get",
            query={"targetId": "tab-1", "storageKind": "session", "profile": "openclaw"},
        )

        self.assertEqual(cookies.body["echo"]["action"], "cookies")
        self.assertEqual(cookies_get.body["echo"]["action"], "cookies_get")
        self.assertEqual(storage_state.body["echo"]["action"], "storage_state")
        self.assertEqual(storage_get.body["echo"]["action"], "storage_get")
        self.assertEqual(storage_get.body["echo"]["storage_kind"], "session")

    def test_dispatch_maps_validation_to_400_and_unknown_to_404(self) -> None:
        client = _FakeBrowserClient()
        dispatcher = BrowserRouteDispatcher(client=client)

        missing_url = dispatcher.dispatch(method="POST", path="/tabs/open", body={})
        missing_name = dispatcher.dispatch(method="POST", path="/profiles/create", body={})
        bad_act = dispatcher.dispatch(method="POST", path="/act", body={"profile": "openclaw"})
        unknown = dispatcher.dispatch(method="PATCH", path="/unknown")

        self.assertEqual(missing_url.status, 400)
        self.assertIn("url is required", missing_url.body["error"])

        self.assertEqual(missing_name.status, 400)
        self.assertIn("name is required", missing_name.body["error"])

        self.assertEqual(bad_act.status, 400)
        self.assertIn("kind is required", bad_act.body["error"])

        missing_download_ref = dispatcher.dispatch(method="POST", path="/download", body={"profile": "openclaw"})
        self.assertEqual(missing_download_ref.status, 400)
        self.assertIn("ref is required", missing_download_ref.body["error"])

        missing_storage_kind = dispatcher.dispatch(method="GET", path="/storage/get", query={"profile": "openclaw"})
        self.assertEqual(missing_storage_kind.status, 400)
        self.assertIn("storageKind is required", missing_storage_kind.body["error"])

        invalid_upload_paths = dispatcher.dispatch(
            method="POST",
            path="/upload",
            body={"paths": "not-a-list", "profile": "openclaw"},
        )
        self.assertEqual(invalid_upload_paths.status, 400)
        self.assertIn("paths must be a list", invalid_upload_paths.body["error"])

        self.assertEqual(unknown.status, 404)
        self.assertIn("unknown browser route", unknown.body["error"])

    def test_status_route_is_profile_aware(self) -> None:
        dispatcher = BrowserRouteDispatcher(client=_FakeStatusBrowserClient())

        result = dispatcher.dispatch(method="GET", path="/", query={"profile": "review"})

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body["profile"], "review")
        self.assertTrue(result.body["running"])
        self.assertEqual(result.body["mode"], "remote-cdp")
        self.assertEqual(result.body["transport"], "cdp")
        self.assertTrue(result.body["cdp_http"])
        self.assertFalse(result.body["cdp_ready"])
