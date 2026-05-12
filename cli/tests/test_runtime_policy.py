import io
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.app_server import main as app_server_main
from cli.agent_cli.app_server_shell_protocol import _shell_protocol_fields
from cli.agent_cli.headless import run_headless
from cli.agent_cli.models import AgentIntent, CommandExecutionResult, PromptResponse, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_core.command_handlers import handle_known_command
from cli.agent_cli.runtime_core.tool_commands import handle_runtime_policy_command
from cli.agent_cli.runtime_policy import (
    RuntimePolicy,
    shell_policy_contract_from_payload,
    shell_policy_decision_contract,
)
from cli.agent_cli.slash_parser import parse_slash_invocation

ROOT = Path(__file__).resolve().parents[2]


class _PolicyAgent:
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "glm",
            "model_key": "glm_5",
            "provider_planner": "openai_chat",
            "provider_model": "glm-5",
            "provider_tools": "tool-calls",
            "session_line": "glm-tools",
            "provider_label": "glm | glm-5 | tool-calls",
            "provider_base_url": "https://open.bigmodel.cn/api/paas/v4",
            "provider_source": "test",
            "platform_family": "unix",
            "platform_os": "linux",
            "shell_kind": "bash",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        return AgentIntent(assistant_text=f"ok: {text}")


class _PolicyTools:
    PROJECT_ROOT = ROOT

    def __init__(self) -> None:
        self.apply_patch_calls: list[str] = []
        self.shell_calls: list[str] = []
        self.shell_start_calls: list[str] = []
        self.shell_write_calls: list[tuple[str, str]] = []
        self.shell_terminate_calls: list[str] = []
        self.web_search_calls: list[str] = []
        self.web_fetch_calls: list[str] = []
        self._sessions: dict[str, dict[str, object]] = {}
        self._call_count = 0

    def _next_call_id(self) -> str:
        self._call_count += 1
        return f"call_{self._call_count}"

    @staticmethod
    def _lifecycle(
        *, phase: str, kind: str, call_id: str, session_id: str, process_id: str, status: str = ""
    ) -> dict[str, object]:
        payload = {
            "phase": phase,
            "kind": kind,
            "call_id": call_id,
            "session_id": session_id,
            "process_id": process_id,
            "source": "runtime_policy_test_tools",
        }
        if status:
            payload["status"] = status
        return payload

    def apply_patch(self, patch_text: str) -> ToolEvent:
        self.apply_patch_calls.append(patch_text)
        return ToolEvent(
            name="apply_patch", ok=True, summary="patch applied", payload={"file_count": 1}
        )

    def shell(
        self, command: str, *, timeout_sec=60, on_activity=None, cancel_event=None
    ) -> ToolEvent:
        self.shell_calls.append(command)
        call_id = self._next_call_id()
        session_id = f"exec_{len(self.shell_calls)}"
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell rc=0",
            payload={
                "command": command,
                "session_id": session_id,
                "call_id": call_id,
                "process_id": session_id,
                "returncode": 0,
                "stdout": "ok\n",
                "stderr": "",
                "duration_ms": 5,
                "lifecycle": self._lifecycle(
                    phase="completed",
                    kind="end",
                    call_id=call_id,
                    session_id=session_id,
                    process_id=session_id,
                    status="ok",
                ),
            },
        )

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        self.shell_start_calls.append(command)
        session_id = f"session_{len(self._sessions) + 1}"
        call_id = self._next_call_id()
        self._sessions[session_id] = {"command": command, "active": True, "call_id": call_id}
        if on_activity is not None:
            on_activity(
                {
                    "phase": "started",
                    "command": command,
                    "session_id": session_id,
                    "process_id": session_id,
                    "call_id": call_id,
                    "lifecycle": self._lifecycle(
                        phase="started",
                        kind="begin",
                        call_id=call_id,
                        session_id=session_id,
                        process_id=session_id,
                        status="started",
                    ),
                }
            )
        return {
            "session_id": session_id,
            "call_id": call_id,
            "process_id": session_id,
            "command": command,
            "lifecycle": self._lifecycle(
                phase="started",
                kind="begin",
                call_id=call_id,
                session_id=session_id,
                process_id=session_id,
                status="started",
            ),
        }

    def shell_write_stdin(self, session_id: str, chars: str, *, on_activity=None) -> ToolEvent:
        self.shell_write_calls.append((session_id, chars))
        session = self._sessions.get(session_id)
        if session is None or not session.get("active"):
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell stdin written",
            payload={
                "session_id": session_id,
                "call_id": str(session.get("call_id") or ""),
                "process_id": session_id,
                "chars": chars,
                "status": "written",
                "lifecycle": self._lifecycle(
                    phase="input",
                    kind="input",
                    call_id=str(session.get("call_id") or ""),
                    session_id=session_id,
                    process_id=session_id,
                    status="written",
                ),
            },
        )

    def shell_terminate(self, session_id: str, *, on_activity=None) -> ToolEvent:
        self.shell_terminate_calls.append(session_id)
        session = self._sessions.get(session_id)
        if session is None or not session.get("active"):
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        session["active"] = False
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell interrupted",
            payload={
                "session_id": session_id,
                "call_id": str(session.get("call_id") or ""),
                "process_id": session_id,
                "status": "interrupted",
                "interrupted": True,
                "returncode": -1,
                "lifecycle": self._lifecycle(
                    phase="completed",
                    kind="end",
                    call_id=str(session.get("call_id") or ""),
                    session_id=session_id,
                    process_id=session_id,
                    status="interrupted",
                ),
            },
        )

    def web_search(
        self, query: str, *, limit=5, domains=None, recency_days=None, market=None
    ) -> ToolEvent:
        self.web_search_calls.append(query)
        return ToolEvent(
            name="web_search", ok=True, summary="web results=1", payload={"ok": True, "count": 1}
        )

    def web_fetch(self, url: str, *, max_chars=12000) -> ToolEvent:
        self.web_fetch_calls.append(url)
        return ToolEvent(
            name="web_fetch", ok=True, summary="web page loaded", payload={"ok": True, "url": url}
        )

    def run_plugin_command(self, name, arg_text, runtime):
        return None


class _InterruptPolicyTools(_PolicyTools):
    def shell(
        self, command: str, *, timeout_sec=60, on_activity=None, cancel_event=None
    ) -> ToolEvent:
        self.shell_calls.append(command)
        call_id = self._next_call_id()
        session_id = f"exec_{len(self.shell_calls)}"
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell interrupted",
            payload={
                "command": command,
                "session_id": session_id,
                "call_id": call_id,
                "process_id": session_id,
                "returncode": -1,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "duration_ms": 5,
                "interrupted": True,
                "status": "interrupted",
                "reason": "user_interrupt",
                "lifecycle": self._lifecycle(
                    phase="completed",
                    kind="end",
                    call_id=call_id,
                    session_id=session_id,
                    process_id=session_id,
                    status="interrupted",
                ),
            },
        )


class _HeadlessRuntime:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.runtime_policy_updates: list[dict[str, object]] = []
        self.resume_calls: list[str] = []
        self.thread_id = ""

    def handle_prompt(self, prompt: str) -> PromptResponse:
        self.prompts.append(prompt)
        return PromptResponse(
            user_text=prompt,
            assistant_text="headless ok",
            status={"approval_policy": "never"},
        )

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ) -> dict[str, str]:
        self.runtime_policy_updates.append(
            {
                "approval_policy": approval_policy,
                "sandbox_mode": sandbox_mode,
                "web_search_mode": web_search_mode,
                "network_access_enabled": network_access_enabled,
            }
        )
        return {
            "approval_policy": str(approval_policy),
            "sandbox_mode": str(sandbox_mode),
            "web_search_mode": str(web_search_mode),
            "network_access": "enabled" if network_access_enabled else "disabled",
        }

    def resume_thread(self, thread_id: str) -> dict[str, object]:
        self.resume_calls.append(thread_id)
        self.thread_id = thread_id
        return {"thread": {"thread_id": thread_id}}


@contextmanager
def background_teammate_policy(**overrides: str):
    env = {
        "AGENT_CLI_COMMAND_POLICY_MODE": "background_teammate",
        "AGENT_CLI_TEST_POLICY": "scoped_only",
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        yield


class _NdjsonInput(io.StringIO):
    def isatty(self) -> bool:
        return False


class RuntimePolicyTest(unittest.TestCase):
    @staticmethod
    def _assert_policy_snapshot_schema(snapshot: dict[str, object] | None) -> None:
        normalized = dict(snapshot or {})
        expected_keys = {
            "approvalPolicy",
            "sandboxMode",
            "networkAccessEnabled",
            "requestPermissionEnabled",
        }
        assert_keys = set(normalized.keys())
        if assert_keys != expected_keys:
            raise AssertionError(f"policySnapshot keys mismatch: {assert_keys} != {expected_keys}")
        approval_policy = normalized.get("approvalPolicy")
        sandbox_mode = normalized.get("sandboxMode")
        network_access_enabled = normalized.get("networkAccessEnabled")
        request_permission_enabled = normalized.get("requestPermissionEnabled")
        if approval_policy is not None and not isinstance(approval_policy, str):
            raise AssertionError(f"approvalPolicy type mismatch: {type(approval_policy)}")
        if sandbox_mode is not None and not isinstance(sandbox_mode, str):
            raise AssertionError(f"sandboxMode type mismatch: {type(sandbox_mode)}")
        if network_access_enabled is not None and not isinstance(network_access_enabled, bool):
            raise AssertionError(
                f"networkAccessEnabled type mismatch: {type(network_access_enabled)}"
            )
        if request_permission_enabled is not None and not isinstance(
            request_permission_enabled, bool
        ):
            raise AssertionError(
                f"requestPermissionEnabled type mismatch: {type(request_permission_enabled)}"
            )

    @staticmethod
    def _assert_policy_decision_reason_pair(decision: str, reason: str) -> None:
        normalized_decision = str(decision or "").strip()
        normalized_reason = str(reason or "").strip()
        if normalized_decision == "allowed":
            if normalized_reason != "policy_allowed":
                raise AssertionError(
                    f"invalid decision-reason pair: {normalized_decision} + {normalized_reason}"
                )
            return
        if normalized_decision == "requires_approval":
            if normalized_reason != "approval_required":
                raise AssertionError(
                    f"invalid decision-reason pair: {normalized_decision} + {normalized_reason}"
                )
            return
        if normalized_decision == "blocked":
            if not normalized_reason.startswith("policy_denied"):
                raise AssertionError(
                    f"invalid decision-reason pair: {normalized_decision} + {normalized_reason}"
                )
            return
        raise AssertionError(f"unexpected policy decision: {normalized_decision}")

    def _assert_policy_triplet(
        self, decision: str, reason: str, snapshot: dict[str, object]
    ) -> None:
        self._assert_policy_decision_reason_pair(decision, reason)
        self._assert_policy_snapshot_schema(snapshot)

    def _build_runtime(self, approval_policy: str) -> AgentCliRuntime:
        return AgentCliRuntime(
            agent=_PolicyAgent(),
            tools=_PolicyTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy=approval_policy),
        )

    def _run_app_server_requests(
        self, runtime: AgentCliRuntime, requests: list[dict]
    ) -> list[dict]:
        lines = "\n".join(json.dumps(item) for item in requests) + "\n"
        stdin = _NdjsonInput(lines)
        stdout = io.StringIO()
        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]

    def _command_exec_response(
        self, runtime: AgentCliRuntime, command: str, *, stream: bool = False
    ) -> dict[str, object]:
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-exec",
                    "method": "command/exec",
                    "params": {"command": command, "stream": stream},
                },
            ],
        )
        return next(line for line in lines if line.get("id") == "cmd-exec")

    def _command_start_response(
        self,
        runtime: AgentCliRuntime,
        command: str,
        *,
        stream: bool = True,
    ) -> dict[str, object]:
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": command, "stream": stream},
                },
            ],
        )
        return next(line for line in lines if line.get("id") == "cmd-start")

    @staticmethod
    def _command_start_policy_readout(
        start_response: dict[str, object],
    ) -> tuple[str, str, dict[str, object]]:
        result = dict(start_response.get("result") or {})
        decision = str(result.get("policyDecision") or "").strip()
        reason = str(result.get("policyDecisionReason") or "").strip()
        snapshot = dict(result.get("policySnapshot") or {})
        if decision:
            return decision, reason, snapshot
        response = dict(result.get("response") or {})
        tool_events = list(response.get("tool_events") or [])
        payload = dict((tool_events[-1].get("payload") if tool_events else {}) or {})
        fields = _shell_protocol_fields(payload)
        return (
            str(fields.get("policyDecision") or "").strip(),
            str(fields.get("policyDecisionReason") or "").strip(),
            dict(fields.get("policySnapshot") or {}),
        )

    def _command_exec_policy_readout(self, exec_response: dict[str, object]) -> tuple[str, str]:
        result = dict(exec_response.get("result") or {})
        decision = str(result.get("policyDecision") or "").strip()
        reason = str(result.get("policyDecisionReason") or "").strip()
        if decision and reason:
            return decision, reason
        payload = dict(result.get("raw") or {})
        if not payload:
            response = dict(result.get("response") or {})
            tool_events = list(response.get("tool_events") or [])
            payload = dict((tool_events[-1].get("payload") if tool_events else {}) or {})
        fields = _shell_protocol_fields(payload)
        return (
            str(fields.get("policyDecision") or "").strip(),
            str(fields.get("policyDecisionReason") or "").strip(),
        )

    def test_runtime_status_command_reports_defaults(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        response = runtime.handle_prompt("/runtime_status")

        self.assertIn("runtime status", response.assistant_text)
        self.assertIn("approval_policy=on-request", response.assistant_text)
        self.assertIn("sandbox_mode=workspace-write", response.assistant_text)
        self.assertIn("web_search_mode=cached", response.assistant_text)
        self.assertIn("network_access=enabled", response.assistant_text)
        self.assertIn("permission_mode=default", response.assistant_text)
        self.assertEqual(response.status["approval_policy"], "on-request")

    def test_runtime_policy_defaults_web_search_mode_from_sandbox(self) -> None:
        default_policy = RuntimePolicy.normalized()
        full_access_policy = RuntimePolicy.normalized(sandbox_mode="danger-full-access")

        self.assertEqual(default_policy.web_search_mode, "cached")
        self.assertEqual(full_access_policy.web_search_mode, "live")

    def test_runtime_policy_updates_recompute_web_search_mode_when_sandbox_changes(self) -> None:
        policy = RuntimePolicy.normalized()
        full_access_policy = policy.with_updates(sandbox_mode="danger-full-access")
        workspace_write_policy = full_access_policy.with_updates(sandbox_mode="workspace-write")
        disabled_policy = workspace_write_policy.with_updates(web_search_mode="disabled")
        disabled_full_access_policy = disabled_policy.with_updates(
            sandbox_mode="danger-full-access"
        )

        self.assertEqual(full_access_policy.web_search_mode, "live")
        self.assertEqual(workspace_write_policy.web_search_mode, "cached")
        self.assertEqual(disabled_full_access_policy.web_search_mode, "disabled")

    def test_runtime_config_command_updates_policy(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        response = runtime.handle_prompt(
            "/runtime_config --approval-policy never --sandbox-mode read-only --web-search-mode disabled --network-access disabled"
        )

        self.assertIn("updated runtime policy", response.assistant_text)
        self.assertIn("approval_policy=never", response.assistant_text)
        self.assertIn("sandbox_mode=read-only", response.assistant_text)
        self.assertIn("web_search_mode=disabled", response.assistant_text)
        self.assertIn("network_access=disabled", response.assistant_text)
        self.assertEqual(runtime.runtime_policy_status()["sandbox_mode"], "read-only")
        self.assertEqual(response.status["network_access"], "disabled")

    def test_runtime_config_command_accepts_permission_mode(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        response = runtime.handle_prompt("/runtime_config --permission-mode accept-edits")

        self.assertIn("updated runtime policy", response.assistant_text)
        self.assertIn("permission_mode=acceptEdits", response.assistant_text)
        self.assertEqual(runtime.runtime_policy_status()["approval_policy"], "never")
        self.assertEqual(runtime.runtime_policy_status()["sandbox_mode"], "workspace-write")
        self.assertEqual(runtime.runtime_policy_status()["network_access"], "enabled")

    def test_runtime_config_permission_mode_conflict_prefers_explicit_options(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        response = runtime.handle_prompt(
            "/runtime_config --permission-mode plan --sandbox-mode workspace-write --network-access disabled"
        )

        self.assertIn("updated runtime policy", response.assistant_text)
        self.assertIn("permission_mode=custom", response.assistant_text)
        self.assertIn(
            "note: permission-mode plan overridden by explicit options", response.assistant_text
        )
        self.assertEqual(runtime.runtime_policy_status()["approval_policy"], "on-request")
        self.assertEqual(runtime.runtime_policy_status()["sandbox_mode"], "workspace-write")
        self.assertEqual(runtime.runtime_policy_status()["network_access"], "disabled")

    def test_runtime_config_slash_invocation_native_path_does_not_require_parse_args(self) -> None:
        class _RuntimeStub:
            def __init__(self) -> None:
                self._status = {
                    "approval_policy": "on-request",
                    "sandbox_mode": "workspace-write",
                    "web_search_mode": "live",
                    "network_access": "enabled",
                }

            def runtime_policy_status(self) -> dict[str, str]:
                return dict(self._status)

            def configure_runtime_policy(
                self,
                *,
                approval_policy=None,
                sandbox_mode=None,
                web_search_mode=None,
                network_access_enabled=None,
            ) -> dict[str, str]:
                if approval_policy is not None:
                    self._status["approval_policy"] = str(approval_policy)
                if sandbox_mode is not None:
                    self._status["sandbox_mode"] = str(sandbox_mode)
                if web_search_mode is not None:
                    self._status["web_search_mode"] = str(web_search_mode)
                if network_access_enabled is not None:
                    self._status["network_access"] = (
                        "enabled" if bool(network_access_enabled) else "disabled"
                    )
                return dict(self._status)

        runtime = _RuntimeStub()

        text, events = handle_runtime_policy_command(
            runtime,
            name="runtime_config",
            arg_text="",
            slash_invocation=parse_slash_invocation(
                "/runtime_config permission-mode accept-edits sandbox-mode workspace-write network-access disabled"
            ),
        ) or ("", [])

        self.assertEqual(events, [])
        self.assertIn("updated runtime policy", text)
        self.assertIn("permission_mode=custom", text)
        self.assertIn("sandbox_mode=workspace-write", text)
        self.assertIn("network_access=disabled", text)

    def test_apply_patch_runs_directly_when_approval_policy_is_never(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        result = handle_known_command(
            runtime,
            name="apply_patch",
            arg_text='"*** Begin Patch\\n*** End Patch"',
            text='/apply_patch "*** Begin Patch\\n*** End Patch"',
        )
        self.assertIsInstance(result, CommandExecutionResult)

        self.assertEqual(result.assistant_text, "Apply workspace patch.")
        self.assertEqual([event.name for event in result.tool_events], ["apply_patch"])
        self.assertEqual(len(tools.apply_patch_calls), 1)

    def test_apply_patch_is_blocked_in_read_only_mode(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())
        runtime.configure_runtime_policy(sandbox_mode="read-only")

        result = handle_known_command(
            runtime,
            name="apply_patch",
            arg_text='"*** Begin Patch\\n*** End Patch"',
            text='/apply_patch "*** Begin Patch\\n*** End Patch"',
        )
        self.assertIsInstance(result, CommandExecutionResult)

        self.assertEqual(result.assistant_text, "Patch blocked.")
        self.assertEqual(result.tool_events[0].payload["error"], "runtime sandbox is read-only")

    def test_shell_runs_opaque_command_without_approval_by_default(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        response = runtime.handle_prompt("/shell echo hello")

        self.assertIn("Run shell command.", response.assistant_text)
        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertEqual(tools.shell_calls, ["echo hello"])

    def test_shell_requests_approval_for_workspace_write_by_default(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        response = runtime.handle_prompt("/shell touch hello.txt")

        self.assertIn("Request shell approval.", response.assistant_text)
        self.assertEqual(
            [event.name for event in response.tool_events], ["shell_approval_requested"]
        )
        self.assertEqual(tools.shell_calls, [])
        self.assertIn("approval_id", response.tool_events[0].payload)
        approval_id = response.tool_events[0].payload["approval_id"]
        self.assertIn(f"/approve {approval_id}", response.assistant_text)
        self.assertIn(f"/reject {approval_id}", response.assistant_text)

    def test_shell_requests_approval_for_pure_network_command_by_default(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        response = runtime.handle_prompt("/shell curl -I https://example.com")

        self.assertIn("Request shell approval.", response.assistant_text)
        self.assertEqual(
            [event.name for event in response.tool_events], ["shell_approval_requested"]
        )
        self.assertEqual(tools.shell_calls, [])
        payload = dict(response.tool_events[0].payload or {})
        self.assertEqual(payload["policy_decision"], "requires_approval")
        self.assertEqual(payload["policy_decision_reason"], "approval_required")
        self.assertEqual(payload["reason_code"], "exec.network.requires_approval")
        self.assertIs(payload["network_access_enabled"], True)

    def test_background_teammate_workspace_write_requests_approval_before_enqueue(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        with patch("cli.agent_cli.background_tasks.enqueue_background_task") as patched_submit:
            response = runtime.handle_prompt(
                "/background_teammate 修复 README 标题 --provider glm --model glm_5 --reasoning-effort medium --sandbox-mode workspace-write --allowed-paths src,tests --blocked-paths README.md --timeout-seconds 30"
            )

        self.assertEqual(
            [event.name for event in response.tool_events],
            ["background_teammate_approval_requested"],
        )
        self.assertEqual(response.tool_events[0].payload["sandbox_mode"], "workspace-write")
        self.assertEqual(response.tool_events[0].payload["allowed_paths"], ["src", "tests"])
        self.assertEqual(response.tool_events[0].payload["blocked_paths"], ["README.md"])
        self.assertEqual(response.tool_events[0].payload["timeout_seconds"], 30.0)
        approval_id = response.tool_events[0].payload["approval_id"]
        self.assertIn(f"/approve {approval_id}", response.assistant_text)
        self.assertIn("staged_run=true", response.assistant_text)
        self.assertIn("final_apply_required=true", response.assistant_text)
        self.assertIn("timeout_seconds=30.0", response.assistant_text)
        patched_submit.assert_not_called()

    def test_apply_patch_requests_approval_with_next_step_commands_by_default(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())
        patch_text = '"*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch"'

        result = handle_known_command(
            runtime,
            name="apply_patch",
            arg_text=patch_text,
            text=f"/apply_patch {patch_text}",
        )
        self.assertIsInstance(result, CommandExecutionResult)

        self.assertEqual([event.name for event in result.tool_events], ["patch_approval_requested"])
        approval_id = result.tool_events[0].payload["approval_id"]
        self.assertIn("Request patch approval.", result.assistant_text)
        self.assertIn(f"/approve {approval_id}", result.assistant_text)
        self.assertIn(f"/reject {approval_id}", result.assistant_text)

    def test_non_shell_builtin_usage_paths_return_structured_result(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())

        fetch_usage = handle_known_command(
            runtime,
            name="web_fetch",
            arg_text="",
            text="/web_fetch",
        )
        self.assertIsInstance(fetch_usage, CommandExecutionResult)
        self.assertEqual(fetch_usage.assistant_text, "Usage: /web_fetch <url> [max-chars <n>]")
        self.assertEqual(fetch_usage.tool_events, [])

        browser_usage = handle_known_command(
            runtime,
            name="browser",
            arg_text="invalid_action",
            text="/browser invalid_action",
        )
        self.assertIsInstance(browser_usage, CommandExecutionResult)
        self.assertIn("Usage: /browser", browser_usage.assistant_text)
        self.assertEqual(browser_usage.tool_events, [])

    def test_approve_command_returns_structured_result(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        approval_response = runtime.handle_prompt("/shell touch hello.txt")
        approval_id = approval_response.tool_events[0].payload["approval_id"]
        result = handle_known_command(
            runtime,
            name="approve",
            arg_text=approval_id,
            text=f"/approve {approval_id}",
        )
        self.assertIsInstance(result, CommandExecutionResult)
        self.assertEqual(result.assistant_text, "")
        self.assertEqual(result.command_display_text, "")
        self.assertEqual(
            [event.name for event in result.tool_events], ["approval_decision", "shell"]
        )
        self.assertTrue(result.item_events)
        completed_tools = [
            str((event.get("item") or {}).get("tool") or "")
            for event in result.item_events
            if isinstance(event, dict) and event.get("type") == "item.completed"
        ]
        self.assertEqual(completed_tools, ["approval_decision"])

    def test_shell_runs_directly_when_approval_policy_is_never(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        response = runtime.handle_prompt("/shell echo hello")

        self.assertIn("Run shell command.", response.assistant_text)
        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertEqual(tools.shell_calls, ["echo hello"])

    def test_shell_denies_unscoped_pytest_under_background_teammate_policy(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        with background_teammate_policy():
            response = runtime.handle_prompt("/shell pytest -q")

        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertEqual(tools.shell_calls, [])
        self.assertEqual(response.tool_events[-1].payload["status"], "policy_denied")
        self.assertEqual(response.tool_events[-1].payload["error_code"], "test_scope_required")
        self.assertIn("explicit test files or node ids", response.assistant_text)

    def test_shell_wraps_scoped_pytest_with_machine_global_lock_under_background_teammate_policy(
        self,
    ) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        with background_teammate_policy(
            AGENT_CLI_TEST_LOCK_PATH="/tmp/agenthub_test_commands.lock"
        ):
            response = runtime.handle_prompt("/shell pytest -q cli/tests/test_runtime_policy.py")

        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertEqual(len(tools.shell_calls), 1)
        wrapped = tools.shell_calls[0]
        self.assertIn("test_command_lock_runner.py", wrapped)
        self.assertIn("/tmp/agenthub_test_commands.lock", wrapped)
        self.assertEqual(
            response.tool_events[-1].payload["command"],
            "pytest -q cli/tests/test_runtime_policy.py",
        )
        self.assertIn("effective_command", response.tool_events[-1].payload)
        self.assertEqual(
            response.tool_events[-1].payload["command_policy"]["test_policy"], "scoped_only"
        )

    def test_shell_user_interrupt_uses_interrupted_assistant_copy(self) -> None:
        tools = _InterruptPolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        response = runtime.handle_prompt("/shell sleep 5")

        self.assertEqual(response.assistant_text, "Execution interrupted.")
        self.assertEqual([event.name for event in response.tool_events], ["shell"])
        self.assertEqual(response.tool_events[-1].payload["reason"], "user_interrupt")

    def test_cli_shell_and_command_exec_match_under_never_policy(self) -> None:
        cli_runtime = self._build_runtime("never")
        cli_response = cli_runtime.handle_prompt("/shell echo stable")
        cli_event = cli_response.tool_events[-1]

        exec_runtime = self._build_runtime("never")
        exec_result = self._command_exec_response(exec_runtime, "echo stable")
        exec_event = exec_result["result"]["response"]["tool_events"][-1]

        self.assertEqual(cli_event.name, exec_event["name"])
        self.assertEqual(cli_event.summary, exec_event["summary"])
        self.assertEqual(cli_event.payload["command"], exec_event["payload"]["command"])
        self.assertEqual(exec_result["result"]["exitCode"], 0)

    def test_cli_shell_and_command_exec_match_for_allowed_commands_when_policy_on_request(
        self,
    ) -> None:
        cli_runtime = self._build_runtime("on-request")
        cli_response = cli_runtime.handle_prompt("/shell echo approve")
        cli_tool_event = cli_response.tool_events[-1]
        self.assertEqual(cli_tool_event.name, "shell")
        cli_fields = _shell_protocol_fields(dict(cli_tool_event.payload or {}))
        self.assertEqual(cli_fields.get("policyDecision"), "allowed")
        self.assertEqual(cli_fields.get("policyDecisionReason"), "policy_allowed")

        exec_runtime = self._build_runtime("on-request")
        exec_result = self._command_exec_response(exec_runtime, "echo approve")
        self.assertEqual(exec_result["result"].get("policyDecision"), "allowed")
        self.assertEqual(exec_result["result"].get("policyDecisionReason"), "policy_allowed")

    def test_exec_command_allows_safe_read_under_unless_trusted(self) -> None:
        runtime = self._build_runtime("unless-trusted")

        response = runtime.handle_prompt("/exec_command pwd")
        payload = dict(response.tool_events[-1].payload)

        self.assertEqual(response.tool_events[-1].name, "exec_command")
        self.assertEqual(payload["policy_decision"], "allowed")
        self.assertEqual(payload["policy_decision_reason"], "policy_allowed")
        self.assertEqual(payload["exec_approval_requirement"]["requirement"], "skip")
        self.assertEqual(payload["command_approval"]["reason_code"], "exec.safe_read.allow")

    def test_exec_command_requests_approval_for_workspace_write_by_default(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        response = runtime.handle_prompt("/exec_command touch helloworld")
        payload = dict(response.tool_events[-1].payload)

        self.assertEqual(response.tool_events[-1].name, "shell_approval_requested")
        self.assertEqual(tools.shell_calls, [])
        self.assertEqual(payload["policy_decision"], "requires_approval")
        self.assertEqual(payload["policy_decision_reason"], "approval_required")
        self.assertEqual(payload["exec_approval_requirement"]["requirement"], "needs_approval")
        self.assertEqual(payload["command_approval"]["reason_code"], "exec.write.requires_approval")
        self.assertIn("approval_id", payload)
        self.assertIn("/approve", response.assistant_text)
        self.assertIn("/reject", response.assistant_text)

    def test_exec_command_requests_approval_for_requested_network_permission(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(network_access_enabled=False)

        response = runtime.handle_prompt(
            '/exec_command python -V --additional-permissions-json \'{"network":{"enabled":true}}\''
        )
        payload = dict(response.tool_events[-1].payload)

        self.assertEqual(response.tool_events[-1].name, "shell_approval_requested")
        self.assertEqual(tools.shell_calls, [])
        self.assertEqual(payload["policy_decision"], "requires_approval")
        self.assertEqual(payload["policy_decision_reason"], "approval_required")
        self.assertEqual(payload["reason_code"], "exec.network.requires_approval")
        self.assertEqual(payload["additional_permissions"], {"network": {"enabled": True}})
        self.assertIs(payload["network_access_enabled"], False)

    def test_exec_command_blocks_dangerous_command_without_approval_path(self) -> None:
        runtime = self._build_runtime("never")

        response = runtime.handle_prompt("/exec_command rm -rf build")
        payload = dict(response.tool_events[-1].payload)

        self.assertEqual(response.tool_events[-1].name, "exec_command")
        self.assertEqual(payload["policy_decision"], "blocked")
        self.assertEqual(
            payload["policy_decision_reason"],
            "policy_denied:exec.dangerous.forbidden.no_approval",
        )
        self.assertEqual(payload["exec_approval_requirement"]["requirement"], "forbidden")
        self.assertEqual(payload["command_approval"]["decision"], "forbidden")
        self.assertEqual(payload["reason_code"], "exec.dangerous.forbidden.no_approval")

    def test_shell_policy_contract_matches_exec_and_start_approval_paths(self) -> None:
        exec_runtime = self._build_runtime("on-request")
        exec_result = self._command_exec_response(exec_runtime, "touch approve.txt")
        exec_payload = dict(exec_result["result"]["response"]["tool_events"][-1]["payload"])

        start_runtime = self._build_runtime("on-request")
        start_result = self._command_start_response(start_runtime, "python -i")
        start_payload = dict(start_result["result"]["response"]["tool_events"][-1]["payload"])

        exec_contract = shell_policy_contract_from_payload(exec_payload)
        start_contract = shell_policy_contract_from_payload(start_payload)
        self.assertEqual(exec_contract["decision"], "requires_approval")
        self.assertEqual(exec_contract["reason"], "approval_required")
        self.assertEqual(start_contract["decision"], "requires_approval")
        self.assertEqual(start_contract["reason"], "approval_required")

    def test_approving_shell_ticket_executes_command(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        approval_response = runtime.handle_prompt("/shell touch hello.txt")
        approval_id = approval_response.tool_events[0].payload["approval_id"]
        decision_response = runtime.handle_prompt(f"/approve {approval_id}")

        self.assertEqual(
            [event.name for event in decision_response.tool_events], ["approval_decision", "shell"]
        )
        self.assertEqual(tools.shell_calls, ["touch hello.txt"])
        turn_tools = [
            str((event.get("item") or {}).get("tool") or "")
            for event in decision_response.turn_events
            if isinstance(event, dict) and event.get("type") == "item.completed"
        ]
        self.assertIn("approval_decision", turn_tools)
        self.assertNotIn("gateway_action_execute", turn_tools)

    def test_approving_background_teammate_workspace_write_ticket_enqueues_task(self) -> None:
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=_PolicyTools())
        fake_handle = SimpleNamespace(
            task_id="bg_teammate_live_1",
            status="queued",
            job_id="job_live_1",
            provider="huey",
        )

        with patch(
            "cli.agent_cli.background_tasks.enqueue_background_task", return_value=fake_handle
        ) as patched_submit:
            approval_response = runtime.handle_prompt(
                "/background_teammate 修复 README 标题 --provider glm --model glm_5 --reasoning-effort medium --sandbox-mode workspace-write --allowed-paths src,tests --blocked-paths README.md --timeout-seconds 30"
            )
            approval_id = approval_response.tool_events[0].payload["approval_id"]
            decision_response = runtime.handle_prompt(f"/approve {approval_id}")

        self.assertEqual(
            [event.name for event in decision_response.tool_events],
            ["approval_decision", "background_teammate_submitted"],
        )
        self.assertIn("task_id=bg_teammate_live_1", decision_response.assistant_text)
        self.assertIn("status=queued", decision_response.assistant_text)
        self.assertIn("sandbox_mode=workspace-write", decision_response.assistant_text)
        self.assertIn("staged_run=true", decision_response.assistant_text)
        self.assertIn("final_apply_required=true", decision_response.assistant_text)
        self.assertIn("timeout_seconds=30.0", decision_response.assistant_text)
        patched_submit.assert_called_once()
        self.assertEqual(patched_submit.call_args.kwargs["task_type"], "teammate")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["task"], "修复 README 标题")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["provider"], "glm")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["model"], "glm_5")
        self.assertEqual(
            patched_submit.call_args.kwargs["payload"]["sandbox_mode"], "workspace-write"
        )
        self.assertEqual(
            patched_submit.call_args.kwargs["payload"]["allowed_paths"], ["src", "tests"]
        )
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["blocked_paths"], ["README.md"])
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["timeout_seconds"], 30.0)

    def test_shell_start_requests_approval_by_default(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        response = runtime.handle_prompt("/shell start python -i")

        self.assertEqual(
            [event.name for event in response.tool_events], ["shell_approval_requested"]
        )
        self.assertEqual(response.tool_events[0].payload["exec_mode"], "session_start")
        self.assertEqual(tools.shell_start_calls, [])

    def test_shell_start_denies_unscoped_pytest_under_background_teammate_policy(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        with background_teammate_policy():
            response = runtime.handle_prompt("/shell start pytest -q")

        self.assertEqual([event.name for event in response.tool_events], ["shell_start"])
        self.assertEqual(tools.shell_start_calls, [])
        self.assertEqual(response.tool_events[-1].payload["status"], "policy_denied")
        self.assertIn("explicit test files or node ids", response.assistant_text)

    def test_approving_shell_start_ticket_starts_interactive_session(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        approval_response = runtime.handle_prompt("/shell start python -i")
        approval_id = approval_response.tool_events[0].payload["approval_id"]
        decision_response = runtime.handle_prompt(f"/approve {approval_id}")

        self.assertEqual(
            [event.name for event in decision_response.tool_events],
            ["approval_decision", "shell_start"],
        )
        self.assertEqual(tools.shell_start_calls, ["python -i"])
        self.assertEqual(decision_response.tool_events[-1].payload["session_id"], "session_1")

    def test_approving_exec_command_ticket_runs_one_shot_shell(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)

        approval_response = runtime.handle_prompt("/exec_command 'python -V' --yield-time-ms 250")
        approval_event = approval_response.tool_events[0]
        approval_id = approval_event.payload["approval_id"]
        decision_response = runtime.handle_prompt(f"/approve {approval_id}")

        self.assertEqual(approval_event.payload["exec_mode"], "exec_once")
        self.assertEqual(
            [event.name for event in decision_response.tool_events], ["approval_decision", "shell"]
        )
        self.assertEqual(tools.shell_calls, ["python -V"])
        self.assertEqual(tools.shell_start_calls, [])
        self.assertEqual(decision_response.tool_events[-1].payload["stdout"], "ok\n")

    def test_cli_shell_start_and_command_start_skip_approval_when_policy_never(self) -> None:
        cli_runtime = self._build_runtime("never")
        cli_response = cli_runtime.handle_prompt("/shell start python -i")
        self.assertEqual(cli_response.tool_events[-1].name, "shell_start")

        start_runtime = self._build_runtime("never")
        start_result = self._command_start_response(start_runtime, "python -i")
        self.assertTrue(start_result["result"].get("accepted"))
        self.assertFalse(start_result["result"].get("approvalRequired"))
        self.assertEqual(start_result["result"].get("policyDecision"), "allowed")
        self.assertEqual(start_result["result"].get("policyDecisionReason"), "policy_allowed")

    def test_cli_shell_start_and_command_start_request_approval_when_policy_on_request(
        self,
    ) -> None:
        cli_runtime = self._build_runtime("on-request")
        cli_response = cli_runtime.handle_prompt("/shell start python -i")
        cli_tool_event = cli_response.tool_events[-1]
        self.assertEqual(cli_tool_event.name, "shell_approval_requested")

        start_runtime = self._build_runtime("on-request")
        start_result = self._command_start_response(start_runtime, "python -i")
        self.assertFalse(start_result["result"].get("accepted"))
        self.assertTrue(start_result["result"].get("approvalRequired"))
        tool_event = start_result["result"]["response"]["tool_events"][-1]
        self.assertEqual(tool_event["name"], "shell_approval_requested")
        policy_fields = _shell_protocol_fields(dict(tool_event.get("payload") or {}))
        self.assertEqual(policy_fields.get("policyDecision"), "requires_approval")
        self.assertEqual(policy_fields.get("policyDecisionReason"), "approval_required")
        self.assertEqual(
            set(dict(policy_fields.get("policySnapshot") or {}).keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )

    def test_shell_policy_contract_matches_exec_and_start_blocked_paths(self) -> None:
        with background_teammate_policy():
            exec_runtime = self._build_runtime("never")
            exec_result = self._command_exec_response(exec_runtime, "pytest -q")
            exec_payload = dict(exec_result["result"]["response"]["tool_events"][-1]["payload"])

            start_runtime = self._build_runtime("never")
            start_result = self._command_start_response(start_runtime, "pytest -q")
            start_payload = dict(start_result["result"]["response"]["tool_events"][-1]["payload"])

        exec_contract = shell_policy_contract_from_payload(exec_payload)
        start_contract = shell_policy_contract_from_payload(start_payload)
        self.assertEqual(exec_contract["decision"], "blocked")
        self.assertTrue(str(exec_contract["reason"]).startswith("policy_denied"))
        self.assertEqual(start_contract["decision"], "blocked")
        self.assertTrue(str(start_contract["reason"]).startswith("policy_denied"))
        self.assertEqual(exec_result["result"].get("policyDecision"), "blocked")
        start_policy_fields = _shell_protocol_fields(start_payload)
        self.assertEqual(start_policy_fields.get("policyDecision"), "blocked")
        self.assertTrue(
            str(start_policy_fields.get("policyDecisionReason") or "").startswith("policy_denied")
        )
        self.assertEqual(
            set(dict(start_policy_fields.get("policySnapshot") or {}).keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )

    def test_command_start_policy_readout_guard_three_state_reason_semantics(self) -> None:
        allowed_start = self._command_start_response(self._build_runtime("never"), "python -i")
        allowed_decision, allowed_reason, allowed_snapshot = self._command_start_policy_readout(
            allowed_start
        )
        self.assertEqual(allowed_decision, "allowed")
        self.assertEqual(allowed_reason, "policy_allowed")
        self._assert_policy_snapshot_schema(allowed_snapshot)

        approval_start = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        approval_decision, approval_reason, approval_snapshot = self._command_start_policy_readout(
            approval_start
        )
        self.assertEqual(approval_decision, "requires_approval")
        self.assertEqual(approval_reason, "approval_required")
        self._assert_policy_snapshot_schema(approval_snapshot)

        with background_teammate_policy():
            blocked_start = self._command_start_response(self._build_runtime("never"), "pytest -q")
        blocked_decision, blocked_reason, blocked_snapshot = self._command_start_policy_readout(
            blocked_start
        )
        self.assertEqual(blocked_decision, "blocked")
        self.assertEqual(blocked_reason, "policy_denied:test_scope_required")
        self._assert_policy_snapshot_schema(blocked_snapshot)

    def test_command_start_policy_readout_fallback_guard_when_top_level_missing(self) -> None:
        approval_start = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        self.assertIsNone(approval_start["result"].get("policyDecision"))
        self.assertIsNone(approval_start["result"].get("policyDecisionReason"))
        approval_decision, approval_reason, approval_snapshot = self._command_start_policy_readout(
            approval_start
        )
        self.assertEqual(approval_decision, "requires_approval")
        self.assertEqual(approval_reason, "approval_required")
        self._assert_policy_snapshot_schema(approval_snapshot)

        with background_teammate_policy():
            blocked_start = self._command_start_response(self._build_runtime("never"), "pytest -q")
        self.assertIsNone(blocked_start["result"].get("policyDecision"))
        self.assertIsNone(blocked_start["result"].get("policyDecisionReason"))
        blocked_decision, blocked_reason, blocked_snapshot = self._command_start_policy_readout(
            blocked_start
        )
        self.assertEqual(blocked_decision, "blocked")
        self.assertEqual(blocked_reason, "policy_denied:test_scope_required")
        self._assert_policy_snapshot_schema(blocked_snapshot)

    def test_command_start_fallback_reason_matches_direct_readout_for_same_response(self) -> None:
        start_response = self._command_start_response(self._build_runtime("never"), "python -i")
        direct_result = dict(start_response.get("result") or {})
        payload = dict(direct_result.get("raw") or {})
        projected = _shell_protocol_fields(payload)

        self.assertEqual(
            str(direct_result.get("policyDecision") or ""),
            str(projected.get("policyDecision") or ""),
        )
        self.assertEqual(
            str(direct_result.get("policyDecisionReason") or ""),
            str(projected.get("policyDecisionReason") or ""),
        )

        forced_fallback = json.loads(json.dumps(start_response))
        forced_fallback_result = dict(forced_fallback.get("result") or {})
        forced_fallback_result.pop("policyDecision", None)
        forced_fallback_result.pop("policyDecisionReason", None)
        forced_fallback_result.pop("policySnapshot", None)
        forced_fallback["result"] = forced_fallback_result
        fallback_decision, fallback_reason, fallback_snapshot = self._command_start_policy_readout(
            forced_fallback
        )

        self.assertEqual(fallback_decision, str(projected.get("policyDecision") or ""))
        self.assertEqual(fallback_reason, str(projected.get("policyDecisionReason") or ""))
        self._assert_policy_snapshot_schema(fallback_snapshot)

    def test_policy_decision_reason_sync_between_top_level_and_payload_projection(self) -> None:
        exec_allowed = self._command_exec_response(self._build_runtime("never"), "echo sync")
        exec_allowed_result = dict(exec_allowed.get("result") or {})
        exec_allowed_projection = _shell_protocol_fields(dict(exec_allowed_result.get("raw") or {}))
        self.assertEqual(
            str(exec_allowed_result.get("policyDecisionReason") or ""),
            str(exec_allowed_projection.get("policyDecisionReason") or ""),
        )

        exec_approval = self._command_exec_response(self._build_runtime("on-request"), "echo sync")
        exec_approval_result = dict(exec_approval.get("result") or {})
        exec_approval_payload = (
            dict(exec_approval_result.get("response") or {}).get("tool_events") or []
        )
        exec_approval_projection = _shell_protocol_fields(
            dict((exec_approval_payload[-1].get("payload") if exec_approval_payload else {}) or {})
        )
        self.assertEqual(
            str(exec_approval_result.get("policyDecisionReason") or ""),
            str(exec_approval_projection.get("policyDecisionReason") or ""),
        )

        with background_teammate_policy():
            exec_blocked = self._command_exec_response(self._build_runtime("never"), "pytest -q")
        exec_blocked_result = dict(exec_blocked.get("result") or {})
        exec_blocked_projection = _shell_protocol_fields(dict(exec_blocked_result.get("raw") or {}))
        self.assertEqual(
            str(exec_blocked_result.get("policyDecisionReason") or ""),
            str(exec_blocked_projection.get("policyDecisionReason") or ""),
        )

        start_allowed = self._command_start_response(self._build_runtime("never"), "python -i")
        start_allowed_result = dict(start_allowed.get("result") or {})
        start_allowed_projection = _shell_protocol_fields(
            dict(start_allowed_result.get("raw") or {})
        )
        self.assertEqual(
            str(start_allowed_result.get("policyDecisionReason") or ""),
            str(start_allowed_projection.get("policyDecisionReason") or ""),
        )

    def test_policy_decision_sync_between_top_level_and_payload_projection(self) -> None:
        exec_allowed = self._command_exec_response(self._build_runtime("never"), "echo sync")
        exec_allowed_result = dict(exec_allowed.get("result") or {})
        exec_allowed_projection = _shell_protocol_fields(dict(exec_allowed_result.get("raw") or {}))
        self.assertEqual(
            str(exec_allowed_result.get("policyDecision") or ""),
            str(exec_allowed_projection.get("policyDecision") or ""),
        )

        exec_approval = self._command_exec_response(self._build_runtime("on-request"), "echo sync")
        exec_approval_result = dict(exec_approval.get("result") or {})
        exec_approval_payload = (
            dict(exec_approval_result.get("response") or {}).get("tool_events") or []
        )
        exec_approval_projection = _shell_protocol_fields(
            dict((exec_approval_payload[-1].get("payload") if exec_approval_payload else {}) or {})
        )
        self.assertEqual(
            str(exec_approval_result.get("policyDecision") or ""),
            str(exec_approval_projection.get("policyDecision") or ""),
        )

        with background_teammate_policy():
            exec_blocked = self._command_exec_response(self._build_runtime("never"), "pytest -q")
        exec_blocked_result = dict(exec_blocked.get("result") or {})
        exec_blocked_projection = _shell_protocol_fields(dict(exec_blocked_result.get("raw") or {}))
        self.assertEqual(
            str(exec_blocked_result.get("policyDecision") or ""),
            str(exec_blocked_projection.get("policyDecision") or ""),
        )

        start_allowed = self._command_start_response(self._build_runtime("never"), "python -i")
        start_allowed_result = dict(start_allowed.get("result") or {})
        start_allowed_projection = _shell_protocol_fields(
            dict(start_allowed_result.get("raw") or {})
        )
        self.assertEqual(
            str(start_allowed_result.get("policyDecision") or ""),
            str(start_allowed_projection.get("policyDecision") or ""),
        )

    def test_policy_snapshot_sync_between_top_level_and_payload_projection(self) -> None:
        exec_allowed = self._command_exec_response(self._build_runtime("never"), "echo snapshot")
        exec_allowed_result = dict(exec_allowed.get("result") or {})
        exec_allowed_projection = _shell_protocol_fields(dict(exec_allowed_result.get("raw") or {}))
        self.assertEqual(
            dict(exec_allowed_result.get("policySnapshot") or {}),
            dict(exec_allowed_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_snapshot_schema(dict(exec_allowed_result.get("policySnapshot") or {}))

        exec_approval = self._command_exec_response(
            self._build_runtime("on-request"), "echo snapshot"
        )
        exec_approval_result = dict(exec_approval.get("result") or {})
        exec_approval_events = list(
            dict(exec_approval_result.get("response") or {}).get("tool_events") or []
        )
        exec_approval_projection = _shell_protocol_fields(
            dict((exec_approval_events[-1].get("payload") if exec_approval_events else {}) or {})
        )
        self.assertEqual(
            dict(exec_approval_result.get("policySnapshot") or {}),
            dict(exec_approval_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_snapshot_schema(dict(exec_approval_result.get("policySnapshot") or {}))

        start_allowed = self._command_start_response(self._build_runtime("never"), "python -i")
        start_allowed_result = dict(start_allowed.get("result") or {})
        start_allowed_projection = _shell_protocol_fields(
            dict(start_allowed_result.get("raw") or {})
        )
        self.assertEqual(
            dict(start_allowed_result.get("policySnapshot") or {}),
            dict(start_allowed_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_snapshot_schema(dict(start_allowed_result.get("policySnapshot") or {}))

        with background_teammate_policy():
            exec_blocked = self._command_exec_response(self._build_runtime("never"), "pytest -q")
            start_blocked = self._command_start_response(self._build_runtime("never"), "pytest -q")
        exec_blocked_result = dict(exec_blocked.get("result") or {})
        exec_blocked_projection = _shell_protocol_fields(dict(exec_blocked_result.get("raw") or {}))
        self.assertEqual(
            dict(exec_blocked_result.get("policySnapshot") or {}),
            dict(exec_blocked_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_snapshot_schema(dict(exec_blocked_result.get("policySnapshot") or {}))

        start_approval = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        start_approval_result = dict(start_approval.get("result") or {})
        self.assertIsNone(start_approval_result.get("policySnapshot"))
        start_approval_events = list(
            dict(start_approval_result.get("response") or {}).get("tool_events") or []
        )
        start_approval_projection = _shell_protocol_fields(
            dict((start_approval_events[-1].get("payload") if start_approval_events else {}) or {})
        )
        _, _, start_approval_snapshot = self._command_start_policy_readout(start_approval)
        self.assertEqual(
            start_approval_snapshot, dict(start_approval_projection.get("policySnapshot") or {})
        )
        self._assert_policy_snapshot_schema(start_approval_snapshot)

        start_blocked_result = dict(start_blocked.get("result") or {})
        self.assertIsNone(start_blocked_result.get("policySnapshot"))
        start_blocked_events = list(
            dict(start_blocked_result.get("response") or {}).get("tool_events") or []
        )
        start_blocked_projection = _shell_protocol_fields(
            dict((start_blocked_events[-1].get("payload") if start_blocked_events else {}) or {})
        )
        _, _, start_blocked_snapshot = self._command_start_policy_readout(start_blocked)
        self.assertEqual(
            start_blocked_snapshot, dict(start_blocked_projection.get("policySnapshot") or {})
        )
        self._assert_policy_snapshot_schema(start_blocked_snapshot)

    def test_policy_snapshot_value_semantics_guard_normalization_and_bool_coercion(self) -> None:
        normalized_fields = _shell_protocol_fields(
            {
                "status": "pending",
                "approval_id": "approval_snapshot_semantics",
                "approval_policy": " NEVER ",
                "sandbox_mode": " Read-Only ",
                "network_access_enabled": "enabled",
                "request_permission_enabled": "0",
            }
        )
        normalized_snapshot = dict(normalized_fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(normalized_snapshot)
        self.assertEqual(
            normalized_snapshot,
            {
                "approvalPolicy": "never",
                "sandboxMode": "read-only",
                "networkAccessEnabled": True,
                "requestPermissionEnabled": False,
            },
        )

        nullable_fields = _shell_protocol_fields(
            {
                "status": "ok",
                "approval_policy": "",
                "sandbox_mode": "",
                "network_access_enabled": "not-a-bool",
                "request_permission_enabled": "unknown",
            }
        )
        nullable_snapshot = dict(nullable_fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(nullable_snapshot)
        self.assertEqual(
            nullable_snapshot,
            {
                "approvalPolicy": None,
                "sandboxMode": None,
                "networkAccessEnabled": None,
                "requestPermissionEnabled": None,
            },
        )

    def test_policy_snapshot_normalization_guard_collapses_synonym_inputs(self) -> None:
        cohorts = [
            (
                {
                    "approvalPolicy": "never",
                    "sandboxMode": "read-only",
                    "networkAccessEnabled": True,
                    "requestPermissionEnabled": False,
                },
                [
                    {
                        "approval_policy": "NEVER",
                        "sandbox_mode": "READ-ONLY",
                        "network_access_enabled": "enabled",
                        "request_permission_enabled": "0",
                    },
                    {
                        "approval_policy": " never ",
                        "sandbox_mode": " read-only ",
                        "network_access_enabled": "true",
                        "request_permission_enabled": "off",
                    },
                    {
                        "approval_policy": "NeVeR",
                        "sandbox_mode": "Read-Only",
                        "network_access_enabled": "1",
                        "request_permission_enabled": "false",
                    },
                ],
            ),
            (
                {
                    "approvalPolicy": "on-request",
                    "sandboxMode": "workspace-write",
                    "networkAccessEnabled": False,
                    "requestPermissionEnabled": True,
                },
                [
                    {
                        "approval_policy": " ON-REQUEST ",
                        "sandbox_mode": " WORKSPACE-WRITE ",
                        "network_access_enabled": "disabled",
                        "request_permission_enabled": "1",
                    },
                    {
                        "approval_policy": "on-request",
                        "sandbox_mode": "workspace-write",
                        "network_access_enabled": "no",
                        "request_permission_enabled": "on",
                    },
                    {
                        "approval_policy": "On-Request",
                        "sandbox_mode": "Workspace-Write",
                        "network_access_enabled": "0",
                        "request_permission_enabled": "yes",
                    },
                ],
            ),
        ]
        for expected_snapshot, payload_variants in cohorts:
            for variant in payload_variants:
                fields = _shell_protocol_fields({"status": "ok", **variant})
                snapshot = dict(fields.get("policySnapshot") or {})
                self._assert_policy_snapshot_schema(snapshot)
                self.assertEqual(snapshot, expected_snapshot)

    def test_policy_snapshot_invalid_input_guard_uses_safe_fallbacks(self) -> None:
        invalid_snapshot_expected = {
            "approvalPolicy": "on-request",
            "sandboxMode": "workspace-write",
            "networkAccessEnabled": None,
            "requestPermissionEnabled": None,
        }
        invalid_payload = {
            "approval_policy": " definitely-not-a-policy ",
            "sandbox_mode": " unsafe-sandbox-mode ",
            "network_access_enabled": "MAYBE",
            "request_permission_enabled": "sometimes",
        }

        approval_fields = _shell_protocol_fields(
            {
                "status": "pending",
                "approval_id": "approval_invalid_input_guard",
                **invalid_payload,
            }
        )
        approval_snapshot = dict(approval_fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(approval_snapshot)
        self.assertEqual(approval_snapshot, invalid_snapshot_expected)
        self.assertEqual(str(approval_fields.get("policyDecision") or ""), "requires_approval")
        self.assertEqual(
            str(approval_fields.get("policyDecisionReason") or ""), "approval_required"
        )

        blocked_fields = _shell_protocol_fields(
            {
                "status": "policy_denied",
                "error_code": "test_scope_required",
                **invalid_payload,
            }
        )
        blocked_snapshot = dict(blocked_fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(blocked_snapshot)
        self.assertEqual(blocked_snapshot, invalid_snapshot_expected)
        self.assertEqual(str(blocked_fields.get("policyDecision") or ""), "blocked")
        self.assertEqual(
            str(blocked_fields.get("policyDecisionReason") or ""),
            "policy_denied:test_scope_required",
        )

    def test_policy_invalid_input_default_guard_preserves_default_axes_without_reason_pollution(
        self,
    ) -> None:
        invalid_token_axes = {
            "approval_policy": "%%%invalid-policy%%%",
            "sandbox_mode": "%%%invalid-sandbox%%%",
            "network_access_enabled": "%%%invalid-bool%%%",
            "request_permission_enabled": "%%%invalid-bool%%%",
        }
        default_snapshot = {
            "approvalPolicy": "on-request",
            "sandboxMode": "workspace-write",
            "networkAccessEnabled": None,
            "requestPermissionEnabled": None,
        }
        cases = [
            (
                {"status": "ok"},
                {"decision": "allowed", "reason": "policy_allowed"},
            ),
            (
                {"status": "pending", "approval_id": "approval_invalid_default"},
                {"decision": "requires_approval", "reason": "approval_required"},
            ),
            (
                {"status": "policy_denied", "error_code": "test_scope_required"},
                {"decision": "blocked", "reason": "policy_denied:test_scope_required"},
            ),
            (
                {
                    "policy_decision": "blocked",
                    "policy_decision_reason": "policy_denied:explicit_override",
                },
                {"decision": "blocked", "reason": "policy_denied:explicit_override"},
            ),
        ]
        for raw_payload, expected in cases:
            fields = _shell_protocol_fields({**invalid_token_axes, **raw_payload})
            snapshot = dict(fields.get("policySnapshot") or {})
            self._assert_policy_snapshot_schema(snapshot)
            self.assertEqual(snapshot, default_snapshot)
            self.assertEqual(str(fields.get("policyDecision") or ""), str(expected["decision"]))
            self.assertEqual(str(fields.get("policyDecisionReason") or ""), str(expected["reason"]))

    def test_explicit_policy_field_precedence_guard_over_inferred_inputs(self) -> None:
        invalid_token_axes = {
            "approval_policy": "%%%invalid-policy%%%",
            "sandbox_mode": "%%%invalid-sandbox%%%",
            "network_access_enabled": "%%%invalid-bool%%%",
            "request_permission_enabled": "%%%invalid-bool%%%",
        }
        default_snapshot = {
            "approvalPolicy": "on-request",
            "sandboxMode": "workspace-write",
            "networkAccessEnabled": None,
            "requestPermissionEnabled": None,
        }
        cases = [
            (
                {
                    "status": "policy_denied",
                    "error_code": "test_scope_required",
                    "approval_id": "approval_should_not_win",
                    "policy_decision": "allowed",
                },
                {"decision": "allowed", "reason": "policy_allowed"},
            ),
            (
                {
                    "status": "ok",
                    "policy_decision": "requires_approval",
                },
                {"decision": "requires_approval", "reason": "approval_required"},
            ),
            (
                {
                    "status": "ok",
                    "policy_decision": "blocked",
                    "policy_decision_reason": "policy_denied:explicit_precedence",
                },
                {"decision": "blocked", "reason": "policy_denied:explicit_precedence"},
            ),
        ]
        for raw_payload, expected in cases:
            fields = _shell_protocol_fields({**invalid_token_axes, **raw_payload})
            snapshot = dict(fields.get("policySnapshot") or {})
            self._assert_policy_snapshot_schema(snapshot)
            self.assertEqual(snapshot, default_snapshot)
            self.assertEqual(str(fields.get("policyDecision") or ""), str(expected["decision"]))
            self.assertEqual(str(fields.get("policyDecisionReason") or ""), str(expected["reason"]))

    def test_explicit_reason_pair_precedence_guard_over_inferred_reason_sources(self) -> None:
        invalid_token_axes = {
            "approval_policy": "%%%invalid-policy%%%",
            "sandbox_mode": "%%%invalid-sandbox%%%",
            "network_access_enabled": "%%%invalid-bool%%%",
            "request_permission_enabled": "%%%invalid-bool%%%",
        }
        default_snapshot = {
            "approvalPolicy": "on-request",
            "sandboxMode": "workspace-write",
            "networkAccessEnabled": None,
            "requestPermissionEnabled": None,
        }
        cases = [
            (
                {
                    "status": "policy_denied",
                    "error_code": "test_scope_required",
                    "policy_decision": "blocked",
                    "policy_decision_reason": "policy_denied:explicit_pair_wins",
                },
                "policy_denied:explicit_pair_wins",
            ),
            (
                {
                    "status": "pending",
                    "approval_id": "approval_should_not_win",
                    "policy_decision": "blocked",
                    "policy_decision_reason": "policy_denied:explicit_pair_wins_again",
                },
                "policy_denied:explicit_pair_wins_again",
            ),
        ]
        for raw_payload, expected_reason in cases:
            fields = _shell_protocol_fields({**invalid_token_axes, **raw_payload})
            snapshot = dict(fields.get("policySnapshot") or {})
            self._assert_policy_snapshot_schema(snapshot)
            self.assertEqual(snapshot, default_snapshot)
            self.assertEqual(str(fields.get("policyDecision") or ""), "blocked")
            self.assertEqual(str(fields.get("policyDecisionReason") or ""), expected_reason)

    def test_explicit_reason_without_explicit_decision_does_not_override_inferred_reason(
        self,
    ) -> None:
        payload = {
            "status": "policy_denied",
            "error_code": "test_scope_required",
            "approval_id": "approval_should_not_win",
            "policy_decision_reason": "policy_denied:explicit_reason_only",
            "approval_policy": "invalid-policy-token",
            "sandbox_mode": "invalid-sandbox-token",
            "network_access_enabled": "invalid-bool-token",
            "request_permission_enabled": "invalid-bool-token",
        }

        contract = shell_policy_contract_from_payload(payload)
        self.assertEqual(str(contract.get("decision") or ""), "blocked")
        self.assertEqual(str(contract.get("reason") or ""), "policy_denied:test_scope_required")

        fields = _shell_protocol_fields(payload)
        snapshot = dict(fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(snapshot)
        self.assertEqual(str(fields.get("policyDecision") or ""), "blocked")
        self.assertEqual(
            str(fields.get("policyDecisionReason") or ""), "policy_denied:test_scope_required"
        )

    def test_explicit_reason_pair_precedence_guard_in_contract_and_projection(self) -> None:
        payload = {
            "status": "policy_denied",
            "error_code": "test_scope_required",
            "approval_id": "approval_should_not_override_explicit_pair",
            "policy_decision": "blocked",
            "policy_decision_reason": "policy_denied:explicit_contract_pair",
            "approval_policy": "invalid-policy-token",
            "sandbox_mode": "invalid-sandbox-token",
            "network_access_enabled": "invalid-bool-token",
            "request_permission_enabled": "invalid-bool-token",
        }

        contract = shell_policy_contract_from_payload(payload)
        self.assertEqual(str(contract.get("decision") or ""), "blocked")
        self.assertEqual(str(contract.get("reason") or ""), "policy_denied:explicit_contract_pair")

        fields = _shell_protocol_fields(payload)
        snapshot = dict(fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(snapshot)
        self.assertEqual(str(fields.get("policyDecision") or ""), "blocked")
        self.assertEqual(
            str(fields.get("policyDecisionReason") or ""), "policy_denied:explicit_contract_pair"
        )

    def test_explicit_reason_pair_precedence_guard_with_normalized_tokens(self) -> None:
        payload = {
            "status": "pending",
            "approval_id": "approval_should_not_override_explicit_pair",
            "error_code": "test_scope_required",
            "policy_decision": "  BLOCKED  ",
            "policy_decision_reason": "  policy_denied:explicit_pair_normalized  ",
            "approval_policy": "invalid-policy-token",
            "sandbox_mode": "invalid-sandbox-token",
            "network_access_enabled": "invalid-bool-token",
            "request_permission_enabled": "invalid-bool-token",
        }

        contract = shell_policy_contract_from_payload(payload)
        self.assertEqual(str(contract.get("decision") or ""), "blocked")
        self.assertEqual(
            str(contract.get("reason") or ""), "policy_denied:explicit_pair_normalized"
        )

        fields = _shell_protocol_fields(payload)
        snapshot = dict(fields.get("policySnapshot") or {})
        self._assert_policy_snapshot_schema(snapshot)
        self.assertEqual(str(fields.get("policyDecision") or ""), "blocked")
        self.assertEqual(
            str(fields.get("policyDecisionReason") or ""), "policy_denied:explicit_pair_normalized"
        )

    def test_policy_decision_reason_pair_guard_on_exec_and_start_surfaces(self) -> None:
        exec_allowed = self._command_exec_response(self._build_runtime("never"), "echo pair")
        exec_allowed_result = dict(exec_allowed.get("result") or {})
        exec_allowed_projection = _shell_protocol_fields(dict(exec_allowed_result.get("raw") or {}))
        self._assert_policy_decision_reason_pair(
            str(exec_allowed_result.get("policyDecision") or ""),
            str(exec_allowed_result.get("policyDecisionReason") or ""),
        )
        self._assert_policy_decision_reason_pair(
            str(exec_allowed_projection.get("policyDecision") or ""),
            str(exec_allowed_projection.get("policyDecisionReason") or ""),
        )

        exec_approval = self._command_exec_response(self._build_runtime("on-request"), "echo pair")
        exec_approval_result = dict(exec_approval.get("result") or {})
        exec_approval_events = list(
            dict(exec_approval_result.get("response") or {}).get("tool_events") or []
        )
        exec_approval_projection = _shell_protocol_fields(
            dict((exec_approval_events[-1].get("payload") if exec_approval_events else {}) or {})
        )
        self._assert_policy_decision_reason_pair(
            str(exec_approval_result.get("policyDecision") or ""),
            str(exec_approval_result.get("policyDecisionReason") or ""),
        )
        self._assert_policy_decision_reason_pair(
            str(exec_approval_projection.get("policyDecision") or ""),
            str(exec_approval_projection.get("policyDecisionReason") or ""),
        )

        with background_teammate_policy():
            exec_blocked = self._command_exec_response(self._build_runtime("never"), "pytest -q")
            start_blocked = self._command_start_response(self._build_runtime("never"), "pytest -q")
        exec_blocked_result = dict(exec_blocked.get("result") or {})
        exec_blocked_projection = _shell_protocol_fields(dict(exec_blocked_result.get("raw") or {}))
        self._assert_policy_decision_reason_pair(
            str(exec_blocked_result.get("policyDecision") or ""),
            str(exec_blocked_result.get("policyDecisionReason") or ""),
        )
        self._assert_policy_decision_reason_pair(
            str(exec_blocked_projection.get("policyDecision") or ""),
            str(exec_blocked_projection.get("policyDecisionReason") or ""),
        )

        start_allowed = self._command_start_response(self._build_runtime("never"), "python -i")
        start_allowed_result = dict(start_allowed.get("result") or {})
        start_allowed_projection = _shell_protocol_fields(
            dict(start_allowed_result.get("raw") or {})
        )
        self._assert_policy_decision_reason_pair(
            str(start_allowed_result.get("policyDecision") or ""),
            str(start_allowed_result.get("policyDecisionReason") or ""),
        )
        self._assert_policy_decision_reason_pair(
            str(start_allowed_projection.get("policyDecision") or ""),
            str(start_allowed_projection.get("policyDecisionReason") or ""),
        )

        start_approval = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        start_approval_decision, start_approval_reason, _ = self._command_start_policy_readout(
            start_approval
        )
        self._assert_policy_decision_reason_pair(start_approval_decision, start_approval_reason)
        start_blocked_decision, start_blocked_reason, _ = self._command_start_policy_readout(
            start_blocked
        )
        self._assert_policy_decision_reason_pair(start_blocked_decision, start_blocked_reason)

    def test_policy_guard_combined_consistency_for_exec_and_start_matrix(self) -> None:
        exec_allowed = self._command_exec_response(self._build_runtime("never"), "echo combined")
        exec_allowed_result = dict(exec_allowed.get("result") or {})
        exec_allowed_projection = _shell_protocol_fields(dict(exec_allowed_result.get("raw") or {}))
        self.assertEqual(
            str(exec_allowed_result.get("policyDecision") or ""),
            str(exec_allowed_projection.get("policyDecision") or ""),
        )
        self.assertEqual(
            str(exec_allowed_result.get("policyDecisionReason") or ""),
            str(exec_allowed_projection.get("policyDecisionReason") or ""),
        )
        self.assertEqual(
            dict(exec_allowed_result.get("policySnapshot") or {}),
            dict(exec_allowed_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(
            str(exec_allowed_result.get("policyDecision") or ""),
            str(exec_allowed_result.get("policyDecisionReason") or ""),
            dict(exec_allowed_result.get("policySnapshot") or {}),
        )

        exec_approval = self._command_exec_response(
            self._build_runtime("on-request"), "echo combined"
        )
        exec_approval_result = dict(exec_approval.get("result") or {})
        exec_approval_events = list(
            dict(exec_approval_result.get("response") or {}).get("tool_events") or []
        )
        exec_approval_projection = _shell_protocol_fields(
            dict((exec_approval_events[-1].get("payload") if exec_approval_events else {}) or {})
        )
        self.assertEqual(
            str(exec_approval_result.get("policyDecision") or ""),
            str(exec_approval_projection.get("policyDecision") or ""),
        )
        self.assertEqual(
            str(exec_approval_result.get("policyDecisionReason") or ""),
            str(exec_approval_projection.get("policyDecisionReason") or ""),
        )
        self.assertEqual(
            dict(exec_approval_result.get("policySnapshot") or {}),
            dict(exec_approval_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(
            str(exec_approval_result.get("policyDecision") or ""),
            str(exec_approval_result.get("policyDecisionReason") or ""),
            dict(exec_approval_result.get("policySnapshot") or {}),
        )

        start_allowed = self._command_start_response(self._build_runtime("never"), "python -i")
        start_allowed_result = dict(start_allowed.get("result") or {})
        start_allowed_projection = _shell_protocol_fields(
            dict(start_allowed_result.get("raw") or {})
        )
        self.assertEqual(
            str(start_allowed_result.get("policyDecision") or ""),
            str(start_allowed_projection.get("policyDecision") or ""),
        )
        self.assertEqual(
            str(start_allowed_result.get("policyDecisionReason") or ""),
            str(start_allowed_projection.get("policyDecisionReason") or ""),
        )
        self.assertEqual(
            dict(start_allowed_result.get("policySnapshot") or {}),
            dict(start_allowed_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(
            str(start_allowed_result.get("policyDecision") or ""),
            str(start_allowed_result.get("policyDecisionReason") or ""),
            dict(start_allowed_result.get("policySnapshot") or {}),
        )

        with background_teammate_policy():
            exec_blocked = self._command_exec_response(self._build_runtime("never"), "pytest -q")
            start_blocked = self._command_start_response(self._build_runtime("never"), "pytest -q")
        exec_blocked_result = dict(exec_blocked.get("result") or {})
        exec_blocked_projection = _shell_protocol_fields(dict(exec_blocked_result.get("raw") or {}))
        self.assertEqual(
            str(exec_blocked_result.get("policyDecision") or ""),
            str(exec_blocked_projection.get("policyDecision") or ""),
        )
        self.assertEqual(
            str(exec_blocked_result.get("policyDecisionReason") or ""),
            str(exec_blocked_projection.get("policyDecisionReason") or ""),
        )
        self.assertEqual(
            dict(exec_blocked_result.get("policySnapshot") or {}),
            dict(exec_blocked_projection.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(
            str(exec_blocked_result.get("policyDecision") or ""),
            str(exec_blocked_result.get("policyDecisionReason") or ""),
            dict(exec_blocked_result.get("policySnapshot") or {}),
        )

        start_approval = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        start_approval_result = dict(start_approval.get("result") or {})
        self.assertIsNone(start_approval_result.get("policyDecision"))
        self.assertIsNone(start_approval_result.get("policyDecisionReason"))
        start_approval_events = list(
            dict(start_approval_result.get("response") or {}).get("tool_events") or []
        )
        start_approval_projection = _shell_protocol_fields(
            dict((start_approval_events[-1].get("payload") if start_approval_events else {}) or {})
        )
        start_approval_decision, start_approval_reason, start_approval_snapshot = (
            self._command_start_policy_readout(start_approval)
        )
        self.assertEqual(
            start_approval_decision, str(start_approval_projection.get("policyDecision") or "")
        )
        self.assertEqual(
            start_approval_reason, str(start_approval_projection.get("policyDecisionReason") or "")
        )
        self.assertEqual(
            start_approval_snapshot, dict(start_approval_projection.get("policySnapshot") or {})
        )
        self._assert_policy_triplet(
            start_approval_decision, start_approval_reason, start_approval_snapshot
        )

        start_blocked_result = dict(start_blocked.get("result") or {})
        self.assertIsNone(start_blocked_result.get("policyDecision"))
        self.assertIsNone(start_blocked_result.get("policyDecisionReason"))
        start_blocked_events = list(
            dict(start_blocked_result.get("response") or {}).get("tool_events") or []
        )
        start_blocked_projection = _shell_protocol_fields(
            dict((start_blocked_events[-1].get("payload") if start_blocked_events else {}) or {})
        )
        start_blocked_decision, start_blocked_reason, start_blocked_snapshot = (
            self._command_start_policy_readout(start_blocked)
        )
        self.assertEqual(
            start_blocked_decision, str(start_blocked_projection.get("policyDecision") or "")
        )
        self.assertEqual(
            start_blocked_reason, str(start_blocked_projection.get("policyDecisionReason") or "")
        )
        self.assertEqual(
            start_blocked_snapshot, dict(start_blocked_projection.get("policySnapshot") or {})
        )
        self._assert_policy_triplet(
            start_blocked_decision, start_blocked_reason, start_blocked_snapshot
        )

    def test_policy_triplet_parity_between_command_exec_and_start_three_state_matrix(self) -> None:
        allowed_exec = self._command_exec_response(self._build_runtime("never"), "echo parity")
        allowed_exec_result = dict(allowed_exec.get("result") or {})
        allowed_exec_triplet = (
            str(allowed_exec_result.get("policyDecision") or ""),
            str(allowed_exec_result.get("policyDecisionReason") or ""),
            dict(allowed_exec_result.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(*allowed_exec_triplet)

        allowed_start = self._command_start_response(self._build_runtime("never"), "python -i")
        allowed_start_triplet = self._command_start_policy_readout(allowed_start)
        self._assert_policy_triplet(*allowed_start_triplet)
        self.assertEqual(allowed_start_triplet, allowed_exec_triplet)

        approval_exec = self._command_exec_response(
            self._build_runtime("on-request"), "touch parity.txt"
        )
        approval_exec_result = dict(approval_exec.get("result") or {})
        approval_exec_triplet = (
            str(approval_exec_result.get("policyDecision") or ""),
            str(approval_exec_result.get("policyDecisionReason") or ""),
            dict(approval_exec_result.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(*approval_exec_triplet)

        approval_start = self._command_start_response(
            self._build_runtime("on-request"), "python -i"
        )
        approval_start_triplet = self._command_start_policy_readout(approval_start)
        self._assert_policy_triplet(*approval_start_triplet)
        self.assertEqual(approval_start_triplet, approval_exec_triplet)

        with background_teammate_policy():
            blocked_exec = self._command_exec_response(self._build_runtime("never"), "pytest -q")
            blocked_start = self._command_start_response(self._build_runtime("never"), "pytest -q")
        blocked_exec_result = dict(blocked_exec.get("result") or {})
        blocked_exec_triplet = (
            str(blocked_exec_result.get("policyDecision") or ""),
            str(blocked_exec_result.get("policyDecisionReason") or ""),
            dict(blocked_exec_result.get("policySnapshot") or {}),
        )
        self._assert_policy_triplet(*blocked_exec_triplet)

        blocked_start_triplet = self._command_start_policy_readout(blocked_start)
        self._assert_policy_triplet(*blocked_start_triplet)
        self.assertEqual(blocked_start_triplet, blocked_exec_triplet)

    def test_shell_policy_contract_preserves_policy_input_dimensions(self) -> None:
        contract = shell_policy_contract_from_payload(
            {
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": False,
                "request_permission_enabled": True,
                "approval_id": "approval_demo",
                "status": "pending",
            }
        )
        self.assertEqual(contract["decision"], "requires_approval")
        self.assertEqual(contract["approval_policy"], "on-request")
        self.assertEqual(contract["sandbox_mode"], "workspace-write")
        self.assertIs(contract["network_access_enabled"], False)
        self.assertIs(contract["request_permission_enabled"], True)

    def test_shell_policy_contract_treats_pending_status_as_requires_approval(self) -> None:
        contract = shell_policy_contract_from_payload(
            {
                "status": "pending",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": True,
                "request_permission_enabled": False,
            }
        )
        self.assertEqual(
            contract,
            {
                "decision": "requires_approval",
                "reason": "approval_required",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": True,
                "request_permission_enabled": False,
            },
        )

    def test_shell_policy_contract_snapshot_guard_core_fields(self) -> None:
        contract = shell_policy_contract_from_payload(
            {
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": False,
                "request_permission_enabled": True,
                "approval_id": "approval_snapshot",
                "status": "pending",
            }
        )
        self.assertEqual(
            list(contract.keys()),
            [
                "decision",
                "reason",
                "approval_policy",
                "sandbox_mode",
                "network_access_enabled",
                "request_permission_enabled",
            ],
        )
        self.assertEqual(
            contract,
            {
                "decision": "requires_approval",
                "reason": "approval_required",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": False,
                "request_permission_enabled": True,
            },
        )

    def test_shell_policy_contract_snapshot_like_guard_locks_required_fields(self) -> None:
        required_fields = [
            "decision",
            "reason",
            "approval_policy",
            "sandbox_mode",
            "network_access_enabled",
            "request_permission_enabled",
        ]
        fixtures = [
            (
                {
                    "status": "ok",
                    "approval_policy": "never",
                    "sandbox_mode": "workspace-write",
                    "network_access_enabled": True,
                    "request_permission_enabled": False,
                },
                {
                    "decision": "allowed",
                    "reason": "policy_allowed",
                    "approval_policy": "never",
                    "sandbox_mode": "workspace-write",
                    "network_access_enabled": True,
                    "request_permission_enabled": False,
                },
            ),
            (
                {
                    "status": "pending",
                    "approval_id": "approval_snapshot_like_guard",
                    "approval_policy": "on-request",
                    "sandbox_mode": "workspace-write",
                    "network_access_enabled": True,
                    "request_permission_enabled": True,
                },
                {
                    "decision": "requires_approval",
                    "reason": "approval_required",
                    "approval_policy": "on-request",
                    "sandbox_mode": "workspace-write",
                    "network_access_enabled": True,
                    "request_permission_enabled": True,
                },
            ),
            (
                {
                    "status": "policy_denied",
                    "error_code": "test_scope_required",
                    "approval_policy": "never",
                    "sandbox_mode": "read-only",
                    "network_access_enabled": False,
                    "request_permission_enabled": True,
                },
                {
                    "decision": "blocked",
                    "reason": "policy_denied:test_scope_required",
                    "approval_policy": "never",
                    "sandbox_mode": "read-only",
                    "network_access_enabled": False,
                    "request_permission_enabled": True,
                },
            ),
        ]
        for payload, expected_contract in fixtures:
            contract = shell_policy_contract_from_payload(payload)
            self.assertEqual(list(contract.keys()), required_fields)
            self.assertEqual(set(contract.keys()), set(required_fields))
            self.assertEqual(contract, expected_contract)
            # Snapshot-like stable rendering guard for contract drift detection.
            self.assertEqual(
                json.dumps(contract, ensure_ascii=False),
                json.dumps(expected_contract, ensure_ascii=False),
            )

    def test_shell_policy_reason_taxonomy_is_stable_across_three_states(self) -> None:
        allowed = shell_policy_decision_contract(
            approval_policy="never",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
            request_permission_enabled=False,
            requires_approval=False,
            blocked=False,
        )
        approval = shell_policy_decision_contract(
            approval_policy="on-request",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
            request_permission_enabled=False,
            requires_approval=True,
            blocked=False,
        )
        blocked = shell_policy_decision_contract(
            approval_policy="never",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
            request_permission_enabled=False,
            requires_approval=False,
            blocked=True,
            blocked_reason="policy_denied:test_scope_required",
        )
        self.assertEqual(allowed["decision"], "allowed")
        self.assertEqual(allowed["reason"], "policy_allowed")
        self.assertEqual(approval["decision"], "requires_approval")
        self.assertEqual(approval["reason"], "approval_required")
        self.assertEqual(blocked["decision"], "blocked")
        self.assertTrue(str(blocked["reason"]).startswith("policy_denied"))

    def test_shell_policy_reason_taxonomy_guard_exact_and_prefix_contracts(self) -> None:
        cases = [
            (
                "allowed",
                shell_policy_contract_from_payload({"status": "ok"}),
                "policy_allowed",
                False,
            ),
            (
                "requires_approval",
                shell_policy_contract_from_payload(
                    {"status": "pending", "approval_id": "approval_guard"}
                ),
                "approval_required",
                False,
            ),
            (
                "blocked_with_code",
                shell_policy_contract_from_payload(
                    {"status": "policy_denied", "error_code": "test_scope_required"}
                ),
                "policy_denied:test_scope_required",
                True,
            ),
            (
                "blocked_without_code",
                shell_policy_contract_from_payload({"status": "policy_denied"}),
                "policy_denied",
                True,
            ),
        ]
        for _name, contract, expected_reason, is_prefix in cases:
            if is_prefix:
                self.assertTrue(str(contract["reason"]).startswith("policy_denied"))
            self.assertEqual(contract["reason"], expected_reason)

    def test_shell_policy_snapshot_guard_required_field_set_across_three_states(self) -> None:
        required_fields = (
            "decision",
            "reason",
            "approval_policy",
            "sandbox_mode",
            "network_access_enabled",
            "request_permission_enabled",
        )
        contracts = [
            shell_policy_contract_from_payload({"status": "ok"}),
            shell_policy_contract_from_payload(
                {"status": "pending", "approval_id": "approval_snapshot_guard"}
            ),
            shell_policy_contract_from_payload(
                {"status": "policy_denied", "error_code": "test_scope_required"}
            ),
        ]
        for contract in contracts:
            self.assertEqual(list(contract.keys()), list(required_fields))
            self.assertEqual(set(contract.keys()), set(required_fields))
            self.assertIsInstance(contract["decision"], str)
            self.assertIsInstance(contract["reason"], str)
            self.assertTrue(
                contract["approval_policy"] is None or isinstance(contract["approval_policy"], str)
            )
            self.assertTrue(
                contract["sandbox_mode"] is None or isinstance(contract["sandbox_mode"], str)
            )
            self.assertTrue(
                contract["network_access_enabled"] is None
                or isinstance(contract["network_access_enabled"], bool)
            )
            self.assertTrue(
                contract["request_permission_enabled"] is None
                or isinstance(contract["request_permission_enabled"], bool)
            )

    def test_shell_policy_reason_taxonomy_guard_requires_exact_allowed_and_approval_values(
        self,
    ) -> None:
        allowed = shell_policy_contract_from_payload({"status": "ok"})
        approval = shell_policy_contract_from_payload(
            {"status": "pending", "approval_id": "approval_taxonomy_guard"}
        )
        blocked = shell_policy_contract_from_payload(
            {"status": "policy_denied", "error_code": "background_teammate_active"}
        )
        self.assertEqual(allowed["decision"], "allowed")
        self.assertEqual(allowed["reason"], "policy_allowed")
        self.assertEqual(approval["decision"], "requires_approval")
        self.assertEqual(approval["reason"], "approval_required")
        self.assertEqual(blocked["decision"], "blocked")
        self.assertTrue(str(blocked["reason"]).startswith("policy_denied:"))

    def test_shell_tool_event_policy_readout_projection_stable_across_three_states(self) -> None:
        approval_runtime = self._build_runtime("on-request")
        approval_event = approval_runtime.handle_prompt("/shell touch hi.txt").tool_events[-1]
        approval_fields = _shell_protocol_fields(dict(approval_event.payload or {}))
        self.assertEqual(approval_fields.get("policyDecision"), "requires_approval")
        self.assertEqual(approval_fields.get("policyDecisionReason"), "approval_required")

        allowed_runtime = self._build_runtime("never")
        allowed_event = allowed_runtime.handle_prompt("/shell echo hi").tool_events[-1]
        allowed_fields = _shell_protocol_fields(dict(allowed_event.payload or {}))
        self.assertEqual(allowed_fields.get("policyDecision"), "allowed")
        self.assertEqual(allowed_fields.get("policyDecisionReason"), "policy_allowed")

        with background_teammate_policy():
            blocked_runtime = self._build_runtime("never")
            blocked_event = blocked_runtime.handle_prompt("/shell pytest -q").tool_events[-1]
        blocked_fields = _shell_protocol_fields(dict(blocked_event.payload or {}))
        self.assertEqual(blocked_fields.get("policyDecision"), "blocked")
        self.assertTrue(
            str(blocked_fields.get("policyDecisionReason") or "").startswith("policy_denied")
        )
        self.assertEqual(
            set(dict(approval_fields.get("policySnapshot") or {}).keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )
        self.assertEqual(
            set(dict(allowed_fields.get("policySnapshot") or {}).keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )
        self.assertEqual(
            set(dict(blocked_fields.get("policySnapshot") or {}).keys()),
            {"approvalPolicy", "sandboxMode", "networkAccessEnabled", "requestPermissionEnabled"},
        )

    def test_policy_snapshot_schema_guard_keys_and_types_across_shell_surfaces(self) -> None:
        approval_runtime = self._build_runtime("on-request")
        approval_fields = _shell_protocol_fields(
            dict(
                approval_runtime.handle_prompt("/shell touch hi.txt").tool_events[-1].payload or {}
            )
        )
        self._assert_policy_snapshot_schema(dict(approval_fields.get("policySnapshot") or {}))

        allowed_runtime = self._build_runtime("never")
        allowed_fields = _shell_protocol_fields(
            dict(allowed_runtime.handle_prompt("/shell echo hi").tool_events[-1].payload or {})
        )
        self._assert_policy_snapshot_schema(dict(allowed_fields.get("policySnapshot") or {}))

        with background_teammate_policy():
            blocked_runtime = self._build_runtime("never")
            blocked_fields = _shell_protocol_fields(
                dict(
                    blocked_runtime.handle_prompt("/shell pytest -q").tool_events[-1].payload or {}
                )
            )
        self._assert_policy_snapshot_schema(dict(blocked_fields.get("policySnapshot") or {}))

        start_runtime = self._build_runtime("on-request")
        start_result = self._command_start_response(start_runtime, "python -i")
        start_payload = dict(start_result["result"]["response"]["tool_events"][-1]["payload"] or {})
        start_fields = _shell_protocol_fields(start_payload)
        self._assert_policy_snapshot_schema(dict(start_fields.get("policySnapshot") or {}))

    def test_policy_snapshot_schema_guard_keys_and_types_for_projection_payload_variants(
        self,
    ) -> None:
        expected_keys = {
            "approvalPolicy",
            "sandboxMode",
            "networkAccessEnabled",
            "requestPermissionEnabled",
        }
        payload_variants = [
            {
                "status": "ok",
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "network_access_enabled": True,
                "request_permission_enabled": False,
            },
            {
                "status": "ok",
                "approval_policy": "",
                "sandbox_mode": "",
                "network_access_enabled": "invalid",
                "request_permission_enabled": "invalid",
            },
            {
                "status": "pending",
                "approval_id": "approval_snapshot_schema_guard",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "network_access_enabled": "enabled",
                "request_permission_enabled": "0",
            },
        ]
        for payload in payload_variants:
            fields = _shell_protocol_fields(dict(payload))
            snapshot = dict(fields.get("policySnapshot") or {})
            self.assertEqual(set(snapshot.keys()), expected_keys)
            self.assertEqual(len(snapshot), len(expected_keys))
            self.assertTrue(
                snapshot.get("approvalPolicy") is None
                or isinstance(snapshot.get("approvalPolicy"), str)
            )
            self.assertTrue(
                snapshot.get("sandboxMode") is None or isinstance(snapshot.get("sandboxMode"), str)
            )
            self.assertTrue(
                snapshot.get("networkAccessEnabled") is None
                or isinstance(snapshot.get("networkAccessEnabled"), bool)
            )
            self.assertTrue(
                snapshot.get("requestPermissionEnabled") is None
                or isinstance(snapshot.get("requestPermissionEnabled"), bool)
            )

    def test_shell_write_and_terminate_use_interactive_session_tools(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(approval_policy="never")

        start_response = runtime.handle_prompt("/shell start python -i")
        session_id = start_response.tool_events[-1].payload["session_id"]
        write_response = runtime.handle_prompt(f'/shell write {session_id} "ping\\n"')
        terminate_response = runtime.handle_prompt(f"/shell terminate {session_id}")

        self.assertEqual(start_response.tool_events[-1].name, "shell_start")
        self.assertEqual(write_response.tool_events[-1].summary, "shell stdin written")
        self.assertEqual(tools.shell_write_calls, [(session_id, "ping\\n")])
        self.assertEqual(tools.shell_terminate_calls, [session_id])
        write_payload = write_response.tool_events[-1].payload
        self.assertEqual(write_payload["session_id"], session_id)
        self.assertEqual(write_payload["process_id"], session_id)
        self.assertEqual(write_payload["status"], "written")
        write_command_items = [
            dict(event.get("item") or {})
            for event in list(write_response.turn_events or [])
            if str(event.get("type") or "") == "item.completed"
            and str(dict(event.get("item") or {}).get("type") or "") == "command_execution"
        ]
        self.assertTrue(write_command_items)
        self.assertEqual(str(write_command_items[-1].get("status") or ""), "completed")
        self.assertTrue(str(write_command_items[-1].get("command") or "").strip())

        terminate_payload = terminate_response.tool_events[-1].payload
        self.assertEqual(terminate_payload["session_id"], session_id)
        self.assertEqual(terminate_payload["process_id"], session_id)
        self.assertEqual(terminate_payload["status"], "interrupted")
        self.assertTrue(terminate_payload["interrupted"])
        terminate_command_items = [
            dict(event.get("item") or {})
            for event in list(terminate_response.turn_events or [])
            if str(event.get("type") or "") == "item.completed"
            and str(dict(event.get("item") or {}).get("type") or "") == "command_execution"
        ]
        self.assertTrue(terminate_command_items)
        self.assertEqual(str(terminate_command_items[-1].get("status") or ""), "failed")

    def test_web_search_is_blocked_when_disabled(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(web_search_mode="disabled")

        response = runtime.handle_prompt("/web_search 北京天气")

        self.assertIn("web search disabled", response.assistant_text.lower())
        self.assertEqual(tools.web_search_calls, [])
        self.assertEqual(
            response.tool_events[0].payload["error"], "runtime web search mode is disabled"
        )

    def test_web_fetch_is_blocked_when_network_access_disabled(self) -> None:
        tools = _PolicyTools()
        runtime = AgentCliRuntime(agent=_PolicyAgent(), tools=tools)
        runtime.configure_runtime_policy(network_access_enabled=False)

        response = runtime.handle_prompt("/web_fetch https://example.com")

        self.assertIn("fetch blocked", response.assistant_text.lower())
        self.assertEqual(tools.web_fetch_calls, [])
        self.assertEqual(
            response.tool_events[0].payload["error"], "runtime network access is disabled"
        )

    def test_headless_builds_runtime_with_policy_args(self) -> None:
        fake_runtime = _HeadlessRuntime()
        stdout = io.StringIO()

        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": "hello",
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": False,
                "provider_status": False,
                "resume": None,
                "permission_mode": None,
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "web_search_mode": "disabled",
                "network_access": "disabled",
            },
        )()

        with patch(
            "cli.agent_cli.headless.build_headless_runtime", return_value=fake_runtime
        ) as build_runtime:
            exit_code = run_headless(args, stdout=stdout, stderr=io.StringIO())

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runtime.prompts, ["hello"])
        _, kwargs = build_runtime.call_args
        self.assertFalse(kwargs["persistent"])
        policy = kwargs["runtime_policy"]
        self.assertEqual(policy.approval_policy, "never")
        self.assertEqual(policy.sandbox_mode, "read-only")
        self.assertEqual(policy.web_search_mode, "disabled")
        self.assertEqual(policy.network_access_enabled, False)

    def test_headless_serve_builds_persistent_runtime(self) -> None:
        fake_runtime = _HeadlessRuntime()
        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": None,
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": True,
                "provider_status": False,
                "resume": None,
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "web_search_mode": "disabled",
                "network_access": "disabled",
            },
        )()

        with patch(
            "cli.agent_cli.headless.build_headless_runtime", return_value=fake_runtime
        ) as build_runtime:
            with patch("cli.agent_cli.headless._run_serve_loop", return_value=0):
                exit_code = run_headless(
                    args, stdin=io.StringIO(), stdout=io.StringIO(), stderr=io.StringIO()
                )

        self.assertEqual(exit_code, 0)
        _, kwargs = build_runtime.call_args
        self.assertTrue(kwargs["persistent"])

    def test_headless_resume_builds_persistent_runtime(self) -> None:
        fake_runtime = _HeadlessRuntime()
        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": "hello",
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": False,
                "provider_status": False,
                "resume": "thread_123",
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "web_search_mode": "disabled",
                "network_access": "disabled",
            },
        )()

        with patch(
            "cli.agent_cli.headless.build_headless_runtime", return_value=fake_runtime
        ) as build_runtime:
            exit_code = run_headless(args, stdout=io.StringIO(), stderr=io.StringIO())

        self.assertEqual(exit_code, 0)
        _, kwargs = build_runtime.call_args
        self.assertTrue(kwargs["persistent"])
        self.assertEqual(kwargs["resume_thread_id"], "thread_123")

    def test_headless_applies_policy_args_to_injected_runtime(self) -> None:
        runtime = _HeadlessRuntime()
        stdout = io.StringIO()

        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": "hello",
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": False,
                "provider_status": False,
                "resume": None,
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "web_search_mode": "disabled",
                "network_access": "disabled",
            },
        )()

        exit_code = run_headless(args, runtime=runtime, stdout=stdout, stderr=io.StringIO())

        self.assertEqual(exit_code, 0)
        self.assertEqual(runtime.prompts, ["hello"])
        self.assertEqual(len(runtime.runtime_policy_updates), 1)
        self.assertEqual(runtime.runtime_policy_updates[0]["approval_policy"], "never")
        self.assertEqual(runtime.runtime_policy_updates[0]["sandbox_mode"], "read-only")
        self.assertEqual(runtime.runtime_policy_updates[0]["web_search_mode"], "disabled")
        self.assertEqual(runtime.runtime_policy_updates[0]["network_access_enabled"], False)

    def test_headless_resume_calls_runtime_before_prompt_execution(self) -> None:
        runtime = _HeadlessRuntime()
        stdout = io.StringIO()

        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": "hello again",
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": False,
                "provider_status": False,
                "resume": "thread_resume_123",
                "permission_mode": None,
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "web_search_mode": "disabled",
                "network_access": "disabled",
            },
        )()

        exit_code = run_headless(args, runtime=runtime, stdout=stdout, stderr=io.StringIO())

        self.assertEqual(exit_code, 0)
        self.assertEqual(runtime.resume_calls, ["thread_resume_123"])
        self.assertEqual(runtime.prompts, ["hello again"])

    def test_headless_permission_mode_maps_to_runtime_policy_axes(self) -> None:
        runtime = _HeadlessRuntime()
        stdout = io.StringIO()

        args = type(
            "Args",
            (),
            {
                "headless": True,
                "prompt": "hello from plan mode",
                "stdin": False,
                "json": False,
                "jsonl": False,
                "serve": False,
                "provider_status": False,
                "resume": None,
                "permission_mode": "plan",
                "approval_policy": None,
                "sandbox_mode": None,
                "web_search_mode": None,
                "network_access": None,
            },
        )()

        exit_code = run_headless(args, runtime=runtime, stdout=stdout, stderr=io.StringIO())

        self.assertEqual(exit_code, 0)
        self.assertEqual(runtime.prompts, ["hello from plan mode"])
        self.assertEqual(len(runtime.runtime_policy_updates), 1)
        self.assertEqual(runtime.runtime_policy_updates[0]["approval_policy"], "on-request")
        self.assertEqual(runtime.runtime_policy_updates[0]["sandbox_mode"], "read-only")
        self.assertEqual(runtime.runtime_policy_updates[0]["network_access_enabled"], True)
