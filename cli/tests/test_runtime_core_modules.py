from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
)
from cli.agent_cli.models_tool_io import MediaIngestResult
from cli.agent_cli.orchestration import taskbook_runtime_results_helper_runtime
from cli.agent_cli.orchestration.taskbook_models import CardResult, ExecutionRef, TaskCard
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ExecutionRefKind,
    TaskCardKind,
)
from cli.agent_cli.provider import _command_for_tool_call
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.runtime import (
    runtime_request_user_input_default_mode_enabled,
    sync_runtime_request_user_input_mode,
)
from cli.agent_cli.runtime_core import (
    activity_detail_for_event,
    activity_events_for_tool_event,
    apply_tool_state,
    build_status_payload,
    detail_for_event,
    execute_agent_intent_result,
    parse_args,
    restore_provider_state,
    run_command_text,
    run_command_text_result,
    snapshot_thread_state_payload,
    split_command,
    try_execute_local_plan,
)
from cli.agent_cli.runtime_core.command_dispatch import tool_result_fallback_text
from cli.agent_cli.runtime_core.event_detail_rendering import _first_excerpt_text
from cli.agent_cli.tools_core import document_tools_runtime, tool_registry_method_bindings_runtime
from cli.agent_cli.ui.request_user_input_bridge import RequestUserInputBridge

_SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII="
)


def _structured_tool_result(name, summary, payload=None, arguments=None):
    resolved_payload = dict(payload or {})
    resolved_arguments = dict(arguments or {})
    event = ToolEvent(name=name, ok=True, summary=summary, payload=resolved_payload)
    return CommandExecutionResult(
        assistant_text=summary,
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=name,
            arguments=resolved_arguments or None,
            ok=True,
            summary=summary,
            structured_content=resolved_payload or None,
        ),
    )


class _DispatchTools:
    def __init__(self, plugin_result=None):
        self._plugin_result = plugin_result

    def run_plugin_command(self, name, arg_text, runtime):
        return self._plugin_result

    def capabilities(self):
        return {"ok": True, "tools": [{"name": "shell", "description": "shell"}]}

    def file_list(self, *, path=None, limit=50):
        return ToolEvent(
            name="file_list",
            ok=True,
            summary="files=2",
            payload={
                "path": path or ".",
                "count": 2,
                "files": [{"path": "README.md", "size": 10}, {"path": "src/app.py", "size": 20}],
            },
        )

    def file_search(self, query, *, path=None, limit=20):
        return ToolEvent(
            name="file_search",
            ok=True,
            summary="file matches=1",
            payload={
                "query": query,
                "path": path or ".",
                "count": 1,
                "file_count": 1,
                "matches": [{"path": "src/app.py", "line": 8, "text": "TODO hello"}],
            },
        )

    def grep_files(self, pattern, *, include=None, path=None, limit=100, **kwargs):
        del kwargs
        return ToolEvent(
            name="grep_files",
            ok=True,
            summary="paths=1",
            payload={
                "pattern": pattern,
                "include": include,
                "path": path or ".",
                "count": 1,
                "paths": ["src/app.py"],
                "text": "src/app.py",
            },
        )

    def glob_files(self, pattern, *, path=None, limit=100):
        return ToolEvent(
            name="glob_files",
            ok=True,
            summary="paths=1",
            payload={
                "pattern": pattern,
                "path": path or ".",
                "count": 1,
                "paths": ["docs/guide.md"],
                "text": "docs/guide.md",
                "limit": limit,
            },
        )

    def list_dir(self, *, dir_path=None, offset=1, limit=25, depth=2):
        return ToolEvent(
            name="list_dir",
            ok=True,
            summary="entries=2",
            payload={
                "dir_path": dir_path or ".",
                "offset": offset,
                "limit": limit,
                "depth": depth,
                "count": 2,
                "returned_count": 2,
                "entries": [
                    {"index": 1, "kind": "file", "path": "README.md"},
                    {"index": 2, "kind": "dir", "path": "src"},
                ],
                "text": "E1: [file] README.md\nE2: [dir] src",
            },
        )

    def file_read(self, path, *, offset=None, limit=None, max_chars=None):
        payload = {
            "path": path,
            "char_count": 20,
            "line_count": 2,
            "truncated": False,
            "text": "L1: hello",
            "excerpt_lines": [{"line": 1, "text": "hello"}],
        }
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if max_chars is not None:
            payload["max_chars"] = max_chars
        return ToolEvent(
            name="file_read",
            ok=True,
            summary="file loaded",
            payload=payload,
        )

    def read_file(self, file_path, *, offset=None, limit=None, mode=None, indentation=None):
        payload = {
            "file_path": file_path,
            "path": file_path,
            "line_count": 2,
            "text": "L1: hello",
        }
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if mode is not None:
            payload["mode"] = mode
        if indentation is not None:
            payload["indentation"] = indentation
        return ToolEvent(
            name="read_file",
            ok=True,
            summary="file loaded",
            payload=payload,
        )

    def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
        return ToolEvent(
            name="web_search",
            ok=True,
            summary=f"web results={limit}",
            payload={
                "query": query,
                "count": limit,
                "results": [],
                "domains": domains or [],
                "recency_days": recency_days,
                "market": market,
            },
        )

    def view_image(self, path):
        return ToolEvent(
            name="view_image",
            ok=True,
            summary="image artifact ready: sample.png",
            payload={
                "ok": True,
                "path": path,
                "requested_path": path,
                "image_artifacts": [
                    {
                        "path": path,
                        "mime_type": "image/png",
                        "size_bytes": 16,
                        "width": 1,
                        "height": 1,
                        "image_url": "data:image/png;base64,AAAA",
                    }
                ],
            },
        )

    def web_fetch(self, url, *, max_chars=12000):
        return ToolEvent(
            name="web_fetch",
            ok=True,
            summary="web page loaded",
            payload={
                "url": url,
                "final_url": url,
                "source_domain": "platform.openai.com",
                "title": "OpenAI API docs",
                "text": "The OpenAI API provides access to models.",
                "max_chars": max_chars,
            },
        )

    def open(self, ref, *, line=1):
        return ToolEvent(
            name="open",
            ok=True,
            summary="page opened",
            payload={
                "ref_id": "page_1",
                "url": ref,
                "final_url": ref,
                "source_domain": "platform.openai.com",
                "title": "OpenAI API docs",
                "line_count": 3,
                "link_count": 1,
                "links": [
                    {
                        "id": 1,
                        "text": "Quickstart",
                        "url": "https://platform.openai.com/docs/quickstart",
                    }
                ],
                "excerpt_lines": [{"line": 1, "text": "Overview"}],
            },
        )

    def click(self, ref_id, *, id):
        return ToolEvent(
            name="click",
            ok=True,
            summary="link opened",
            payload={
                "source_ref_id": ref_id,
                "clicked_link_id": id,
                "clicked_link_text": "Quickstart",
                "ref_id": "page_2",
                "url": "https://platform.openai.com/docs/quickstart",
                "final_url": "https://platform.openai.com/docs/quickstart",
                "title": "Quickstart",
                "excerpt_lines": [{"line": 1, "text": "Install the SDK first."}],
            },
        )

    def find(self, ref_id, *, pattern):
        return ToolEvent(
            name="find",
            ok=True,
            summary="matches=1",
            payload={
                "ref_id": ref_id,
                "pattern": pattern,
                "count": 1,
                "matches": [
                    {"line": 2, "text": "Use the Responses API for text and tool calling."}
                ],
            },
        )

    def browser(self, action, **kwargs):
        return ToolEvent(
            name="browser_action",
            ok=True,
            summary=f"browser {action} ok",
            payload={"action": action, **kwargs},
        )


class _GrepBindingRegistry:
    def workspace_root(self):
        return Path("/tmp")


class _DispatchAgent:
    @staticmethod
    def provider_status():
        return {"provider_ready": "true", "provider_model": "demo"}

    @staticmethod
    def available_providers():
        return []

    @staticmethod
    def available_models(provider_name=None):
        return []


class _DispatchRuntime:
    def __init__(self, *, plugin_result=None, interrupted=False):
        self.tools = _DispatchTools(plugin_result)
        self.agent = _DispatchAgent()
        self.history = []
        self._interrupted = interrupted
        self._runtime_policy = {
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "web_search_mode": "live",
            "network_access": "enabled",
        }

    def _is_interrupt_requested(self):
        return self._interrupted

    def _normalize_shell_override(self, shell):
        return current_host_platform().normalize_shell_override(shell)

    def _interrupt_tuple(self):
        return ("interrupted", [])

    @staticmethod
    def _single_event(prefix, event):
        return (prefix, [event])

    @staticmethod
    def _parse_args(arg_text):
        return parse_args(arg_text)

    def runtime_policy_status(self):
        return dict(self._runtime_policy)

    def configure_runtime_policy(
        self,
        *,
        approval_policy=None,
        sandbox_mode=None,
        web_search_mode=None,
        network_access_enabled=None,
    ):
        if approval_policy is not None:
            self._runtime_policy["approval_policy"] = str(approval_policy)
        if sandbox_mode is not None:
            self._runtime_policy["sandbox_mode"] = str(sandbox_mode)
        if web_search_mode is not None:
            self._runtime_policy["web_search_mode"] = str(web_search_mode)
        if network_access_enabled is not None:
            enabled = bool(network_access_enabled)
            self._runtime_policy["network_access"] = "enabled" if enabled else "disabled"
        return self.runtime_policy_status()

    def web_access_allowed(self):
        return self._runtime_policy["network_access"] == "enabled"

    def web_search_enabled(self):
        return self.web_access_allowed() and self._runtime_policy["web_search_mode"] != "disabled"

    def patch_requires_approval(self):
        return self._runtime_policy["approval_policy"] != "never"

    def workspace_is_read_only(self):
        return self._runtime_policy["sandbox_mode"] == "read-only"

    def request_patch_approval(self, patch_text):
        return ToolEvent(
            name="patch_approval_requested",
            ok=True,
            summary="patch approval requested approval_1",
            payload={
                "approval_id": "approval_1",
                "file_count": 1,
                "changes": [{"path": "demo.txt", "change_type": "add"}],
            },
        )

    def approvals_event(self, *, limit=20, status=None):
        return ToolEvent(
            name="approval_list",
            ok=True,
            summary="approvals=1",
            payload={
                "count": 1,
                "status": status,
                "approvals": [
                    {
                        "approval_id": "approval_1",
                        "status": "pending",
                        "action_type": "apply_patch",
                        "summary": "Approve workspace patch",
                    }
                ],
            },
        )

    def request_shell_approval(self, command, *, requested_by="cli", timeout_sec=60, **kwargs):
        return ToolEvent(
            name="shell_approval_requested",
            ok=True,
            summary="shell approval requested approval_2",
            payload={
                "approval_id": "approval_2",
                "status": "pending",
                "summary": "Approve shell command",
                "reason": "user approval required before running local shell command",
                "command": command,
                "timeout_sec": timeout_sec,
                **dict(kwargs or {}),
            },
        )

    def request_background_teammate_approval(
        self,
        task,
        *,
        requested_by="cli",
        provider="",
        model="",
        reasoning_effort="",
        task_cwd=None,
        queue_cwd=None,
        approval_policy="never",
        sandbox_mode="workspace-write",
        allowed_paths=None,
        blocked_paths=None,
        timeout_seconds=None,
    ):
        del requested_by, queue_cwd
        resolved_allowed_paths = list(allowed_paths or [])
        resolved_blocked_paths = list(blocked_paths or [])
        return ToolEvent(
            name="background_teammate_approval_requested",
            ok=True,
            summary="background teammate approval requested approval_bg_1",
            payload={
                "approval_id": "approval_bg_1",
                "status": "pending",
                "task_type": "teammate",
                "task": task,
                "provider": provider,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "cwd": task_cwd,
                "approval_policy": approval_policy,
                "sandbox_mode": sandbox_mode,
                "allowed_paths": resolved_allowed_paths,
                "blocked_paths": resolved_blocked_paths,
                "timeout_seconds": timeout_seconds,
                "summary_text": "\n".join(
                    [
                        "background teammate approval requested",
                        "approval_id=approval_bg_1",
                        "status=pending",
                        f"provider={provider}" if provider else "",
                        f"model={model}" if model else "",
                        f"reasoning_effort={reasoning_effort}" if reasoning_effort else "",
                        f"cwd={task_cwd}" if task_cwd else "",
                        f"approval_policy={approval_policy}",
                        f"sandbox_mode={sandbox_mode}",
                        "staged_run=true",
                        "final_apply_required=true",
                        f"timeout_seconds={timeout_seconds}" if timeout_seconds is not None else "",
                        f"allowed_paths={resolved_allowed_paths}" if resolved_allowed_paths else "",
                        f"blocked_paths={resolved_blocked_paths}" if resolved_blocked_paths else "",
                        f"task={task}",
                        "/approve approval_bg_1",
                        "/reject approval_bg_1",
                    ]
                )
                .replace("\n\n", "\n")
                .strip(),
            },
        )

    def decide_approval(
        self, approval_id, *, approved=None, decision=None, decided_by, decision_note=""
    ):
        resolved_decision = str(decision or ("accept" if approved else "decline"))
        approved = resolved_decision in {
            "accept",
            "accept_for_session",
            "accept_with_execpolicy_amendment",
        }
        events = [
            ToolEvent(
                name="approval_decision",
                ok=True,
                summary=("approved" if approved else "rejected") + f" {approval_id}",
                payload={
                    "approval_id": approval_id,
                    "status": "approved" if approved else "rejected",
                    "action_type": "apply_patch",
                    "decision_by": decided_by,
                    "decision_note": decision_note,
                },
            )
        ]
        if approved and approval_id == "approval_bg_1":
            events.append(
                ToolEvent(
                    name="background_teammate_submitted",
                    ok=True,
                    summary="background teammate submitted bg_teammate_2",
                    payload={
                        "task_id": "bg_teammate_2",
                        "status": "queued",
                        "provider": "glm",
                        "model": "glm_5",
                        "reasoning_effort": "medium",
                        "approval_policy": "never",
                        "sandbox_mode": "workspace-write",
                        "allowed_paths": ["src", "tests"],
                        "blocked_paths": ["README.md"],
                        "timeout_seconds": 30.0,
                        "summary_text": "\n".join(
                            [
                                "background teammate submitted",
                                "task_id=bg_teammate_2",
                                "status=queued",
                                "provider=glm",
                                "model=glm_5",
                                "reasoning_effort=medium",
                                "approval_policy=never",
                                "sandbox_mode=workspace-write",
                                "staged_run=true",
                                "final_apply_required=true",
                                "timeout_seconds=30.0",
                                "allowed_paths=['src', 'tests']",
                                "blocked_paths=['README.md']",
                                "task=总结仓库入口",
                            ]
                        ),
                    },
                )
            )
            return {"tool_events": events}
        if approved:
            events.append(
                ToolEvent(
                    name="apply_patch",
                    ok=True,
                    summary="apply_patch files=1",
                    payload={
                        "file_count": 1,
                        "changes": [{"path": "demo.txt", "change_type": "update"}],
                    },
                )
            )
        return {"tool_events": events}

    def start_shell_session(
        self,
        command,
        *,
        cwd=None,
        login=True,
        tty=False,
        shell=None,
        max_output_chars=12000,
        on_activity=None,
    ):
        del max_output_chars, on_activity
        return {
            "session_id": "session_1",
            "call_id": "call_1",
            "process_id": "proc_1",
            "command": command,
            "cwd": cwd,
            "login": login,
            "tty": tty,
            "shell": shell,
        }

    def write_shell_stdin_result(
        self,
        session_id,
        chars,
        *,
        yield_time_ms=None,
        allow_extended_empty_poll=False,
        on_activity=None,
    ):
        del allow_extended_empty_poll
        del on_activity
        payload = {
            "session_id": session_id,
            "call_id": "call_1",
            "process_id": "proc_1",
            "command": "python -V",
            "yield_time_ms": yield_time_ms,
            "stdout": "Python 3.12.0\n",
            "stderr": "",
            "aggregated_output": "Python 3.12.0\n",
            "status": "ok" if chars == "" else "written",
            "ok": True,
            "duration_ms": 12,
        }
        return CommandExecutionResult(
            assistant_text="shell",
            tool_events=[ToolEvent(name="shell", ok=True, summary="shell ok", payload=payload)],
            item_events=[],
        )


def _make_structured_command_runtime(**tool_methods):
    tools = SimpleNamespace(
        run_plugin_command=lambda name, arg_text, runtime: None,
        **tool_methods,
    )

    class _Runtime:
        def __init__(self) -> None:
            self.tools = tools
            self.agent = SimpleNamespace()
            self.history = []

        @staticmethod
        def _parse_args(arg_text):
            return parse_args(arg_text)

        @staticmethod
        def _is_interrupt_requested():
            return False

        @staticmethod
        def _interrupt_tuple():
            return ("interrupted", [])

        @staticmethod
        def web_access_allowed():
            return True

        @staticmethod
        def web_search_enabled():
            return True

    return _Runtime()


class RuntimeCoreModulesTest(unittest.TestCase):
    def test_tool_result_fallback_text_prefers_generic_webpage_label(self) -> None:
        text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="web_fetch",
                    ok=True,
                    summary="web page loaded",
                    payload={
                        "url": "https://example.com/report",
                        "final_url": "https://example.com/report",
                        "title": "Quarterly Report",
                    },
                )
            ]
        )

        self.assertIn("已读取网页：Quarterly Report", text)
        self.assertIn("https://example.com/report", text)
        self.assertNotIn("web page loaded", text)

    def test_tool_result_fallback_text_includes_approval_next_steps(self) -> None:
        shell_text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="shell_approval_requested",
                    ok=True,
                    summary="shell approval requested approval_2",
                    payload={"approval_id": "approval_2", "command": "echo hello"},
                )
            ]
        )
        self.assertIn("已提交命令审批：approval_2", shell_text)
        self.assertIn("/approve approval_2", shell_text)
        self.assertIn("/reject approval_2", shell_text)
        self.assertIn("echo hello", shell_text)

        patch_text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="patch_approval_requested",
                    ok=True,
                    summary="patch approval requested approval_3",
                    payload={"approval_id": "approval_3"},
                )
            ]
        )
        self.assertIn("已提交补丁审批：approval_3", patch_text)
        self.assertIn("/approve approval_3", patch_text)
        self.assertIn("/reject approval_3", patch_text)

    def test_tool_result_fallback_text_prefers_exec_command_stderr_for_failures(self) -> None:
        text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="exec_command",
                    ok=False,
                    summary="exec_command exited",
                    payload={
                        "stderr": "ls: cannot access '/missing': No such file or directory\n",
                        "aggregated_output": "ls: cannot access '/missing': No such file or directory\n",
                        "exit_code": 2,
                    },
                )
            ]
        )

        self.assertEqual(text, "ls: cannot access '/missing': No such file or directory")

    def test_tool_result_fallback_text_prefers_exec_command_output_for_success(self) -> None:
        text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command exited",
                    payload={
                        "stdout": "/repo\n",
                        "aggregated_output": "/repo\n",
                        "function_call_output": (
                            "Process exited with code 0\n" "Output:\n" "/repo\n"
                        ),
                        "exit_code": 0,
                    },
                )
            ]
        )

        self.assertEqual(text, "/repo")

    def test_tool_result_fallback_text_marks_legacy_file_aliases(self) -> None:
        search_text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="file_search",
                    ok=True,
                    summary="file matches=1",
                    payload={"query": "provider status"},
                )
            ]
        )
        self.assertIn("兼容命令 /file_search", search_text)
        self.assertIn("建议优先使用 grep_files", search_text)

        list_text = tool_result_fallback_text(
            [
                ToolEvent(
                    name="file_list",
                    ok=True,
                    summary="files=3",
                    payload={"path": "cli"},
                )
            ]
        )
        self.assertIn("兼容命令 /file_list", list_text)
        self.assertIn("建议优先使用 list_dir", list_text)

    def test_split_command_and_parse_args(self) -> None:
        self.assertEqual(split_command("/help"), ("help", ""))
        self.assertEqual(split_command("/shell echo hi"), ("shell", "echo hi"))

        positionals, options = parse_args("--limit 5 --debug foo bar")
        self.assertEqual(positionals, ["foo", "bar"])
        self.assertEqual(options["limit"], "5")
        self.assertTrue(options["debug"])

    def test_parse_args_supports_exec_command_flags(self) -> None:
        positionals, options = parse_args(
            "--workdir cli --shell /bin/bash --login false --yield-time-ms 250 --max-output-tokens 800 --tty 'python -V'"
        )
        self.assertEqual(positionals, ["python -V"])
        self.assertEqual(options["workdir"], "cli")
        self.assertEqual(options["shell"], "/bin/bash")
        self.assertEqual(options["login"], "false")
        self.assertEqual(options["yield-time-ms"], "250")
        self.assertEqual(options["max-output-tokens"], "800")
        self.assertTrue(options["tty"])

    def test_grep_binding_result_forwards_claude_projection_kwargs(self) -> None:
        captured = {}

        def _fake_grep_files_result(registry, pattern, **kwargs):
            captured["registry"] = registry
            captured["pattern"] = pattern
            captured["kwargs"] = dict(kwargs)
            return _structured_tool_result("grep_files", "grep ok")

        registry = _GrepBindingRegistry()
        with patch(
            "cli.agent_cli.tools_core.tool_registry_method_bindings_runtime.tool_library_runtime.grep_files_result",
            side_effect=_fake_grep_files_result,
        ):
            result = tool_registry_method_bindings_runtime.grep_files_result(
                registry,
                "P0",
                include="*.md",
                path="cli/docs",
                limit=7,
                output_mode="content",
                case_insensitive=True,
                file_type="md",
                line_numbers=True,
                after_context=1,
                before_context=2,
                context=3,
                offset=4,
                multiline=True,
            )

        self.assertEqual(result.assistant_text, "grep ok")
        self.assertIs(captured["registry"], registry)
        self.assertEqual(captured["pattern"], "P0")
        self.assertEqual(
            captured["kwargs"],
            {
                "include": "*.md",
                "path": "cli/docs",
                "limit": 7,
                "output_mode": "content",
                "case_insensitive": True,
                "file_type": "md",
                "line_numbers": True,
                "after_context": 1,
                "before_context": 2,
                "context": 3,
                "offset": 4,
                "multiline": True,
            },
        )

    def test_apply_tool_state_updates_send_flow(self) -> None:
        selected, pending, ready = apply_tool_state(
            selected_conversation=None,
            pending_send_text="",
            send_ready=False,
            event=ToolEvent(
                name="draft_reply",
                ok=True,
                summary="draft ready",
                payload={"conversation_name": "demo", "draft_reply": "draft text"},
            ),
        )
        self.assertEqual(selected, "demo")
        self.assertEqual(pending, "draft text")
        self.assertFalse(ready)

        selected, pending, ready = apply_tool_state(
            selected_conversation=selected,
            pending_send_text=pending,
            send_ready=ready,
            event=ToolEvent(
                name="prepare_send",
                ok=True,
                summary="prepare ok",
                payload={"conversation_name": "demo", "draft_text": "draft text"},
            ),
        )
        self.assertTrue(ready)

        selected, pending, ready = apply_tool_state(
            selected_conversation=selected,
            pending_send_text=pending,
            send_ready=ready,
            event=ToolEvent(
                name="send_reply",
                ok=True,
                summary="sent",
                payload={"conversation_name": "demo", "confirmed": True},
            ),
        )
        self.assertEqual(pending, "")
        self.assertFalse(ready)

    def test_activity_rendering_and_status_payload(self) -> None:
        event = ToolEvent(
            name="shell",
            ok=True,
            summary="shell ok: Get-ChildItem -Force",
            payload={"command": "Get-ChildItem -Force", "returncode": 0, "duration_ms": 5},
        )
        activities = activity_events_for_tool_event(event)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].title, "Ran Get-ChildItem -Force")
        self.assertIn("exit 0", activities[0].detail)

        help_search_event = ToolEvent(
            name="shell",
            ok=True,
            summary="shell ok: pytest --help | rg -n -- '-q'",
            payload={"command": "pytest --help | rg -n -- '-q'", "returncode": 0, "duration_ms": 5},
        )
        help_search_activities = activity_events_for_tool_event(help_search_event)
        self.assertEqual(
            help_search_activities[0].params.get("exploration_summaries"),
            [{"kind": "search", "query": "-q", "path": "pytest --help"}],
        )

        comment_label_event = ToolEvent(
            name="shell",
            ok=True,
            summary="shell ok: python -V",
            payload={
                "command": "# Capture Python version\npython -V",
                "returncode": 0,
                "duration_ms": 5,
            },
        )
        comment_label_activities = activity_events_for_tool_event(comment_label_event)
        self.assertEqual(comment_label_activities[0].title, "Ran Capture Python version")
        self.assertEqual(
            comment_label_activities[0].params.get("command_display"), "Capture Python version"
        )

        compound_command_event = ToolEvent(
            name="shell",
            ok=True,
            summary="shell ok: compound git sync",
            payload={
                "command": "cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1",
                "returncode": 0,
                "duration_ms": 5,
            },
        )
        compound_command_activities = activity_events_for_tool_event(compound_command_event)
        self.assertEqual(
            compound_command_activities[0].title,
            "Ran git fetch upstream / git merge upstream/main --no-edit",
        )
        self.assertEqual(
            compound_command_activities[0].params.get("command_display"),
            "git fetch upstream / git merge upstream/main --no-edit",
        )

        patch_event = ToolEvent(
            name="apply_patch",
            ok=True,
            summary="apply_patch files=2",
            payload={
                "file_count": 2,
                "added_count": 1,
                "updated_count": 1,
                "deleted_count": 0,
                "moved_count": 0,
                "changes": [
                    {"path": "/tmp/demo.txt", "change_type": "update"},
                    {"path": "/tmp/new.txt", "change_type": "add"},
                ],
            },
        )
        patch_activities = activity_events_for_tool_event(patch_event)
        self.assertEqual(patch_activities[0].title, "Applied patch")
        self.assertIn("files=2", patch_activities[0].detail)
        self.assertIn("updated_count=1", detail_for_event(patch_event))

        write_event = ToolEvent(
            name="apply_patch",
            ok=True,
            summary="apply_patch files=1",
            payload={
                "request_kind": "structured_write",
                "source_tool_name": "Write",
                "function_call_name": "Write",
                "file_count": 1,
                "changes": [
                    {
                        "path": "/tmp/new.txt",
                        "change_type": "add",
                        "write_mode": "create",
                    }
                ],
            },
        )
        write_activities = activity_events_for_tool_event(write_event)
        self.assertEqual(write_activities[0].title, "Created file")
        self.assertIn("/tmp/new.txt", write_activities[0].detail)
        self.assertIn("write_mode=create", detail_for_event(write_event))

        file_read_event = ToolEvent(
            name="file_read",
            ok=True,
            summary="file loaded",
            payload={
                "path": "README.md",
                "char_count": 120,
                "line_count": 8,
                "truncated": False,
                "excerpt_lines": [{"line": 1, "text": "# Demo"}],
            },
        )
        file_read_activities = activity_events_for_tool_event(file_read_event)
        self.assertEqual(file_read_activities[0].title, "Read file")
        self.assertIn("README.md", file_read_activities[0].detail)
        self.assertIn("line_count=8", detail_for_event(file_read_event))

        prepare_detail = detail_for_event(
            ToolEvent(
                name="prepare_send",
                ok=False,
                summary="blocked",
                payload={
                    "draft_text": "sensitive message",
                    "approval_message": "manual approval required",
                    "risk_guard": {"summary": "contains sensitive content"},
                    "recovery_suggestions": ["review text", "confirm manually"],
                },
            )
        )
        self.assertIn("manual approval required", prepare_detail)
        self.assertIn("risk: contains sensitive content", prepare_detail)

        status = build_status_payload(
            source_text="/shell Get-ChildItem -Force",
            events=[event],
            provider_status={"provider_name": "deepseek", "provider_ready": "true"},
            runtime_policy_status={"approval_policy": "on-request"},
            approval_status={"pending_approvals": "1", "latest_pending_approval_id": "approval_1"},
            selected_conversation=None,
            send_ready=False,
            pending_send_text="",
            active_run_token=None,
            thread_id="t1",
            thread_name="morning",
        )
        self.assertEqual(status["last_tool"], "shell")
        self.assertEqual(status["thread_id"], "t1")
        self.assertEqual(status["pending_approvals"], "1")
        self.assertEqual(status["latest_pending_approval_id"], "approval_1")

    def test_event_detail_rendering_wrapper_preserves_shell_approval_and_read_file_output(
        self,
    ) -> None:
        shell_approval_event = ToolEvent(
            name="shell_approval_requested",
            ok=True,
            summary="approval requested",
            payload={
                "approval_id": "approval_42",
                "command": "rm -rf /tmp/demo",
                "timeout_sec": 30,
            },
        )
        self.assertEqual(
            activity_detail_for_event(shell_approval_event),
            "approval_42\nrm -rf /tmp/demo\ntimeout=30",
        )

        read_file_event = ToolEvent(
            name="read_file",
            ok=True,
            summary="file read ok",
            payload={
                "file_path": "agent_cli/runtime_core/event_detail_rendering.py",
                "line_count": 12,
                "offset": 5,
                "limit": 3,
                "text": "def activity_detail_for_event(event):",
            },
        )
        self.assertEqual(
            detail_for_event(read_file_event),
            "\n".join(
                [
                    "file_path=agent_cli/runtime_core/event_detail_rendering.py",
                    "line_count=12",
                    "offset=5",
                    "limit=3",
                    "def activity_detail_for_event(event):",
                ]
            ),
        )

    def test_first_excerpt_text_wrapper_prefers_excerpt_then_text(self) -> None:
        self.assertEqual(
            _first_excerpt_text(
                {"excerpt_lines": [{"line": 9, "text": " Overview "}], "text": "fallback"}
            ),
            "Overview",
        )
        self.assertEqual(
            _first_excerpt_text({"text": "first line\nsecond line"}),
            "first line",
        )

    def test_run_command_text_result_supports_update_plan(self) -> None:
        runtime = _DispatchRuntime()
        result = run_command_text_result(
            runtime,
            '/update_plan \'{"explanation":"sync","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"}]}\'',
        )

        self.assertEqual(result.assistant_text, "Plan updated")
        self.assertEqual(result.tool_events[0].name, "update_plan")
        self.assertEqual(
            runtime.latest_task_plan,
            {
                "explanation": "sync",
                "plan": [
                    {"step": "inspect", "status": "completed"},
                    {"step": "patch", "status": "in_progress"},
                ],
            },
        )
        self.assertEqual([event["type"] for event in result.item_events], ["item.started"])
        self.assertEqual(result.item_events[0]["item"]["type"], "todo_list")
        self.assertEqual(
            result.item_events[0]["item"]["items"],
            [
                {"text": "inspect", "completed": True},
                {"text": "patch", "completed": False},
            ],
        )
        completed_plan = next(
            event
            for event in result.turn_events
            if event["type"] == "item.completed" and event["item"]["type"] == "todo_list"
        )
        self.assertEqual(completed_plan["item"]["id"], result.item_events[0]["item"]["id"])

    def test_run_command_text_result_rejects_request_user_input_in_default_mode(self) -> None:
        runtime = _DispatchRuntime()
        result = run_command_text_result(
            runtime,
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
        )

        self.assertEqual(result.tool_events[0].name, "request_user_input")
        self.assertFalse(result.tool_events[0].ok)
        self.assertEqual(result.assistant_text, "request_user_input is unavailable in Default mode")

    def test_run_command_text_result_request_user_input_round_trip_with_handler(self) -> None:
        runtime = _DispatchRuntime()
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda payload: {
            "answers": {
                "confirm_path": {"answers": ["yes"]},
            },
            "questions": payload["questions"],
        }
        result = run_command_text_result(
            runtime,
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
        )

        response = json.loads(result.assistant_text)
        self.assertEqual(response["answers"]["confirm_path"]["answers"], ["yes"])
        self.assertEqual(result.tool_events[0].payload["questions"][0]["is_other"], True)
        self.assertEqual(result.item_events[0]["item"]["tool"], "request_user_input")

    def test_run_command_text_result_supports_exit_with_resume_metadata(self) -> None:
        runtime = _DispatchRuntime()
        runtime.thread_id = "thread_exit_123"
        runtime.thread_name = "demo thread"

        result = run_command_text_result(runtime, "/exit")

        self.assertEqual(result.assistant_text.splitlines()[0], "exiting session")
        self.assertIn("thread_id=thread_exit_123", result.assistant_text)
        self.assertIn("resume_command=agenthub resume thread_exit_123", result.assistant_text)
        self.assertEqual(len(result.tool_events), 1)
        self.assertEqual(result.tool_events[0].name, "app_exit_requested")
        self.assertTrue(result.tool_events[0].ok)
        self.assertEqual(
            result.tool_events[0].payload,
            {
                "ok": True,
                "thread_id": "thread_exit_123",
                "thread_name": "demo thread",
                "resume_command": "agenthub resume thread_exit_123",
            },
        )
        self.assertEqual(result.item_events[0]["item"]["tool"], "app_exit_requested")

    def test_run_command_text_result_supports_quit_alias_for_exit(self) -> None:
        runtime = _DispatchRuntime()
        runtime.thread_id = "thread_exit_alias"

        result = run_command_text_result(runtime, "/quit")

        self.assertEqual(result.tool_events[0].name, "app_exit_requested")
        self.assertEqual(result.tool_events[0].payload["thread_id"], "thread_exit_alias")
        self.assertEqual(
            result.tool_events[0].payload["resume_command"],
            "agenthub resume thread_exit_alias",
        )

    def test_run_command_text_result_supports_preview_control(self) -> None:
        runtime = _DispatchRuntime()

        result = run_command_text_result(runtime, "/preview close")

        self.assertEqual(result.assistant_text, "Preview close requested.")
        self.assertEqual(result.tool_events[0].name, "preview_control_requested")
        self.assertEqual(result.tool_events[0].payload, {"action": "close"})
        self.assertEqual(result.item_events[0]["item"]["tool"], "preview_control_requested")

    def test_run_command_text_result_rejects_invalid_preview_action(self) -> None:
        runtime = _DispatchRuntime()

        result = run_command_text_result(runtime, "/preview resize")

        self.assertEqual(result.assistant_text, "Usage: /preview [open|close|toggle|status]")
        self.assertEqual(result.tool_events, [])

    def test_request_user_input_bridge_handler_round_trip_normalizes_response_shape(self) -> None:
        bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_test")
        captured_requests: list[str] = []

        def _on_request(pending) -> None:
            captured_requests.append(pending.request_id)
            bridge.resolve_request(
                pending.request_id,
                {
                    "answers": {
                        "confirm_path": {"answer": "yes"},
                        "ignored_key": {"answers": ["no"]},
                    }
                },
            )

        handler = bridge.build_handler(on_request=_on_request)
        response = handler(
            {
                "questions": [
                    {
                        "id": "confirm_path",
                        "header": "Confirm",
                        "question": "Proceed?",
                        "options": [
                            {"label": "Yes (Recommended)", "description": "Continue."},
                            {"label": "No", "description": "Stop."},
                        ],
                    }
                ]
            }
        )

        self.assertEqual(captured_requests, ["rui_test"])
        self.assertEqual(response, {"answers": {"confirm_path": {"answers": ["yes"]}}})
        self.assertEqual(bridge.snapshot(), [])

    def test_request_user_input_bridge_handler_cancelled_returns_none(self) -> None:
        bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_cancel")

        def _on_request(pending) -> None:
            bridge.cancel_request(pending.request_id)

        handler = bridge.build_handler(on_request=_on_request)
        response = handler(
            {
                "questions": [
                    {
                        "id": "confirm_path",
                        "header": "Confirm",
                        "question": "Proceed?",
                        "options": [
                            {"label": "Yes", "description": "Continue."},
                            {"label": "No", "description": "Stop."},
                        ],
                    }
                ]
            }
        )
        self.assertIsNone(response)
        self.assertEqual(bridge.snapshot(), [])

    def test_sync_runtime_request_user_input_mode_follows_provider_parity_flag(self) -> None:
        runtime = SimpleNamespace(
            agent=SimpleNamespace(
                _planner=SimpleNamespace(
                    config=SimpleNamespace(
                        raw_model={"default_mode_request_user_input": True},
                        raw_provider={},
                    )
                )
            ),
            default_mode_request_user_input=False,
        )
        enabled = sync_runtime_request_user_input_mode(runtime)
        self.assertTrue(enabled)
        self.assertTrue(runtime.default_mode_request_user_input)

    def test_runtime_request_user_input_default_mode_enabled_returns_false_without_planner(
        self,
    ) -> None:
        enabled = runtime_request_user_input_default_mode_enabled(
            agent=SimpleNamespace(_planner=None)
        )
        self.assertFalse(enabled)

    def test_run_command_text_result_request_user_input_rejects_non_object_handler_result(
        self,
    ) -> None:
        runtime = _DispatchRuntime()
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda _payload: []  # type: ignore[assignment]
        result = run_command_text_result(
            runtime,
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
        )

        self.assertEqual(result.tool_events[0].name, "request_user_input")
        self.assertFalse(result.tool_events[0].ok)
        self.assertEqual(
            result.assistant_text,
            "request_user_input was cancelled before receiving a response",
        )

    def test_run_command_text_result_request_user_input_normalizes_answers_to_canonical_shape(
        self,
    ) -> None:
        runtime = _DispatchRuntime()
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda _payload: {
            "answers": {
                "confirm_path": "yes",
            }
        }
        result = run_command_text_result(
            runtime,
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
        )

        response = json.loads(result.assistant_text)
        self.assertEqual(
            response["answers"]["confirm_path"],
            {"answers": ["yes"]},
        )
        self.assertTrue(result.tool_events[0].ok)

    def test_run_command_text_result_supports_background_tasks_listing(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            config=SimpleNamespace(enabled=True, provider="huey"),
            queue=SimpleNamespace(provider_label="huey-immediate"),
            list_recent=lambda limit: [
                SimpleNamespace(
                    task_id="bg_demo",
                    status=SimpleNamespace(value="completed"),
                    summary="benchmark completed",
                    artifact={
                        "report_path": "/tmp/demo/report.json",
                        "workflow_state": "recoverable",
                        "terminal_state": "orphaned",
                        "terminal_reason": "orphan_cleanup",
                        "last_wait_decision": "blocking_join",
                        "last_wait_blocked_ms": 120,
                        "last_wait_timed_out": True,
                        "step_count": 1,
                        "checkpoint_count": 2,
                        "recovery_action_count": 1,
                        "notification_state": "foreground_adopted",
                        "current_step_status": "completed",
                        "current_step_title": "benchmark subprocess",
                    },
                )
            ],
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            result = run_command_text_result(runtime, "/background_tasks --limit 5")

        self.assertIn("background_tasks=1", result.assistant_text)
        self.assertIn("bg_demo", result.assistant_text)
        self.assertIn("benchmark completed", result.assistant_text)
        self.assertIn("/tmp/demo/report.json", result.assistant_text)
        self.assertIn("workflow=recoverable", result.assistant_text)
        self.assertIn("steps=1", result.assistant_text)
        self.assertIn("checkpoints=2", result.assistant_text)
        self.assertIn("recoveries=1", result.assistant_text)
        self.assertIn("notify=foreground_adopted", result.assistant_text)
        self.assertIn("terminal_state=orphaned", result.assistant_text)
        self.assertIn("terminal=orphan_cleanup", result.assistant_text)
        self.assertIn("wait=blocking_join:120ms:timed_out", result.assistant_text)
        self.assertIn("current=completed:benchmark subprocess", result.assistant_text)

    def test_run_command_text_result_supports_unified_workflows_listing(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        runtime._delegated_agent_state_snapshot = lambda: [
            {
                "agent_id": "agent_1",
                "role": "teammate",
                "status": "completed",
                "provider_name": "glm",
                "model": "glm-5",
                "workflow_state": "completed",
                "wall_time_ms": 840,
                "terminal_state": "completed",
                "completion_state": "ready_to_adopt",
                "last_wait_decision": "status_snapshot",
                "last_wait_blocked_ms": 12,
                "delegation_mode": "background",
                "current_step_status": "completed",
                "current_step_title": "repo summary",
                "result_contract": {
                    "goal": "总结仓库入口和 provider 配置",
                    "next_action": "review_or_adopt_teammate_result",
                },
            }
        ]
        fake_adapter = SimpleNamespace(
            config=SimpleNamespace(enabled=True, provider="huey"),
            queue=SimpleNamespace(provider_label="huey-immediate"),
            list_recent=lambda limit: [
                SimpleNamespace(
                    task_id="bg_delegate_agent_1",
                    status=SimpleNamespace(value="completed"),
                    summary="mirrored teammate result",
                    artifact={
                        "workflow_state": "completed",
                        "notification_state": "ready",
                    },
                ),
                SimpleNamespace(
                    task_id="bg_bench_1",
                    status=SimpleNamespace(value="completed"),
                    summary="benchmark completed",
                    artifact={
                        "report_path": "/tmp/demo/report.json",
                        "workflow_state": "completed",
                        "wall_time_ms": 1450,
                        "terminal_state": "closed_by_request",
                        "terminal_reason": "close_requested",
                        "timeout_reason": "tool_timeout",
                        "last_wait_decision": "blocking_join",
                        "last_wait_blocked_ms": 400,
                        "notification_state": "foreground_adopted",
                        "current_step_status": "completed",
                        "current_step_title": "benchmark subprocess",
                    },
                ),
            ],
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            result = run_command_text_result(runtime, "/workflows --limit 5")

        self.assertIn("workflows=2", result.assistant_text)
        self.assertIn("delegated_workflows=1", result.assistant_text)
        self.assertIn("background_tasks=1", result.assistant_text)
        self.assertIn("mirrored_background_tasks=1", result.assistant_text)
        self.assertIn("agent_1", result.assistant_text)
        self.assertIn("completion=ready_to_adopt", result.assistant_text)
        self.assertIn("terminal_state=completed", result.assistant_text)
        self.assertIn("wall=840ms", result.assistant_text)
        self.assertIn("wait=status_snapshot:12ms", result.assistant_text)
        self.assertIn("next=review_or_adopt_teammate_result", result.assistant_text)
        self.assertIn("goal=总结仓库入口和 provider 配置", result.assistant_text)
        self.assertIn("bg_bench_1", result.assistant_text)
        self.assertIn("terminal_state=closed_by_request", result.assistant_text)
        self.assertIn("terminal=close_requested", result.assistant_text)
        self.assertIn("wall=1450ms", result.assistant_text)
        self.assertIn("timeout_reason=tool_timeout", result.assistant_text)
        self.assertIn("wait=blocking_join:400ms", result.assistant_text)
        self.assertNotIn("bg_delegate_agent_1", result.assistant_text)

    def test_run_command_text_result_supports_background_benchmark_submission(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_handle = SimpleNamespace(
            task_id="bg_benchmark_1",
            status="queued",
            job_id="job_1",
            provider="huey",
        )

        with patch(
            "cli.agent_cli.background_tasks.enqueue_background_task", return_value=fake_handle
        ) as patched_submit:
            result = run_command_text_result(
                runtime,
                "/background_benchmark --timeout-seconds 90 --scenario single_turn_headless --case openai:gpt_54",
            )

        self.assertIn("background benchmark submitted", result.assistant_text)
        self.assertIn("task_id=bg_benchmark_1", result.assistant_text)
        self.assertIn("status=queued", result.assistant_text)
        self.assertIn("provider=huey", result.assistant_text)
        patched_submit.assert_called_once()
        self.assertEqual(patched_submit.call_args.kwargs["task_type"], "benchmark")
        self.assertEqual(
            patched_submit.call_args.kwargs["payload"]["argv"],
            ["--scenario", "single_turn_headless", "--case", "openai:gpt_54"],
        )
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["timeout_seconds"], 90.0)

    def test_run_command_text_result_supports_background_smoke_submission(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_handle = SimpleNamespace(
            task_id="bg_smoke_1",
            status="queued",
            job_id="job_1",
            provider="huey",
        )

        with patch(
            "cli.agent_cli.background_tasks.enqueue_background_task", return_value=fake_handle
        ) as patched_submit:
            result = run_command_text_result(
                runtime,
                "/background_smoke multi_llm --timeout-seconds 45 --case followup_pwd",
            )

        self.assertIn("background smoke submitted", result.assistant_text)
        self.assertIn("task_id=bg_smoke_1", result.assistant_text)
        self.assertIn("kind=multi_llm", result.assistant_text)
        patched_submit.assert_called_once()
        self.assertEqual(patched_submit.call_args.kwargs["task_type"], "smoke")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["kind"], "multi_llm")
        self.assertEqual(
            patched_submit.call_args.kwargs["payload"]["argv"], ["--case", "followup_pwd"]
        )
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["timeout_seconds"], 45.0)

    def test_run_command_text_result_supports_background_teammate_submission(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_handle = SimpleNamespace(
            task_id="bg_teammate_1",
            status="queued",
            job_id="job_1",
            provider="huey",
        )

        with patch(
            "cli.agent_cli.background_tasks.enqueue_background_task", return_value=fake_handle
        ) as patched_submit:
            result = run_command_text_result(
                runtime,
                "/background_teammate 总结仓库入口 --provider glm --model glm_5 --reasoning-effort medium --timeout-seconds 30",
            )

        self.assertIn("background teammate submitted", result.assistant_text)
        self.assertIn("task_id=bg_teammate_1", result.assistant_text)
        self.assertIn("provider=glm", result.assistant_text)
        self.assertIn("model=glm_5", result.assistant_text)
        patched_submit.assert_called_once()
        self.assertEqual(patched_submit.call_args.kwargs["task_type"], "teammate")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["task"], "总结仓库入口")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["provider"], "glm")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["model"], "glm_5")
        self.assertEqual(patched_submit.call_args.kwargs["payload"]["timeout_seconds"], 30.0)

    def test_run_command_text_result_supports_background_teammate_workspace_write_approval(
        self,
    ) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")

        with patch("cli.agent_cli.background_tasks.enqueue_background_task") as patched_submit:
            result = run_command_text_result(
                runtime,
                "/background_teammate 总结仓库入口 --provider glm --model glm_5 --reasoning-effort medium --sandbox-mode workspace-write --allowed-paths src,tests --blocked-paths README.md --timeout-seconds 30",
            )

        self.assertIn("background teammate approval requested", result.assistant_text)
        self.assertIn("approval_id=approval_bg_1", result.assistant_text)
        self.assertIn("final_apply_required=true", result.assistant_text)
        self.assertIn("timeout_seconds=30.0", result.assistant_text)
        self.assertEqual(
            [event.name for event in result.tool_events], ["background_teammate_approval_requested"]
        )
        self.assertEqual(result.tool_events[0].payload["sandbox_mode"], "workspace-write")
        self.assertEqual(result.tool_events[0].payload["allowed_paths"], ["src", "tests"])
        self.assertEqual(result.tool_events[0].payload["blocked_paths"], ["README.md"])
        self.assertEqual(result.tool_events[0].payload["timeout_seconds"], 30.0)
        patched_submit.assert_not_called()

    def test_run_command_text_result_approve_uses_background_teammate_summary_text(self) -> None:
        runtime = _DispatchRuntime()

        result = run_command_text_result(runtime, "/approve approval_bg_1")

        self.assertIn("background teammate submitted", result.assistant_text)
        self.assertIn("task_id=bg_teammate_2", result.assistant_text)
        self.assertIn("final_apply_required=true", result.assistant_text)
        self.assertIn("timeout_seconds=30.0", result.assistant_text)
        self.assertEqual(
            [event.name for event in result.tool_events],
            ["approval_decision", "background_teammate_submitted"],
        )

    def test_run_command_text_result_supports_background_task_status_cancel_retry(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            get_status=lambda task_id: {
                "task_id": task_id,
                "status": "running",
                "task_type": "teammate",
                "dispatch_id": 2,
                "queue_state": "running",
                "cancel_requested": False,
                "runner_pid": 1234,
                "retry_count": 1,
                "summary": "running",
                "artifact": {
                    "snapshot_path": "/tmp/demo/task.json",
                    "provider": "glm",
                    "model": "glm_5",
                    "policy_helper_profile": "policy_helper_regression",
                    "policy_helper_helper_combo_count": 2,
                    "policy_helper_helper_combo_ids": ["glm_low_latency", "deepseek_low_latency"],
                    "policy_helper_override": {"provider": "glm", "model": "glm-5"},
                    "timeout_seconds": 30.0,
                    "timed_out": True,
                    "notification_state": "orphaned",
                    "terminal_state": "orphaned",
                    "terminal_reason": "role_override_changed",
                    "foreground_taken_over_at": "2026-04-05T10:00:06+00:00",
                    "runtime_provider_name": "openai",
                    "runtime_provider_model": "gpt-5.4",
                    "runtime_timing_summary": "total=0.40s",
                    "route_report": {
                        "provider_name": "openai",
                        "provider_model": "gpt-5.4",
                        "routes": {
                            "policy_helper": "glm | glm-5 | source=route",
                            "tool_followup": "openai | gpt-5.4 | source=main",
                        },
                    },
                    "tool_event_names": ["apply_patch", "exec_command"],
                    "modified_files": ["taskboard/export.py", "README.md"],
                    "commands": ["pytest -q tests/test_export.py", "python -m pytest -q"],
                    "test_commands": ["pytest -q tests/test_export.py", "python -m pytest -q"],
                },
            },
            cancel=lambda task_id: {
                "task_id": task_id,
                "status": "running",
                "queue_state": "running",
                "cancel_requested": True,
                "summary": "running",
            },
            retry=lambda task_id: {
                "task_id": task_id,
                "status": "queued",
                "dispatch_id": 3,
                "retry_count": 2,
                "summary": "queued for retry",
            },
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            status_result = run_command_text_result(runtime, "/background_task_status bg_demo")
            cancel_result = run_command_text_result(runtime, "/background_task_cancel bg_demo")
            retry_result = run_command_text_result(runtime, "/background_task_retry bg_demo")

        self.assertIn("background task status", status_result.assistant_text)
        self.assertIn("task_type=teammate", status_result.assistant_text)
        self.assertIn("dispatch_id=2", status_result.assistant_text)
        self.assertIn("snapshot_path=/tmp/demo/task.json", status_result.assistant_text)
        self.assertIn("timeout_seconds=30.0", status_result.assistant_text)
        self.assertIn("timed_out=true", status_result.assistant_text)
        self.assertIn("notification_state=orphaned", status_result.assistant_text)
        self.assertIn("terminal_state=orphaned", status_result.assistant_text)
        self.assertIn("terminal_reason=role_override_changed", status_result.assistant_text)
        self.assertIn(
            "foreground_taken_over_at=2026-04-05T10:00:06+00:00", status_result.assistant_text
        )
        self.assertIn("runtime_provider_name=openai", status_result.assistant_text)
        self.assertIn("runtime_provider_model=gpt-5.4", status_result.assistant_text)
        self.assertIn(
            "policy_helper_profile=policy_helper_regression", status_result.assistant_text
        )
        self.assertIn("policy_helper_helper_combo_count=2", status_result.assistant_text)
        self.assertIn(
            'policy_helper_helper_combo_ids=["glm_low_latency", "deepseek_low_latency"]',
            status_result.assistant_text,
        )
        self.assertIn(
            'policy_helper_override={"provider": "glm", "model": "glm-5"}',
            status_result.assistant_text,
        )
        self.assertIn(
            'route_report={"provider_name": "openai", "provider_model": "gpt-5.4", "routes": {"policy_helper": "glm | glm-5 | source=route", "tool_followup": "openai | gpt-5.4 | source=main"}}',
            status_result.assistant_text,
        )
        self.assertIn(
            'tool_event_names=["apply_patch", "exec_command"]', status_result.assistant_text
        )
        self.assertIn(
            'modified_files=["taskboard/export.py", "README.md"]', status_result.assistant_text
        )
        self.assertIn(
            'commands=["pytest -q tests/test_export.py", "python -m pytest -q"]',
            status_result.assistant_text,
        )
        self.assertIn(
            'test_commands=["pytest -q tests/test_export.py", "python -m pytest -q"]',
            status_result.assistant_text,
        )
        self.assertIn("background task cancel requested", cancel_result.assistant_text)
        self.assertIn("cancel_requested=true", cancel_result.assistant_text)
        self.assertIn("background task retry submitted", retry_result.assistant_text)
        self.assertIn("dispatch_id=3", retry_result.assistant_text)
        self.assertIn("retry_count=2", retry_result.assistant_text)

    def test_run_command_text_result_supports_background_worker_status(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            config=SimpleNamespace(enabled=True, provider="huey"),
            queue=SimpleNamespace(provider_label="huey"),
            worker_status=lambda: {
                "health": "healthy",
                "status": "idle",
                "mode": "loop",
                "state_path": "/tmp/demo/worker_state.json",
                "results_dir": "/tmp/demo/results",
                "db_path": "/tmp/demo/background_tasks.sqlite3",
                "cwd": "/tmp/demo",
                "huey_available": True,
                "immediate": False,
                "state_present": True,
                "worker_count": 1,
                "worker_pid": 4321,
                "max_jobs": 2,
                "last_processed_count": 1,
                "last_cleanup_count": 1,
                "last_cleanup_task_ids": ["bg_demo"],
                "started_at": "2026-04-05T10:00:00+00:00",
                "last_heartbeat_at": "2026-04-05T10:00:05+00:00",
                "last_poll_at": "2026-04-05T10:00:05+00:00",
                "last_processed_at": "2026-04-05T10:00:04+00:00",
                "last_cleanup_at": "2026-04-05T10:00:03+00:00",
                "poll_interval": 1.0,
                "heartbeat_age_seconds": 0.5,
                "stale_after_seconds": 5.0,
            },
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            result = run_command_text_result(runtime, "/background_worker_status")

        self.assertIn("background worker status", result.assistant_text)
        self.assertIn("enabled=true", result.assistant_text)
        self.assertIn("health=healthy", result.assistant_text)
        self.assertIn("status=idle", result.assistant_text)
        self.assertIn("mode=loop", result.assistant_text)
        self.assertIn("worker_pid=4321", result.assistant_text)
        self.assertIn("last_cleanup_count=1", result.assistant_text)
        self.assertIn('last_cleanup_task_ids=["bg_demo"]', result.assistant_text)
        self.assertIn("heartbeat_age_seconds=0.5", result.assistant_text)
        self.assertIn("stale_after_seconds=5.0", result.assistant_text)

    def test_run_command_text_result_supports_background_worker_run_once(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            config=SimpleNamespace(enabled=True, provider="huey"),
            queue=SimpleNamespace(provider_label="huey"),
            worker_status=lambda: {
                "health": "healthy",
                "status": "stopped",
                "state_path": "/tmp/demo/worker_state.json",
                "last_cleanup_count": 2,
            },
        )

        with (
            patch(
                "cli.agent_cli.background_tasks.build_background_task_adapter",
                return_value=fake_adapter,
            ),
            patch(
                "cli.agent_cli.background_tasks.worker_entry.run_worker_once",
                return_value=2,
            ) as patched_run_once,
        ):
            result = run_command_text_result(
                runtime,
                "/background_worker_run_once --max-jobs 2 --stale-after-seconds 45",
            )

        patched_run_once.assert_called_once_with(
            cwd=Path("/tmp/demo"),
            max_jobs=2,
            stale_after_seconds=45.0,
        )
        self.assertIn("background worker run once completed", result.assistant_text)
        self.assertIn("processed=2", result.assistant_text)
        self.assertIn("max_jobs=2", result.assistant_text)
        self.assertIn("stale_after_seconds=45.0", result.assistant_text)
        self.assertIn("last_cleanup_count=2", result.assistant_text)

    def test_run_command_text_result_supports_background_worker_start(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")

        with patch(
            "cli.agent_cli.background_tasks.worker_entry.start_worker_process",
            return_value={
                "started": True,
                "worker_pid": 8765,
                "state_path": "/tmp/demo/worker_state.json",
                "stdout_path": "/tmp/demo/worker_stdout.log",
                "stderr_path": "/tmp/demo/worker_stderr.log",
                "cwd": "/tmp/demo",
                "command": ["python", "-m", "cli.agent_cli.background_tasks.worker_entry"],
            },
        ) as patched_start:
            result = run_command_text_result(
                runtime,
                "/background_worker_start --max-jobs 3 --poll-interval 2 --stale-after-seconds 60",
            )

        patched_start.assert_called_once_with(
            cwd=Path("/tmp/demo"),
            max_jobs=3,
            poll_interval=2.0,
            stale_after_seconds=60.0,
        )
        self.assertIn("background worker started", result.assistant_text)
        self.assertIn("worker_pid=8765", result.assistant_text)
        self.assertIn("poll_interval=2.0", result.assistant_text)
        self.assertIn("stale_after_seconds=60.0", result.assistant_text)
        self.assertIn(
            'command=["python", "-m", "cli.agent_cli.background_tasks.worker_entry"]',
            result.assistant_text,
        )

    def test_run_command_text_result_supports_background_worker_stop(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")

        with patch(
            "cli.agent_cli.background_tasks.worker_entry.stop_worker_process",
            return_value={
                "stopped": True,
                "worker_pid": 8765,
                "forced": False,
                "state_path": "/tmp/demo/worker_state.json",
            },
        ) as patched_stop:
            result = run_command_text_result(runtime, "/background_worker_stop")

        patched_stop.assert_called_once_with(cwd=Path("/tmp/demo"), force=False)
        self.assertIn("background worker stopped", result.assistant_text)
        self.assertIn("worker_pid=8765", result.assistant_text)
        self.assertIn("forced=false", result.assistant_text)

    def test_run_command_text_result_background_worker_stop_treats_not_running_as_stopped(
        self,
    ) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")

        with patch(
            "cli.agent_cli.background_tasks.worker_entry.stop_worker_process",
            return_value={
                "stopped": True,
                "reason": "worker_not_running",
                "worker_pid": 8765,
                "forced": True,
                "state_path": "/tmp/demo/worker_state.json",
            },
        ) as patched_stop:
            result = run_command_text_result(runtime, "/background_worker_stop --force")

        patched_stop.assert_called_once_with(cwd=Path("/tmp/demo"), force=True)
        self.assertIn("background worker stopped", result.assistant_text)
        self.assertIn("reason=worker_not_running", result.assistant_text)
        self.assertIn("forced=true", result.assistant_text)

    def test_run_command_text_result_supports_background_task_apply_reject(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            apply_staged_changes=lambda task_id: {
                "task_id": task_id,
                "status": "completed",
                "summary": "background teammate changes applied to live workspace",
                "artifact": {
                    "staged_workspace": True,
                    "final_apply_state": "applied",
                    "applied_files": ["src/demo.py"],
                },
            },
            reject_staged_changes=lambda task_id: {
                "task_id": task_id,
                "status": "completed",
                "summary": "background teammate staged changes rejected",
                "artifact": {
                    "staged_workspace": True,
                    "final_apply_state": "rejected",
                },
            },
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            apply_result = run_command_text_result(runtime, "/background_task_apply bg_demo")
            reject_result = run_command_text_result(runtime, "/background_task_reject bg_demo")

        self.assertIn("background task changes applied", apply_result.assistant_text)
        self.assertIn("final_apply_state=applied", apply_result.assistant_text)
        self.assertIn('applied_files=["src/demo.py"]', apply_result.assistant_text)
        self.assertIn("background task staged changes rejected", reject_result.assistant_text)
        self.assertIn("final_apply_state=rejected", reject_result.assistant_text)

    def test_run_command_text_result_background_task_status_shows_review_fields(self) -> None:
        runtime = _DispatchRuntime()
        runtime.cwd = Path("/tmp/demo")
        fake_adapter = SimpleNamespace(
            get_status=lambda task_id: {
                "task_id": task_id,
                "status": "completed",
                "task_type": "teammate",
                "dispatch_id": 4,
                "queue_state": "completed",
                "cancel_requested": False,
                "runner_pid": 0,
                "retry_count": 0,
                "summary": "teammate staged changes ready for final apply",
                "artifact": {
                    "review_path": "/tmp/demo/review.json",
                    "live_cwd": "/tmp/demo/repo",
                    "stage_cwd": "/tmp/demo/results/bg_workspace",
                    "wall_time_ms": 2500,
                    "current_step_wall_time_ms": 1800,
                    "timeout_budget_seconds": 30,
                    "timeout_hit": True,
                    "timeout_reason": "model_timeout",
                    "timeout_source": "planner",
                    "last_wait_decision": "blocking_join",
                    "last_wait_reason": "wait_for_child_result",
                    "last_wait_at": "2026-04-05T10:00:06+00:00",
                    "last_wait_blocked_ms": 320,
                    "last_wait_timed_out": True,
                    "staged_workspace": True,
                    "final_apply_pending": True,
                    "final_apply_state": "pending",
                    "allowed_paths": ["src"],
                    "blocked_paths": [".git"],
                    "review_commands": [
                        "/background_task_apply bg_demo",
                        "/background_task_reject bg_demo",
                    ],
                    "bootstrap_diagnostics": {
                        "cwd_exists": True,
                        "is_dir": True,
                        "git_root_detected": False,
                        "git_dir_present": False,
                        "dependency_files": ["pyproject.toml"],
                        "bootstrap_warnings": ["git root not detected"],
                        "bootstrap_error_category": "",
                    },
                },
            },
        )

        with patch(
            "cli.agent_cli.background_tasks.build_background_task_adapter",
            return_value=fake_adapter,
        ):
            result = run_command_text_result(runtime, "/background_task_status bg_demo")

        self.assertIn("review_path=/tmp/demo/review.json", result.assistant_text)
        self.assertIn("wall_time_ms=2500", result.assistant_text)
        self.assertIn("current_step_wall_time_ms=1800", result.assistant_text)
        self.assertIn("timeout_budget_seconds=30", result.assistant_text)
        self.assertIn("timeout_hit=true", result.assistant_text)
        self.assertIn("timeout_reason=model_timeout", result.assistant_text)
        self.assertIn("timeout_source=planner", result.assistant_text)
        self.assertIn("last_wait_decision=blocking_join", result.assistant_text)
        self.assertIn("last_wait_reason=wait_for_child_result", result.assistant_text)
        self.assertIn("last_wait_at=2026-04-05T10:00:06+00:00", result.assistant_text)
        self.assertIn("last_wait_blocked_ms=320", result.assistant_text)
        self.assertIn("last_wait_timed_out=true", result.assistant_text)
        self.assertIn("staged_workspace=true", result.assistant_text)
        self.assertIn("final_apply_pending=true", result.assistant_text)
        self.assertIn("final_apply_state=pending", result.assistant_text)
        self.assertIn('allowed_paths=["src"]', result.assistant_text)
        self.assertIn('blocked_paths=[".git"]', result.assistant_text)
        self.assertIn(
            'review_commands=["/background_task_apply bg_demo", "/background_task_reject bg_demo"]',
            result.assistant_text,
        )
        self.assertIn("cwd_exists=true", result.assistant_text)
        self.assertIn("is_dir=true", result.assistant_text)
        self.assertIn("git_root_detected=false", result.assistant_text)
        self.assertIn('dependency_files=["pyproject.toml"]', result.assistant_text)
        self.assertIn('bootstrap_warnings=["git root not detected"]', result.assistant_text)

    def test_run_command_text_result_supports_spawn_agent(self) -> None:
        runtime = _DispatchRuntime()
        runtime.spawn_agent_result = lambda **kwargs: CommandExecutionResult(
            assistant_text="delegated answer",
            tool_events=[
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawn_agent completed",
                    payload={
                        "ok": True,
                        "role": kwargs["role"],
                        "task": kwargs["task"],
                        "model": "glm-5",
                        "provider_name": "glm",
                        "text": "delegated answer",
                    },
                )
            ],
            item_events=[],
        )
        result = run_command_text_result(
            runtime,
            '/spawn_agent \'{"task":"inspect","role":"teammate","model":"inherit","provider":"glm","reasoning_effort":"medium","timeout":30}\'',
        )

        self.assertEqual(result.assistant_text, "delegated answer")
        self.assertEqual(result.tool_events[0].name, "spawn_agent")
        self.assertEqual(result.tool_events[0].payload["role"], "teammate")
        self.assertEqual(result.tool_events[0].payload["task"], "inspect")

    def test_run_command_text_result_supports_async_spawn_agent(self) -> None:
        runtime = _DispatchRuntime()
        runtime.spawn_agent_result = lambda **kwargs: CommandExecutionResult(
            assistant_text="delegated agent agent_1 started",
            tool_events=[
                ToolEvent(
                    name="spawn_agent",
                    ok=True,
                    summary="spawn_agent started",
                    payload={
                        "ok": True,
                        "agent_id": "agent_1",
                        "status": "queued",
                        "async": kwargs["async_mode"],
                    },
                )
            ],
            item_events=[],
        )
        result = run_command_text_result(
            runtime,
            '/spawn_agent \'{"task":"inspect","role":"subagent","async":true}\'',
        )

        self.assertEqual(result.assistant_text, "delegated agent agent_1 started")
        self.assertEqual(result.tool_events[0].payload["agent_id"], "agent_1")
        self.assertTrue(result.tool_events[0].payload["async"])

    def test_run_command_text_result_passes_codex_collab_flags_for_id_style_tools(self) -> None:
        runtime = _DispatchRuntime()
        captured: dict[str, object] = {}

        def _spawn_agent_result(**kwargs):
            captured["spawn"] = dict(kwargs)
            return _structured_tool_result(
                "spawn_agent", "spawn_agent started", payload={"ok": True}, arguments=kwargs
            )

        def _send_input_result(target, **kwargs):
            captured["send"] = {"target": target, **kwargs}
            return _structured_tool_result(
                "send_input",
                "send_input accepted",
                payload={"target": target},
                arguments={"id": target},
            )

        def _resume_agent_result(target, **kwargs):
            captured["resume"] = {"target": target, **kwargs}
            return _structured_tool_result(
                "resume_agent",
                "resume_agent completed",
                payload={"target": target},
                arguments={"id": target},
            )

        def _close_agent_result(target, **kwargs):
            captured["close"] = {"target": target, **kwargs}
            return _structured_tool_result(
                "close_agent",
                "close_agent completed",
                payload={"target": target},
                arguments={"id": target},
            )

        runtime.spawn_agent_result = _spawn_agent_result
        runtime.send_input_result = _send_input_result
        runtime.resume_agent_result = _resume_agent_result
        runtime.close_agent_result = _close_agent_result

        run_command_text_result(
            runtime,
            '/spawn_agent \'{"message":"inspect","agent_type":"subagent"}\'',
        )
        run_command_text_result(
            runtime,
            '/send_input \'{"id":"agent_1","message":"follow up"}\'',
        )
        run_command_text_result(
            runtime,
            '/resume_agent \'{"id":"agent_1"}\'',
        )
        run_command_text_result(
            runtime,
            '/close_agent \'{"id":"agent_1"}\'',
        )

        self.assertTrue(captured["spawn"]["codex_collab_payload"])
        self.assertIsNone(captured["spawn"]["async_mode"])
        self.assertTrue(captured["send"]["codex_style"])
        self.assertTrue(captured["resume"]["codex_style"])
        self.assertTrue(captured["close"]["codex_style"])

    def test_run_command_text_result_passes_delegation_metadata(self) -> None:
        runtime = _DispatchRuntime()
        captured: dict[str, object] = {}

        def _spawn_agent_result(**kwargs):
            captured.update(kwargs)
            return _structured_tool_result(
                "spawn_agent",
                "spawn_agent completed",
                payload={
                    "role": kwargs["role"],
                    "task": kwargs["task"],
                    "delegation_reason": kwargs.get("reason"),
                    "delegation_mode": kwargs.get("mode"),
                    "wait_required": kwargs.get("wait_required"),
                    "task_shape": kwargs.get("task_shape"),
                },
                arguments=kwargs,
            )

        runtime.spawn_agent_result = _spawn_agent_result
        result = run_command_text_result(
            runtime,
            '/spawn_agent \'{"task":"inspect","role":"subagent","async":true,"reason":"research_side_task","mode":"background","wait_required":false,"task_shape":"read_only"}\'',
        )

        self.assertEqual(result.tool_events[0].payload["delegation_reason"], "research_side_task")
        self.assertEqual(result.tool_events[0].payload["delegation_mode"], "background")
        self.assertFalse(result.tool_events[0].payload["wait_required"])
        self.assertEqual(result.tool_events[0].payload["task_shape"], "read_only")
        self.assertEqual(captured["reason"], "research_side_task")
        self.assertEqual(captured["mode"], "background")
        self.assertEqual(captured["task_shape"], "read_only")
        self.assertEqual(captured["wait_required"], False)

    def test_run_command_text_result_keeps_async_unspecified_for_teammate_defaults(self) -> None:
        runtime = _DispatchRuntime()
        captured: dict[str, object] = {}

        def _spawn_agent_result(**kwargs):
            captured.update(kwargs)
            return _structured_tool_result(
                "spawn_agent",
                "spawn_agent started",
                payload={
                    "role": kwargs["role"],
                    "task": kwargs["task"],
                    "async": True,
                    "delegation_mode": "background",
                },
                arguments=kwargs,
            )

        runtime.spawn_agent_result = _spawn_agent_result
        result = run_command_text_result(
            runtime,
            '/spawn_agent \'{"task":"inspect","role":"teammate"}\'',
        )

        self.assertEqual(result.tool_events[0].payload["role"], "teammate")
        self.assertTrue(result.tool_events[0].payload["async"])
        self.assertEqual(result.tool_events[0].payload["delegation_mode"], "background")
        self.assertIsNone(captured["async_mode"])

    def test_run_command_text_result_supports_send_wait_resume_and_close_agent(self) -> None:
        runtime = _DispatchRuntime()
        runtime.send_input_result = lambda target, **kwargs: _structured_tool_result(
            "send_input",
            "send_input accepted",
            payload={
                "target": target,
                "message": kwargs["message"],
                "interrupt_requested": kwargs["interrupt"],
            },
            arguments={
                "target": target,
                "message": kwargs["message"],
                "interrupt": kwargs["interrupt"],
            },
        )
        runtime.wait_agent_result = lambda target, **kwargs: _structured_tool_result(
            "wait_agent",
            "delegated answer",
            payload={
                "target": target,
                "status": "completed",
                "text": "delegated answer",
                "timeout_ms": kwargs.get("timeout_ms"),
            },
            arguments={"target": target, "timeout_ms": kwargs.get("timeout_ms")},
        )
        runtime.resume_agent_result = lambda target, **kwargs: _structured_tool_result(
            "resume_agent",
            "resume_agent completed",
            payload={"target": target, "status": "completed"},
            arguments={"target": target},
        )
        runtime.close_agent_result = lambda target, **kwargs: _structured_tool_result(
            "close_agent",
            "close_agent completed",
            payload={"target": target, "status": "closed"},
            arguments={"target": target},
        )

        send_result = run_command_text_result(
            runtime, "/send_input agent_1 'follow up' --interrupt"
        )
        wait_result = run_command_text_result(runtime, "/wait_agent agent_1 --timeout-ms 250")
        resume_result = run_command_text_result(runtime, "/resume_agent agent_1")
        close_result = run_command_text_result(runtime, "/close_agent agent_1")

        self.assertEqual(send_result.tool_events[0].name, "send_input")
        self.assertEqual(send_result.tool_events[0].payload["message"], "follow up")
        self.assertTrue(send_result.tool_events[0].payload["interrupt_requested"])
        self.assertEqual(wait_result.tool_events[0].name, "wait_agent")
        self.assertEqual(wait_result.assistant_text, "delegated answer")
        self.assertEqual(wait_result.tool_events[0].payload["timeout_ms"], "250")
        self.assertEqual(resume_result.tool_events[0].name, "resume_agent")
        self.assertEqual(close_result.tool_events[0].name, "close_agent")

    def test_run_command_text_result_supports_agent_workflow_and_recover_agent(self) -> None:
        runtime = _DispatchRuntime()
        runtime.agent_workflow_result = lambda target, **kwargs: _structured_tool_result(
            "agent_workflow",
            "workflow_state=recoverable",
            payload={
                "target": target,
                "workflow_state": "recoverable",
                "step_count": 2,
                "checkpoint_count": 5,
                "steps": [{"step_id": "step_2", "status": "failed"}],
            },
            arguments={"target": target, **kwargs},
        )
        runtime.recover_agent_result = lambda target, **kwargs: _structured_tool_result(
            "recover_agent",
            "recover_agent accepted",
            payload={
                "target": target,
                "recovery_action": kwargs.get("action") or "retry_step",
                "recovered_step_id": kwargs.get("step_id") or "step_2",
            },
            arguments={"target": target, **kwargs},
        )

        workflow_result = run_command_text_result(
            runtime, "/agent_workflow agent_1 --steps 3 --checkpoints 4"
        )
        recover_result = run_command_text_result(
            runtime, "/recover_agent agent_1 --action retry_step --step-id step_2"
        )

        self.assertEqual(workflow_result.tool_events[0].name, "agent_workflow")
        self.assertEqual(workflow_result.tool_events[0].payload["workflow_state"], "recoverable")
        self.assertEqual(workflow_result.tool_events[0].payload["step_count"], 2)
        self.assertEqual(recover_result.tool_events[0].name, "recover_agent")
        self.assertEqual(recover_result.tool_events[0].payload["recovery_action"], "retry_step")
        self.assertEqual(recover_result.tool_events[0].payload["recovered_step_id"], "step_2")

    def test_run_command_text_result_supports_wait_agent_reason(self) -> None:
        runtime = _DispatchRuntime()
        captured: dict[str, object] = {}

        def _wait_agent_result(target, **kwargs):
            captured["target"] = target
            captured.update(kwargs)
            return _structured_tool_result(
                "wait_agent",
                "delegated answer",
                payload={
                    "target": target,
                    "status": "completed",
                    "text": "delegated answer",
                    "wait_reason": kwargs.get("reason"),
                    "wait_required": kwargs.get("wait_required"),
                },
                arguments={"target": target, **kwargs},
            )

        runtime.wait_agent_result = _wait_agent_result
        result = run_command_text_result(
            runtime,
            "/wait_agent agent_1 --timeout-ms 250 --reason wait_for_child_result",
        )

        self.assertEqual(result.tool_events[0].payload["wait_reason"], "wait_for_child_result")
        self.assertTrue(result.tool_events[0].payload["wait_required"])
        self.assertEqual(captured["reason"], "wait_for_child_result")

    def test_run_command_text_result_supports_exec_command(self) -> None:
        runtime = _DispatchRuntime()
        runtime._runtime_policy["approval_policy"] = "never"
        result = run_command_text_result(
            runtime,
            "/exec_command 'python -V' --workdir cli --yield-time-ms 250 --tty",
        )

        self.assertEqual(result.tool_events[0].name, "exec_command")
        self.assertNotIn("session_id", result.tool_events[0].payload)
        self.assertNotIn("process_id", result.tool_events[0].payload)
        self.assertNotIn("Process running with session ID", result.assistant_text)
        self.assertIn("Python 3.12.0", result.assistant_text)
        self.assertEqual(result.item_events[0]["item"]["type"], "command_execution")
        self.assertEqual(
            [event["type"] for event in result.item_events], ["item.started", "item.completed"]
        )

    def test_run_command_text_result_exec_command_keeps_session_for_running_process(self) -> None:
        class _RunningDispatchRuntime(_DispatchRuntime):
            def write_shell_stdin_result(
                self,
                session_id,
                chars,
                *,
                yield_time_ms=None,
                allow_extended_empty_poll=False,
                on_activity=None,
            ):
                del allow_extended_empty_poll
                del on_activity
                payload = {
                    "session_id": session_id,
                    "call_id": "call_1",
                    "process_id": "proc_1",
                    "command": "python -i",
                    "yield_time_ms": yield_time_ms,
                    "stdout": ">>> ",
                    "stderr": "",
                    "aggregated_output": ">>> ",
                    "status": "noop",
                    "ok": True,
                    "duration_ms": 12,
                }
                return CommandExecutionResult(
                    assistant_text="shell",
                    tool_events=[
                        ToolEvent(name="shell", ok=True, summary="shell running", payload=payload)
                    ],
                    item_events=[],
                )

        runtime = _RunningDispatchRuntime()
        runtime._runtime_policy["approval_policy"] = "never"
        result = run_command_text_result(
            runtime,
            "/exec_command 'python -i' --yield-time-ms 250 --tty",
        )

        self.assertEqual(result.tool_events[0].name, "exec_command")
        self.assertEqual(result.tool_events[0].payload["session_id"], "session_1")
        self.assertEqual(result.tool_events[0].payload["process_id"], "proc_1")
        self.assertEqual(result.tool_events[0].summary, "exec_command running session_1")
        self.assertNotIn("completion_state", result.tool_events[0].payload)
        self.assertIn("Process running with session ID session_1", result.assistant_text)

    def test_run_command_text_result_normalizes_exec_command_shell_override(self) -> None:
        runtime = _DispatchRuntime()
        runtime._runtime_policy["approval_policy"] = "never"
        result = run_command_text_result(
            runtime,
            "/exec_command 'python -V' --shell posix --yield-time-ms 250",
        )

        expected_shell = current_host_platform().normalize_shell_override("posix")
        self.assertEqual(result.tool_events[0].payload["shell"], expected_shell)

    def test_run_command_text_result_normalizes_leading_cd_into_workdir(self) -> None:
        runtime = _DispatchRuntime()
        runtime._runtime_policy["approval_policy"] = "never"
        result = run_command_text_result(
            runtime,
            "/exec_command 'cd cli && python -V' --yield-time-ms 250",
        )

        payload = result.tool_events[0].payload
        self.assertEqual(payload["command"], "python -V")
        self.assertEqual(payload["workdir"], "cli")
        self.assertNotIn("cd cli &&", payload["command"])
        self.assertEqual(result.item_events[0]["item"]["command"], "python -V")

    def test_run_command_text_result_normalizes_exec_command_shell_override_for_approval(
        self,
    ) -> None:
        runtime = _DispatchRuntime()
        result = run_command_text_result(
            runtime,
            "/exec_command 'python -V' --shell posix --yield-time-ms 250",
        )

        expected_shell = current_host_platform().normalize_shell_override("posix")
        self.assertEqual(result.tool_events[0].name, "shell_approval_requested")
        self.assertEqual(result.tool_events[0].payload["shell"], expected_shell)
        self.assertEqual(result.tool_events[0].payload["exec_mode"], "exec_once")

    def test_run_command_text_result_supports_write_stdin(self) -> None:
        runtime = _DispatchRuntime()
        result = run_command_text_result(
            runtime,
            "/write_stdin session_1 'ping\\n' --yield-time-ms 250",
        )

        self.assertEqual(result.tool_events[0].name, "write_stdin")
        self.assertEqual(result.tool_events[0].payload["session_id"], "session_1")
        self.assertIn("Python 3.12.0", result.assistant_text)
        self.assertEqual(result.item_events[0]["item"]["type"], "command_execution")

        snapshot = snapshot_thread_state_payload(
            provider_status={"provider_name": "deepseek"},
            runtime_policy_status={"approval_policy": "never", "network_access": "disabled"},
            approval_status={"pending_approvals": "2", "latest_pending_approval_id": "approval_2"},
            selected_conversation="demo",
            pending_send_text="draft",
            send_ready=True,
            thread_id="t1",
            thread_name="morning",
        )
        self.assertEqual(snapshot["send_ready"], "true")
        self.assertEqual(snapshot["pending_send_text"], "draft")
        self.assertEqual(snapshot["approval_policy"], "never")
        self.assertEqual(snapshot["pending_approvals"], "2")

    def test_execute_agent_intent_result_skips_command_text_when_turn_events_already_include_tool_items(
        self,
    ) -> None:
        runtime = SimpleNamespace()
        command_text_called = {"count": 0}

        def _run_command_text_result(command_text: str):
            command_text_called["count"] += 1
            return CommandExecutionResult(
                assistant_text="ignored",
                tool_events=[],
                item_events=[],
                turn_events=[],
            )

        runtime._run_command_text_result = _run_command_text_result

        intent = AgentIntent(
            assistant_text="",
            commentary_text="",
            command_text="/shell echo hi",
            status_hint="tool",
            tool_events=[],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_command",
                        "type": "command_execution",
                        "command": "/shell echo hi",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
        )

        result = execute_agent_intent_result(runtime, intent)

        self.assertEqual(command_text_called["count"], 0)
        self.assertEqual(result.turn_events[0]["type"], "turn.started")
        self.assertEqual(result.turn_events[-1]["type"], "turn.completed")

    def test_execute_agent_intent_result_preserves_preamble_as_commentary_and_uses_command_result_as_final_text(
        self,
    ) -> None:
        runtime = SimpleNamespace()

        def _run_command_text_result(command_text: str):
            self.assertEqual(command_text, "/file_list")
            tool_event = ToolEvent(
                name="file_list",
                ok=True,
                summary="files=2",
                payload={"path": ".", "count": 2},
            )
            item_events = generic_tool_call_item_events(
                tool_name="file_list",
                arguments={"path": "."},
                ok=True,
                summary="files=2",
                structured_content={"path": ".", "count": 2},
            )
            return CommandExecutionResult(
                assistant_text="README.md\nsrc/",
                tool_events=[tool_event],
                item_events=item_events,
                turn_events=[],
            )

        runtime._run_command_text_result = _run_command_text_result

        intent = AgentIntent(
            assistant_text="识别为列出当前工作区文件，准备读取文件列表。",
            commentary_text="",
            command_text="/file_list",
            status_hint="tool",
            tool_events=[],
            turn_events=[],
        )

        result = execute_agent_intent_result(runtime, intent)

        self.assertEqual(result.assistant_text, "README.md\nsrc/")
        agent_messages = [
            event["item"]["text"]
            for event in result.turn_events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "agent_message"
        ]
        self.assertEqual(
            agent_messages,
            [
                "识别为列出当前工作区文件，准备读取文件列表。",
                "README.md\nsrc/",
            ],
        )
        tool_indices = [
            index
            for index, event in enumerate(result.turn_events)
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "mcp_tool_call"
        ]
        self.assertTrue(tool_indices)
        self.assertLess(
            next(
                index
                for index, event in enumerate(result.turn_events)
                if event.get("type") == "item.completed"
                and isinstance(event.get("item"), dict)
                and event["item"].get("type") == "agent_message"
                and event["item"].get("text") == "识别为列出当前工作区文件，准备读取文件列表。"
            ),
            tool_indices[0],
        )

    def test_execute_agent_intent_result_preserves_final_agent_message_when_failed_tool_turn_already_has_answer(
        self,
    ) -> None:
        runtime = SimpleNamespace()
        intent = AgentIntent(
            assistant_text="结果如下：命令失败。",
            commentary_text="",
            command_text=None,
            status_hint="tool",
            tool_events=[
                ToolEvent(
                    name="exec_command",
                    ok=False,
                    summary="exec_command exited",
                    payload={
                        "stderr": "ls: cannot access '/missing': No such file or directory\n",
                        "aggregated_output": "ls: cannot access '/missing': No such file or directory\n",
                        "exit_code": 2,
                    },
                )
            ],
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "我先按你的要求跑一下 `ls /missing`，然后把结果直接告诉你。",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "ls /missing",
                        "aggregated_output": "ls: cannot access '/missing': No such file or directory",
                        "exit_code": 2,
                        "status": "failed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "agent_message",
                        "text": "结果如下：命令失败。",
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        result = execute_agent_intent_result(runtime, intent)

        self.assertEqual(result.assistant_text, "结果如下：命令失败。")

    def test_execute_agent_intent_result_uses_exec_output_fallback_when_tool_turn_has_no_final_answer(
        self,
    ) -> None:
        runtime = SimpleNamespace()
        intent = AgentIntent(
            assistant_text="",
            commentary_text="",
            command_text=None,
            status_hint="tool",
            tool_events=[
                ToolEvent(
                    name="exec_command",
                    ok=True,
                    summary="exec_command exited",
                    payload={
                        "stdout": "/home/lyc/project/AgentHub\n",
                        "aggregated_output": "/home/lyc/project/AgentHub\n",
                        "function_call_output": (
                            "Process exited with code 0\n"
                            "Output:\n"
                            "/home/lyc/project/AgentHub\n"
                        ),
                        "exit_code": 0,
                    },
                )
            ],
            turn_events=[],
        )

        result = execute_agent_intent_result(runtime, intent)

        self.assertEqual(result.assistant_text, "/home/lyc/project/AgentHub")
        self.assertNotIn("exec_command exited", result.assistant_text)

    def test_run_command_text_dispatch_variants(self) -> None:
        class _DispatchTools:
            def __init__(self, plugin_result):
                self._plugin_result = plugin_result

            def run_plugin_command(self, name, arg_text, runtime):
                return self._plugin_result

            def capabilities(self):
                return {"ok": True, "tools": [{"name": "shell", "description": "shell"}]}

            def file_list(self, *, path=None, limit=50):
                return ToolEvent(
                    name="file_list",
                    ok=True,
                    summary="files=2",
                    payload={
                        "path": path or ".",
                        "count": 2,
                        "files": [
                            {"path": "README.md", "size": 10},
                            {"path": "src/app.py", "size": 20},
                        ],
                    },
                )

            def file_search(self, query, *, path=None, limit=20):
                return ToolEvent(
                    name="file_search",
                    ok=True,
                    summary="file matches=1",
                    payload={
                        "query": query,
                        "path": path or ".",
                        "count": 1,
                        "file_count": 1,
                        "matches": [{"path": "src/app.py", "line": 8, "text": "TODO hello"}],
                    },
                )

            def grep_files(self, pattern, *, include=None, path=None, limit=100, **kwargs):
                return ToolEvent(
                    name="grep_files",
                    ok=True,
                    summary="paths=1",
                    payload={
                        "pattern": pattern,
                        "include": include,
                        "path": path or ".",
                        "count": 1,
                        "paths": ["src/app.py"],
                        "text": "src/app.py",
                        **({key: value for key, value in kwargs.items() if value is not None}),
                    },
                )

            def glob_files(self, pattern, *, path=None, limit=100):
                return ToolEvent(
                    name="glob_files",
                    ok=True,
                    summary="files=1",
                    payload={
                        "pattern": pattern,
                        "path": path or ".",
                        "count": 1,
                        "paths": ["docs/guide.md"],
                        "text": "docs/guide.md",
                    },
                )

            def list_dir(self, *, dir_path=None, offset=1, limit=25, depth=2):
                return ToolEvent(
                    name="list_dir",
                    ok=True,
                    summary="entries=2",
                    payload={
                        "dir_path": dir_path or ".",
                        "offset": offset,
                        "limit": limit,
                        "depth": depth,
                        "count": 2,
                        "returned_count": 2,
                        "entries": [
                            {"index": 1, "kind": "file", "path": "README.md"},
                            {"index": 2, "kind": "dir", "path": "src"},
                        ],
                        "text": "E1: [file] README.md\nE2: [dir] src",
                    },
                )

            def file_read(self, path, *, offset=None, limit=None, max_chars=None):
                payload = {
                    "path": path,
                    "char_count": 20,
                    "line_count": 2,
                    "truncated": False,
                    "text": "L1: hello",
                    "excerpt_lines": [{"line": 1, "text": "hello"}],
                }
                if offset is not None:
                    payload["offset"] = offset
                if limit is not None:
                    payload["limit"] = limit
                if max_chars is not None:
                    payload["max_chars"] = max_chars
                return ToolEvent(
                    name="file_read",
                    ok=True,
                    summary="file loaded",
                    payload=payload,
                )

            def read_file(self, file_path, *, offset=None, limit=None, mode=None, indentation=None):
                payload = {
                    "file_path": file_path,
                    "path": file_path,
                    "line_count": 2,
                    "text": "L1: hello",
                }
                if offset is not None:
                    payload["offset"] = offset
                if limit is not None:
                    payload["limit"] = limit
                if mode is not None:
                    payload["mode"] = mode
                if indentation is not None:
                    payload["indentation"] = indentation
                return ToolEvent(
                    name="read_file",
                    ok=True,
                    summary="file loaded",
                    payload=payload,
                )

            def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
                return ToolEvent(
                    name="web_search",
                    ok=True,
                    summary=f"web results={limit}",
                    payload={
                        "query": query,
                        "count": limit,
                        "results": [],
                        "domains": domains or [],
                        "recency_days": recency_days,
                        "market": market,
                    },
                )

            def view_image(self, path):
                return ToolEvent(
                    name="view_image",
                    ok=True,
                    summary="image artifact ready: sample.png",
                    payload={
                        "ok": True,
                        "path": path,
                        "requested_path": path,
                        "image_artifacts": [
                            {
                                "path": path,
                                "mime_type": "image/png",
                                "size_bytes": 16,
                                "width": 1,
                                "height": 1,
                                "image_url": "data:image/png;base64,AAAA",
                            }
                        ],
                    },
                )

            def web_fetch(self, url, *, max_chars=12000):
                return ToolEvent(
                    name="web_fetch",
                    ok=True,
                    summary="web page loaded",
                    payload={
                        "url": url,
                        "final_url": url,
                        "source_domain": "platform.openai.com",
                        "title": "OpenAI API docs",
                        "text": "The OpenAI API provides access to models.",
                        "max_chars": max_chars,
                    },
                )

            def open(self, ref, *, line=1):
                return ToolEvent(
                    name="open",
                    ok=True,
                    summary="page opened",
                    payload={
                        "ref_id": "page_1",
                        "url": ref,
                        "final_url": ref,
                        "source_domain": "platform.openai.com",
                        "title": "OpenAI API docs",
                        "line_count": 3,
                        "link_count": 1,
                        "links": [
                            {
                                "id": 1,
                                "text": "Quickstart",
                                "url": "https://platform.openai.com/docs/quickstart",
                            }
                        ],
                        "excerpt_lines": [{"line": 1, "text": "Overview"}],
                    },
                )

            def click(self, ref_id, *, id):
                return ToolEvent(
                    name="click",
                    ok=True,
                    summary="link opened",
                    payload={
                        "source_ref_id": ref_id,
                        "clicked_link_id": id,
                        "clicked_link_text": "Quickstart",
                        "ref_id": "page_2",
                        "url": "https://platform.openai.com/docs/quickstart",
                        "final_url": "https://platform.openai.com/docs/quickstart",
                        "title": "Quickstart",
                        "excerpt_lines": [{"line": 1, "text": "Install the SDK first."}],
                    },
                )

            def find(self, ref_id, *, pattern):
                return ToolEvent(
                    name="find",
                    ok=True,
                    summary="matches=1",
                    payload={
                        "ref_id": ref_id,
                        "pattern": pattern,
                        "count": 1,
                        "matches": [
                            {"line": 2, "text": "Use the Responses API for text and tool calling."}
                        ],
                    },
                )

            def browser(self, action, **kwargs):
                return ToolEvent(
                    name="browser_action",
                    ok=True,
                    summary=f"browser {action} ok",
                    payload={
                        "action": action,
                        **kwargs,
                    },
                )

        class _DispatchAgent:
            @staticmethod
            def provider_status():
                return {"provider_ready": "true", "provider_model": "demo"}

            @staticmethod
            def available_providers():
                return []

            @staticmethod
            def available_models(provider_name=None):
                return []

        class _DispatchRuntime:
            def __init__(self, *, plugin_result=None, interrupted=False):
                self.tools = _DispatchTools(plugin_result)
                self.agent = _DispatchAgent()
                self.history = []
                self._interrupted = interrupted
                self._runtime_policy = {
                    "approval_policy": "on-request",
                    "sandbox_mode": "workspace-write",
                    "web_search_mode": "live",
                    "network_access": "enabled",
                }

            def _is_interrupt_requested(self):
                return self._interrupted

            def _interrupt_tuple(self):
                return ("interrupted", [])

            @staticmethod
            def _single_event(prefix, event):
                return (prefix, [event])

            @staticmethod
            def _parse_args(arg_text):
                return parse_args(arg_text)

            def runtime_policy_status(self):
                return dict(self._runtime_policy)

            def configure_runtime_policy(
                self,
                *,
                approval_policy=None,
                sandbox_mode=None,
                web_search_mode=None,
                network_access_enabled=None,
            ):
                if approval_policy is not None:
                    self._runtime_policy["approval_policy"] = str(approval_policy)
                if sandbox_mode is not None:
                    self._runtime_policy["sandbox_mode"] = str(sandbox_mode)
                if web_search_mode is not None:
                    self._runtime_policy["web_search_mode"] = str(web_search_mode)
                if network_access_enabled is not None:
                    enabled = bool(network_access_enabled)
                    self._runtime_policy["network_access"] = "enabled" if enabled else "disabled"
                return self.runtime_policy_status()

            def web_access_allowed(self):
                return self._runtime_policy["network_access"] == "enabled"

            def web_search_enabled(self):
                return (
                    self.web_access_allowed()
                    and self._runtime_policy["web_search_mode"] != "disabled"
                )

            def patch_requires_approval(self):
                return self._runtime_policy["approval_policy"] != "never"

            def workspace_is_read_only(self):
                return self._runtime_policy["sandbox_mode"] == "read-only"

            def request_patch_approval(self, patch_text):
                return ToolEvent(
                    name="patch_approval_requested",
                    ok=True,
                    summary="patch approval requested approval_1",
                    payload={
                        "approval_id": "approval_1",
                        "file_count": 1,
                        "changes": [{"path": "demo.txt", "change_type": "add"}],
                    },
                )

            def approvals_event(self, *, limit=20, status=None):
                return ToolEvent(
                    name="approval_list",
                    ok=True,
                    summary="approvals=1",
                    payload={
                        "count": 1,
                        "status": status,
                        "approvals": [
                            {
                                "approval_id": "approval_1",
                                "status": "pending",
                                "action_type": "apply_patch",
                                "summary": "Approve workspace patch",
                            }
                        ],
                    },
                )

            def request_shell_approval(self, command, *, requested_by="cli", timeout_sec=60):
                return ToolEvent(
                    name="shell_approval_requested",
                    ok=True,
                    summary="shell approval requested approval_2",
                    payload={
                        "approval_id": "approval_2",
                        "status": "pending",
                        "summary": "Approve shell command",
                        "reason": "user approval required before running local shell command",
                        "command": command,
                        "timeout_sec": timeout_sec,
                    },
                )

            def decide_approval(
                self, approval_id, *, approved=None, decision=None, decided_by, decision_note=""
            ):
                resolved_decision = str(decision or ("accept" if approved else "decline"))
                approved = resolved_decision in {
                    "accept",
                    "accept_for_session",
                    "accept_with_execpolicy_amendment",
                }
                events = [
                    ToolEvent(
                        name="approval_decision",
                        ok=True,
                        summary=("approved" if approved else "rejected") + f" {approval_id}",
                        payload={
                            "approval_id": approval_id,
                            "status": "approved" if approved else "rejected",
                            "action_type": "apply_patch",
                            "decision_by": decided_by,
                            "decision_note": decision_note,
                        },
                    )
                ]
                if approved:
                    events.append(
                        ToolEvent(
                            name="apply_patch",
                            ok=True,
                            summary="apply_patch files=1",
                            payload={
                                "file_count": 1,
                                "changes": [{"path": "demo.txt", "change_type": "update"}],
                            },
                        )
                    )
                return {"tool_events": events}

        help_text, help_events = run_command_text(_DispatchRuntime(), "/help")
        self.assertEqual(help_events, [])
        self.assertIn("/help", help_text)

        grep_text, grep_events = run_command_text(
            _DispatchRuntime(), "/grep_files hello --path src --limit 5"
        )
        self.assertEqual(grep_text, "src/app.py")
        self.assertEqual([item.name for item in grep_events], ["grep_files"])

        glob_text, glob_events = run_command_text(
            _DispatchRuntime(), "/glob_files '**/*.md' --path docs --limit 5"
        )
        self.assertEqual(glob_text, "docs/guide.md")
        self.assertEqual([item.name for item in glob_events], ["glob_files"])

        list_dir_text, list_dir_events = run_command_text(
            _DispatchRuntime(), "/list_dir src --offset 1 --limit 5 --depth 2"
        )
        self.assertEqual(list_dir_text, "E1: [file] README.md\nE2: [dir] src")
        self.assertEqual([item.name for item in list_dir_events], ["list_dir"])

        read_file_text, read_file_events = run_command_text(
            _DispatchRuntime(), "/read_file README.md --offset 3 --limit 5"
        )
        self.assertEqual(read_file_text, "L1: hello")
        self.assertEqual([item.name for item in read_file_events], ["read_file"])

        class _CanonicalReadTools(_DispatchTools):
            def __init__(self):
                super().__init__(None)
                self.seen_file_path = None

            def _normalize_workspace_file_path(self, raw_path):
                return str((Path("/workspace") / str(raw_path or "")).resolve())

            def read_file(self, file_path, *, offset=None, limit=None, mode=None, indentation=None):
                self.seen_file_path = file_path
                return super().read_file(
                    file_path, offset=offset, limit=limit, mode=mode, indentation=indentation
                )

        class _CanonicalReadRuntime(_DispatchRuntime):
            def __init__(self):
                super().__init__()
                self.tools = _CanonicalReadTools()

        canonical_runtime = _CanonicalReadRuntime()
        _, canonical_read_events = run_command_text(
            canonical_runtime, "/read_file README.md --offset 3 --limit 5"
        )
        self.assertEqual([item.name for item in canonical_read_events], ["read_file"])
        self.assertEqual(
            canonical_runtime.tools.seen_file_path,
            str((Path("/workspace") / "README.md").resolve()),
        )
        self.assertEqual(
            canonical_read_events[0].payload["file_path"],
            str((Path("/workspace") / "README.md").resolve()),
        )

        class _CanonicalListDirTools(_DispatchTools):
            def __init__(self):
                super().__init__(None)
                self.seen_dir_path = None

            def _normalize_workspace_file_path(self, raw_path):
                return str((Path("/workspace") / str(raw_path or "")).resolve())

            def list_dir(self, *, dir_path=None, offset=1, limit=25, depth=2):
                self.seen_dir_path = dir_path
                return super().list_dir(dir_path=dir_path, offset=offset, limit=limit, depth=depth)

        class _CanonicalListDirRuntime(_DispatchRuntime):
            def __init__(self):
                super().__init__()
                self.tools = _CanonicalListDirTools()

        canonical_list_runtime = _CanonicalListDirRuntime()
        _, canonical_list_events = run_command_text(
            canonical_list_runtime, "/list_dir src --offset 1 --limit 5 --depth 2"
        )
        self.assertEqual([item.name for item in canonical_list_events], ["list_dir"])
        self.assertEqual(
            canonical_list_runtime.tools.seen_dir_path, str((Path("/workspace") / "src").resolve())
        )
        self.assertEqual(
            canonical_list_events[0].payload["dir_path"],
            str((Path("/workspace") / "src").resolve()),
        )

        list_text, list_events = run_command_text(_DispatchRuntime(), "/file_list src --limit 5")
        self.assertEqual(list_text, "List workspace files.")
        self.assertEqual([item.name for item in list_events], ["file_list"])

        search_text, search_events = run_command_text(
            _DispatchRuntime(), "/file_search hello --path src --limit 5"
        )
        self.assertEqual(search_text, "Search workspace files.")
        self.assertEqual([item.name for item in search_events], ["file_search"])

        read_text, read_events = run_command_text(
            _DispatchRuntime(), "/file_read README.md --offset 3 --limit 5"
        )
        self.assertEqual(read_text, "Read workspace file.")
        self.assertEqual([item.name for item in read_events], ["file_read"])
        self.assertEqual(read_events[0].payload["offset"], 3)
        self.assertEqual(read_events[0].payload["limit"], 5)

        plugin_event = ToolEvent(name="plugin_demo", ok=True, summary="ok", payload={"k": "v"})
        routed_text, routed_events = run_command_text(
            _DispatchRuntime(plugin_result=("plugin handled", [plugin_event])),
            "/custom value",
        )
        self.assertEqual(routed_text, "plugin handled")
        self.assertEqual([item.name for item in routed_events], ["plugin_demo"])

        unknown_text, unknown_events = run_command_text(_DispatchRuntime(), "/not_exists")
        self.assertEqual(unknown_events, [])
        self.assertIn("/not_exists", unknown_text)

        interrupted_text, interrupted_events = run_command_text(
            _DispatchRuntime(interrupted=True),
            "/shell echo hi",
        )
        self.assertEqual(interrupted_text, "interrupted")
        self.assertEqual(interrupted_events, [])

        web_text, web_events = run_command_text(
            _DispatchRuntime(),
            "/web_search OpenAI docs --limit 3 --domains openai.com,github.com --recency-days 7 --market us",
        )
        self.assertEqual(web_text, "Search the web.")
        self.assertEqual([item.name for item in web_events], ["web_search"])
        self.assertEqual(web_events[0].payload["query"], "OpenAI docs")
        self.assertEqual(web_events[0].payload["domains"], ["openai.com", "github.com"])
        self.assertEqual(web_events[0].payload["recency_days"], 7)
        self.assertEqual(web_events[0].payload["market"], "us")

        fetch_text, fetch_events = run_command_text(
            _DispatchRuntime(),
            "/web_fetch https://platform.openai.com/docs/overview --max-chars 3000",
        )
        self.assertEqual(fetch_text, "Fetch the webpage.")
        self.assertEqual([item.name for item in fetch_events], ["web_fetch"])
        self.assertEqual(
            fetch_events[0].payload["url"], "https://platform.openai.com/docs/overview"
        )
        self.assertEqual(fetch_events[0].payload["max_chars"], 3000)

        open_text, open_events = run_command_text(
            _DispatchRuntime(),
            "/open https://platform.openai.com/docs/overview --line 3",
        )
        self.assertEqual(open_text, "Open webpage.")
        self.assertEqual([item.name for item in open_events], ["open"])

        click_text, click_events = run_command_text(_DispatchRuntime(), "/click page_1 1")
        self.assertEqual(click_text, "Open clicked link.")
        self.assertEqual([item.name for item in click_events], ["click"])

        find_text, find_events = run_command_text(_DispatchRuntime(), "/find page_1 Responses API")
        self.assertEqual(find_text, "Find text in page.")
        self.assertEqual([item.name for item in find_events], ["find"])

        image_text, image_events = run_command_text(
            _DispatchRuntime(), "/view_image /tmp/sample.png"
        )
        self.assertEqual(image_text, "View local image.")
        self.assertEqual([item.name for item in image_events], ["view_image"])
        self.assertTrue(image_events[0].payload["ok"])
        self.assertEqual(image_events[0].payload["path"], "/tmp/sample.png")
        self.assertEqual(image_events[0].payload["image_artifacts"][0]["mime_type"], "image/png")

        web_search_result = run_command_text_result(
            _DispatchRuntime(),
            "/web_search 'OpenAI docs' --limit 3 --domains openai.com,github.com --recency-days 7 --market us",
        )
        self.assertEqual(web_search_result.assistant_text, "Search the web.")
        self.assertEqual(web_search_result.item_events[0]["item"]["tool"], "web_search")
        self.assertEqual(
            web_search_result.item_events[0]["item"]["arguments"]["query"], "OpenAI docs"
        )
        self.assertEqual(
            web_search_result.item_events[1]["item"]["result"]["structured_content"]["query"],
            "OpenAI docs",
        )

        web_fetch_result = run_command_text_result(
            _DispatchRuntime(),
            "/web_fetch https://platform.openai.com/docs/overview --max-chars 3000",
        )
        self.assertEqual(web_fetch_result.assistant_text, "Fetch the webpage.")
        self.assertEqual(web_fetch_result.item_events[0]["item"]["tool"], "web_fetch")
        self.assertEqual(
            web_fetch_result.item_events[1]["item"]["result"]["structured_content"]["url"],
            "https://platform.openai.com/docs/overview",
        )

        view_image_result = run_command_text_result(
            _DispatchRuntime(), "/view_image /tmp/sample.png"
        )
        self.assertEqual(view_image_result.assistant_text, "View local image.")
        self.assertEqual(view_image_result.item_events[0]["item"]["tool"], "view_image")
        self.assertEqual(
            view_image_result.item_events[0]["item"]["arguments"]["path"], "/tmp/sample.png"
        )
        self.assertTrue(
            view_image_result.item_events[1]["item"]["result"]["structured_content"]["ok"]
        )
        self.assertEqual(
            view_image_result.item_events[1]["item"]["result"]["structured_content"][
                "image_artifacts"
            ][0]["width"],
            1,
        )

    def test_view_image_command_installs_codex_model_capabilities_into_tool_registry(self) -> None:
        class _CapabilityAwareTools(_DispatchTools):
            def __init__(self):
                super().__init__()
                self.seen_detail = "unset"
                self.seen_capable = None

            def view_image(self, path):
                self.seen_detail = getattr(self, "_view_image_detail", None)
                self.seen_capable = getattr(self, "_view_image_input_capable", None)
                return ToolEvent(
                    name="view_image",
                    ok=bool(self.seen_capable),
                    summary="view image captured",
                    payload={
                        "ok": bool(self.seen_capable),
                        "requested_path": path,
                        "detail": self.seen_detail,
                        "image_artifacts": [],
                    },
                )

        runtime = _DispatchRuntime()
        runtime.tools = _CapabilityAwareTools()
        runtime.agent._planner = SimpleNamespace(
            config=ProviderConfig(
                model="gpt-5.3-codex",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                interaction_profile="codex_openai",
                interaction_profile_source="test",
            )
        )

        result = run_command_text_result(runtime, "/view_image /tmp/sample.png")

        self.assertEqual(result.assistant_text, "View local image.")
        self.assertTrue(runtime.tools.seen_capable)
        self.assertEqual(runtime.tools.seen_detail, "original")
        self.assertFalse(hasattr(runtime.tools, "_view_image_detail"))
        self.assertFalse(hasattr(runtime.tools, "_view_image_input_capable"))

    def test_view_image_command_disables_tool_for_text_only_codex_models(self) -> None:
        class _CapabilityAwareTools(_DispatchTools):
            def __init__(self):
                super().__init__()
                self.seen_detail = "unset"
                self.seen_capable = None

            def view_image(self, path):
                self.seen_detail = getattr(self, "_view_image_detail", None)
                self.seen_capable = getattr(self, "_view_image_input_capable", None)
                return ToolEvent(
                    name="view_image",
                    ok=bool(self.seen_capable),
                    summary="view image captured",
                    payload={
                        "ok": bool(self.seen_capable),
                        "requested_path": path,
                        "detail": self.seen_detail,
                        "error_code": "unsupported_image_input_capability",
                    },
                )

        runtime = _DispatchRuntime()
        runtime.tools = _CapabilityAwareTools()
        runtime.agent._planner = SimpleNamespace(
            config=ProviderConfig(
                model="gpt-oss-20b",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                interaction_profile="codex_openai",
                interaction_profile_source="test",
            )
        )

        result = run_command_text_result(runtime, "/view_image /tmp/sample.png")

        self.assertEqual(result.assistant_text, "View local image.")
        self.assertFalse(runtime.tools.seen_capable)
        self.assertIsNone(runtime.tools.seen_detail)
        self.assertFalse(result.tool_events[0].ok)

        grep_result = run_command_text_result(
            _DispatchRuntime(), "/grep_files hello --path src --limit 5"
        )
        self.assertEqual(grep_result.assistant_text, "src/app.py")
        self.assertEqual(grep_result.item_events[0]["item"]["tool"], "grep_files")

        glob_result = run_command_text_result(
            _DispatchRuntime(), "/glob_files '**/*.md' --path docs --limit 5"
        )
        self.assertEqual(glob_result.assistant_text, "docs/guide.md")
        self.assertEqual(glob_result.item_events[0]["item"]["tool"], "glob_files")

        list_dir_result = run_command_text_result(
            _DispatchRuntime(), "/list_dir src --offset 1 --limit 5 --depth 2"
        )
        self.assertEqual(list_dir_result.assistant_text, "E1: [file] README.md\nE2: [dir] src")
        self.assertEqual(list_dir_result.item_events[0]["item"]["tool"], "list_dir")

        canonical_read_result = run_command_text_result(
            _DispatchRuntime(), "/read_file README.md --offset 3 --limit 5"
        )
        self.assertEqual(canonical_read_result.assistant_text, "L1: hello")
        self.assertEqual(canonical_read_result.item_events[0]["item"]["tool"], "read_file")

        read_result = run_command_text_result(
            _DispatchRuntime(), "/file_read README.md --offset 3 --limit 5"
        )
        self.assertEqual(read_result.assistant_text, "Read workspace file.")
        self.assertEqual(read_result.item_events[0]["type"], "item.started")
        self.assertEqual(read_result.item_events[0]["item"]["type"], "mcp_tool_call")
        self.assertEqual(read_result.item_events[0]["item"]["tool"], "file_read")
        self.assertEqual(read_result.item_events[0]["item"]["arguments"]["path"], "README.md")
        self.assertEqual(read_result.item_events[0]["item"]["arguments"]["offset"], 3)
        self.assertEqual(read_result.item_events[0]["item"]["arguments"]["limit"], 5)
        self.assertEqual(
            read_result.item_events[1]["item"]["result"]["structured_content"]["path"], "README.md"
        )
        self.assertEqual(read_result.turn_events[0]["type"], "turn.started")
        self.assertEqual(read_result.turn_events[-1]["type"], "turn.completed")

        browser_result = run_command_text_result(
            _DispatchRuntime(),
            "/browser open --url https://example.com/report --profile review --transport proxy",
        )
        self.assertEqual(browser_result.assistant_text, "Browser open.")
        self.assertEqual(browser_result.item_events[0]["item"]["tool"], "browser")
        self.assertEqual(browser_result.item_events[0]["item"]["arguments"]["action"], "open")
        self.assertEqual(
            browser_result.item_events[0]["item"]["arguments"]["url"], "https://example.com/report"
        )
        self.assertEqual(browser_result.item_events[0]["item"]["arguments"]["profile"], "review")
        self.assertEqual(
            browser_result.item_events[1]["item"]["result"]["structured_content"]["action"], "open"
        )

    def test_run_command_text_result_preserves_structured_web_search_result(self) -> None:
        structured = _structured_tool_result(
            "web_search",
            "structured web search summary",
            payload={"query": "reference alignment"},
            arguments={"query": "reference alignment", "limit": 5},
        )
        runtime = _make_structured_command_runtime(
            web_search_result=lambda *args, **kwargs: structured,
        )
        result = run_command_text_result(runtime, "/web_search reference alignment --limit 5")
        self.assertEqual(result.assistant_text, "structured web search summary")
        self.assertEqual(result.item_events[-1]["item"]["tool"], "web_search")

    def test_run_command_text_result_prefers_structured_web_fetch_result(self) -> None:
        structured = _structured_tool_result(
            "web_fetch",
            "structured web fetch summary",
            payload={"url": "https://example.com/report"},
            arguments={"url": "https://example.com/report", "max_chars": 1000},
        )
        runtime = _make_structured_command_runtime(
            web_fetch_result=lambda *args, **kwargs: structured,
        )
        result = run_command_text_result(
            runtime, "/web_fetch https://example.com/report --max-chars 1000"
        )
        self.assertEqual(result.assistant_text, "structured web fetch summary")
        self.assertEqual(result.item_events[-1]["item"]["tool"], "web_fetch")

    def test_run_command_text_result_preserves_structured_open_and_click_results(self) -> None:
        open_result = _structured_tool_result(
            "open",
            "structured open summary",
            payload={"ref_id": "page_1"},
            arguments={"ref": "https://example.com/docs", "line": 2},
        )
        click_result = _structured_tool_result(
            "click",
            "structured click summary",
            payload={"ref_id": "page_1", "clicked_link_id": 1},
            arguments={"ref_id": "page_1", "id": 1},
        )
        runtime_open = _make_structured_command_runtime(
            open_result=lambda *args, **kwargs: open_result,
        )
        open_command_result = run_command_text_result(
            runtime_open, "/open https://example.com/docs --line 2"
        )
        self.assertEqual(open_command_result.assistant_text, "structured open summary")
        self.assertEqual(open_command_result.item_events[-1]["item"]["tool"], "open")

        runtime_click = _make_structured_command_runtime(
            click_result=lambda *args, **kwargs: click_result,
        )
        click_command_result = run_command_text_result(runtime_click, "/click page_1 1")
        self.assertEqual(click_command_result.assistant_text, "structured click summary")
        self.assertEqual(click_command_result.item_events[-1]["item"]["tool"], "click")

    def test_run_command_text_result_prefers_structured_browser_result(self) -> None:
        structured = _structured_tool_result(
            "browser",
            "structured browser summary",
            payload={"action": "status"},
            arguments={"action": "status"},
        )
        runtime = _make_structured_command_runtime(
            browser_result=lambda *args, **kwargs: structured,
        )
        result = run_command_text_result(runtime, "/browser status")
        self.assertEqual(result.assistant_text, "structured browser summary")
        self.assertEqual(result.item_events[-1]["item"]["tool"], "browser")

    def test_web_search_activity_rendering_and_tool_call_mapping(self) -> None:
        event = ToolEvent(
            name="web_search",
            ok=True,
            summary="web results=2",
            payload={
                "query": "OpenAI docs",
                "count": 2,
                "results": [
                    {"rank": 1, "source_domain": "platform.openai.com", "title": "OpenAI API docs"},
                    {"rank": 2, "source_domain": "github.com", "title": "openai-python"},
                ],
            },
        )

        activities = activity_events_for_tool_event(event)
        self.assertEqual(activities[0].title, "Searched the web")
        self.assertEqual(activities[0].kind, "web")
        self.assertIn("count=2", activities[0].detail)
        self.assertIn("platform.openai.com", detail_for_event(event))

        command = _command_for_tool_call(
            "web_search",
            {
                "query": "OpenAI docs",
                "limit": 3,
                "domains": ["openai.com", "github.com"],
                "recency_days": 7,
                "market": "us",
            },
            current_host_platform(),
        )
        self.assertEqual(
            command,
            "/web_search 'OpenAI docs' --limit 3 --domains openai.com,github.com --recency-days 7 --market us",
        )

        patch_command = _command_for_tool_call(
            "apply_patch",
            {"patch": "*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch"},
            current_host_platform(),
        )
        self.assertEqual(
            patch_command,
            "/apply_patch '*** Begin Patch\n*** Add File: demo.txt\n+hello\n*** End Patch'",
        )

        self.assertEqual(
            _command_for_tool_call(
                "grep_files",
                {"pattern": "hello", "path": "src", "limit": 5},
                current_host_platform(),
            ),
            "/grep_files hello --path src --limit 5",
        )
        self.assertEqual(
            _command_for_tool_call(
                "list_dir",
                {"dir_path": "src", "offset": 1, "limit": 5, "depth": 2},
                current_host_platform(),
            ),
            "/list_dir src --offset 1 --limit 5 --depth 2",
        )
        current_dir_command = _command_for_tool_call(
            "list_dir",
            {"dir_path": ".", "limit": 5, "depth": 1},
            current_host_platform(),
        )
        self.assertEqual(current_dir_command, "/list_dir . --limit 5 --depth 1")
        self.assertEqual(
            _command_for_tool_call(
                "read_file",
                {"file_path": "README.md", "offset": 3, "limit": 5},
                current_host_platform(),
            ),
            "/read_file README.md --offset 3 --limit 5",
        )
        self.assertEqual(
            _command_for_tool_call(
                "file_list", {"path": "src", "limit": 5}, current_host_platform()
            ),
            "/list_dir src --limit 5",
        )
        self.assertEqual(
            _command_for_tool_call(
                "file_search",
                {"query": "hello", "path": "src", "limit": 5},
                current_host_platform(),
            ),
            "/grep_files hello --path src --limit 5",
        )
        self.assertEqual(
            _command_for_tool_call(
                "file_read", {"path": "README.md", "offset": 3, "limit": 5}, current_host_platform()
            ),
            "/read_file README.md --offset 3 --limit 5",
        )

        fetch_event = ToolEvent(
            name="web_fetch",
            ok=True,
            summary="web page loaded",
            payload={
                "url": "https://platform.openai.com/docs/overview",
                "ref_id": "page_1",
                "final_url": "https://platform.openai.com/docs/overview",
                "source_domain": "platform.openai.com",
                "title": "OpenAI API docs",
                "text": "The OpenAI API provides access to models and tools.",
                "source_scope": "main",
                "link_count": 8,
                "excerpt_lines": [{"line": 5, "text": "Introduction to OpenAI."}],
            },
        )
        fetch_activities = activity_events_for_tool_event(fetch_event)
        self.assertEqual(fetch_activities[0].title, "Fetched webpage")
        self.assertEqual(fetch_activities[0].kind, "web")
        self.assertIn("platform.openai.com", fetch_activities[0].detail)
        self.assertIn("scope=main", fetch_activities[0].detail)
        self.assertIn("links=8", fetch_activities[0].detail)
        self.assertIn("preview=Introduction to OpenAI.", fetch_activities[0].detail)
        self.assertIn("OpenAI API docs", detail_for_event(fetch_event))
        self.assertIn("preview=Introduction to OpenAI.", detail_for_event(fetch_event))

        fetch_command = _command_for_tool_call(
            "web_fetch",
            {"url": "https://platform.openai.com/docs/overview", "max_chars": 3000},
            current_host_platform(),
        )
        self.assertEqual(
            fetch_command,
            "/web_fetch https://platform.openai.com/docs/overview --max-chars 3000",
        )

        view_image_event = ToolEvent(
            name="view_image",
            ok=True,
            summary="image artifact ready: diagram.png",
            payload={
                "ok": True,
                "path": "/tmp/diagram.png",
                "requested_path": "/tmp/diagram.png",
                "image_artifacts": [
                    {
                        "path": "/tmp/diagram.png",
                        "mime_type": "image/png",
                        "size_bytes": 42,
                        "width": 64,
                        "height": 48,
                        "image_url": "data:image/png;base64,AAAA",
                    }
                ],
            },
        )
        view_image_activities = activity_events_for_tool_event(view_image_event)
        self.assertEqual(view_image_activities[0].title, "Viewed image")
        self.assertIn("/tmp/diagram.png", view_image_activities[0].detail)
        self.assertNotIn("format=png", detail_for_event(view_image_event))

        view_image_command = _command_for_tool_call(
            "view_image",
            {"path": "/tmp/diagram.png"},
            current_host_platform(),
        )
        self.assertEqual(view_image_command, "/view_image /tmp/diagram.png")

        browser_command = _command_for_tool_call(
            "browser",
            {
                "action": "act",
                "profile": "openclaw",
                "tab": "tab-1",
                "kind": "evaluate",
                "ref": "r1",
                "fn": "() => document.title",
                "time_ms": 120,
            },
            current_host_platform(),
        )
        self.assertEqual(
            browser_command,
            "/browser act --profile openclaw --tab tab-1 --ref r1 --kind evaluate --fn '() => document.title' --time-ms 120",
        )

        browser_resize_command = _command_for_tool_call(
            "browser",
            {
                "action": "act",
                "kind": "resize",
                "width": 1440,
                "height": 900,
            },
            current_host_platform(),
        )
        self.assertEqual(
            browser_resize_command, "/browser act --kind resize --width 1440 --height 900"
        )

        open_event = ToolEvent(
            name="open",
            ok=True,
            summary="page opened",
            payload={
                "ref_id": "page_1",
                "source_domain": "platform.openai.com",
                "title": "OpenAI API docs",
                "source_scope": "main",
                "link_count": 1,
                "excerpt_lines": [{"line": 1, "text": "Overview"}],
                "links": [
                    {
                        "id": 1,
                        "text": "Quickstart",
                        "url": "https://platform.openai.com/docs/quickstart",
                    }
                ],
            },
        )
        open_activities = activity_events_for_tool_event(open_event)
        self.assertEqual(open_activities[0].title, "Opened webpage")
        self.assertEqual(open_activities[0].kind, "web")
        self.assertIn("page_1", open_activities[0].detail)
        self.assertIn("scope=main", open_activities[0].detail)
        self.assertIn("links=1", open_activities[0].detail)
        self.assertIn("preview=Overview", open_activities[0].detail)
        self.assertIn("Quickstart", detail_for_event(open_event))
        self.assertIn("preview=Overview", detail_for_event(open_event))

        click_event = ToolEvent(
            name="click",
            ok=True,
            summary="link opened",
            payload={
                "ref_id": "page_1",
                "final_url": "https://platform.openai.com/docs/quickstart",
                "title": "Quickstart",
                "clicked_link_text": "Quickstart",
                "links": [
                    {
                        "id": 1,
                        "text": "Quickstart",
                        "url": "https://platform.openai.com/docs/quickstart",
                    }
                ],
                "excerpt_lines": [{"line": 1, "text": "Install the SDK first."}],
            },
        )
        click_activities = activity_events_for_tool_event(click_event)
        self.assertEqual(click_activities[0].kind, "web")
        self.assertIn("preview=Install the SDK first.", click_activities[0].detail)
        self.assertIn("preview=Install the SDK first.", detail_for_event(click_event))

        click_command = _command_for_tool_call(
            "click",
            {"ref_id": "page_1", "id": 1},
            current_host_platform(),
        )
        self.assertEqual(click_command, "/browser click_legacy --ref page_1 --id 1")

        find_command = _command_for_tool_call(
            "find",
            {"ref_id": "page_1", "pattern": "Responses API"},
            current_host_platform(),
        )
        self.assertEqual(find_command, "/browser find_legacy --ref page_1 --text 'Responses API'")

    def test_view_image_runtime_emits_image_artifact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            image_path.write_bytes(_SAMPLE_PNG_BYTES)
            expected_path = str(image_path.resolve())

            event = document_tools_runtime.view_image(
                path=str(image_path),
                workspace_root_factory=lambda: Path(temp_dir),
                event_factory=lambda name, ok, summary, payload: ToolEvent(
                    name=name,
                    ok=ok,
                    summary=summary,
                    payload=payload,
                ),
            )

        self.assertTrue(event.ok)
        self.assertEqual(event.summary, "image artifact ready: sample.png")
        payload = MediaIngestResult.from_dict(event.payload)
        self.assertTrue(payload.ok)
        self.assertEqual(payload.requested_path, str(image_path))
        self.assertEqual(payload.path, expected_path)
        self.assertEqual(len(payload.image_artifacts), 1)
        artifact = payload.image_artifacts[0]
        self.assertEqual(artifact.path, expected_path)
        self.assertEqual(artifact.mime_type, "image/png")
        self.assertEqual(artifact.width, 1)
        self.assertEqual(artifact.height, 1)
        self.assertEqual(artifact.size_bytes, len(_SAMPLE_PNG_BYTES))
        self.assertTrue(artifact.image_url.startswith("data:image/png;base64,"))

    def test_view_image_runtime_fails_closed_for_invalid_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            image_path.write_bytes(b"not an image")

            event = document_tools_runtime.view_image(
                path=str(image_path),
                workspace_root_factory=lambda: Path(temp_dir),
                event_factory=lambda name, ok, summary, payload: ToolEvent(
                    name=name,
                    ok=ok,
                    summary=summary,
                    payload=payload,
                ),
            )

        self.assertFalse(event.ok)
        self.assertEqual(event.summary, "view image failed")
        payload = MediaIngestResult.from_dict(event.payload)
        self.assertFalse(payload.ok)
        self.assertEqual(payload.error_code, "invalid_image")
        self.assertIn("not a valid supported image", payload.display_message)
        self.assertEqual(payload.requested_path, str(image_path))
        self.assertEqual(payload.path, str(image_path.resolve()))
        self.assertEqual(payload.image_artifacts, ())

    def test_view_image_runtime_preserves_original_detail_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            image_path.write_bytes(_SAMPLE_PNG_BYTES)

            event = document_tools_runtime.view_image(
                path=str(image_path),
                detail="original",
                workspace_root_factory=lambda: Path(temp_dir),
                event_factory=lambda name, ok, summary, payload: ToolEvent(
                    name=name,
                    ok=ok,
                    summary=summary,
                    payload=payload,
                ),
            )

        self.assertTrue(event.ok)
        payload = MediaIngestResult.from_dict(event.payload)
        self.assertTrue(payload.ok)
        self.assertEqual(payload.detail, "original")
        self.assertEqual(payload.image_artifacts[0].detail, "original")

    def test_view_image_runtime_fails_closed_when_image_input_capability_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            image_path.write_bytes(_SAMPLE_PNG_BYTES)

            event = document_tools_runtime.view_image(
                path=str(image_path),
                image_input_capable=False,
                workspace_root_factory=lambda: Path(temp_dir),
                event_factory=lambda name, ok, summary, payload: ToolEvent(
                    name=name,
                    ok=ok,
                    summary=summary,
                    payload=payload,
                ),
            )

        self.assertFalse(event.ok)
        self.assertEqual(event.summary, "view image failed")
        payload = MediaIngestResult.from_dict(event.payload)
        self.assertFalse(payload.ok)
        self.assertEqual(payload.error_code, "unsupported_image_input_capability")
        self.assertIn("does not support image inputs", payload.display_message)

    def test_try_execute_local_plan_is_noop_when_local_planning_disabled(self) -> None:
        calls: list[str] = []

        class _Runtime:
            def _should_try_local_plan(self, text):
                calls.append(text)
                return False

            def _preview_local_plan(self, text):
                raise AssertionError(f"_preview_local_plan should not run for {text}")

        result = try_execute_local_plan(_Runtime(), "list current directory")

        self.assertIsNone(result)
        self.assertEqual(calls, ["list current directory"])

    def test_restore_provider_state_does_not_override_ready_runtime_provider(self) -> None:
        switch_calls: list[tuple[str, str]] = []

        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "deepseek",
                    "model_key": "deepseek_reasoner",
                }

            @staticmethod
            def switch_model(model_key):
                switch_calls.append(("model", model_key))

            @staticmethod
            def switch_provider(provider_name):
                switch_calls.append(("provider", provider_name))

            @staticmethod
            def switch_provider_line(line):
                switch_calls.append(("line", line))

        class _Runtime:
            agent = _Agent()

            @staticmethod
            def _state_value(state, key):
                return state.get(key)

        restore_provider_state(
            _Runtime(),
            {
                "provider_name": "openai",
                "model_key": "gpt_54",
                "session_line": "openai-tools",
            },
        )

        self.assertEqual(switch_calls, [])

    def test_restore_provider_state_restores_session_route_overrides_even_when_provider_is_ready(
        self,
    ) -> None:
        switch_calls: list[tuple[str, str]] = []
        route_override_calls: list[dict[str, dict[str, str]]] = []

        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "deepseek",
                    "model_key": "deepseek_reasoner",
                }

            @staticmethod
            def set_session_route_overrides(overrides):
                route_override_calls.append(dict(overrides or {}))

            @staticmethod
            def switch_model(model_key):
                switch_calls.append(("model", model_key))

            @staticmethod
            def switch_provider(provider_name):
                switch_calls.append(("provider", provider_name))

            @staticmethod
            def switch_provider_line(line):
                switch_calls.append(("line", line))

        class _Runtime:
            agent = _Agent()

            @staticmethod
            def _state_value(state, key):
                return state.get(key)

        restore_provider_state(
            _Runtime(),
            {
                "provider_name": "openai",
                "model_key": "gpt_54",
                "session_route_overrides": {
                    "tool_followup": {
                        "provider": "glm",
                        "model": "glm_5",
                        "source": "session_override",
                    }
                },
            },
        )

        self.assertEqual(
            route_override_calls,
            [
                {
                    "tool_followup": {
                        "provider": "glm",
                        "model": "glm_5",
                        "source": "session_override",
                    }
                }
            ],
        )
        self.assertEqual(switch_calls, [])

    def test_restore_provider_state_restores_session_delegate_overrides_even_when_provider_is_ready(
        self,
    ) -> None:
        switch_calls: list[tuple[str, str]] = []
        delegate_override_calls: list[dict[str, dict[str, str]]] = []

        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "deepseek",
                    "model_key": "deepseek_reasoner",
                }

            @staticmethod
            def set_session_delegate_overrides(overrides):
                delegate_override_calls.append(dict(overrides or {}))

            @staticmethod
            def switch_model(model_key):
                switch_calls.append(("model", model_key))

            @staticmethod
            def switch_provider(provider_name):
                switch_calls.append(("provider", provider_name))

            @staticmethod
            def switch_provider_line(line):
                switch_calls.append(("line", line))

        class _Runtime:
            agent = _Agent()

            @staticmethod
            def _state_value(state, key):
                return state.get(key)

        restore_provider_state(
            _Runtime(),
            {
                "provider_name": "openai",
                "model_key": "gpt_54",
                "session_delegation_overrides": {
                    "teammate": {
                        "provider": "glm",
                        "model": "glm_5",
                        "source": "session_override",
                    }
                },
            },
        )

        self.assertEqual(
            delegate_override_calls,
            [
                {
                    "teammate": {
                        "provider": "glm",
                        "model": "glm_5",
                        "source": "session_override",
                    }
                }
            ],
        )
        self.assertEqual(switch_calls, [])

    def test_restore_provider_state_can_rehydrate_thread_provider_when_runtime_is_not_ready(
        self,
    ) -> None:
        switch_calls: list[tuple[str, str]] = []

        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "false",
                    "provider_name": "-",
                    "model_key": "-",
                }

            @staticmethod
            def switch_model(model_key):
                switch_calls.append(("model", model_key))

            @staticmethod
            def switch_provider(provider_name):
                switch_calls.append(("provider", provider_name))

            @staticmethod
            def switch_provider_line(line):
                switch_calls.append(("line", line))

        class _Runtime:
            agent = _Agent()

            @staticmethod
            def _state_value(state, key):
                return state.get(key)

        restore_provider_state(
            _Runtime(),
            {
                "provider_name": "openai",
                "model_key": "gpt_54",
                "session_line": "openai-tools",
            },
        )

        self.assertEqual(switch_calls, [("model", "gpt_54")])

    def test_delegated_result_parts_normalize_join_state_without_next_action(self) -> None:
        card = TaskCard(card_id="CARD-900", kind=TaskCardKind.READ_ONLY)
        parts = taskbook_runtime_results_helper_runtime.delegated_result_parts(
            card=card,
            execution_ref=ExecutionRef(kind=ExecutionRefKind.DELEGATED_SUBAGENT, agent_id="ag_900"),
            snapshot={
                "status": "completed",
                "completion_state": "ready_to_adopt",
                "terminal_state": "completed",
                "text": "",
            },
            result_contract={
                "status": "completed",
                "summary": "",
                "next_action": "",
                "touched_scope": [],
            },
            terminal_status=CardResultStatus.COMPLETED,
            root=Path("/tmp/demo"),
            string_list_fn=lambda value: (
                list(value)
                if isinstance(value, list)
                else ([str(value)] if str(value or "").strip() else [])
            ),
            selector_value_fn=lambda value: str(value or "").strip(),
        )

        result = CardResult(
            result_id="result_900",
            card_id="CARD-900",
            status=CardResultStatus.COMPLETED,
            summary=parts["summary"],
            modified_files=parts["modified_files"],
            commands=parts["commands"],
            blockers=parts["blockers"],
            needs_review=parts["needs_review"],
            suggested_next_action=parts["suggested_next_action"],
        )
        decision, reason, _ = taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result, card=card
        )

        self.assertEqual(parts["result_state"], "pending_review")
        self.assertEqual(parts["suggested_next_action"], "review_or_adopt_teammate_result")
        self.assertEqual(parts["summary"], "awaiting operator review")
        self.assertTrue(parts["needs_review"])
        self.assertEqual(decision, CardAcceptanceDecision.BLOCK)
        self.assertEqual(reason, "review_or_adopt_teammate_result")

    def test_delegated_result_parts_keep_adopted_distinct_from_returned(self) -> None:
        card = TaskCard(card_id="CARD-901", kind=TaskCardKind.READ_ONLY)
        common_kwargs = {
            "card": card,
            "execution_ref": ExecutionRef(
                kind=ExecutionRefKind.DELEGATED_SUBAGENT, agent_id="ag_901"
            ),
            "terminal_status": CardResultStatus.COMPLETED,
            "root": Path("/tmp/demo"),
            "string_list_fn": lambda value: (
                list(value)
                if isinstance(value, list)
                else ([str(value)] if str(value or "").strip() else [])
            ),
            "selector_value_fn": lambda value: str(value or "").strip(),
        }
        returned_parts = taskbook_runtime_results_helper_runtime.delegated_result_parts(
            snapshot={
                "status": "completed",
                "completion_state": "completed",
                "terminal_state": "completed",
            },
            result_contract={"status": "completed", "summary": "", "touched_scope": []},
            **common_kwargs,
        )
        adopted_parts = taskbook_runtime_results_helper_runtime.delegated_result_parts(
            snapshot={
                "status": "completed",
                "completion_state": "adopted",
                "terminal_state": "completed",
            },
            result_contract={"status": "completed", "summary": "", "touched_scope": []},
            **common_kwargs,
        )

        self.assertEqual(returned_parts["result_state"], "returned")
        self.assertEqual(returned_parts["suggested_next_action"], "result_returned")
        self.assertEqual(adopted_parts["result_state"], "adopted")
        self.assertEqual(adopted_parts["suggested_next_action"], "already_adopted")

    def test_background_result_parts_prefer_blocked_over_adopted_hints(self) -> None:
        parts = taskbook_runtime_results_helper_runtime.background_result_parts(
            {
                "status": "completed",
                "summary": "",
                "completion_state": "adopted",
            },
            execution_ref=ExecutionRef(kind=ExecutionRefKind.BACKGROUND_TASK, task_id="bg_902"),
            artifact={
                "terminal_state": "completed",
                "notification_state": "foreground_adopted",
                "final_apply_state": "blocked",
                "final_apply_pending": False,
                "modified_files": ["cli/agent_cli/runtime.py"],
                "commands": ["pytest -q"],
                "test_commands": ["pytest -q"],
            },
            terminal_status=CardResultStatus.COMPLETED,
            string_list_fn=lambda value: (
                list(value)
                if isinstance(value, list)
                else ([str(value)] if str(value or "").strip() else [])
            ),
            selector_value_fn=lambda value: str(value or "").strip(),
        )

        self.assertEqual(parts["result_state"], "blocked")
        self.assertTrue(parts["needs_review"])
        self.assertIn("final_apply_blocked", parts["blockers"])
