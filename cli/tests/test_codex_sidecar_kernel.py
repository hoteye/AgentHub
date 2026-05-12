from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Queue
from time import monotonic
from typing import Any

from cli.agent_cli.runtime_kernels import (
    ForkSessionRequest,
    KernelSession,
    ResumeSessionRequest,
    StartSessionRequest,
    StartTurnRequest,
)
from cli.agent_cli.runtime_kernels.codex_sidecar import (
    CodexSidecarArtifactConfig,
    CodexSidecarClient,
    CodexSidecarKernel,
    CodexSidecarRuntimeAdapter,
    CodexSidecarSupervisor,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.approval import (
    command_approval_response_for_decision,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.dynamic_tools import (
    AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE,
    codex_visible_child_dynamic_tool_metadata,
    codex_visible_child_dynamic_tools,
    internal_command_for_dynamic_tool,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.errors import CodexSidecarRequestError
from cli.agent_cli.runtime_kernels.codex_sidecar.evaluation_bridge import (
    CodexSidecarEvaluationBridge,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.fs_bridge import CodexSidecarFsBridge
from cli.agent_cli.runtime_kernels.codex_sidecar.mapper import CodexSidecarTurnEventMapper
from cli.agent_cli.runtime_kernels.codex_sidecar.model_catalog import CodexSidecarModelCatalog

FAKE_CODEX_BIN = Path(__file__).parent / "fixtures" / "fake_codex_sidecar.py"


class FakeInitializeClient:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.request_calls: list[tuple[str, dict[str, Any] | None]] = []
        self._lock = threading.Lock()

    def initialize(self) -> dict[str, object]:
        with self._lock:
            self.initialize_calls += 1
        return {}

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        return {
            "thread": {"id": f"thread-{len(self.request_calls)}", "name": "Fake"},
            "model": "fake-model",
            "modelProvider": "fake-provider",
            "cwd": "/tmp",
        }

    def close(self) -> None:
        return


class FakeTurnControlClient(FakeInitializeClient):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        if method == "thread/start":
            return {
                "thread": {"id": "thread-1", "name": "Fake"},
                "model": "fake-model",
                "modelProvider": "fake-provider",
                "cwd": "/tmp",
            }
        if method == "turn/interrupt":
            return {}
        if method == "turn/steer":
            return {"turnId": str((params or {}).get("expectedTurnId") or "")}
        return super().request(method, params)


class FakeThreadManagementClient(FakeInitializeClient):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        if method == "thread/list":
            return {"data": [], "nextCursor": None, "backwardsCursor": None}
        if method == "thread/loaded/list":
            return {"data": []}
        if method in {
            "thread/read",
            "thread/unarchive",
            "thread/rollback",
            "thread/metadata/update",
        }:
            return {"thread": {"id": str((params or {}).get("threadId") or "thread-1")}}
        return {}


class FakeVisibleChildBackend:
    active_tab_id = "parent-tab"
    _tab_order = ["parent-tab", "child-tab"]
    _tabs = {"parent-tab": object(), "child-tab": object()}

    def __init__(self) -> None:
        self.dispatch_calls: list[dict[str, object]] = []

    def display_tab_label(self, tab_id: str) -> str:
        return "1" if tab_id == "parent-tab" else "2"

    def child_tab_ids(self, parent_tab_id: str) -> list[str]:
        return ["child-tab"] if parent_tab_id == "parent-tab" else []

    def dispatch_visible_child_task(self, **kwargs: object) -> dict[str, object]:
        self.dispatch_calls.append(dict(kwargs))
        return {
            "tab_id": "child-tab",
            "task_id": "fake_dynamic_run:dynamic_child:0",
            "provider_name": "openai",
            "model": "gpt-fake",
            "route_label": "dispatch_visible_child_tab",
        }

    def visible_child_task_run_snapshots(self, parent_tab_id: str) -> list[dict[str, object]]:
        if parent_tab_id != "parent-tab":
            return []
        return [
            {
                "run_id": "fake_dynamic_run",
                "tab_id": "child-tab",
                "state": "completed",
                "terminal_state": "completed",
                "objective_state": "claimed_done",
                "summary": "fake visible child completed",
                "assignment_ref": {
                    "run_id": "fake_dynamic_run",
                    "card_id": "dynamic_child",
                    "attempt": 0,
                },
            }
        ]


class FakeModelCatalogClient(FakeInitializeClient):
    def __init__(self) -> None:
        super().__init__()
        self.model_calls = 0
        self.capability_calls = 0

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        if method == "model/list":
            self.model_calls += 1
            return {
                "data": [
                    {
                        "id": "gpt-fake",
                        "model": "gpt-fake",
                        "displayName": "GPT Fake",
                        "hidden": False,
                    }
                ],
                "nextCursor": None,
            }
        if method == "modelProvider/capabilities/read":
            self.capability_calls += 1
            return {
                "namespaceTools": True,
                "imageGeneration": False,
                "webSearch": True,
            }
        if method == "thread/start":
            return {
                "thread": {
                    "id": f"thread-{len(self.request_calls)}",
                    "name": "Fake",
                },
                "model": str((params or {}).get("model") or "fake-model"),
                "modelProvider": str((params or {}).get("modelProvider") or "fake-provider"),
                "cwd": str((params or {}).get("cwd") or "/tmp"),
            }
        return super().request(method, params)


class FakeFsClient(FakeInitializeClient):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        if method == "fs/readFile":
            return {"dataBase64": "aGVsbG8="}
        if method == "fs/readDirectory":
            return {"entries": [{"fileName": "note.txt", "isDirectory": False, "isFile": True}]}
        if method == "fs/getMetadata":
            return {
                "isDirectory": False,
                "isFile": True,
                "isSymlink": False,
                "createdAtMs": 1,
                "modifiedAtMs": 2,
            }
        return super().request(method, params)


class FakeEvaluationClient(FakeInitializeClient):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        self.request_calls.append((method, params))
        if method == "mcpServerStatus/list":
            return {"data": [{"name": "fake-mcp", "tools": {}, "authStatus": {"type": "none"}}]}
        if method == "skills/list":
            return {
                "data": [{"cwd": "/tmp/work", "skills": [{"name": "fake-skill"}], "errors": []}]
            }
        if method == "plugin/list":
            return {
                "marketplaces": [{"name": "fake-market", "plugins": [{"name": "fake-plugin"}]}],
                "marketplaceLoadErrors": [],
                "featuredPluginIds": [],
            }
        if method == "plugin/read":
            return {"plugin": {"summary": {"name": str((params or {}).get("pluginName") or "")}}}
        if method == "mcpServer/resource/read":
            return {"contents": [{"text": "resource"}]}
        if method == "mcpServer/tool/call":
            return {"content": [{"type": "text", "text": "called"}], "isError": False}
        return super().request(method, params)


class CodexSidecarClientTest(unittest.TestCase):
    def test_initialize_sends_handshake_and_collects_initialized_notification(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )
        try:
            result = client.initialize()
            notification = client.get_notification(timeout=1)
        finally:
            client.close()

        self.assertEqual(result["userAgent"], "fake-codex-sidecar/0.1")
        self.assertIsNotNone(notification)
        self.assertEqual(notification.method, "server/initialized")

    def test_request_error_raises_request_error(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )
        try:
            with self.assertRaises(CodexSidecarRequestError):
                client.request("unknown/method")
        finally:
            client.close()

    def test_route_payload_dispatches_by_json_rpc_id(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )
        first: Queue[dict[str, object]] = Queue(maxsize=1)
        second: Queue[dict[str, object]] = Queue(maxsize=1)
        with client._responses_lock:
            client._responses[1] = first
            client._responses[2] = second

        client._route_payload({"id": 2, "result": {"ok": "second"}})
        client._route_payload({"method": "turn/completed", "params": {"turnId": "t1"}})
        client._route_payload({"id": 1, "result": {"ok": "first"}})

        self.assertEqual(first.get_nowait()["result"], {"ok": "first"})
        self.assertEqual(second.get_nowait()["result"], {"ok": "second"})
        notification = client.get_notification(timeout=0)
        self.assertIsNotNone(notification)
        self.assertEqual(notification.method, "turn/completed")

    def test_route_payload_dispatches_server_request_by_method_and_id(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )

        client._route_payload(
            {
                "id": 8,
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "cmd-1",
                    "command": "printf ok",
                },
            }
        )

        request = client.get_server_request(timeout=0)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.request_id, 8)
        self.assertEqual(request.method, "item/commandExecution/requestApproval")
        self.assertEqual(request.params["command"], "printf ok")

    def test_matching_consumers_defer_other_thread_notifications_and_requests(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )
        client._route_payload(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-b",
                    "turn": {"id": "turn-b"},
                },
            }
        )
        client._route_payload(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-a",
                    "turn": {"id": "turn-a"},
                },
            }
        )
        client._route_payload(
            {
                "id": "approval-b",
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "thread-b",
                    "turnId": "turn-b",
                    "approvalId": "approval-b",
                },
            }
        )
        client._route_payload(
            {
                "id": "approval-a",
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "thread-a",
                    "turnId": "turn-a",
                    "approvalId": "approval-a",
                },
            }
        )

        notification_a = client.get_notification_matching(
            lambda item: item.params.get("threadId") == "thread-a",
            timeout=0,
        )
        request_a = client.get_server_request_matching(
            lambda item: item.params.get("threadId") == "thread-a",
            timeout=0,
        )
        notification_b = client.get_notification_matching(
            lambda item: item.params.get("threadId") == "thread-b",
            timeout=0,
        )
        request_b = client.get_server_request_matching(
            lambda item: item.params.get("threadId") == "thread-b",
            timeout=0,
        )

        self.assertIsNotNone(notification_a)
        self.assertIsNotNone(notification_b)
        self.assertEqual(notification_a.params["threadId"], "thread-a")
        self.assertEqual(notification_b.params["threadId"], "thread-b")
        self.assertIsNotNone(request_a)
        self.assertIsNotNone(request_b)
        self.assertEqual(request_a.params["approvalId"], "approval-a")
        self.assertEqual(request_b.params["approvalId"], "approval-b")

    def test_route_payload_projects_invalid_notification_as_protocol_error(self) -> None:
        client = CodexSidecarClient(
            CodexSidecarSupervisor(codex_bin=FAKE_CODEX_BIN),
            request_timeout=3,
        )

        client._route_payload({"method": "", "params": {"x": 1}})

        notification = client.get_notification(timeout=0)
        self.assertIsNotNone(notification)
        self.assertEqual(notification.method, "$agenthub/protocolError")


class CodexSidecarKernelTest(unittest.TestCase):
    def test_kernel_can_be_constructed_with_explicit_binary(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)

        self.assertIsInstance(kernel.client, CodexSidecarClient)
        asyncio.run(kernel.aclose())

    def test_start_session_initializes_and_starts_thread(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(
                kernel.start_session(
                    StartSessionRequest(
                        cwd="/tmp/work",
                        model="gpt-fake",
                        model_provider="openai",
                        metadata={
                            "approvalPolicy": "never",
                            "sandbox": "danger-full-access",
                        },
                    )
                )
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(session.engine, "codex_sidecar")
        self.assertEqual(session.session_id, "thread-1")
        self.assertEqual(session.thread_name, "Fake Thread")
        self.assertEqual(session.cwd, "/tmp/work")
        self.assertEqual(session.model, "gpt-fake")
        self.assertEqual(session.model_provider, "openai")
        self.assertEqual(session.metadata["raw_result"]["approvalPolicy"], "never")

    def test_concurrent_start_session_initializes_once(self) -> None:
        client = FakeInitializeClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        barrier = threading.Barrier(4)
        sessions = []

        def start_session() -> None:
            barrier.wait()
            sessions.append(asyncio.run(kernel.start_session(StartSessionRequest())))

        threads = [threading.Thread(target=start_session) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(len(sessions), 4)

    def test_start_turn_uses_existing_sidecar_session(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            turn = asyncio.run(
                kernel.start_turn(
                    StartTurnRequest(
                        session_id=session.session_id,
                        text="hello",
                    )
                )
            )
            notifications = []
            deadline = monotonic() + 3
            while monotonic() < deadline:
                notification = kernel.client.get_notification(timeout=0.1)
                if notification is None:
                    continue
                notifications.append(notification)
                if notification.method == "turn/completed":
                    break
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(turn.turn_id, "turn-1")
        self.assertIsNone(turn.response)
        self.assertEqual(turn.metadata["raw_result"]["turn"]["id"], "turn-1")
        self.assertEqual(turn.metadata["raw_result"]["turn"]["status"], "inProgress")
        self.assertIn("turn/started", [notification.method for notification in notifications])
        self.assertIn("turn/completed", [notification.method for notification in notifications])

    def test_resume_session_uses_thread_resume(self) -> None:
        client = FakeInitializeClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        session = asyncio.run(
            kernel.resume_session(
                ResumeSessionRequest(
                    thread_id="thread-existing",
                    path="/tmp/thread.jsonl",
                    cwd="/tmp/work",
                    metadata={"approvalPolicy": "never", "sandbox": "danger-full-access"},
                )
            )
        )

        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(session.session_id, "thread-1")
        method, params = client.request_calls[-1]
        self.assertEqual(method, "thread/resume")
        assert params is not None
        self.assertEqual(params["threadId"], "thread-existing")
        self.assertEqual(params["path"], "/tmp/thread.jsonl")
        self.assertEqual(params["cwd"], "/tmp/work")
        self.assertEqual(params["approvalPolicy"], "never")
        self.assertEqual(params["sandbox"], "danger-full-access")
        self.assertEqual(params["persistExtendedHistory"], True)

    def test_fork_session_uses_thread_fork(self) -> None:
        client = FakeInitializeClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        session = asyncio.run(
            kernel.fork_session(
                ForkSessionRequest(
                    source_thread_id="thread-source",
                    source_path="/tmp/source.jsonl",
                    cwd="/tmp/work",
                    metadata={"approvalPolicy": "on-request"},
                )
            )
        )

        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(session.session_id, "thread-1")
        method, params = client.request_calls[-1]
        self.assertEqual(method, "thread/fork")
        assert params is not None
        self.assertEqual(params["threadId"], "thread-source")
        self.assertEqual(params["path"], "/tmp/source.jsonl")
        self.assertEqual(params["cwd"], "/tmp/work")
        self.assertEqual(params["approvalPolicy"], "on-request")
        self.assertEqual(params["persistExtendedHistory"], True)

    def test_thread_start_params_include_codex_dynamic_tools_metadata(self) -> None:
        client = FakeInitializeClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        metadata = codex_visible_child_dynamic_tool_metadata()

        asyncio.run(kernel.start_session(StartSessionRequest(metadata=metadata)))

        method, params = client.request_calls[-1]
        self.assertEqual(method, "thread/start")
        assert params is not None
        tools = params.get("dynamicTools")
        self.assertIsInstance(tools, list)
        assert isinstance(tools, list)
        self.assertEqual(
            [item.get("name") for item in tools],
            ["spawn_child_tab", "send_child_tab", "wait_child_tasks"],
        )
        self.assertNotIn("spawn_agent", {str(item.get("name")) for item in tools})
        self.assertTrue(all(item.get("namespace") == "agenthub" for item in tools))

    def test_codex_visible_child_dynamic_tool_specs_use_app_server_shape(self) -> None:
        tools = codex_visible_child_dynamic_tools()

        self.assertEqual(len(tools), 3)
        by_name = {str(item["name"]): item for item in tools}
        self.assertEqual(
            set(by_name),
            {"spawn_child_tab", "send_child_tab", "wait_child_tasks"},
        )
        self.assertNotIn("spawn_agent", by_name)
        self.assertIn("Do not use spawn_agent", by_name["spawn_child_tab"]["description"])
        for tool in tools:
            self.assertEqual(tool["namespace"], AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE)
            self.assertIn("inputSchema", tool)
            self.assertIn("deferLoading", tool)
            self.assertNotIn("input_schema", tool)
            self.assertEqual(tool["deferLoading"], False)
        self.assertEqual(
            internal_command_for_dynamic_tool(
                namespace="agenthub",
                tool="spawn_child_tab",
            ),
            "__spawn_child_tab",
        )
        self.assertEqual(
            internal_command_for_dynamic_tool(
                namespace="other",
                tool="spawn_child_tab",
            ),
            "",
        )

    def test_kernel_prepends_bundle_path_entries_to_supervisor_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_root = root / "install" / "runtime" / "codex" / "linux-x86_64" / "v1"
            codex_bin = bundle_root / "codex-app-server"
            rg_dir = bundle_root / "path"
            resource_dir = bundle_root / "codex-resources"
            rg_dir.mkdir(parents=True)
            resource_dir.mkdir()
            codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            rg = rg_dir / "rg"
            rg.write_text("#!/bin/sh\n", encoding="utf-8")
            bwrap = resource_dir / "bwrap"
            bwrap.write_text("#!/bin/sh\n", encoding="utf-8")
            for path in (codex_bin, rg, bwrap):
                path.chmod(0o755)
            (bundle_root / "manifest.json").write_text(
                (
                    '{"codexVersion":"0.1.0","pathEntries":["path"],'
                    '"resources":{"path":"path/rg","bwrap":"codex-resources/bwrap"}}\n'
                ),
                encoding="utf-8",
            )

            kernel = CodexSidecarKernel(
                artifact_config=CodexSidecarArtifactConfig(
                    install_root=root / "install",
                    runtime_version="v1",
                    allow_path_lookup=False,
                ),
                extra_env={"PATH": "/usr/bin:/bin"},
            )

        supervisor = kernel.client.supervisor
        path_parts = str(supervisor.extra_env["PATH"]).split(":")
        self.assertEqual(path_parts[0], str(rg_dir.resolve(strict=False)))
        self.assertEqual(path_parts[1], str(resource_dir.resolve(strict=False)))
        self.assertEqual(path_parts[-2:], ["/usr/bin", "/bin"])

    def test_cancel_turn_uses_turn_interrupt(self) -> None:
        client = FakeTurnControlClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(kernel.start_session(StartSessionRequest()))

        asyncio.run(kernel.cancel_turn(session.session_id, "turn-123"))

        method, params = client.request_calls[-1]
        self.assertEqual(method, "turn/interrupt")
        assert params is not None
        self.assertEqual(params["threadId"], "thread-1")
        self.assertEqual(params["turnId"], "turn-123")

    def test_steer_turn_uses_turn_steer_expected_turn_id(self) -> None:
        client = FakeTurnControlClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(kernel.start_session(StartSessionRequest()))

        result = asyncio.run(
            kernel.steer_turn(
                session_id=session.session_id,
                turn_id="turn-123",
                text="focus tests",
            )
        )

        method, params = client.request_calls[-1]
        self.assertEqual(method, "turn/steer")
        assert params is not None
        self.assertEqual(params["threadId"], "thread-1")
        self.assertEqual(params["expectedTurnId"], "turn-123")
        self.assertEqual(params["input"][0]["text"], "focus tests")
        self.assertEqual(result["turnId"], "turn-123")

    def test_thread_management_methods_use_codex_wire_shape(self) -> None:
        client = FakeThreadManagementClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        self.assertEqual(
            kernel.read_thread("thread-1", include_turns=False)["thread"]["id"], "thread-1"
        )
        kernel.list_threads(
            cursor="cursor-1",
            limit=5,
            sort_key="updated_at",
            sort_direction="asc",
            model_providers=["openai"],
            source_kinds=["cli"],
            archived=True,
            cwd=["/tmp/a", "/tmp/b"],
            use_state_db_only=True,
            search_term="needle",
        )
        kernel.list_loaded_threads(cursor="loaded-1", limit=2)
        kernel.archive_thread("thread-1")
        kernel.unarchive_thread("thread-1")
        kernel.rollback_thread("thread-1", num_turns=2)
        kernel.compact_thread("thread-1")
        kernel.set_thread_name("thread-1", "Renamed")
        kernel.update_thread_metadata("thread-1", {"gitInfo": {"branch": "main"}})

        calls = client.request_calls
        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(calls[0][0], "thread/read")
        self.assertEqual(calls[0][1], {"threadId": "thread-1", "includeTurns": False})
        self.assertEqual(calls[1][0], "thread/list")
        assert calls[1][1] is not None
        self.assertEqual(
            calls[1][1],
            {
                "cursor": "cursor-1",
                "limit": 5,
                "sortKey": "updated_at",
                "sortDirection": "asc",
                "modelProviders": ["openai"],
                "sourceKinds": ["cli"],
                "archived": True,
                "cwd": ["/tmp/a", "/tmp/b"],
                "useStateDbOnly": True,
                "searchTerm": "needle",
            },
        )
        self.assertEqual(calls[2], ("thread/loaded/list", {"cursor": "loaded-1", "limit": 2}))
        self.assertEqual(calls[3], ("thread/archive", {"threadId": "thread-1"}))
        self.assertEqual(calls[4], ("thread/unarchive", {"threadId": "thread-1"}))
        self.assertEqual(calls[5], ("thread/rollback", {"threadId": "thread-1", "numTurns": 2}))
        self.assertEqual(calls[6], ("thread/compact/start", {"threadId": "thread-1"}))
        self.assertEqual(calls[7], ("thread/name/set", {"threadId": "thread-1", "name": "Renamed"}))
        self.assertEqual(
            calls[8],
            ("thread/metadata/update", {"threadId": "thread-1", "gitInfo": {"branch": "main"}}),
        )

    def test_thread_management_rejects_invalid_inputs(self) -> None:
        client = FakeThreadManagementClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "thread_id is required"):
            kernel.read_thread("")
        with self.assertRaisesRegex(RuntimeError, "num_turns >= 1"):
            kernel.rollback_thread("thread-1", num_turns=0)
        with self.assertRaisesRegex(RuntimeError, "must not be empty"):
            kernel.set_thread_name("thread-1", " ")

    def test_thread_management_round_trips_fake_sidecar(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest(cwd="/tmp/work")))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            runtime.handle_prompt("first turn")
            runtime.handle_prompt("second turn")

            read_result = kernel.read_thread(session.thread_id, include_turns=True)
            list_result = kernel.list_threads(limit=10)
            loaded_result = kernel.list_loaded_threads(limit=10)
            name_result = kernel.set_thread_name(session.thread_id, "Thread Name")
            metadata_result = kernel.update_thread_metadata(
                session.thread_id,
                {"gitInfo": {"branch": "feature/sidecar"}},
            )
            rollback_result = kernel.rollback_thread(session.thread_id, num_turns=1)
            archive_result = kernel.archive_thread(session.thread_id)
            archived_list_result = kernel.list_threads(archived=True)
            unarchive_result = kernel.unarchive_thread(session.thread_id)
            compact_result = kernel.compact_thread(session.thread_id)
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(len(read_result["thread"]["turns"]), 2)
        self.assertEqual([item["id"] for item in list_result["data"]], [session.thread_id])
        self.assertIn(session.thread_id, loaded_result["data"])
        self.assertEqual(name_result, {})
        self.assertEqual(
            metadata_result["thread"]["gitInfo"],
            {"branch": "feature/sidecar"},
        )
        self.assertEqual(len(rollback_result["thread"]["turns"]), 1)
        self.assertEqual(archive_result, {})
        self.assertEqual([item["id"] for item in archived_list_result["data"]], [session.thread_id])
        self.assertEqual(unarchive_result["thread"]["id"], session.thread_id)
        self.assertEqual(compact_result, {})

    def test_model_catalog_methods_use_codex_wire_shape(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        models = kernel.list_models(limit=5, cursor="cursor-1", include_hidden=True)
        capabilities = kernel.read_model_provider_capabilities()

        self.assertEqual(models["data"][0]["id"], "gpt-fake")
        self.assertEqual(capabilities["namespaceTools"], True)
        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(
            client.request_calls[0],
            ("model/list", {"cursor": "cursor-1", "limit": 5, "includeHidden": True}),
        )
        self.assertEqual(client.request_calls[1], ("modelProvider/capabilities/read", {}))

    def test_model_catalog_caches_models_and_capabilities(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        catalog = CodexSidecarModelCatalog(kernel, ttl_seconds=60)

        first_models = catalog.list_models()
        second_models = catalog.list_models()
        first_caps = catalog.read_provider_capabilities()
        second_caps = catalog.read_provider_capabilities()

        self.assertEqual(first_models, second_models)
        self.assertEqual(first_caps, second_caps)
        self.assertEqual(client.model_calls, 1)
        self.assertEqual(client.capability_calls, 1)
        status = catalog.status_fields()
        self.assertEqual(status["codex_model_catalog_source"], "sidecar")
        self.assertEqual(status["codex_model_count"], "1")
        self.assertEqual(status["codex_provider_capabilities"], "namespaceTools,webSearch")

    def test_model_catalog_round_trips_fake_sidecar_and_provider_status(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            models = runtime.model_catalog.list_models(include_hidden=True)
            capabilities = runtime.model_catalog.read_provider_capabilities()
            status = runtime.agent.provider_status()
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(len(models["data"]), 2)
        self.assertEqual(capabilities["webSearch"], True)
        self.assertEqual(status["codex_model_count"], "2")
        self.assertEqual(status["codex_model_catalog_source"], "sidecar")
        self.assertEqual(status["codex_provider_capabilities"], "namespaceTools,webSearch")

    def test_runtime_adapter_handles_sidecar_provider_and_models_slash_commands(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(kernel.start_session(StartSessionRequest()))
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)

        provider_response = runtime.handle_prompt("/provider")
        models_response = runtime.handle_prompt("/models include-hidden refresh")

        self.assertTrue(provider_response.handled_as_command)
        self.assertIn("runtime_kernel=codex_sidecar", provider_response.assistant_text)
        self.assertTrue(models_response.handled_as_command)
        self.assertIn("- gpt-fake: GPT Fake", models_response.assistant_text)
        self.assertNotIn("turn/start", [method for method, _params in client.request_calls])
        self.assertIn(
            ("model/list", {"includeHidden": True}),
            client.request_calls,
        )

    def test_runtime_adapter_handles_agenthub_orchestration_slash_commands_locally(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(kernel.start_session(StartSessionRequest(cwd=tmpdir)))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)

            response = runtime.handle_prompt(
                "/orchestrate read README and summarize project capability\n"
                "owned_files: README.md\n"
                "acceptance_criteria: summary reported"
            )
            matches = runtime.slash_command_matches("orchestrate_p")

        self.assertTrue(response.handled_as_command)
        self.assertIn("orchestration run created", response.assistant_text)
        self.assertEqual(response.status["command"], "orchestrate")
        self.assertEqual([item["name"] for item in matches], ["orchestrate_progress"])
        self.assertNotIn("turn/start", [method for method, _params in client.request_calls])

    def test_runtime_adapter_handles_exit_and_quit_locally(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(kernel.start_session(StartSessionRequest()))
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)

        exit_response = runtime.handle_prompt("/exit")
        quit_response = runtime.handle_prompt("/quit")

        self.assertTrue(exit_response.handled_as_command)
        self.assertEqual(exit_response.tool_events[0].name, "app_exit_requested")
        self.assertEqual(exit_response.tool_events[0].payload["thread_id"], session.thread_id)
        self.assertTrue(quit_response.handled_as_command)
        self.assertEqual(quit_response.tool_events[0].name, "app_exit_requested")
        self.assertEqual(runtime.turn_results, [exit_response, quit_response])
        self.assertNotIn("turn/start", [method for method, _params in client.request_calls])

    def test_runtime_adapter_provider_slash_surfaces_agenthub_and_projected_paths(
        self,
    ) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(kernel.start_session(StartSessionRequest()))
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
        runtime.agent._artifact_metadata["projected_config"] = {
            "codex_sidecar_config_path": "/tmp/codex-home/config.toml",
            "codex_sidecar_auth_path": "/tmp/codex-home/auth.json",
            "codex_sidecar_source_config_path": "/tmp/agenthub/config.toml",
            "codex_sidecar_source_auth_path": "/tmp/agenthub/auth.json",
            "codex_sidecar_agenthub_provider": "openai",
            "codex_sidecar_model_provider": "agenthub-openai",
        }
        runtime.kernel_session = KernelSession(
            engine="codex_sidecar",
            session_id=runtime.kernel_session.session_id,
            thread_id=runtime.kernel_session.thread_id,
            thread_name=runtime.kernel_session.thread_name,
            cwd=runtime.kernel_session.cwd,
            model=runtime.kernel_session.model,
            model_provider="agenthub-openai",
            metadata=runtime.kernel_session.metadata,
        )
        runtime.agent._session = runtime.kernel_session

        response = runtime.handle_prompt("/provider")

        self.assertTrue(response.handled_as_command)
        self.assertIn("provider_label=openai | fake-model | codex-sidecar", response.assistant_text)
        self.assertIn("provider_name=openai", response.assistant_text)
        self.assertNotIn("provider_name=agenthub-openai", response.assistant_text)
        self.assertNotIn("codex_sidecar_model_provider=agenthub-openai", response.assistant_text)
        self.assertIn("provider_config_path=/tmp/agenthub/config.toml", response.assistant_text)
        self.assertIn("provider_auth_path=/tmp/agenthub/auth.json", response.assistant_text)
        self.assertIn(
            "codex_sidecar_config_path=/tmp/codex-home/config.toml",
            response.assistant_text,
        )
        self.assertIn(
            "codex_sidecar_auth_path=/tmp/codex-home/auth.json",
            response.assistant_text,
        )

    def test_runtime_adapter_model_switch_maps_public_openai_to_sidecar_provider_id(
        self,
    ) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(
            kernel.start_session(
                StartSessionRequest(
                    cwd="/tmp/work",
                    model="old-model",
                    model_provider="agenthub-openai",
                )
            )
        )
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
        runtime.agent._artifact_metadata["projected_config"] = {
            "codex_sidecar_agenthub_provider": "openai",
            "codex_sidecar_model_provider": "agenthub-openai",
        }

        response = runtime.handle_prompt("/model gpt-fake provider openai")

        self.assertTrue(response.handled_as_command)
        self.assertIn("provider=openai", response.assistant_text)
        self.assertEqual(runtime.kernel_session.model_provider, "agenthub-openai")
        self.assertEqual(runtime.agent.provider_status()["provider_name"], "openai")
        self.assertIn(
            (
                "thread/start",
                {
                    "persistExtendedHistory": True,
                    "cwd": "/tmp/work",
                    "modelProvider": "agenthub-openai",
                    "model": "gpt-fake",
                },
            ),
            client.request_calls,
        )

    def test_runtime_adapter_model_slash_starts_fresh_sidecar_thread(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(
            kernel.start_session(StartSessionRequest(cwd="/tmp/work", model="old-model"))
        )
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
        runtime.history = [{"role": "user", "content": "old"}]
        runtime.history_turns = [{"user_text": "old", "assistant_text": "old"}]
        runtime.turn_results = [object()]  # type: ignore[list-item]

        response = runtime.handle_prompt("/model gpt-fake provider openai high")

        self.assertTrue(response.handled_as_command)
        self.assertIn("updated session model=gpt-fake", response.assistant_text)
        self.assertIn("switch_semantics=new_thread", response.assistant_text)
        self.assertIn("reasoning_effort_note=", response.assistant_text)
        self.assertEqual(runtime.kernel_session.model, "gpt-fake")
        self.assertEqual(runtime.kernel_session.model_provider, "openai")
        self.assertNotEqual(runtime.kernel_session.thread_id, session.thread_id)
        self.assertEqual(runtime.history, [])
        self.assertEqual(runtime.history_turns, [])
        self.assertEqual(runtime.turn_results, [response])
        self.assertEqual(runtime.agent.provider_status()["provider_model"], "gpt-fake")
        self.assertEqual(runtime.evaluation_bridge.thread_id, runtime.kernel_session.thread_id)
        self.assertIn(
            (
                "thread/start",
                {
                    "persistExtendedHistory": True,
                    "cwd": "/tmp/work",
                    "modelProvider": "openai",
                    "model": "gpt-fake",
                },
            ),
            client.request_calls,
        )
        self.assertNotIn("turn/start", [method for method, _params in client.request_calls])

    def test_runtime_adapter_provider_slash_starts_fresh_sidecar_thread(self) -> None:
        client = FakeModelCatalogClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        session = asyncio.run(
            kernel.start_session(
                StartSessionRequest(cwd="/tmp/work", model="gpt-fake", model_provider="openai")
            )
        )
        runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
        runtime.history = [{"role": "user", "content": "old"}]

        response = runtime.handle_prompt("/provider codex")

        self.assertTrue(response.handled_as_command)
        self.assertIn("updated session provider=codex", response.assistant_text)
        self.assertIn("switch_semantics=new_thread", response.assistant_text)
        self.assertEqual(runtime.kernel_session.model, "gpt-fake")
        self.assertEqual(runtime.kernel_session.model_provider, "codex")
        self.assertEqual(runtime.history, [])
        self.assertEqual(runtime.turn_results, [response])
        self.assertIn(
            (
                "thread/start",
                {
                    "persistExtendedHistory": True,
                    "cwd": "/tmp/work",
                    "modelProvider": "codex",
                    "model": "gpt-fake",
                },
            ),
            client.request_calls,
        )
        self.assertNotIn("turn/start", [method for method, _params in client.request_calls])

    def test_runtime_adapter_handles_sidecar_thread_management_slash_commands(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            runtime.handle_prompt("first turn")
            runtime.handle_prompt("second turn")

            list_response = runtime.handle_prompt("/codex_threads limit 5")
            read_response = runtime.handle_prompt(f"/codex_thread {session.thread_id}")
            rollback_response = runtime.handle_prompt("/codex_rollback turns 1")
            compact_response = runtime.handle_prompt("/codex_compact")
        finally:
            asyncio.run(kernel.aclose())

        self.assertTrue(list_response.handled_as_command)
        self.assertIn(f"- {session.thread_id} - name=", list_response.assistant_text)
        self.assertIn("turns=2", read_response.assistant_text)
        self.assertIn("codex rollback complete", rollback_response.assistant_text)
        self.assertIn("remaining_turns=1", rollback_response.assistant_text)
        self.assertIn("codex compact requested", compact_response.assistant_text)

    def test_fs_methods_use_codex_wire_shape_and_require_absolute_paths(self) -> None:
        client = FakeFsClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]

        read_result = kernel.fs_read_file("/tmp/note.txt")
        directory_result = kernel.fs_read_directory("/tmp")
        metadata_result = kernel.fs_get_metadata("/tmp/note.txt")

        self.assertEqual(read_result["dataBase64"], "aGVsbG8=")
        self.assertEqual(directory_result["entries"][0]["fileName"], "note.txt")
        self.assertEqual(metadata_result["modifiedAtMs"], 2)
        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(client.request_calls[0], ("fs/readFile", {"path": "/tmp/note.txt"}))
        self.assertEqual(client.request_calls[1], ("fs/readDirectory", {"path": "/tmp"}))
        self.assertEqual(client.request_calls[2], ("fs/getMetadata", {"path": "/tmp/note.txt"}))
        with self.assertRaisesRegex(RuntimeError, "must be absolute"):
            kernel.fs_read_file("relative.txt")

    def test_fs_bridge_normalizes_workspace_paths_and_blocks_escape(self) -> None:
        client = FakeFsClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "note.txt").write_text("hello", encoding="utf-8")
            bridge = CodexSidecarFsBridge(kernel=kernel, workspace_root=workspace)

            file_result = bridge.read_file("note.txt")
            directory_result = bridge.read_directory(".")
            metadata_result = bridge.get_metadata("note.txt")

            self.assertEqual(file_result["content"], "hello")
            self.assertEqual(directory_result["entries"][0]["name"], "note.txt")
            self.assertEqual(metadata_result["is_file"], True)
            with self.assertRaises(PermissionError):
                bridge.read_file("../outside.txt")

    def test_fs_bridge_round_trips_fake_sidecar(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "note.txt").write_text("hello sidecar", encoding="utf-8")
            (workspace / "subdir").mkdir()
            try:
                session = asyncio.run(kernel.start_session(StartSessionRequest(cwd=str(workspace))))
                runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)

                read_result = runtime.fs_bridge.read_file("note.txt")
                raw_result = runtime.fs_bridge.read_file_raw("note.txt")
                directory_result = runtime.fs_bridge.read_directory(".")
                metadata_result = runtime.fs_bridge.get_metadata("note.txt")
            finally:
                asyncio.run(kernel.aclose())

        self.assertEqual(read_result["content"], "hello sidecar")
        self.assertEqual(read_result["encoding"], "utf-8")
        self.assertEqual(read_result["decode_errors"], "replace")
        self.assertEqual(raw_result["content_bytes"], b"hello sidecar")
        self.assertIn("note.txt", [item["name"] for item in directory_result["entries"]])
        self.assertEqual(metadata_result["is_file"], True)

    def test_evaluation_bridge_methods_use_codex_wire_shape(self) -> None:
        client = FakeEvaluationClient()
        kernel = CodexSidecarKernel(client=client)  # type: ignore[arg-type]
        bridge = CodexSidecarEvaluationBridge(kernel=kernel, thread_id="thread-1")

        bridge.list_mcp_servers(limit=5, cursor="c1", detail="toolsAndAuthOnly")
        bridge.list_skills(cwds=["/tmp/work"], force_reload=True)
        bridge.list_plugins(cwds=["/tmp/work"])
        bridge.read_plugin("fake-plugin")
        bridge.read_mcp_resource(server="fake-mcp", uri="file://resource")
        blocked = bridge.call_mcp_tool(server="fake-mcp", tool="echo", arguments={"x": 1})
        bridge.allowed_mcp_tools.add("fake-mcp/echo")
        allowed = bridge.call_mcp_tool(server="fake-mcp", tool="echo", arguments={"x": 1})

        self.assertEqual(client.initialize_calls, 1)
        self.assertEqual(
            client.request_calls[0],
            (
                "mcpServerStatus/list",
                {"cursor": "c1", "limit": 5, "detail": "toolsAndAuthOnly"},
            ),
        )
        self.assertEqual(
            client.request_calls[1], ("skills/list", {"cwds": ["/tmp/work"], "forceReload": True})
        )
        self.assertEqual(client.request_calls[2], ("plugin/list", {"cwds": ["/tmp/work"]}))
        self.assertEqual(client.request_calls[3], ("plugin/read", {"pluginName": "fake-plugin"}))
        self.assertEqual(
            client.request_calls[4],
            (
                "mcpServer/resource/read",
                {"server": "fake-mcp", "uri": "file://resource", "threadId": "thread-1"},
            ),
        )
        self.assertEqual(blocked["isError"], True)
        self.assertEqual(
            client.request_calls[5],
            (
                "mcpServer/tool/call",
                {
                    "server": "fake-mcp",
                    "tool": "echo",
                    "threadId": "thread-1",
                    "arguments": {"x": 1},
                },
            ),
        )
        self.assertEqual(allowed["isError"], False)

    def test_evaluation_bridge_namespace_summary_round_trips_fake_sidecar(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            summary = runtime.evaluation_bridge.namespace_summary()
            blocked = runtime.evaluation_bridge.call_mcp_tool(
                server="fake-mcp",
                tool="echo",
                arguments={"message": "hi"},
            )
            runtime.evaluation_bridge.allowed_mcp_tools.add("fake-mcp/echo")
            allowed = runtime.evaluation_bridge.call_mcp_tool(
                server="fake-mcp",
                tool="echo",
                arguments={"message": "hi"},
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(summary["mcp_servers"], ["mcp:fake-mcp"])
        self.assertEqual(summary["skills"], ["codex:skill:fake-skill"])
        self.assertEqual(summary["plugins"], ["codex:fake-market/fake-plugin"])
        self.assertEqual(blocked["isError"], True)
        self.assertEqual(allowed["content"][0]["text"], "fake tool result")

    def test_evaluation_bridge_mcp_allowlist_is_shared_by_kernel(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            first = asyncio.run(kernel.start_session(StartSessionRequest()))
            second = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime_a = CodexSidecarRuntimeAdapter(kernel=kernel, session=first)
            runtime_b = CodexSidecarRuntimeAdapter(kernel=kernel, session=second)

            blocked = runtime_b.evaluation_bridge.call_mcp_tool(
                server="fake-mcp",
                tool="echo",
                arguments={"message": "hi"},
            )
            runtime_a.evaluation_bridge.allow_mcp_tool("fake-mcp", "echo")
            allowed = runtime_b.evaluation_bridge.call_mcp_tool(
                server="fake-mcp",
                tool="echo",
                arguments={"message": "hi"},
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(blocked["isError"], True)
        self.assertEqual(allowed["content"][0]["text"], "fake tool result")

    def test_fork_session_with_fake_sidecar_requires_rollout(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            with self.assertRaises(CodexSidecarRequestError):
                asyncio.run(
                    kernel.fork_session(ForkSessionRequest(source_thread_id=session.thread_id))
                )
        finally:
            asyncio.run(kernel.aclose())

    def test_fork_session_with_fake_sidecar_after_turn_returns_forked_thread(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            source = asyncio.run(kernel.start_session(StartSessionRequest(cwd="/tmp/work")))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=source)
            runtime.handle_prompt("seed fork")

            forked = asyncio.run(
                kernel.fork_session(ForkSessionRequest(source_thread_id=source.thread_id))
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertNotEqual(forked.thread_id, source.thread_id)
        self.assertEqual(forked.metadata["forked_from_thread_id"], source.thread_id)
        self.assertEqual(len(forked.metadata["thread_turns"]), 1)

    def test_forked_fake_sidecar_thread_inherits_visible_child_dynamic_tools(self) -> None:
        metadata = codex_visible_child_dynamic_tool_metadata()
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        backend = FakeVisibleChildBackend()
        try:
            source = asyncio.run(
                kernel.start_session(StartSessionRequest(cwd="/tmp/work", metadata=metadata))
            )
            source_runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=source)
            source_runtime.handle_prompt("seed fork")

            forked = asyncio.run(
                kernel.fork_session(ForkSessionRequest(source_thread_id=source.thread_id))
            )
            child_runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=forked)
            child_runtime.visible_child_tab_backend = backend
            child_runtime.visible_child_parent_tab_id = "parent-tab"

            response = child_runtime.handle_prompt("please exercise dynamic child tool")
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(len(backend.dispatch_calls), 1)
        self.assertEqual(
            backend.dispatch_calls[0],
            {
                "parent_tab_id": "parent-tab",
                "task_text": "Inspect README from inherited dynamic tool",
                "metadata": {
                    "run_id": "fake_dynamic_run",
                    "card_id": "dynamic_child",
                    "source": "spawn_child_tab",
                },
            },
        )
        self.assertIn("dynamic:success: visible child tab spawned", response.assistant_text)
        methods = [
            item.get("method") for item in response.protocol_diagnostics["codex_sidecar_events"]
        ]
        self.assertIn("item/tool/call", methods)
        self.assertEqual(forked.metadata["forked_from_thread_id"], source.thread_id)

    def test_resume_session_with_fake_sidecar_returns_persisted_turns(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            source = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=source)
            runtime.handle_prompt("seed resume")

            resumed = asyncio.run(
                kernel.resume_session(ResumeSessionRequest(thread_id=source.thread_id))
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(resumed.thread_id, source.thread_id)
        self.assertEqual(len(resumed.metadata["thread_turns"]), 1)

    def test_runtime_adapter_waits_for_turn_completed_and_projects_events(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            observed_events: list[dict[str, object]] = []
            runtime.turn_event_callback = lambda event: observed_events.append(dict(event))

            response = runtime.handle_prompt("hello sidecar")
        finally:
            asyncio.run(kernel.aclose())

        event_types = [event.get("type") for event in response.turn_events]
        self.assertEqual(event_types[0], "turn.started")
        self.assertEqual(event_types[-1], "turn.completed")
        self.assertIn("item.updated", event_types)
        self.assertIn("item.completed", event_types)
        command_updates = [
            event
            for event in response.turn_events
            if event.get("type") == "item.updated"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]
        self.assertEqual(command_updates[-1]["item"]["aggregated_output"], "ok\n")
        self.assertEqual(response.assistant_text, "fake sidecar reply")
        self.assertEqual(response.status["input_tokens"], 4)
        self.assertEqual(response.status["cached_input_tokens"], 1)
        self.assertEqual(response.status["output_tokens"], 6)
        self.assertEqual(response.status["model_context_window"], 128000)
        self.assertEqual(runtime.history_turns[-1]["turn_events"], response.turn_events)
        self.assertEqual(observed_events, response.turn_events)
        methods = [
            item.get("method") for item in response.protocol_diagnostics["codex_sidecar_events"]
        ]
        self.assertIn("item/agentMessage/delta", methods)
        self.assertIn("thread/tokenUsage/updated", methods)
        self.assertIn("turn/completed", methods)

    def test_runtime_adapter_round_trips_sidecar_command_approval(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            observed_activities: list[Any] = []
            runtime.activity_callback = lambda event: observed_activities.append(event)

            result_holder: dict[str, Any] = {}
            worker = threading.Thread(
                target=lambda: result_holder.setdefault(
                    "response",
                    runtime.handle_prompt("needs approval"),
                ),
                daemon=True,
            )
            worker.start()
            deadline = monotonic() + 3
            while monotonic() < deadline:
                ticket = runtime.gateway_state_store.get_approval_ticket("codex_fake_approval_1")
                if ticket is not None:
                    break
                threading.Event().wait(0.02)
            else:
                self.fail("sidecar approval ticket was not registered")

            decision = runtime.decide_approval(
                "codex_fake_approval_1",
                decision="accept",
                decided_by="test",
            )
            worker.join(timeout=3)
        finally:
            asyncio.run(kernel.aclose())

        self.assertFalse(worker.is_alive())
        self.assertIn("response", result_holder)
        ticket = runtime.gateway_state_store.get_approval_ticket("codex_fake_approval_1")
        self.assertIsNotNone(ticket)
        assert ticket is not None
        self.assertEqual(ticket.status, "approved")
        self.assertEqual(decision["codex_sidecar_response"], {"decision": "accept"})
        self.assertEqual(observed_activities[0].code, "approval.request.shell")
        self.assertEqual(observed_activities[0].params["approval_id"], "codex_fake_approval_1")
        event_types = [event.get("type") for event in result_holder["response"].turn_events]
        self.assertEqual(event_types[-1], "turn.completed")
        methods = [
            item.get("method")
            for item in result_holder["response"].protocol_diagnostics["codex_sidecar_events"]
        ]
        self.assertIn("item/commandExecution/requestApproval", methods)

    def test_runtime_adapter_replies_dynamic_tool_failure_for_unknown_dynamic_tool(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            activities: list[Any] = []
            runtime.activity_callback = activities.append
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )

            kernel.client._route_payload(
                {
                    "id": "unsupported-1",
                    "method": "item/tool/call",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "tool-1",
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["success"], False)
        self.assertEqual(responses[0]["contentItems"][0]["type"], "inputText")
        self.assertIn(
            "unsupported AgentHub dynamic tool",
            responses[0]["contentItems"][0]["text"],
        )
        self.assertEqual(activities, [])

    def test_runtime_adapter_replies_error_for_unsupported_sidecar_request(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            activities: list[Any] = []
            runtime.activity_callback = activities.append
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )

            kernel.client._route_payload(
                {
                    "id": "unsupported-1",
                    "method": "item/unknown/request",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "unknown-1",
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["error"]["code"], -32601)
        self.assertIn("unsupported sidecar server request", responses[0]["error"]["message"])
        self.assertEqual(activities[0].code, "codex_sidecar.unsupported_server_request")

    def test_runtime_adapter_registers_file_change_approval_and_decides(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )

            kernel.client._route_payload(
                {
                    "id": "file-approval-1",
                    "method": "item/fileChange/requestApproval",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "patch-1",
                        "reason": "apply patch",
                        "grantRoot": "/tmp/work",
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
            ticket = runtime.list_approval_tickets(limit=1, status="pending")[0]
            result = runtime.decide_approval(
                ticket.approval_id,
                decision="accept_for_session",
                decided_by="test",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(ticket.metadata["approval_kind"], "file_change")
        self.assertEqual(ticket.grant_root, "/tmp/work")
        self.assertEqual(result["codex_sidecar_response"], {"decision": "acceptForSession"})
        self.assertEqual(responses, [{"decision": "acceptForSession"}])

    def test_runtime_adapter_registers_permission_approval_and_decides(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )
            permissions = {"fileSystem": {"write": ["/tmp/work"]}}

            kernel.client._route_payload(
                {
                    "id": "perm-approval-1",
                    "method": "item/permissions/requestApproval",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "perm-1",
                        "cwd": "/tmp/work",
                        "reason": "write files",
                        "permissions": permissions,
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
            ticket = runtime.list_approval_tickets(limit=1, status="pending")[0]
            result = runtime.decide_approval(
                ticket.approval_id,
                decision="accept_for_session",
                decided_by="test",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(ticket.metadata["approval_kind"], "permissions")
        self.assertEqual(
            result["codex_sidecar_response"], {"permissions": permissions, "scope": "session"}
        )
        self.assertEqual(responses, [{"permissions": permissions, "scope": "session"}])

    def test_runtime_adapter_handles_tool_request_user_input(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            prompts: list[dict[str, object]] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )
            runtime.request_user_input_handler = lambda payload: (
                prompts.append(dict(payload)) or {"answers": {"confirm": {"answers": ["Yes"]}}}
            )

            kernel.client._route_payload(
                {
                    "id": "rui-1",
                    "method": "item/tool/requestUserInput",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "tool-1",
                        "questions": [
                            {
                                "id": "confirm",
                                "header": "Confirm",
                                "question": "Continue?",
                                "options": [
                                    {"label": "Yes", "description": "Continue."},
                                    {"label": "No", "description": "Cancel."},
                                ],
                            }
                        ],
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(prompts[0]["questions"][0]["id"], "confirm")
        self.assertEqual(responses, [{"answers": {"confirm": {"answers": ["Yes"]}}}])

    def test_runtime_adapter_handles_mcp_elicitation_with_request_user_input(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )
            runtime.request_user_input_handler = lambda _payload: {
                "answers": {"mcp_elicitation": {"answers": ["Accept"]}}
            }

            kernel.client._route_payload(
                {
                    "id": "mcp-1",
                    "method": "mcpServer/elicitation/request",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "serverName": "demo",
                        "mode": "form",
                        "message": "Allow MCP?",
                        "requestedSchema": {},
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(responses, [{"action": "accept", "content": {}}])

    def test_runtime_adapter_diagnoses_missing_tool_request_user_input_handler(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            activities: list[object] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )
            runtime.activity_callback = lambda activity: activities.append(activity)

            kernel.client._route_payload(
                {
                    "id": "rui-missing-1",
                    "method": "item/tool/requestUserInput",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "itemId": "tool-1",
                        "questions": [
                            {"id": "confirm", "header": "Confirm", "question": "Continue?"}
                        ],
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(responses, [{"answers": {}}])
        self.assertEqual(activities[0].code, "codex_sidecar.server_request_diagnostic")
        self.assertIn("not configured", activities[0].detail)

    def test_runtime_adapter_diagnoses_invalid_mcp_elicitation_answer(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            responses: list[dict[str, object]] = []
            activities: list[object] = []
            kernel.client.respond_to_server_request = (  # type: ignore[method-assign]
                lambda _request, response: responses.append(dict(response))
            )
            runtime.activity_callback = lambda activity: activities.append(activity)
            runtime.request_user_input_handler = lambda _payload: {"answers": {"other": "Accept"}}

            kernel.client._route_payload(
                {
                    "id": "mcp-invalid-1",
                    "method": "mcpServer/elicitation/request",
                    "params": {
                        "threadId": session.thread_id,
                        "turnId": "turn-1",
                        "serverName": "demo",
                        "mode": "form",
                        "message": "Allow MCP?",
                        "requestedSchema": {},
                    },
                }
            )
            runtime._drain_server_requests_for_turn(
                mapper=CodexSidecarTurnEventMapper(),
                thread_id=session.thread_id,
                turn_id="turn-1",
            )
        finally:
            asyncio.run(kernel.aclose())

        self.assertEqual(responses, [{"action": "cancel", "content": None}])
        self.assertEqual(activities[0].code, "codex_sidecar.server_request_diagnostic")
        self.assertIn("missing answers.mcp_elicitation.answers", activities[0].detail)

    def test_runtime_adapter_interrupts_active_sidecar_turn(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            result_holder: dict[str, Any] = {}
            worker = threading.Thread(
                target=lambda: result_holder.setdefault(
                    "response",
                    runtime.handle_prompt("slow turn for interrupt"),
                ),
                daemon=True,
            )
            worker.start()
            deadline = monotonic() + 3
            while monotonic() < deadline:
                if runtime.has_active_run():
                    break
                threading.Event().wait(0.02)
            else:
                self.fail("sidecar turn did not become active")

            interrupt_result = runtime.interrupt_active_run()
            worker.join(timeout=3)
        finally:
            asyncio.run(kernel.aclose())

        self.assertTrue(interrupt_result["ok"])
        self.assertFalse(worker.is_alive())
        event_types = [event.get("type") for event in result_holder["response"].turn_events]
        self.assertIn("turn.interrupted", event_types)
        self.assertFalse(runtime.has_active_run())

    def test_runtime_adapter_steers_active_sidecar_turn(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            runtime = CodexSidecarRuntimeAdapter(kernel=kernel, session=session)
            result_holder: dict[str, Any] = {}
            worker = threading.Thread(
                target=lambda: result_holder.setdefault(
                    "response",
                    runtime.handle_prompt("slow turn for steer"),
                ),
                daemon=True,
            )
            worker.start()
            deadline = monotonic() + 3
            while monotonic() < deadline:
                if runtime.has_active_run():
                    break
                threading.Event().wait(0.02)
            else:
                self.fail("sidecar turn did not become active")

            steer_result = runtime.steer_active_run("focus tests")
            worker.join(timeout=3)
        finally:
            asyncio.run(kernel.aclose())

        self.assertTrue(steer_result["accepted"])
        self.assertFalse(worker.is_alive())
        self.assertIn("steer:focus tests", result_holder["response"].assistant_text)
        self.assertFalse(runtime.has_active_run())

    def test_command_approval_execpolicy_amendment_uses_codex_wire_shape(self) -> None:
        response = command_approval_response_for_decision(
            {
                "type": "accept_with_execpolicy_amendment",
                "proposed_rule": {
                    "decision": "allow",
                    "match_kind": "prefix",
                    "command_tokens": ["python", "-m", "pytest"],
                    "normalized_command": "python -m pytest",
                },
            }
        )

        self.assertEqual(
            response,
            {
                "decision": {
                    "acceptWithExecpolicyAmendment": {
                        "execpolicy_amendment": ["python", "-m", "pytest"],
                    }
                }
            },
        )

    def test_runtime_adapter_treats_unscoped_protocol_error_as_terminal(self) -> None:
        from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter import (
            _notification_matches_turn,
        )

        self.assertTrue(
            _notification_matches_turn(
                {"error": "bad json"},
                thread_id="thread-1",
                turn_id="turn-1",
                method="$agenthub/protocolError",
            )
        )
        self.assertTrue(
            _notification_matches_turn(
                {"error": {"message": "boom"}},
                thread_id="thread-1",
                turn_id="turn-1",
                method="error",
            )
        )

    def test_close_session_unbinds_local_session_without_closing_sidecar(self) -> None:
        kernel = CodexSidecarKernel(codex_bin=FAKE_CODEX_BIN, request_timeout=3)
        try:
            session = asyncio.run(kernel.start_session(StartSessionRequest()))
            asyncio.run(kernel.close_session(session.session_id))

            with self.assertRaises(RuntimeError):
                asyncio.run(
                    kernel.start_turn(
                        StartTurnRequest(session_id=session.session_id, text="after close")
                    )
                )
        finally:
            asyncio.run(kernel.aclose())


if __name__ == "__main__":
    unittest.main()
