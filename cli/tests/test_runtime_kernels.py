from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_kernels import (
    ForkSessionRequest,
    ResumeSessionRequest,
    StartSessionRequest,
    StartTurnRequest,
    build_default_registry,
)
from cli.agent_cli.runtime_kernels.agenthub_python import AgentHubPythonKernel
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError
from cli.agent_cli.runtime_kernels.registry import RuntimeKernelRegistry


class FakeAgent:
    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_name": "fake-provider",
            "provider_model": "fake-model",
        }


class FakeRuntime:
    created: list[FakeRuntime] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)
        self.thread_prefix = str(kwargs.get("thread_prefix") or "thread")
        self.thread_store = kwargs.get("thread_store", object())
        self.gateway_state_store = kwargs.get("gateway_state_store")
        self.gateway_broadcaster = kwargs.get("gateway_broadcaster")
        self.runtime_policy = kwargs.get("runtime_policy")
        self.agent = FakeAgent()
        self.thread_id = ""
        self.thread_name = ""
        self.cwd = ""
        self.started: list[dict[str, Any]] = []
        self.resumed: list[dict[str, Any]] = []
        self.prompts: list[dict[str, Any]] = []
        self.interrupts = 0
        FakeRuntime.created.append(self)

    def start_thread(self, *, name: str | None = None, cwd: str | None = None) -> dict[str, Any]:
        self.thread_id = f"{self.thread_prefix}-{len(self.started) + 1}"
        self.thread_name = name or self.thread_id
        self.cwd = cwd or self.cwd
        self.started.append({"name": name, "cwd": cwd})
        return {"thread_id": self.thread_id, "name": self.thread_name}

    def resume_thread(
        self,
        thread_id: str | None = None,
        *,
        path: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.thread_id = thread_id or ("history-thread" if history is not None else "path-thread")
        self.thread_name = self.thread_id
        self.resumed.append({"thread_id": thread_id, "path": path, "history": history})
        return {"thread": {"thread_id": self.thread_id, "name": self.thread_name}}

    def handle_prompt(
        self,
        text: str,
        *,
        attachments: list[PromptAttachment] | None = None,
    ) -> PromptResponse:
        self.prompts.append({"text": text, "attachments": list(attachments or [])})
        return PromptResponse(
            user_text=text,
            assistant_text=f"reply: {text}",
            attachments=list(attachments or []),
        )

    def interrupt_active_run(self) -> dict[str, bool]:
        self.interrupts += 1
        return {"ok": True, "interrupted": True}

    @staticmethod
    def runtime_policy_status() -> dict[str, str]:
        return {"approval_policy": "never"}


class RuntimeKernelRegistryTest(unittest.TestCase):
    def test_registry_creates_registered_kernel(self) -> None:
        registry = RuntimeKernelRegistry()
        runtime = FakeRuntime()
        registry.register("agenthub_python", lambda: AgentHubPythonKernel(runtime))

        kernel = registry.create("agenthub_python")

        self.assertIsInstance(kernel, AgentHubPythonKernel)
        self.assertEqual(registry.engines(), ("agenthub_python",))

    def test_registry_raises_for_missing_kernel(self) -> None:
        registry = RuntimeKernelRegistry()

        with self.assertRaises(RuntimeError):
            registry.create("codex_sidecar")

    def test_default_registry_registers_python_kernel(self) -> None:
        registry = build_default_registry()

        self.assertTrue(registry.has("agenthub_python"))


class AgentHubPythonKernelTest(unittest.TestCase):
    def test_start_session_wraps_existing_runtime_thread(self) -> None:
        runtime = FakeRuntime()
        kernel = AgentHubPythonKernel(runtime)

        session = asyncio.run(
            kernel.start_session(StartSessionRequest(name="Main", cwd="/tmp/work"))
        )

        self.assertEqual(session.engine, "agenthub_python")
        self.assertEqual(session.session_id, "thread-1")
        self.assertEqual(session.thread_name, "Main")
        self.assertEqual(session.cwd, "/tmp/work")
        self.assertEqual(session.model_provider, "fake-provider")
        self.assertEqual(runtime.started, [{"name": "Main", "cwd": "/tmp/work"}])

    def test_resume_session_delegates_to_runtime(self) -> None:
        runtime = FakeRuntime()
        kernel = AgentHubPythonKernel(runtime)

        session = asyncio.run(
            kernel.resume_session(ResumeSessionRequest(thread_id="thread-existing"))
        )

        self.assertEqual(session.session_id, "thread-existing")
        self.assertEqual(
            runtime.resumed,
            [{"thread_id": "thread-existing", "path": None, "history": None}],
        )

    def test_start_turn_delegates_to_session_runtime(self) -> None:
        runtime = FakeRuntime()
        kernel = AgentHubPythonKernel(runtime)
        session = asyncio.run(kernel.start_session(StartSessionRequest()))
        attachment = PromptAttachment(path="/tmp/a.txt", name="a.txt")

        turn = asyncio.run(
            kernel.start_turn(
                StartTurnRequest(
                    session_id=session.session_id,
                    text="hello",
                    attachments=[attachment],
                )
            )
        )

        self.assertIsNotNone(turn.response)
        self.assertEqual(turn.response.assistant_text, "reply: hello")
        self.assertEqual(runtime.prompts, [{"text": "hello", "attachments": [attachment]}])

    def test_multiple_sessions_use_independent_runtime_instances(self) -> None:
        first_runtime = FakeRuntime(thread_prefix="first")
        second_runtime = FakeRuntime(thread_prefix="second")
        runtimes = [first_runtime, second_runtime]
        kernel = AgentHubPythonKernel(runtime_factory=lambda: runtimes.pop(0))

        first = asyncio.run(kernel.start_session(StartSessionRequest(name="First")))
        second = asyncio.run(kernel.start_session(StartSessionRequest(name="Second")))

        self.assertEqual(first.session_id, "first-1")
        self.assertEqual(second.session_id, "second-1")
        first_turn = asyncio.run(
            kernel.start_turn(StartTurnRequest(session_id=first.session_id, text="first"))
        )
        second_turn = asyncio.run(
            kernel.start_turn(StartTurnRequest(session_id=second.session_id, text="second"))
        )

        self.assertEqual(first_turn.response.assistant_text, "reply: first")
        self.assertEqual(second_turn.response.assistant_text, "reply: second")
        self.assertEqual(first_runtime.prompts[0]["text"], "first")
        self.assertEqual(second_runtime.prompts[0]["text"], "second")
        self.assertEqual(runtimes, [])

    def test_cancel_turn_delegates_to_runtime_interrupt(self) -> None:
        runtime = FakeRuntime()
        kernel = AgentHubPythonKernel(runtime)
        session = asyncio.run(kernel.start_session(StartSessionRequest()))

        asyncio.run(kernel.cancel_turn(session.session_id, "turn-1"))

        self.assertEqual(runtime.interrupts, 1)

    def test_close_session_removes_session_mapping(self) -> None:
        runtime = FakeRuntime()
        kernel = AgentHubPythonKernel(runtime)
        session = asyncio.run(kernel.start_session(StartSessionRequest()))

        asyncio.run(kernel.close_session(session.session_id))

        with self.assertRaises(RuntimeKernelSessionError):
            asyncio.run(
                kernel.start_turn(StartTurnRequest(session_id=session.session_id, text="x"))
            )

    def test_fork_session_uses_existing_thread_fork_record(self) -> None:
        FakeRuntime.created = []
        source_runtime = FakeRuntime()
        source_runtime.thread_id = "source-thread"
        kernel = AgentHubPythonKernel(source_runtime)
        asyncio.run(kernel.start_session(StartSessionRequest()))

        with (
            patch("cli.agent_cli.runtime.AgentCliRuntime", FakeRuntime),
            patch(
                "cli.agent_cli.runtime_core.thread_fork.fork_thread_record",
                return_value={"thread_id": "fork-thread"},
            ) as fork_thread,
        ):
            session = asyncio.run(
                kernel.fork_session(
                    ForkSessionRequest(source_session_id="thread-1", cwd="/tmp/fork")
                )
            )

        self.assertEqual(session.session_id, "fork-thread")
        self.assertEqual(FakeRuntime.created[-1].resumed[0]["thread_id"], "fork-thread")
        fork_thread.assert_called_once()
        self.assertEqual(fork_thread.call_args.kwargs["source_thread_id"], "thread-1")
        self.assertEqual(fork_thread.call_args.kwargs["cwd"], "/tmp/fork")


if __name__ == "__main__":
    unittest.main()
