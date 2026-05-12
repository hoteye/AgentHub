# ruff: noqa: E402

import base64
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

from cli.tests.provider_boundary_test_support import provider_status_path_fields


def _install_system_prompts_import_fallback() -> None:
    module_name = "cli.agent_cli.providers.system_prompts"
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)

    def _prompt_stub(*_args: Any, **_kwargs: Any) -> str:
        return ""

    module.build_chat_completions_system_prompt = _prompt_stub
    module.build_openai_json_system_prompt = _prompt_stub
    module.build_openai_native_system_prompt = _prompt_stub
    sys.modules[module_name] = module


def _install_runtime_core_provider_connect_fallback() -> None:
    module_name = "cli.agent_cli.runtime_core.provider_connect_runtime"
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)

    def _handle_connect_command(_runtime: Any, *, arg_text: str = "") -> tuple[str, list[Any]]:
        detail = str(arg_text or "").strip()
        suffix = f" ({detail})" if detail else ""
        return (f"connect command fallback unavailable{suffix}", [])

    module.handle_connect_command = _handle_connect_command
    sys.modules[module_name] = module


def _install_provider_protocol_fallbacks() -> None:
    pkg_name = "cli.agent_cli.providers.protocols"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = []  # type: ignore[attr-defined]

        class _UnavailablePlanner:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("provider protocol planner is unavailable in test fallback")

        pkg.AnthropicClaudePlanner = _UnavailablePlanner
        pkg.ChatCompletionsPlanner = _UnavailablePlanner
        pkg.DeepSeekPlanner = _UnavailablePlanner
        pkg.OpenAIPlanner = _UnavailablePlanner
        sys.modules[pkg_name] = pkg

    module_name = "cli.agent_cli.providers.protocols.anthropic_messages"
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)

    class AnthropicClaudePlanner:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("anthropic planner is unavailable in test fallback")

    def load_claude_provider_config(*_args: Any, **_kwargs: Any) -> Any:
        return None

    def should_use_claude_provider(*_args: Any, **_kwargs: Any) -> bool:
        return False

    module.AnthropicClaudePlanner = AnthropicClaudePlanner
    module.load_claude_provider_config = load_claude_provider_config
    module.should_use_claude_provider = should_use_claude_provider
    sys.modules[module_name] = module


def _install_provider_catalog_toml_runtime_fallback() -> None:
    module_name = "cli.agent_cli.provider_catalog_toml_runtime"
    if module_name in sys.modules:
        return
    module_path = ROOT / "cli" / "agent_cli" / "provider_catalog_toml_runtime.py"
    if module_path.exists():
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return
    module = types.ModuleType(module_name)
    module.quoted_toml_string = lambda value: json.dumps(str(value), ensure_ascii=False)
    module.upsert_root_toml_string_key = lambda existing, *, key, value: str(existing or "")
    module.read_user_model_selection_toml = lambda *, config_paths, read_toml_fn, selection_keys: {}
    module.save_user_model_selection = lambda *, path, **kwargs: path
    sys.modules[module_name] = module


def _is_transient_provider_import_error(exc: ImportError) -> bool:
    text = str(exc)
    return (
        ("planner_postprocessing" in text)
        or ("provider_connect_runtime" in text)
        or ("anthropic_messages" in text)
    )


try:
    from cli.agent_cli.agent import RuleBasedAgent
except ImportError as exc:
    if not _is_transient_provider_import_error(exc):
        raise
    _install_system_prompts_import_fallback()
    _install_runtime_core_provider_connect_fallback()
    _install_provider_protocol_fallbacks()
    sys.modules.pop("cli.agent_cli.agent", None)
    from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli import app_server_helpers
from cli.agent_cli.app_server import _exit_code_for_response
from cli.agent_cli.app_server import main as app_server_main
from cli.agent_cli.app_server_payloads import reference_turn_payload
from cli.agent_cli.app_server_protocol_runtime import (
    APP_SERVER_BASE_METHODS,
    APP_SERVER_CAPABILITY_METHODS,
    APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
    APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED,
    APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT,
    APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS,
    APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND,
    APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED,
    APP_SERVER_GATEWAY_EXTENSION_METHODS,
    REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS,
    app_server_capability_methods,
    app_server_gateway_extension_methods,
)
from cli.agent_cli.gateway_api.gui_bridge_api import dispatch_gui_bridge_action
from cli.agent_cli.gateway_core import (
    TriggerRegistration,
    create_gateway_event,
    create_workflow_run,
)
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    PromptResponse,
    ResponseInputItem,
    ToolEvent,
    generic_tool_call_item_events,
)

try:
    from cli.agent_cli.runtime import AgentCliRuntime
except ImportError as exc:
    if not _is_transient_provider_import_error(exc):
        raise
    _install_system_prompts_import_fallback()
    _install_runtime_core_provider_connect_fallback()
    _install_provider_protocol_fallbacks()
    sys.modules.pop("cli.agent_cli.runtime", None)
from cli.agent_cli.providers.config_catalog_types import ProviderConfig
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_kernels.base import KernelSession
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.tools import ToolRegistry
from shared.integrations import HttpClient, compute_hmac_sha256_hex
from workers.actions import ActionResult, ControlledActionWorker

EXPECTED_APP_SERVER_GATEWAY_EXTENSION_METHODS: tuple[str, ...] = (
    "access.posture.get",
    "approvals.get",
    "approvals.list",
    "approvals.resolve",
    "browser.playbook.run",
    "browser.proxy",
    "browser.workflow.run",
    "config.apply",
    "config.restart.report",
    "config.validate",
    "connect.capabilities",
    "connect.initialize",
    "connect.ping",
    "gateway.events.list",
    "gateway.state.get",
    "gateway.trace.timeline",
    "gateway.workflows.list",
    "github.actions.dispatch",
    "github.comments.create",
    "github.issues.create",
    "github.webhook.ingest",
    "health.get",
    "health.probes",
    "logs.tail",
    "nodes.list",
    "plugins.connectors.list",
    "plugins.list",
    "plugins.triggers.list",
    "workflows.get",
    "workflows.list",
    "workflows.resume",
)


def test_reference_turn_payload_canonicalizes_provider_shell_items_to_command_execution() -> None:
    payload = reference_turn_payload(
        {
            "turn_id": "turn_1",
            "status": {},
            "turn_events": [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "shell_call",
                        "call_id": "call_shell_1",
                        "action": {
                            "type": "exec",
                            "command": ["python", "-V"],
                        },
                        "status": "completed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "shell_call_output",
                        "call_id": "call_shell_1",
                        "output": [
                            {
                                "stdout": "Python 3.13.0\n",
                                "stderr": "",
                                "outcome": {"type": "exit", "exit_code": 0},
                            }
                        ],
                        "status": "completed",
                    },
                },
            ],
        },
        include_items=True,
    )

    assert payload["items"] == [
        {
            "id": "call_shell_1",
            "type": "commandExecution",
            "status": "completed",
            "aggregatedOutput": "Python 3.13.0\n",
            "exitCode": 0,
            "call_id": "call_shell_1",
            "command": "python -V",
            "cwd": "",
            "commandActions": [],
            "processId": None,
            "durationMs": None,
        }
    ]


# This module verifies the app-server execution protocol itself.
# It intentionally pins direct shell-path cases to approval_policy=never,
# so protocol assertions stay stable even when the product default policy is approval-gated.
class _AppServerAgent(RuleBasedAgent):
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "model_key": "deepseek_reasoner",
            "provider_planner": "deepseek_reasoner",
            "provider_model": "deepseek-reasoner",
            "provider_tools": "tool-calls",
            "session_line": "reasoner",
            "provider_label": "deepseek | deepseek-reasoner | tool-calls",
            "provider_base_url": "https://api.deepseek.com",
            "provider_source": "test",
            **provider_status_path_fields(),
            "platform_family": "windows",
            "platform_os": "windows",
            "shell_kind": "powershell",
        }

    def available_models(self, provider_name: str | None = None) -> list[dict[str, str]]:
        models = [
            {
                "model_key": "deepseek_reasoner",
                "provider_name": "deepseek",
                "model_id": "deepseek-reasoner",
                "display_name": "DeepSeek Reasoner",
                "planner_kind": "deepseek_reasoner",
                "wire_api": "responses",
                "supports_tools": "true",
                "supports_reasoning": "true",
            },
            {
                "model_key": "gpt_54",
                "provider_name": "openai",
                "model_id": "gpt-5.4",
                "display_name": "GPT-5.4",
                "planner_kind": "openai_responses",
                "wire_api": "responses",
                "supports_tools": "true",
                "supports_reasoning": "true",
            },
        ]
        normalized = str(provider_name or "").strip()
        if not normalized:
            return models
        return [item for item in models if item["provider_name"] == normalized]

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        normalized = text.strip().lower()
        if normalized == "list current directory":
            return AgentIntent(
                commentary_text="Checking current workspace before execution.",
                assistant_text="Recognized as a local directory query. Preparing shell execution.",
                command_text="/shell Get-ChildItem -Force",
                status_hint="tool",
            )
        if normalized == "long running task":
            return AgentIntent(
                assistant_text="Recognized as a long-running shell task. Preparing shell execution.",
                command_text="/shell sleep",
                status_hint="tool",
            )
        return AgentIntent(assistant_text=f"echo: {text}")


class _StreamingPromptRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_ready": "true",
                "provider_name": "stream-test",
                "provider_model": "gpt-5.4",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.thread_id = "thread_stream"
        self.thread_name = "stream"

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        if self.turn_event_callback is not None:
            self.turn_event_callback({"type": "turn.started"})
            self.turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "reasoning", "text": "先定位入口"},
                }
            )
            self.turn_event_callback(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "入口在 cli/agent_cli/headless.py",
                    },
                }
            )
            self.turn_event_callback(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                }
            )
        return PromptResponse(
            user_text=text,
            assistant_text="入口在 cli/agent_cli/headless.py",
            commentary_text="先定位入口",
            turn_events=[
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "reasoning", "text": "先定位入口"},
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "入口在 cli/agent_cli/headless.py",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ],
            status=self.agent.provider_status(),
        )


class _AppServerTools:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, object]] = {}
        self._exec_count = 0
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
            "source": "app_server_test_tools",
        }
        if status:
            payload["status"] = status
        return payload

    def capabilities(self) -> dict:
        return {
            "ok": True,
            "tools": [
                {"name": "shell", "description": "shell"},
                {"name": "office_skills", "description": "office skills"},
            ],
        }

    def shell(self, command: str) -> ToolEvent:
        self._exec_count += 1
        exec_session_id = f"exec_{self._exec_count}"
        call_id = self._next_call_id()
        callback = getattr(self, "_shell_activity_callback", None)
        cancel_getter = getattr(self, "_shell_cancel_event_getter", None)
        cancel_event = cancel_getter() if callable(cancel_getter) else None
        if callback is not None:
            callback(
                {
                    "phase": "started",
                    "command": command,
                    "session_id": exec_session_id,
                    "process_id": exec_session_id,
                    "call_id": call_id,
                    "lifecycle": self._lifecycle(
                        phase="started",
                        kind="begin",
                        call_id=call_id,
                        session_id=exec_session_id,
                        process_id=exec_session_id,
                        status="started",
                    ),
                }
            )
        if command == "sleep":
            started_at = time.monotonic()
            while time.monotonic() - started_at < 2.0:
                if cancel_event is not None and cancel_event.is_set():
                    payload = {
                        "command": command,
                        "session_id": exec_session_id,
                        "call_id": call_id,
                        "process_id": exec_session_id,
                        "returncode": -1,
                        "stdout": "",
                        "stderr": "",
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "interrupted": True,
                        "lifecycle": self._lifecycle(
                            phase="completed",
                            kind="end",
                            call_id=call_id,
                            session_id=exec_session_id,
                            process_id=exec_session_id,
                            status="interrupted",
                        ),
                    }
                    if callback is not None:
                        callback(
                            {
                                "phase": "completed",
                                "command": command,
                                "session_id": exec_session_id,
                                "call_id": call_id,
                                "process_id": exec_session_id,
                                "returncode": -1,
                                "stdout": "",
                                "stderr": "",
                                "duration_ms": payload["duration_ms"],
                                "interrupted": True,
                                "timed_out": False,
                                "ok": False,
                                "status": "interrupted",
                                "lifecycle": self._lifecycle(
                                    phase="completed",
                                    kind="end",
                                    call_id=call_id,
                                    session_id=exec_session_id,
                                    process_id=exec_session_id,
                                    status="interrupted",
                                ),
                            }
                        )
                    return ToolEvent(
                        name="shell",
                        ok=False,
                        summary="shell interrupted",
                        payload=payload,
                    )
                time.sleep(0.02)
        return ToolEvent(
            name="shell",
            ok=True,
            summary=f"shell ok: {command}",
            payload={
                "command": command,
                "session_id": exec_session_id,
                "call_id": call_id,
                "process_id": exec_session_id,
                "returncode": 0,
                "stdout": "a.txt\nb.txt\n",
                "stderr": "",
                "duration_ms": 5,
                "interrupted": False,
                "lifecycle": self._lifecycle(
                    phase="completed",
                    kind="end",
                    call_id=call_id,
                    session_id=exec_session_id,
                    process_id=exec_session_id,
                    status="ok",
                ),
            },
        )

    def shell_start(self, command: str, *, on_activity=None) -> dict[str, object]:
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

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        session = self._sessions.get(session_id)
        if session is None or not session.get("active"):
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        status = "noop" if not chars else "written"
        normalized_yield = int(yield_time_ms) if yield_time_ms is not None else None
        if on_activity is not None:
            on_activity(
                {
                    "phase": "input",
                    "command": str(session.get("command") or ""),
                    "session_id": session_id,
                    "process_id": session_id,
                    "call_id": str(session.get("call_id") or ""),
                    "stdin": chars,
                    "chars": chars,
                    "status": status,
                    "yield_time_ms": normalized_yield,
                    "lifecycle": self._lifecycle(
                        phase="input",
                        kind="input",
                        call_id=str(session.get("call_id") or ""),
                        session_id=session_id,
                        process_id=session_id,
                        status=status,
                    ),
                }
            )
        if on_activity is not None and chars:
            on_activity(
                {
                    "phase": "output",
                    "command": str(session.get("command") or ""),
                    "session_id": session_id,
                    "process_id": session_id,
                    "call_id": str(session.get("call_id") or ""),
                    "stream": "stdout",
                    "text": f"echo:{chars.strip()}",
                    "chunk": base64.b64encode(f"echo:{chars.strip()}\n".encode()).decode("ascii"),
                    "lifecycle": self._lifecycle(
                        phase="output",
                        kind="output_delta",
                        call_id=str(session.get("call_id") or ""),
                        session_id=session_id,
                        process_id=session_id,
                    ),
                }
            )
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell stdin written",
            payload={
                "command": str(session.get("command") or ""),
                "session_id": session_id,
                "call_id": str(session.get("call_id") or ""),
                "process_id": session_id,
                "stdin": chars,
                "chars": chars,
                "status": status,
                "yield_time_ms": normalized_yield,
                "lifecycle": self._lifecycle(
                    phase="input",
                    kind="input",
                    call_id=str(session.get("call_id") or ""),
                    session_id=session_id,
                    process_id=session_id,
                    status=status,
                ),
            },
        )

    def shell_terminate(self, session_id: str, *, on_activity=None) -> ToolEvent:
        session = self._sessions.get(session_id)
        if session is None or not session.get("active"):
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        session["active"] = False
        if on_activity is not None:
            on_activity(
                {
                    "phase": "completed",
                    "command": str(session.get("command") or ""),
                    "session_id": session_id,
                    "process_id": session_id,
                    "call_id": str(session.get("call_id") or ""),
                    "returncode": -1,
                    "stdout": "",
                    "stderr": "",
                    "duration_ms": 1,
                    "interrupted": True,
                    "timed_out": False,
                    "ok": False,
                    "status": "interrupted",
                    "lifecycle": self._lifecycle(
                        phase="completed",
                        kind="end",
                        call_id=str(session.get("call_id") or ""),
                        session_id=session_id,
                        process_id=session_id,
                        status="interrupted",
                    ),
                }
            )
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


class _LifecycleAppServerTools(_AppServerTools):
    def _augment(self, payload: dict[str, object]) -> dict[str, object]:
        wrapped = dict(payload or {})
        lifecycle = dict(wrapped.get("lifecycle") or {})
        lifecycle["phase"] = (
            str(payload.get("phase") or lifecycle.get("phase") or "").strip().lower()
        )
        lifecycle["source"] = "app_server_test"
        wrapped["lifecycle"] = lifecycle
        return wrapped

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._augment(payload))

        return super().shell_start(command, on_activity=callback, **kwargs)

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._augment(payload))

        return super().shell_write_stdin(
            session_id, chars, yield_time_ms=yield_time_ms, on_activity=callback
        )

    def shell_terminate(self, session_id: str, *, on_activity=None) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._augment(payload))

        return super().shell_terminate(session_id, on_activity=callback)


class _NoLifecycleAppServerTools(_AppServerTools):
    def _strip_lifecycle(self, payload: dict[str, object] | None) -> dict[str, object]:
        cleaned = dict(payload or {})
        cleaned.pop("lifecycle", None)
        return cleaned

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._strip_lifecycle(payload))

        result = super().shell_start(command, on_activity=callback, **kwargs)
        cleaned = self._strip_lifecycle(result)
        cleaned.setdefault("phase", "started")
        return cleaned

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._strip_lifecycle(payload))

        event = super().shell_write_stdin(
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            on_activity=callback,
        )
        payload = self._strip_lifecycle(event.payload)
        payload.setdefault("phase", "input")
        event.payload = payload
        return event

    def shell_terminate(self, session_id: str, *, on_activity=None) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._strip_lifecycle(payload))

        event = super().shell_terminate(session_id, on_activity=callback)
        payload = self._strip_lifecycle(event.payload)
        payload.setdefault("phase", "completed")
        event.payload = payload
        return event


class _LifecycleOnlyAppServerTools(_AppServerTools):
    @staticmethod
    def _normalize(payload: dict[str, object] | None) -> dict[str, object]:
        cleaned = dict(payload or {})
        cleaned.pop("phase", None)
        cleaned.pop("status", None)
        return cleaned

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._normalize(payload))

        return self._normalize(super().shell_start(command, on_activity=callback, **kwargs))

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._normalize(payload))

        event = super().shell_write_stdin(
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            on_activity=callback,
        )
        event.payload = self._normalize(event.payload)
        return event


class _IoModeAppServerTools(_AppServerTools):
    @staticmethod
    def _with_io_mode(payload: dict[str, object] | None) -> dict[str, object]:
        wrapped = dict(payload or {})
        wrapped["io_mode"] = "pty"
        return wrapped

    def shell(self, command: str) -> ToolEvent:
        event = super().shell(command)
        event.payload = self._with_io_mode(event.payload)
        return event

    def shell_start(self, command: str, *, on_activity=None, **kwargs) -> dict[str, object]:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._with_io_mode(payload))

        result = super().shell_start(command, on_activity=callback, **kwargs)
        return self._with_io_mode(result)

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._with_io_mode(payload))

        event = super().shell_write_stdin(
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            on_activity=callback,
        )
        event.payload = self._with_io_mode(event.payload)
        return event

    def shell_terminate(self, session_id: str, *, on_activity=None) -> ToolEvent:
        def callback(payload: dict[str, object]) -> None:
            if on_activity is not None:
                on_activity(self._with_io_mode(payload))

        event = super().shell_terminate(session_id, on_activity=callback)
        event.payload = self._with_io_mode(event.payload)
        return event


def _structured_tool_result(name, summary, payload=None, arguments=None):
    event = ToolEvent(name=name, ok=True, summary=summary, payload=dict(payload or {}))
    return CommandExecutionResult(
        assistant_text=summary,
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=name,
            arguments=dict(arguments or {}) or None,
            ok=True,
            summary=summary,
            structured_content=dict(payload or {}) or None,
        ),
    )


class _WriteCompletesSessionTools(_AppServerTools):
    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        on_activity=None,
    ) -> ToolEvent:
        session = self._sessions.get(session_id)
        if session is None or not session.get("active"):
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        if chars.strip() != "exit":
            return super().shell_write_stdin(
                session_id,
                chars,
                yield_time_ms=yield_time_ms,
                on_activity=on_activity,
            )
        session["active"] = False
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell rc=0",
            payload={
                "phase": "completed",
                "command": str(session.get("command") or ""),
                "session_id": session_id,
                "call_id": str(session.get("call_id") or ""),
                "process_id": session_id,
                "returncode": 0,
                "exit_code": 0,
                "stdout": "bye\n",
                "stderr": "",
                "aggregated_output": "bye\n",
                "status": "ok",
                "yield_time_ms": int(yield_time_ms) if yield_time_ms is not None else None,
                "lifecycle": self._lifecycle(
                    phase="completed",
                    kind="end",
                    call_id=str(session.get("call_id") or ""),
                    session_id=session_id,
                    process_id=session_id,
                    status="ok",
                ),
            },
        )


class _PipedStringIO(io.StringIO):
    def isatty(self) -> bool:
        return False


class _AsyncInputPipe:
    def __init__(self) -> None:
        self._lines: list[str] = []
        self._closed = False
        self._condition = threading.Condition()

    def push_json(self, payload: dict[str, Any]) -> None:
        self.push_line(json.dumps(payload))

    def push_line(self, line: str) -> None:
        with self._condition:
            self._lines.append(line if line.endswith("\n") else f"{line}\n")
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def isatty(self) -> bool:
        return False

    def __iter__(self):
        return self

    def __next__(self) -> str:
        with self._condition:
            while not self._lines and not self._closed:
                self._condition.wait(timeout=0.1)
            if self._lines:
                return self._lines.pop(0)
            raise StopIteration


class _ObservedOutputBuffer:
    def __init__(self) -> None:
        self._buffer = ""
        self._lines: list[dict[str, Any]] = []
        self._condition = threading.Condition()

    def write(self, text: str) -> int:
        with self._condition:
            self._buffer += text
            while "\n" in self._buffer:
                raw_line, self._buffer = self._buffer.split("\n", 1)
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                self._lines.append(json.loads(raw_line))
            self._condition.notify_all()
        return len(text)

    def flush(self) -> None:
        return None

    def wait_for_line(
        self, predicate: Callable[[dict[str, Any]], bool], *, timeout: float = 5.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                for line in self._lines:
                    if predicate(line):
                        return line
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError("Timed out waiting for app-server output")
                self._condition.wait(timeout=min(remaining, 0.1))

    def lines(self) -> list[dict[str, Any]]:
        with self._condition:
            return [dict(line) for line in self._lines]


class _FakeBrowserActionExecutor:
    def __call__(self, action_request) -> ActionResult:
        browser_request = dict((action_request.payload or {}).get("browser_request") or {})
        command = str(browser_request.get("action") or "snapshot")
        return ActionResult(
            ok=True,
            action=str(action_request.action_type or ""),
            summary=f"executed {command}",
            output={
                "ok": True,
                "action": command,
                "target_id": str(browser_request.get("target_id") or "tab-1"),
                "path": f"/tmp/{command}.txt",
            },
        )


class _SubscribeCompletedAppServerTools(_AppServerTools):
    def shell_start(self, command: str, *, on_activity=None) -> dict[str, object]:
        result = super().shell_start(command, on_activity=on_activity)
        session_id = str(result.get("session_id") or "")
        call_id = str(result.get("call_id") or "")
        self._sessions[session_id]["active"] = False
        self._sessions[session_id]["completed_payload"] = {
            "phase": "completed",
            "command": command,
            "session_id": session_id,
            "process_id": session_id,
            "call_id": call_id,
            "returncode": 0,
            "exit_code": 0,
            "stdout": "approval instant complete\n",
            "stderr": "",
            "aggregated_output": "approval instant complete\n",
            "output_text": "approval instant complete\n",
            "duration_ms": 1,
            "interrupted": False,
            "timed_out": False,
            "ok": True,
            "status": "ok",
            "lifecycle": self._lifecycle(
                phase="completed",
                kind="end",
                call_id=call_id,
                session_id=session_id,
                process_id=session_id,
                status="ok",
            ),
        }
        return result

    def shell_subscribe(self, session_id: str, *, on_activity=None) -> ToolEvent:
        session = dict(self._sessions.get(session_id) or {})
        if not session:
            return ToolEvent(
                name="shell",
                ok=False,
                summary="shell session missing",
                payload={"session_id": session_id, "status": "missing"},
            )
        call_id = str(session.get("call_id") or "")
        if on_activity is not None:
            on_activity(
                {
                    "phase": "subscribe",
                    "command": str(session.get("command") or ""),
                    "session_id": session_id,
                    "process_id": session_id,
                    "call_id": call_id,
                    "status": "subscribed",
                    "lifecycle": self._lifecycle(
                        phase="subscribe",
                        kind="subscribe",
                        call_id=call_id,
                        session_id=session_id,
                        process_id=session_id,
                        status="subscribed",
                    ),
                }
            )
            completed_payload = dict(session.get("completed_payload") or {})
            if completed_payload:
                on_activity(completed_payload)
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell session subscribed",
            payload={
                "session_id": session_id,
                "call_id": call_id,
                "process_id": session_id,
                "command": str(session.get("command") or ""),
                "status": "subscribed",
                "lifecycle": self._lifecycle(
                    phase="subscribe",
                    kind="subscribe",
                    call_id=call_id,
                    session_id=session_id,
                    process_id=session_id,
                    status="subscribed",
                ),
            },
        )


class AppServerProtocolTest(unittest.TestCase):
    @staticmethod
    def _direct_exec_policy() -> RuntimePolicy:
        return RuntimePolicy.normalized(approval_policy="never")

    @staticmethod
    def _demo_plugin_path() -> Path:
        return ROOT / "plugins" / "demo_plugin"

    def _build_gateway_runtime(self, root: Path) -> AgentCliRuntime:
        source_root = root / "source"
        plugins_root = root / "plugins_target"
        state_path = root / "plugin_state.json"
        source_root.mkdir(parents=True, exist_ok=True)
        copied = source_root / "demo_plugin"
        shutil.copytree(self._demo_plugin_path(), copied)
        (copied / "runtime.py").write_text(
            "\n".join(
                [
                    "from cli.agent_cli.host.plugin_hooks import RuntimeHooks",
                    "",
                    "def runtime_hooks():",
                    "    return RuntimeHooks(",
                    "        build_connector_registrations=lambda plugin_name='demo_plugin': [",
                    "            {",
                    "                'connector_key': 'demo_webhook',",
                    "                'plugin_name': plugin_name,",
                    "                'display_name': 'Demo Webhook',",
                    "                'version': '1',",
                    "                'connector_kind': 'inbound',",
                    "                'supports_webhook': True,",
                    "                'supports_polling': False,",
                    "                'supports_actions': False,",
                    "                'event_types': ['demo.event'],",
                    "                'action_types': [],",
                    "            }",
                    "        ],",
                    "        build_trigger_registrations=lambda: [",
                    "            {",
                    "                'trigger_key': 'demo_trigger',",
                    "                'plugin_name': 'demo_plugin',",
                    "                'trigger_kind': 'event',",
                    "                'connector_key': 'demo_webhook',",
                    "                'event_types': ['demo.event'],",
                    "                'workflow_name': 'handle_demo_event',",
                    "                'priority': 10,",
                    "            }",
                    "        ],",
                    "    )",
                ]
            ),
            encoding="utf-8",
        )

        manager = PluginManager(plugin_root=plugins_root, state_path=state_path)
        installed = manager.install_plugin(str(copied))
        self.assertTrue(installed["ok"])

        tools = ToolRegistry()
        tools._plugin_manager = manager
        return AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=tools,
            runtime_policy=self._direct_exec_policy(),
        )

    def _run_app_server_requests(
        self, runtime: AgentCliRuntime, requests: list[dict]
    ) -> list[dict]:
        lines = "\n".join(json.dumps(item) for item in requests) + "\n"
        stdin = _PipedStringIO(lines)
        stdout = io.StringIO()
        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]

    def setUp(self) -> None:
        self.runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )

    @staticmethod
    def _codex_openai_config() -> ProviderConfig:
        return ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            interaction_profile="codex_openai",
            interaction_profile_source="test",
        )

    def test_rejects_requests_before_initialize(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(json.dumps({"id": 1, "method": "session/providerStatus"}) + "\n")

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(code, 0)
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["error"]["code"], -32002)
        self.assertEqual(payload["error"]["message"], APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED)
        self.assertEqual(
            payload["error"]["data"], {"detail": APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED}
        )

    def test_initialize_and_initialized_handshake(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "init-1",
                            "method": "initialize",
                            "params": {"clientInfo": {"name": "test-client", "version": "1.0.0"}},
                        }
                    ),
                    json.dumps({"method": "initialized", "params": {"ready": True}}),
                    json.dumps({"id": "ping-1", "method": "server/ping"}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["id"], "init-1")
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "agent_cli_app_server")
        self.assertEqual(lines[0]["result"]["platformFamily"], "windows")
        methods = list(lines[0]["result"]["capabilities"]["methods"])
        self.assertEqual(app_server_capability_methods(), list(APP_SERVER_CAPABILITY_METHODS))
        self.assertEqual(methods, list(APP_SERVER_CAPABILITY_METHODS))
        self.assertEqual(
            app_server_gateway_extension_methods(),
            list(APP_SERVER_GATEWAY_EXTENSION_METHODS),
        )
        self.assertEqual(
            list(APP_SERVER_GATEWAY_EXTENSION_METHODS),
            list(EXPECTED_APP_SERVER_GATEWAY_EXTENSION_METHODS),
        )
        self.assertEqual(len(methods), len(set(methods)))
        self.assertIn("gateway/dispatch", lines[0]["result"]["capabilities"]["methods"])
        self.assertIn("gateway/webhook", lines[0]["result"]["capabilities"]["methods"])
        self.assertIn("action/execute", lines[0]["result"]["capabilities"]["methods"])
        self.assertIn("session/run", lines[0]["result"]["capabilities"]["methods"])
        self.assertIn("browser/proxy", lines[0]["result"]["capabilities"]["methods"])
        self.assertEqual(lines[1]["id"], "ping-1")
        self.assertTrue(lines[1]["result"]["ok"])

    def test_initialize_requires_initialized_notification_before_followup(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"id": "ping", "method": "server/ping", "params": {}},
            ],
        )
        ping = next(item for item in lines if item.get("id") == "ping")
        self.assertEqual(ping["error"]["code"], -32002)
        self.assertEqual(ping["error"]["message"], APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED)
        self.assertEqual(ping["error"]["data"], {"detail": APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED})

    def test_supported_reference_method_bridges_thread_read_fork_turn_start_model_and_mcp_status(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")

            runtime1 = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            bootstrap_lines = self._run_app_server_requests(
                runtime1,
                [
                    {"id": "init", "method": "initialize", "params": {}},
                    {"method": "initialized", "params": {}},
                    {
                        "id": "thread-start",
                        "method": "thread/start",
                        "params": {"name": "Morning", "cwd": str(workspace)},
                    },
                    {
                        "id": "run",
                        "method": "session/run",
                        "params": {"prompt": "list current directory"},
                    },
                ],
            )
            thread_id = next(line for line in bootstrap_lines if line.get("id") == "thread-start")[
                "result"
            ]["thread"]["thread_id"]

            class _McpAwareTools(_AppServerTools):
                def capabilities(self) -> dict:
                    payload = super().capabilities()
                    payload["mcp_servers"] = {
                        "atlas": {"status": "connected", "enabled": True, "scope": "workspace"},
                    }
                    return payload

            runtime2 = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_McpAwareTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            lines = self._run_app_server_requests(
                runtime2,
                [
                    {"id": "init2", "method": "initialize", "params": {}},
                    {"method": "initialized", "params": {}},
                    {
                        "id": "read-summary",
                        "method": "thread/read",
                        "params": {"threadId": thread_id},
                    },
                    {
                        "id": "read-full",
                        "method": "thread/read",
                        "params": {"threadId": thread_id, "includeTurns": True},
                    },
                    {"id": "fork", "method": "thread/fork", "params": {"threadId": thread_id}},
                    {
                        "id": "turn",
                        "method": "turn/start",
                        "params": {
                            "threadId": thread_id,
                            "input": [{"type": "text", "text": "list current directory"}],
                        },
                    },
                    {"id": "models", "method": "model/list", "params": {}},
                    {"id": "mcp", "method": "mcpServerStatus/list", "params": {}},
                ],
            )

            read_summary = next(line for line in lines if line.get("id") == "read-summary")
            read_full = next(line for line in lines if line.get("id") == "read-full")
            fork = next(line for line in lines if line.get("id") == "fork")
            turn = next(line for line in lines if line.get("id") == "turn")
            models = next(line for line in lines if line.get("id") == "models")
            mcp = next(line for line in lines if line.get("id") == "mcp")
            thread_started = next(line for line in lines if line.get("method") == "thread/started")
            turn_started = next(line for line in lines if line.get("method") == "turn/started")
            item_started = next(line for line in lines if line.get("method") == "item/started")
            command_output_delta = next(
                line for line in lines if line.get("method") == "item/commandExecution/outputDelta"
            )
            item_completed = next(
                line
                for line in lines
                if line.get("method") == "item/completed"
                and dict(line.get("params") or {}).get("item", {}).get("type") == "commandExecution"
            )
            turn_completed = next(line for line in lines if line.get("method") == "turn/completed")
            turn_index = next(index for index, line in enumerate(lines) if line.get("id") == "turn")
            turn_started_index = next(
                index for index, line in enumerate(lines) if line.get("method") == "turn/started"
            )
            item_started_index = next(
                index for index, line in enumerate(lines) if line.get("method") == "item/started"
            )
            command_output_delta_index = next(
                index
                for index, line in enumerate(lines)
                if line.get("method") == "item/commandExecution/outputDelta"
            )
            item_completed_index = next(
                index
                for index, line in enumerate(lines)
                if line.get("method") == "item/completed"
                and dict(line.get("params") or {}).get("item", {}).get("type") == "commandExecution"
            )
            turn_completed_index = next(
                index for index, line in enumerate(lines) if line.get("method") == "turn/completed"
            )

            self.assertEqual(read_summary["result"]["thread"]["id"], thread_id)
            self.assertEqual(read_summary["result"]["thread"]["status"], "notLoaded")
            self.assertEqual(read_summary["result"]["thread"]["turns"], [])

            self.assertEqual(read_full["result"]["thread"]["id"], thread_id)
            self.assertEqual(read_full["result"]["thread"]["status"], "notLoaded")
            self.assertEqual(len(read_full["result"]["thread"]["turns"]), 1)
            self.assertEqual(read_full["result"]["thread"]["turns"][0]["status"], "completed")
            self.assertEqual(
                read_full["result"]["thread"]["turns"][0]["items"][0]["type"], "userMessage"
            )

            self.assertNotEqual(fork["result"]["thread"]["id"], thread_id)
            self.assertEqual(fork["result"]["thread"]["status"], "idle")
            self.assertTrue(fork["result"]["thread"]["turns"])
            self.assertEqual(fork["result"]["approvalPolicy"], "never")
            self.assertEqual(fork["result"]["sandbox"]["type"], "workspaceWrite")
            self.assertEqual(fork["result"]["sandbox"]["writableRoots"], [fork["result"]["cwd"]])
            self.assertIsNone(fork["result"]["reasoningEffort"])
            self.assertIsNone(fork["result"]["serviceTier"])
            self.assertEqual(
                thread_started["params"]["thread"]["id"], fork["result"]["thread"]["id"]
            )

            self.assertEqual(turn["result"]["turn"]["status"], "inProgress")
            self.assertLess(turn_index, turn_started_index)
            self.assertLess(turn_started_index, item_started_index)
            self.assertLess(item_started_index, command_output_delta_index)
            self.assertLess(command_output_delta_index, item_completed_index)
            self.assertLess(item_completed_index, turn_completed_index)
            self.assertEqual(turn_started["params"]["threadId"], thread_id)
            self.assertEqual(turn_started["params"]["turn"]["id"], turn["result"]["turn"]["id"])
            self.assertEqual(turn_started["params"]["turn"]["status"], "inProgress")
            self.assertEqual(item_started["params"]["threadId"], thread_id)
            self.assertEqual(item_started["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(item_started["params"]["item"]["type"], "commandExecution")
            self.assertEqual(item_started["params"]["item"]["status"], "inProgress")
            self.assertEqual(command_output_delta["params"]["threadId"], thread_id)
            self.assertEqual(command_output_delta["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(
                command_output_delta["params"]["itemId"], item_started["params"]["item"]["id"]
            )
            self.assertEqual(command_output_delta["params"]["delta"], "a.txt\nb.txt")
            self.assertEqual(item_completed["params"]["threadId"], thread_id)
            self.assertEqual(item_completed["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(
                item_completed["params"]["item"]["id"], item_started["params"]["item"]["id"]
            )
            self.assertEqual(item_completed["params"]["item"]["type"], "commandExecution")
            self.assertEqual(item_completed["params"]["item"]["status"], "completed")
            self.assertEqual(item_completed["params"]["item"]["aggregatedOutput"], "a.txt\nb.txt")
            self.assertEqual(turn_completed["params"]["threadId"], thread_id)
            self.assertEqual(turn_completed["params"]["turn"]["id"], turn["result"]["turn"]["id"])
            self.assertEqual(turn_completed["params"]["turn"]["status"], "completed")

            model_ids = {item["model"] for item in models["result"]["data"]}
            self.assertIn("deepseek-reasoner", model_ids)
            self.assertTrue(any(item["isDefault"] for item in models["result"]["data"]))

            self.assertEqual(mcp["result"]["data"][0]["name"], "atlas")
            self.assertEqual(mcp["result"]["data"][0]["authStatus"], "unsupported")

    def test_thread_start_codex_sidecar_engine_switches_runtime_and_model_catalog(self) -> None:
        class _SidecarKernelDouble:
            def __init__(self, **kwargs) -> None:
                self.requests = []
                self.kwargs = kwargs

            async def start_session(self, request):
                self.requests.append(request)
                return KernelSession(
                    engine="codex_sidecar",
                    session_id="session-1",
                    thread_id="thread-sidecar",
                    thread_name="Sidecar",
                    cwd=str(Path("/tmp/sidecar-work").resolve()),
                    model="gpt-fake",
                    model_provider="openai",
                    metadata={"thread_path": "/tmp/thread-sidecar.json"},
                )

            async def fork_session(self, request):
                self.requests.append(request)
                return KernelSession(
                    engine="codex_sidecar",
                    session_id="thread-sidecar-fork",
                    thread_id="thread-sidecar-fork",
                    thread_name="Sidecar Fork",
                    cwd=str(Path("/tmp/sidecar-work").resolve()),
                    model="gpt-fake",
                    model_provider="openai",
                    metadata={
                        **dict(request.metadata or {}),
                        "raw_result": {
                            "thread": {
                                "id": "thread-sidecar-fork",
                                "name": "Sidecar Fork",
                                "cwd": str(Path("/tmp/sidecar-work").resolve()),
                            }
                        },
                    },
                )

            def list_models(self, **_kwargs):
                return {
                    "data": [
                        {
                            "id": "gpt-fake",
                            "model": "gpt-fake",
                            "displayName": "GPT Fake",
                            "providerName": "openai",
                            "supportedReasoningEfforts": ["low", "medium"],
                            "defaultReasoningEffort": "medium",
                            "hidden": False,
                        }
                    ],
                    "nextCursor": None,
                }

            def read_model_provider_capabilities(self):
                return {"namespaceTools": True, "webSearch": True}

            async def aclose(self):
                return None

        kernels = []

        def kernel_factory(**kwargs):
            kernel = _SidecarKernelDouble(**kwargs)
            kernels.append(kernel)
            return kernel

        with patch("cli.agent_cli.app_server.CodexSidecarKernel", side_effect=kernel_factory):
            lines = self._run_app_server_requests(
                self.runtime,
                [
                    {"id": "init", "method": "initialize", "params": {}},
                    {"method": "initialized", "params": {}},
                    {
                        "id": "thread-start",
                        "method": "thread/start",
                        "params": {
                            "engine": "codex_sidecar",
                            "name": "Sidecar",
                            "cwd": "/tmp/sidecar-work",
                            "model": "gpt-fake",
                            "modelProvider": "openai",
                            "approvalPolicy": "never",
                        },
                    },
                    {
                        "id": "fork",
                        "method": "thread/fork",
                        "params": {
                            "threadId": "thread-sidecar",
                            "approvalPolicy": "never",
                            "sandbox": "workspace-write",
                        },
                    },
                    {"id": "models", "method": "model/list", "params": {}},
                ],
            )

        started = next(line for line in lines if line.get("id") == "thread-start")
        fork = next(line for line in lines if line.get("id") == "fork")
        models = next(line for line in lines if line.get("id") == "models")
        thread = started["result"]["thread"]
        self.assertEqual(thread["thread_id"], "thread-sidecar")
        self.assertEqual(thread["metadata"]["runtime_kernel"], "codex_sidecar")
        self.assertEqual(started["result"]["provider_status"]["provider_source"], "codex_sidecar")
        self.assertEqual(started["result"]["approval_policy"], "never")
        self.assertEqual(fork["result"]["thread"]["thread_id"], "thread-sidecar-fork")
        self.assertEqual(fork["result"]["approvalPolicy"], "never")
        self.assertEqual(fork["result"]["sandbox"]["type"], "workspaceWrite")
        self.assertEqual(models["result"]["data"][0]["id"], "gpt-fake")
        self.assertEqual(models["result"]["data"][0]["providerName"], "openai")
        self.assertEqual(kernels[0].kwargs["cwd"], "/tmp/sidecar-work")
        self.assertEqual(kernels[0].requests[0].model_provider, "openai")
        self.assertEqual(kernels[0].requests[0].metadata["approvalPolicy"], "never")

    def test_thread_start_codex_sidecar_omits_default_model_provider(self) -> None:
        class _SidecarKernelDouble:
            def __init__(self, **kwargs) -> None:
                self.requests = []
                self.kwargs = kwargs

            async def start_session(self, request):
                self.requests.append(request)
                return KernelSession(
                    engine="codex_sidecar",
                    session_id="session-1",
                    thread_id="thread-sidecar",
                    cwd=str(Path("/tmp/sidecar-work").resolve()),
                    model_provider="codex",
                )

            async def aclose(self):
                return None

        kernels = []

        def kernel_factory(**kwargs):
            kernel = _SidecarKernelDouble(**kwargs)
            kernels.append(kernel)
            return kernel

        with patch("cli.agent_cli.app_server.CodexSidecarKernel", side_effect=kernel_factory):
            lines = self._run_app_server_requests(
                self.runtime,
                [
                    {"id": "init", "method": "initialize", "params": {}},
                    {"method": "initialized", "params": {}},
                    {
                        "id": "thread-start",
                        "method": "thread/start",
                        "params": {
                            "engine": "codex_sidecar",
                            "cwd": "/tmp/sidecar-work",
                        },
                    },
                ],
            )

        started = next(line for line in lines if line.get("id") == "thread-start")
        self.assertEqual(started["result"]["provider_status"]["provider_name"], "codex")
        self.assertEqual(kernels[0].kwargs["cwd"], "/tmp/sidecar-work")
        self.assertIsNone(kernels[0].requests[0].model_provider)

    def test_codex_sidecar_thread_start_turn_model_read_and_fork_with_fake_sidecar(self) -> None:
        fake_codex_bin = ROOT / "cli" / "tests" / "fixtures" / "fake_codex_sidecar.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "fake-sidecar-state.json"
            env = {
                "AGENTHUB_CODEX_SIDECAR_TEST_BIN": str(fake_codex_bin),
                "FAKE_CODEX_SIDECAR_STATE": str(state_path),
            }
            with patch.dict(os.environ, env, clear=False):
                lines = self._run_app_server_requests(
                    self.runtime,
                    [
                        {"id": "init", "method": "initialize", "params": {}},
                        {"method": "initialized", "params": {}},
                        {
                            "id": "thread-start",
                            "method": "thread/start",
                            "params": {"engine": "codex_sidecar", "modelProvider": "openai"},
                        },
                        {"id": "models", "method": "model/list", "params": {}},
                        {
                            "id": "turn",
                            "method": "turn/start",
                            "params": {
                                "threadId": "thread-1",
                                "input": [{"type": "text", "text": "hello sidecar"}],
                            },
                        },
                    ],
                )

            thread_start = next(line for line in lines if line.get("id") == "thread-start")
            models = next(line for line in lines if line.get("id") == "models")
            turn = next(line for line in lines if line.get("id") == "turn")
            agent_delta = next(
                line for line in lines if line.get("method") == "item/agentMessage/delta"
            )
            command_output_delta = next(
                line for line in lines if line.get("method") == "item/commandExecution/outputDelta"
            )
            completed = [line for line in lines if line.get("method") == "turn/completed"]

            self.assertEqual(thread_start["result"]["thread"]["thread_id"], "thread-1")
            self.assertEqual(
                thread_start["result"]["provider_status"]["provider_source"],
                "codex_sidecar",
            )
            self.assertEqual(models["result"]["data"][0]["model"], "gpt-fake-default")
            self.assertEqual(turn["result"]["turn"]["status"], "inProgress")
            self.assertEqual(agent_delta["params"]["delta"], "fake sidecar reply")
            self.assertEqual(command_output_delta["params"]["delta"], "ok\n")
            self.assertTrue(completed)

            with patch.dict(os.environ, env, clear=False):
                lines = self._run_app_server_requests(
                    self.runtime,
                    [
                        {"id": "init", "method": "initialize", "params": {}},
                        {"method": "initialized", "params": {}},
                        {
                            "id": "resume",
                            "method": "thread/resume",
                            "params": {"engine": "codex_sidecar", "threadId": "thread-1"},
                        },
                        {
                            "id": "read",
                            "method": "thread/read",
                            "params": {"threadId": "thread-1", "includeTurns": True},
                        },
                        {
                            "id": "fork",
                            "method": "thread/fork",
                            "params": {"threadId": "thread-1"},
                        },
                    ],
                )

            resume = next(line for line in lines if line.get("id") == "resume")
            read = next(line for line in lines if line.get("id") == "read")
            fork = next(line for line in lines if line.get("id") == "fork")
            self.assertEqual(resume["result"]["thread"]["thread_id"], "thread-1")
            self.assertEqual(
                read["result"]["thread"]["turns"][0]["items"][1]["text"],
                "fake sidecar reply",
            )
            self.assertEqual(fork["result"]["thread"]["thread_id"], "thread-2")

    def test_turn_start_emits_plan_updates_plan_delta_and_raw_response_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=ThreadStore(Path(temp_dir)),
                runtime_policy=self._direct_exec_policy(),
            )

            plan_text = "# Final plan\n- first\n- second\n"
            turn_events = [
                {"type": "turn.started"},
                {
                    "type": "item.started",
                    "item": {
                        "id": "todo_1",
                        "type": "todo_list",
                        "items": [
                            {"text": "inspect", "completed": True},
                            {"text": "patch", "completed": False},
                        ],
                        "explanation": "sync",
                        "plan": [
                            {"step": "inspect", "status": "completed"},
                            {"step": "patch", "status": "in_progress"},
                        ],
                    },
                },
                {
                    "type": "item.started",
                    "item": {
                        "id": "plan_1",
                        "type": "plan",
                        "text": plan_text,
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "plan_1",
                        "type": "plan",
                        "text": plan_text,
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "msg_1",
                        "type": "agent_message",
                        "text": "done",
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                },
            ]

            def _handle_prompt(text: str, *, attachments=None) -> PromptResponse:
                del attachments
                if runtime.turn_event_callback is not None:
                    for event in turn_events:
                        runtime.turn_event_callback(dict(event))
                return PromptResponse(
                    user_text=text,
                    assistant_text="done",
                    response_items=[
                        ResponseInputItem(
                            item_type="reasoning",
                            content=[{"type": "reasoning", "text": "先看计划"}],
                            extra={"summary": ["先看计划"]},
                        ),
                        ResponseInputItem(
                            item_type="message",
                            role="assistant",
                            content=[{"type": "output_text", "text": "done"}],
                            extra={"id": "raw_msg_1"},
                        ),
                    ],
                    turn_events=[dict(event) for event in turn_events],
                    status=runtime.agent.provider_status(),
                )

            runtime.handle_prompt = _handle_prompt
            thread_id = str(runtime.start_thread().get("thread_id") or "")

            lines = self._run_app_server_requests(
                runtime,
                [
                    {"id": "init", "method": "initialize", "params": {}},
                    {"method": "initialized", "params": {}},
                    {
                        "id": "turn",
                        "method": "turn/start",
                        "params": {
                            "threadId": thread_id,
                            "input": [{"type": "text", "text": "Plan this"}],
                        },
                    },
                ],
            )

            turn = next(line for line in lines if line.get("id") == "turn")
            turn_plan_updated = next(
                line for line in lines if line.get("method") == "turn/plan/updated"
            )
            plan_delta = next(line for line in lines if line.get("method") == "item/plan/delta")
            raw_items = [
                line for line in lines if line.get("method") == "rawResponseItem/completed"
            ]
            turn_completed = next(line for line in lines if line.get("method") == "turn/completed")

            self.assertEqual(turn["result"]["turn"]["status"], "inProgress")
            self.assertEqual(turn_plan_updated["params"]["threadId"], thread_id)
            self.assertEqual(turn_plan_updated["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(turn_plan_updated["params"]["explanation"], "sync")
            self.assertEqual(
                turn_plan_updated["params"]["plan"],
                [
                    {"step": "inspect", "status": "completed"},
                    {"step": "patch", "status": "inProgress"},
                ],
            )
            self.assertEqual(plan_delta["params"]["threadId"], thread_id)
            self.assertEqual(plan_delta["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(plan_delta["params"]["itemId"], "plan_1")
            self.assertEqual(plan_delta["params"]["delta"], plan_text)
            self.assertEqual(len(raw_items), 2)
            self.assertEqual(raw_items[0]["params"]["threadId"], thread_id)
            self.assertEqual(raw_items[0]["params"]["turnId"], turn["result"]["turn"]["id"])
            self.assertEqual(raw_items[0]["params"]["item"]["type"], "reasoning")
            self.assertEqual(raw_items[1]["params"]["item"]["type"], "message")

            raw_indices = [
                index
                for index, line in enumerate(lines)
                if line.get("method") == "rawResponseItem/completed"
            ]
            turn_completed_index = next(
                index for index, line in enumerate(lines) if line.get("method") == "turn/completed"
            )
            self.assertTrue(all(index < turn_completed_index for index in raw_indices))
            self.assertEqual(turn_completed["params"]["turn"]["status"], "completed")

    def test_model_list_supports_cursor_and_include_hidden(self) -> None:
        class _ModelAgent(_AppServerAgent):
            def available_models(self, provider_name: str | None = None) -> list[dict[str, str]]:
                del provider_name
                return [
                    {
                        "model_key": "visible_one",
                        "provider_name": "openai",
                        "model_id": "gpt-5.4",
                        "display_name": "GPT-5.4",
                        "planner_kind": "openai_responses",
                        "wire_api": "responses",
                        "supports_tools": "true",
                        "supports_reasoning": "true",
                        "default_reasoning_effort": "high",
                    },
                    {
                        "model_key": "hidden_one",
                        "provider_name": "openai",
                        "model_id": "gpt-5.4-mini",
                        "display_name": "GPT-5.4 Mini",
                        "planner_kind": "openai_responses",
                        "wire_api": "responses",
                        "supports_tools": "true",
                        "supports_reasoning": "true",
                        "hidden": True,
                    },
                    {
                        "model_key": "visible_two",
                        "provider_name": "deepseek",
                        "model_id": "deepseek-reasoner",
                        "display_name": "DeepSeek Reasoner",
                        "planner_kind": "deepseek_reasoner",
                        "wire_api": "responses",
                        "supports_tools": "true",
                        "supports_reasoning": "true",
                        "show_in_picker": True,
                    },
                ]

        runtime = AgentCliRuntime(
            agent=_ModelAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {"id": "page1", "method": "model/list", "params": {"limit": 1}},
                {"id": "page2", "method": "model/list", "params": {"cursor": "1", "limit": 1}},
                {"id": "all", "method": "model/list", "params": {"includeHidden": True}},
                {"id": "bad", "method": "model/list", "params": {"cursor": "bad"}},
            ],
        )

        page1 = next(line for line in lines if line.get("id") == "page1")
        page2 = next(line for line in lines if line.get("id") == "page2")
        all_models = next(line for line in lines if line.get("id") == "all")
        bad = next(line for line in lines if line.get("id") == "bad")

        self.assertEqual([item["id"] for item in page1["result"]["data"]], ["visible_one"])
        self.assertEqual(page1["result"]["nextCursor"], "1")
        self.assertEqual([item["id"] for item in page2["result"]["data"]], ["visible_two"])
        self.assertIsNone(page2["result"]["nextCursor"])
        self.assertEqual(page1["result"]["data"][0]["defaultReasoningEffort"], "high")
        self.assertFalse(any(item["hidden"] for item in page1["result"]["data"]))

        all_ids = [item["id"] for item in all_models["result"]["data"]]
        self.assertEqual(all_ids, ["visible_one", "hidden_one", "visible_two"])
        hidden_model = next(
            item for item in all_models["result"]["data"] if item["id"] == "hidden_one"
        )
        self.assertTrue(hidden_model["hidden"])

        self.assertEqual(bad["error"]["code"], -32602)
        self.assertEqual(bad["error"]["message"], "Invalid params")
        self.assertEqual(bad["error"]["data"], {"detail": "invalid cursor: bad"})

    def test_mcp_server_status_list_supports_cursor(self) -> None:
        class _McpTools(_AppServerTools):
            def capabilities(self) -> dict:
                payload = super().capabilities()
                payload["mcp_server_entries"] = [
                    {"name": "atlas", "status": "connected", "enabled": True, "scope": "workspace"},
                    {
                        "name": "docs",
                        "status": "login_required",
                        "enabled": True,
                        "scope": "global",
                    },
                    {"name": "ops", "status": "connected", "enabled": False, "scope": "workspace"},
                ]
                return payload

        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_McpTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {"id": "page1", "method": "mcpServerStatus/list", "params": {"limit": 2}},
                {
                    "id": "page2",
                    "method": "mcpServerStatus/list",
                    "params": {"cursor": "2", "limit": 2},
                },
                {"id": "bad", "method": "mcpServerStatus/list", "params": {"cursor": "bad"}},
            ],
        )

        page1 = next(line for line in lines if line.get("id") == "page1")
        page2 = next(line for line in lines if line.get("id") == "page2")
        bad = next(line for line in lines if line.get("id") == "bad")

        self.assertEqual([item["name"] for item in page1["result"]["data"]], ["atlas", "docs"])
        self.assertEqual(page1["result"]["nextCursor"], "2")
        self.assertEqual(page1["result"]["data"][1]["authStatus"], "notLoggedIn")
        self.assertEqual([item["name"] for item in page2["result"]["data"]], ["ops"])
        self.assertIsNone(page2["result"]["nextCursor"])

        self.assertEqual(bad["error"]["code"], -32602)
        self.assertEqual(bad["error"]["message"], "Invalid params")
        self.assertEqual(bad["error"]["data"], {"detail": "invalid cursor: bad"})

    def test_returns_compatibility_hint_for_known_unsupported_reference_methods(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {"id": "unsupported-skills", "method": "skills/list", "params": {}},
                {
                    "id": "unsupported-turn",
                    "method": "turn/interrupt",
                    "params": {"threadId": "thr_1", "turnId": "turn_1"},
                },
            ],
        )
        skills_error = next(
            item["error"] for item in lines if item.get("id") == "unsupported-skills"
        )
        turn_error = next(item["error"] for item in lines if item.get("id") == "unsupported-turn")

        self.assertEqual(skills_error["code"], -32601)
        self.assertEqual(skills_error["message"], APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)
        self.assertEqual(
            skills_error["data"],
            {
                "detail": "skills/list",
                "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
                "replacement": "tools/list",
            },
        )
        self.assertEqual(turn_error["code"], -32601)
        self.assertEqual(
            turn_error["data"],
            {
                "detail": "turn/interrupt",
                "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
                "replacement": "session/interrupt",
            },
        )

    def test_unsupported_reference_replacement_matrix_guard(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "m1",
                    "method": "turn/interrupt",
                    "params": {"threadId": "thr_1", "turnId": "turn_1"},
                },
                {"id": "m2", "method": "skills/list", "params": {}},
                {"id": "m3", "method": "config/read", "params": {}},
            ],
        )
        expected = {
            "turn/interrupt": "session/interrupt",
            "skills/list": "tools/list",
            "config/read": "session/providerStatus",
        }
        for request_id, method in [
            ("m1", "turn/interrupt"),
            ("m2", "skills/list"),
            ("m3", "config/read"),
        ]:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = payload["error"]
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)
            self.assertEqual(error["data"]["detail"], method)
            self.assertEqual(
                error["data"]["compatibility"],
                APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            )
            replacement = error["data"]["replacement"]
            self.assertEqual(replacement, expected[method])
            self.assertIsInstance(replacement, str)
            self.assertTrue(replacement.strip())
            self.assertNotEqual(replacement, method)
            self.assertNotIn("unsupported", replacement.casefold())
            self.assertNotIn("unknown", replacement.casefold())

    def test_unsupported_replacement_field_guard_for_two_methods_with_variant_requests(
        self,
    ) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "turn-1",
                    "method": "turn/interrupt",
                    "params": {"threadId": "thr_1", "turnId": "turn_1"},
                },
                {
                    "id": "turn-2",
                    "method": "turn/interrupt",
                    "params": {"threadId": "thr_2", "turnId": "turn_2"},
                },
                {"id": "skills-1", "method": "skills/list", "params": {}},
                {"id": "skills-2", "method": "skills/list", "params": {"limit": 5}},
            ],
        )
        request_matrix = [
            ("turn-1", "turn/interrupt"),
            ("turn-2", "turn/interrupt"),
            ("skills-1", "skills/list"),
            ("skills-2", "skills/list"),
        ]
        replacements_by_method: dict[str, set[str]] = {}
        for request_id, method in request_matrix:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload.get("error") or {})
            self.assertEqual(error.get("code"), -32601)
            self.assertEqual(error.get("message"), APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)
            data = dict(error.get("data") or {})
            self.assertEqual(data.get("detail"), method)
            self.assertEqual(
                data.get("compatibility"),
                APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
            )
            self.assertIn("replacement", data)
            replacement = str(data.get("replacement") or "").strip()
            self.assertTrue(replacement)
            replacements_by_method.setdefault(method, set()).add(replacement)

        self.assertEqual(
            replacements_by_method["turn/interrupt"],
            {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["turn/interrupt"])},
        )
        self.assertEqual(
            replacements_by_method["skills/list"],
            {str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"])},
        )

    def test_unsupported_reference_method_matrix_not_initialized_invalid_params_and_not_found(
        self,
    ) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            json.dumps({"id": "pre-init", "method": "skills/list", "params": {}}) + "\n"
        )
        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        pre_init = json.loads(stdout.getvalue().strip())
        self.assertEqual(pre_init["error"]["code"], -32002)
        self.assertEqual(pre_init["error"]["message"], APP_SERVER_ERROR_MESSAGE_NOT_INITIALIZED)
        self.assertEqual(
            pre_init["error"]["data"], {"detail": APP_SERVER_ERROR_DETAIL_NOT_INITIALIZED}
        )

        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {"id": "invalid-params", "method": "skills/list", "params": []},
                {"id": "unsupported", "method": "skills/list", "params": {}},
            ],
        )
        invalid_params = next(item["error"] for item in lines if item.get("id") == "invalid-params")
        unsupported = next(item["error"] for item in lines if item.get("id") == "unsupported")

        self.assertEqual(invalid_params["code"], -32602)
        self.assertEqual(invalid_params["message"], APP_SERVER_ERROR_MESSAGE_INVALID_PARAMS)
        self.assertEqual(
            invalid_params["data"], {"detail": APP_SERVER_ERROR_DETAIL_PARAMS_MUST_BE_OBJECT}
        )
        self.assertEqual(unsupported["code"], -32601)
        self.assertEqual(unsupported["message"], APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)
        self.assertEqual(
            unsupported["data"],
            {
                "detail": "skills/list",
                "compatibility": APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
                "replacement": "tools/list",
            },
        )

    def test_unsupported_replacement_map_completeness_guard(self) -> None:
        assert isinstance(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS, dict)
        assert REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS
        seen_casefold: set[str] = set()
        for method, replacement in REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.items():
            method_key = str(method or "").strip()
            replacement_key = str(replacement or "").strip()
            assert method_key
            assert replacement_key
            assert replacement_key != method_key
            assert replacement_key.casefold() not in {"unsupported", "unknown"}
            method_casefold = method_key.casefold()
            assert method_casefold not in seen_casefold
            seen_casefold.add(method_casefold)

    def test_unsupported_replacement_target_reachability_guard(self) -> None:
        reachable = set(app_server_capability_methods())
        for method, replacement in REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.items():
            replacement_key = str(replacement or "").strip()
            assert (
                replacement_key in reachable
            ), f"replacement target is unreachable: {method} -> {replacement_key}"

    def test_unsupported_replacement_style_guard(self) -> None:
        base_methods = set(APP_SERVER_BASE_METHODS)
        extension_methods = set(app_server_gateway_extension_methods())
        for method, replacement in REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS.items():
            replacement_key = str(replacement or "").strip()
            assert replacement_key in (
                base_methods | extension_methods
            ), f"replacement target is unreachable: {method} -> {replacement_key}"
            if replacement_key in base_methods:
                assert replacement_key == "initialize" or (
                    "/" in replacement_key and "." not in replacement_key
                ), f"replacement should use base slash-style: {method} -> {replacement_key}"
                continue
            assert (
                "." in replacement_key and "/" not in replacement_key
            ), f"replacement should use extension dot-style: {method} -> {replacement_key}"

    def test_app_server_error_object_snapshot_guard_for_unsupported_and_unknown_methods(
        self,
    ) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {"id": "unsupported-skills", "method": "skills/list", "params": {}},
                {"id": "unknown-method", "method": "missing/method", "params": {}},
            ],
        )

        unsupported_payload = next(item for item in lines if item.get("id") == "unsupported-skills")
        unknown_payload = next(item for item in lines if item.get("id") == "unknown-method")

        self.assertEqual(list(unsupported_payload.keys()), ["id", "error"])
        self.assertEqual(list(unknown_payload.keys()), ["id", "error"])

        unsupported_error = unsupported_payload["error"]
        unknown_error = unknown_payload["error"]
        self.assertEqual(list(unsupported_error.keys()), ["code", "message", "data"])
        self.assertEqual(list(unknown_error.keys()), ["code", "message", "data"])
        self.assertEqual(unsupported_error["code"], -32601)
        self.assertEqual(unknown_error["code"], -32601)
        self.assertEqual(unsupported_error["message"], APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)
        self.assertEqual(unknown_error["message"], APP_SERVER_ERROR_MESSAGE_METHOD_NOT_FOUND)

        unsupported_data = unsupported_error["data"]
        unknown_data = unknown_error["data"]
        self.assertEqual(list(unsupported_data.keys()), ["detail", "compatibility", "replacement"])
        self.assertEqual(list(unknown_data.keys()), ["detail"])
        self.assertEqual(unsupported_data["detail"], "skills/list")
        self.assertEqual(
            unsupported_data["compatibility"],
            APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
        )
        self.assertEqual(
            unsupported_data["replacement"],
            str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["skills/list"]),
        )
        self.assertEqual(unknown_data["detail"], "missing/method")
        self.assertNotIn("compatibility", unknown_data)
        self.assertNotIn("replacement", unknown_data)

    def test_app_server_error_shape_diff_guard_between_unsupported_and_unknown_method(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "unsupported-turn",
                    "method": "turn/interrupt",
                    "params": {"threadId": "thr_1", "turnId": "turn_1"},
                },
                {"id": "unknown", "method": "missing/method", "params": {}},
            ],
        )

        unsupported_error = next(
            item["error"] for item in lines if item.get("id") == "unsupported-turn"
        )
        unknown_error = next(item["error"] for item in lines if item.get("id") == "unknown")
        unsupported_data = dict(unsupported_error["data"])
        unknown_data = dict(unknown_error["data"])

        self.assertEqual(set(unsupported_data.keys()), {"detail", "compatibility", "replacement"})
        self.assertEqual(set(unknown_data.keys()), {"detail"})
        self.assertEqual(
            set(unsupported_data.keys()) - set(unknown_data.keys()),
            {"compatibility", "replacement"},
        )
        self.assertEqual(set(unknown_data.keys()) - set(unsupported_data.keys()), set())
        self.assertEqual(
            unsupported_data["compatibility"],
            APP_SERVER_ERROR_COMPATIBILITY_UNSUPPORTED_REFERENCE_METHOD,
        )
        self.assertEqual(
            unsupported_data["replacement"],
            str(REFERENCE_UNSUPPORTED_METHOD_REPLACEMENTS["turn/interrupt"]),
        )
        self.assertEqual(unsupported_data["detail"], "turn/interrupt")
        self.assertEqual(unknown_data["detail"], "missing/method")

    def test_gateway_state_and_approval_methods_expose_persisted_items(self) -> None:
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="manual",
            source_id="cli",
            payload={"ticket": "T-1"},
        )
        self.runtime.dispatch_gateway_event(event)
        approval_payload = self.runtime.request_gateway_action(
            action_type="demo.noop",
            connector_key="demo_webhook",
            plugin_name="demo_plugin",
            request_payload={"action": "noop", "parameters": {"ticket": "T-1"}},
            requested_by="test",
            trace_id=event.trace_id,
            event_id=event.event_id,
            approval_required=True,
            approval_summary="Approve demo noop",
        )
        approval_id = approval_payload["approval_ticket"].approval_id

        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "state", "method": "gateway/state", "params": {"limit": 5}}),
                    json.dumps(
                        {
                            "id": "approvals",
                            "method": "approval/list",
                            "params": {"status": "pending"},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "approve",
                            "method": "approval/decide",
                            "params": {
                                "approvalId": approval_id,
                                "decision": "approve",
                                "decidedBy": "tester",
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        state_result = next(item["result"] for item in lines if item.get("id") == "state")
        approval_list_result = next(
            item["result"] for item in lines if item.get("id") == "approvals"
        )
        approve_result = next(item["result"] for item in lines if item.get("id") == "approve")

        self.assertEqual(state_result["events"][0]["event_id"], event.event_id)
        self.assertEqual(approval_list_result["approvalTickets"][0]["approval_id"], approval_id)
        self.assertEqual(approve_result["approvalTicket"]["status"], "approved")
        self.assertEqual(approve_result["actionResult"]["action"], "noop")
        self.assertIn("toolEvents", approve_result)
        self.assertEqual(approve_result["turnEvents"][0]["type"], "turn.started")
        self.assertEqual(approve_result["turnEvents"][-1]["type"], "turn.completed")
        decision_items = [
            dict(item.get("item") or {})
            for item in list(approve_result.get("itemEvents") or [])
            if str(item.get("type") or "") == "item.completed"
        ]
        self.assertTrue(
            any(str(item.get("tool") or "") == "approval_decision" for item in decision_items)
        )
        self.assertTrue(
            any(str(item.get("tool") or "") == "gateway_action_execute" for item in decision_items)
        )

    def test_gateway_state_and_approval_list_include_operator_diagnostics(self) -> None:
        event = create_gateway_event(
            event_type="demo.event",
            source_kind="manual",
            source_id="cli",
            payload={"ticket": "T-2"},
        )
        workflow_run = create_workflow_run(
            trigger=TriggerRegistration(
                trigger_key="demo_trigger",
                plugin_name="demo_plugin",
                trigger_kind="event",
                connector_key="demo_webhook",
                event_types=["demo.event"],
                workflow_name="handle_demo_event",
            ),
            event=event,
            status="approval_requested",
            current_step="workflow_executed",
            context={
                "workflow_result": {
                    "status": "approval_requested",
                    "reasoning_summary": "demo workflow recommended one noop action",
                    "evidence_refs": ["demo://ticket/T-2"],
                    "action_request_count": 1,
                }
            },
        )
        self.runtime.gateway_state_store.save_event(event)
        self.runtime.gateway_state_store.save_workflow_run(workflow_run)
        approval_payload = self.runtime.request_gateway_action(
            action_type="demo.noop",
            connector_key="demo_webhook",
            plugin_name="demo_plugin",
            request_payload={"action": "noop", "parameters": {"ticket": "T-2"}},
            requested_by="workflow.demo",
            trace_id=event.trace_id,
            event_id=event.event_id,
            workflow_run_id=workflow_run.workflow_run_id,
            approval_required=True,
            approval_summary="Approve demo noop",
            metadata={
                "workflow_name": workflow_run.workflow_name,
                "reasoning_summary": "demo workflow recommended one noop action",
                "evidence_refs": ["demo://ticket/T-2"],
            },
        )
        approval_id = approval_payload["approval_ticket"].approval_id

        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "state", "method": "gateway/state", "params": {"limit": 5}}),
                    json.dumps(
                        {
                            "id": "approvals",
                            "method": "approval/list",
                            "params": {"status": "pending"},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "approve",
                            "method": "approval/decide",
                            "params": {
                                "approvalId": approval_id,
                                "decision": "approve",
                                "decidedBy": "tester",
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        state_result = next(item["result"] for item in lines if item.get("id") == "state")
        approval_list_result = next(
            item["result"] for item in lines if item.get("id") == "approvals"
        )

        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["reasoning"]["summary"],
            "demo workflow recommended one noop action",
        )
        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["recommendation"]["items"][0][
                "action_type"
            ],
            "demo.noop",
        )
        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["approval"]["status"], "pending"
        )
        self.assertEqual(
            approval_list_result["approvalDiagnostics"][0]["reasoning"]["summary"],
            "demo workflow recommended one noop action",
        )
        self.assertEqual(
            approval_list_result["approvalDiagnostics"][0]["approval"]["status"], "pending"
        )

    def test_gateway_state_exposes_browser_workflow_diagnostics(self) -> None:
        self.runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            browser_action_executor=_FakeBrowserActionExecutor(),
            runtime_policy=self._direct_exec_policy(),
        )
        proposed = dispatch_gui_bridge_action(
            self.runtime,
            action="browser.workflow.mutate",
            request_id="req_browser_workflow",
            payload={
                "profile": "openclaw",
                "target_id": "tab-1",
                "kind": "click",
                "ref": "e4",
                "reasoning_summary": "submit the current form",
                "approval_summary": "Approve browser click submit",
            },
        )
        self.assertTrue(proposed["ok"])

        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "state", "method": "gateway/state", "params": {"limit": 10}}),
                    json.dumps(
                        {
                            "id": "approvals",
                            "method": "approval/list",
                            "params": {"status": "pending"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        state_result = next(item["result"] for item in lines if item.get("id") == "state")
        approval_list_result = next(
            item["result"] for item in lines if item.get("id") == "approvals"
        )

        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["browser_workflow"][
                "playbook_kind"
            ],
            "mutate_after_approval",
        )
        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["recommendation"]["items"][0][
                "action_type"
            ],
            "browser.act.click",
        )
        self.assertEqual(
            state_result["diagnostics"]["workflowDiagnostics"][0]["approval"]["status"], "pending"
        )
        self.assertEqual(
            approval_list_result["approvalDiagnostics"][0]["recommendation"]["action_family"],
            "browser",
        )
        self.assertEqual(
            approval_list_result["approvalDiagnostics"][0]["recommendation"]["browser"][
                "action_kind"
            ],
            "click",
        )

    def test_session_run_with_stream_emits_activity_then_result(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-1",
                            "method": "session/run",
                            "params": {"prompt": "list current directory", "stream": True},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        notifications = [line for line in lines if line.get("method") == "session/activity"]
        turn_notifications = [line for line in lines if line.get("method") == "session/turn_event"]
        results = [line for line in lines if line.get("id") == "run-1"]
        self.assertTrue(notifications)
        self.assertTrue(turn_notifications)
        self.assertEqual(notifications[0]["params"]["requestId"], "run-1")
        self.assertEqual(turn_notifications[0]["params"]["requestId"], "run-1")
        self.assertEqual(results[-1]["result"]["exitCode"], 0)
        self.assertEqual(
            results[-1]["result"]["response"]["commentary_text"],
            "Checking current workspace before execution.",
        )
        self.assertEqual(results[-1]["result"]["response"]["tool_events"][-1]["name"], "shell")

    def test_session_run_with_stream_emits_live_turn_events_before_result(self) -> None:
        # Modeled after Reference streamed turn semantics:
        # - reference_baseline/reference-rs/core/tests/suite/cli_stream.rs
        # - reference_baseline/reference-rs/exec/tests/event_processor_with_json_output.rs
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-stream-turn",
                            "method": "session/run",
                            "params": {"prompt": "streaming prompt", "stream": True},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=_StreamingPromptRuntime(), stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        turn_notifications = [line for line in lines if line.get("method") == "session/turn_event"]
        result_index = next(
            index for index, line in enumerate(lines) if line.get("id") == "run-stream-turn"
        )
        first_turn_event_index = next(
            index for index, line in enumerate(lines) if line.get("method") == "session/turn_event"
        )
        self.assertLess(first_turn_event_index, result_index)
        self.assertEqual(turn_notifications[0]["params"]["event"]["type"], "turn.started")
        self.assertEqual(turn_notifications[1]["params"]["event"]["item"]["type"], "reasoning")
        self.assertEqual(turn_notifications[2]["params"]["event"]["item"]["type"], "agent_message")
        self.assertEqual(
            sum(
                1
                for line in turn_notifications
                if line["params"]["event"]["type"] == "turn.started"
            ),
            1,
        )

    def test_session_run_prefers_structured_web_search_result(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.agent.plan = (
            lambda text, history=None, *, tool_executor=None, attachments=None: AgentIntent(
                assistant_text="",
                commentary_text="",
                command_text="/web_search structured entry --limit 1",
                status_hint="tool",
            )
        )
        structured_result = _structured_tool_result(
            "web_search",
            "structured gateway web summary",
            payload={"query": "structured entry"},
            arguments={"query": "structured entry", "limit": 1},
        )
        runtime.tools.web_search_result = lambda *args, **kwargs: structured_result

        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-structured",
                            "method": "session/run",
                            "params": {"prompt": "structured prompt", "stream": False},
                        }
                    ),
                ]
            )
            + "\n"
        )
        stdout = io.StringIO()

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        run_result = next(line for line in lines if line.get("id") == "run-structured")
        response = run_result["result"]["response"]
        self.assertEqual(response["assistant_text"], "structured gateway web summary")
        self.assertEqual([item["name"] for item in response["tool_events"]], ["web_search"])
        self.assertEqual(response["turn_events"][0]["type"], "turn.started")
        self.assertEqual(response["turn_events"][-1]["type"], "turn.completed")
        completed_tool = next(
            event
            for event in response["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(completed_tool["item"]["tool"], "web_search")

    def test_app_server_soft_failed_tool_keeps_exit_code_zero(self) -> None:
        response = PromptResponse(
            user_text="search missing",
            assistant_text="No matches found.",
            tool_events=[
                ToolEvent(
                    name="grep_files",
                    ok=False,
                    summary="No matches found.",
                    payload={
                        "result_success": False,
                        "text": "No matches found.",
                        "pattern": "needle",
                        "path": ".",
                    },
                )
            ],
        )

        self.assertEqual(_exit_code_for_response(response), 0)

    def test_app_server_codex_noninteractive_failed_exec_with_final_answer_keeps_exit_code_zero(
        self,
    ) -> None:
        response = PromptResponse(
            user_text="write file",
            assistant_text="写入失败，当前是只读沙箱。",
            tool_events=[
                ToolEvent(
                    name="exec_command",
                    ok=False,
                    summary="exec_command exited",
                    payload={
                        "returncode": 1,
                        "stderr": "/bin/bash: line 1: note.txt: Permission denied",
                    },
                )
            ],
            protocol_diagnostics={"headless_contract": {"codex_noninteractive": True}},
        )

        self.assertEqual(_exit_code_for_response(response), 0)

    def test_session_run_supports_update_plan_slash_command(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-plan",
                            "method": "session/run",
                            "params": {
                                "prompt": '/update_plan \'{"explanation":"sync","plan":[{"step":"inspect","status":"completed"},{"step":"patch","status":"in_progress"}]}\'',
                                "stream": False,
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        run_result = next(line for line in lines if line.get("id") == "run-plan")
        response = run_result["result"]["response"]
        self.assertTrue(response["handled_as_command"])
        self.assertEqual(response["assistant_text"], "Plan updated")
        self.assertEqual(response["tool_events"][-1]["name"], "update_plan")
        completed_tool = next(
            event
            for event in response["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "todo_list"
        )
        self.assertEqual(
            completed_tool["item"]["items"],
            [
                {"text": "inspect", "completed": True},
                {"text": "patch", "completed": False},
            ],
        )

    def test_session_run_supports_request_user_input_round_trip(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.collaboration_mode = "plan"
        runtime.request_user_input_handler = lambda payload: {
            "answers": {"confirm_path": {"answers": ["yes"]}},
            "questions": payload["questions"],
        }
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-request-user-input",
                            "method": "session/run",
                            "params": {
                                "prompt": '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                                "stream": False,
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        run_result = next(line for line in lines if line.get("id") == "run-request-user-input")
        response = run_result["result"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertEqual(
            json.loads(response["assistant_text"])["answers"]["confirm_path"]["answers"], ["yes"]
        )
        completed_tool = next(
            event
            for event in response["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
        )
        self.assertEqual(completed_tool["item"]["tool"], "request_user_input")

    def test_session_start_request_user_input_emits_async_request_and_resolves_before_completion(
        self,
    ) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.collaboration_mode = "plan"
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})
        stdin.push_json(
            {
                "id": "run-request-user-input-async",
                "method": "session/start",
                "params": {
                    "prompt": '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                    "stream": True,
                },
            }
        )

        start_result = stdout.wait_for_line(
            lambda line: line.get("id") == "run-request-user-input-async"
        )
        self.assertTrue(start_result["result"]["accepted"])

        server_request = stdout.wait_for_line(
            lambda line: line.get("method") == "item/tool/requestUserInput"
        )
        request_id = server_request["id"]
        self.assertEqual(
            server_request["params"]["threadId"], "thread_run-request-user-input-async"
        )
        self.assertEqual(server_request["params"]["questions"][0]["id"], "confirm_path")

        stdin.push_json(
            {
                "id": request_id,
                "result": {
                    "answers": {
                        "confirm_path": {"answers": ["yes"]},
                    }
                },
            }
        )

        resolved = stdout.wait_for_line(lambda line: line.get("method") == "serverRequest/resolved")
        completed = stdout.wait_for_line(lambda line: line.get("method") == "session/completed")
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        self.assertEqual(resolved["params"]["threadId"], "thread_run-request-user-input-async")
        self.assertEqual(resolved["params"]["requestId"], request_id)
        self.assertEqual(completed["params"]["requestId"], "run-request-user-input-async")
        response = completed["params"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertEqual(
            json.loads(response["assistant_text"])["answers"]["confirm_path"]["answers"], ["yes"]
        )
        lines = stdout.lines()
        resolved_idx = next(
            index
            for index, line in enumerate(lines)
            if line.get("method") == "serverRequest/resolved"
        )
        completed_idx = next(
            index for index, line in enumerate(lines) if line.get("method") == "session/completed"
        )
        self.assertLess(resolved_idx, completed_idx)

    def test_session_start_request_user_input_non_object_client_result_is_cancelled(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.collaboration_mode = "plan"
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})
        stdin.push_json(
            {
                "id": "run-request-user-input-malformed",
                "method": "session/start",
                "params": {
                    "prompt": '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                    "stream": True,
                },
            }
        )

        start_result = stdout.wait_for_line(
            lambda line: line.get("id") == "run-request-user-input-malformed"
        )
        self.assertTrue(start_result["result"]["accepted"])
        server_request = stdout.wait_for_line(
            lambda line: line.get("method") == "item/tool/requestUserInput"
        )
        request_id = server_request["id"]
        stdin.push_json(
            {
                "id": request_id,
                "result": ["unexpected-list-payload"],
            }
        )

        resolved = stdout.wait_for_line(lambda line: line.get("method") == "serverRequest/resolved")
        completed = stdout.wait_for_line(lambda line: line.get("method") == "session/completed")
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        self.assertEqual(resolved["params"]["requestId"], request_id)
        response = completed["params"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertFalse(response["tool_events"][-1]["ok"])
        self.assertEqual(
            response["assistant_text"],
            "request_user_input was cancelled before receiving a response",
        )

    def test_session_start_request_user_input_client_error_is_cancelled(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.collaboration_mode = "plan"
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})
        stdin.push_json(
            {
                "id": "run-request-user-input-error",
                "method": "session/start",
                "params": {
                    "prompt": '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                    "stream": True,
                },
            }
        )

        start_result = stdout.wait_for_line(
            lambda line: line.get("id") == "run-request-user-input-error"
        )
        self.assertTrue(start_result["result"]["accepted"])
        server_request = stdout.wait_for_line(
            lambda line: line.get("method") == "item/tool/requestUserInput"
        )
        request_id = server_request["id"]
        stdin.push_json(
            {
                "id": request_id,
                "error": {"code": -32042, "message": "operator cancelled"},
            }
        )

        resolved = stdout.wait_for_line(lambda line: line.get("method") == "serverRequest/resolved")
        completed = stdout.wait_for_line(lambda line: line.get("method") == "session/completed")
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        self.assertEqual(resolved["params"]["requestId"], request_id)
        response = completed["params"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertFalse(response["tool_events"][-1]["ok"])
        self.assertEqual(
            response["assistant_text"],
            "request_user_input was cancelled before receiving a response",
        )

    def test_session_start_request_user_input_normalizes_non_canonical_answers_shape(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        runtime.collaboration_mode = "plan"
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})
        stdin.push_json(
            {
                "id": "run-request-user-input-normalized",
                "method": "session/start",
                "params": {
                    "prompt": '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?","options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\'',
                    "stream": True,
                },
            }
        )

        start_result = stdout.wait_for_line(
            lambda line: line.get("id") == "run-request-user-input-normalized"
        )
        self.assertTrue(start_result["result"]["accepted"])
        server_request = stdout.wait_for_line(
            lambda line: line.get("method") == "item/tool/requestUserInput"
        )
        request_id = server_request["id"]
        stdin.push_json(
            {
                "id": request_id,
                "result": {
                    "answers": {
                        "confirm_path": "yes",
                    }
                },
            }
        )

        _resolved = stdout.wait_for_line(
            lambda line: line.get("method") == "serverRequest/resolved"
        )
        completed = stdout.wait_for_line(lambda line: line.get("method") == "session/completed")
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        response = completed["params"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertTrue(response["tool_events"][-1]["ok"])
        normalized = json.loads(response["assistant_text"])
        self.assertEqual(normalized["answers"]["confirm_path"], {"answers": ["yes"]})

    def test_session_run_supports_exec_command_slash_command(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-exec-command",
                            "method": "session/run",
                            "params": {
                                "prompt": "/exec_command 'python -V' --yield-time-ms 250 --tty",
                                "stream": False,
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        run_result = next(line for line in lines if line.get("id") == "run-exec-command")
        response = run_result["result"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "exec_command")
        self.assertIn("Process running with session ID", response["assistant_text"])
        completed_tool = next(
            event
            for event in response["turn_events"]
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        )
        self.assertEqual(completed_tool["item"]["command"], "/bin/bash -lc 'python -V'")

    def test_command_exec_runs_shell_without_session_run(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-1",
                            "method": "command/exec",
                            "params": {"command": "Get-ChildItem -Force"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "cmd-1")
        self.assertEqual(result["result"]["exitCode"], 0)
        self.assertEqual(result["result"]["response"]["user_text"], "/shell Get-ChildItem -Force")
        self.assertTrue(result["result"]["response"]["handled_as_command"])
        self.assertEqual(
            result["result"]["response"]["tool_events"][-1]["payload"]["command"],
            "Get-ChildItem -Force",
        )
        self.assertEqual(result["result"]["response"]["turn_events"][0]["type"], "turn.started")
        self.assertEqual(result["result"]["response"]["turn_events"][-1]["type"], "turn.completed")
        self.assertEqual(result["result"]["phase"], "completed")
        self.assertEqual(result["result"]["eventKind"], "end")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(result["result"]["command"], "Get-ChildItem -Force")
        self.assertEqual(result["result"]["source"], "unified_exec_startup")
        self.assertEqual(result["result"]["stdout"], "a.txt\nb.txt\n")
        self.assertEqual(result["result"]["stderr"], "")
        self.assertEqual(result["result"]["aggregatedOutput"], "a.txt\nb.txt\n")
        self.assertEqual(result["result"]["raw"]["call_id"], "call_1")
        self.assertTrue(
            str(
                result["result"]["response"]["tool_events"][-1]["payload"].get("session_id") or ""
            ).strip()
        )
        self.assertTrue(
            str(
                result["result"]["response"]["tool_events"][-1]["payload"].get("process_id") or ""
            ).strip()
        )

    def test_command_exec_respects_approval_policy_and_returns_shell_approval_event(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-approval",
                            "method": "command/exec",
                            "params": {"command": "Get-ChildItem -Force"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "cmd-approval")
        self.assertEqual(
            result["result"]["response"]["tool_events"][-1]["name"], "shell_approval_requested"
        )
        self.assertIn("approval_id", result["result"]["response"]["tool_events"][-1]["payload"])

    def test_command_start_respects_approval_policy_and_returns_shell_approval_event(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start-approval",
                            "method": "command/start",
                            "params": {"command": "python -i", "stream": True},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "cmd-start-approval")
        self.assertFalse(result["result"]["accepted"])
        self.assertTrue(result["result"].get("approvalRequired"))
        tool_event = result["result"]["response"]["tool_events"][-1]
        self.assertEqual(tool_event["name"], "shell_approval_requested")
        self.assertIn("approval_id", tool_event["payload"])

    def test_command_start_returns_session_id_and_command_write_stdin_streams_output(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start",
                            "method": "command/start",
                            "params": {"command": "python -i", "stream": True},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "cmd-write",
                            "method": "command/writeStdin",
                            "params": {"sessionId": "session_1", "chars": "ping\\n"},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "cmd-stop",
                            "method": "command/terminate",
                            "params": {"sessionId": "session_1"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        start_result = next(line for line in lines if line.get("id") == "cmd-start")
        write_result = next(line for line in lines if line.get("id") == "cmd-write")
        terminate_result = next(line for line in lines if line.get("id") == "cmd-stop")
        activity = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        completed = next(line for line in lines if line.get("method") == "command/completed")
        self.assertEqual(start_result["result"]["sessionId"], "session_1")
        self.assertEqual(start_result["result"]["processId"], "session_1")
        self.assertEqual(start_result["result"]["callId"], "call_1")
        self.assertEqual(start_result["result"]["lifecycle"]["phase"], "started")
        self.assertEqual(start_result["result"]["phase"], "started")
        self.assertEqual(start_result["result"]["eventKind"], "begin")
        self.assertEqual(start_result["result"]["command"], "python -i")
        self.assertEqual(start_result["result"]["source"], "unified_exec_startup")
        self.assertEqual(start_result["result"]["status"], "started")
        self.assertEqual(start_result["result"]["raw"]["call_id"], "call_1")
        self.assertIn("stdout", start_result["result"])
        self.assertIn("stderr", start_result["result"])
        self.assertIn("aggregatedOutput", start_result["result"])
        self.assertIsNone(start_result["result"]["stdout"])
        self.assertIsNone(start_result["result"]["stderr"])
        self.assertIsNone(start_result["result"]["aggregatedOutput"])
        self.assertTrue(write_result["result"]["accepted"])
        self.assertEqual(write_result["result"]["toolEvent"]["payload"]["session_id"], "session_1")
        self.assertEqual(write_result["result"]["sessionId"], "session_1")
        self.assertEqual(write_result["result"]["processId"], "session_1")
        self.assertEqual(write_result["result"]["callId"], "call_1")
        self.assertEqual(write_result["result"]["lifecycle"]["phase"], "input")
        self.assertEqual(write_result["result"]["phase"], "input")
        self.assertEqual(write_result["result"]["eventKind"], "input")
        self.assertEqual(write_result["result"]["command"], "python -i")
        self.assertEqual(write_result["result"]["source"], "unified_exec_interaction")
        self.assertEqual(write_result["result"]["status"], "written")
        self.assertEqual(write_result["result"]["interactionInput"], "ping\\n")
        self.assertEqual(write_result["result"]["stdin"], "ping\\n")
        self.assertEqual(write_result["result"]["raw"]["call_id"], "call_1")
        self.assertIn("stdout", write_result["result"])
        self.assertIn("stderr", write_result["result"])
        self.assertIn("aggregatedOutput", write_result["result"])
        self.assertIsNone(write_result["result"]["stdout"])
        self.assertIsNone(write_result["result"]["stderr"])
        self.assertIsNone(write_result["result"]["aggregatedOutput"])
        self.assertEqual(write_result["result"]["toolEvent"]["payload"]["process_id"], "session_1")
        self.assertEqual(write_result["result"]["toolEvent"]["payload"]["status"], "written")
        self.assertTrue(any("echo:ping" in item["params"]["event"]["detail"] for item in activity))
        self.assertEqual(completed["params"]["phase"], "completed")
        self.assertEqual(completed["params"]["status"], "interrupted")
        self.assertEqual(completed["params"]["lifecycle"]["phase"], "completed")
        self.assertEqual(completed["params"]["lifecycle"]["status"], "interrupted")
        self.assertTrue(
            any(item["params"]["raw"]["session_id"] == "session_1" for item in activity)
        )
        self.assertTrue(
            any(
                dict(item.get("params", {}).get("raw") or {}).get("process_id") == "session_1"
                for item in activity
            )
        )
        self.assertTrue(any(item["params"]["sessionId"] == "session_1" for item in activity))
        self.assertTrue(any(item["params"]["processId"] == "session_1" for item in activity))
        self.assertTrue(all(item["params"]["callId"] == "call_1" for item in activity))
        self.assertTrue(
            all(
                dict(item["params"].get("lifecycle") or {}).get("call_id") == "call_1"
                for item in activity
            )
        )
        self.assertTrue(any(item["params"].get("phase") == "input" for item in activity))
        self.assertTrue(any(item["params"].get("eventKind") == "input" for item in activity))
        self.assertTrue(
            any(
                item["params"].get("source") == "unified_exec_interaction"
                for item in activity
                if item["params"].get("phase") == "input"
            )
        )
        self.assertTrue(any(item["params"].get("stdin") == "ping\\n" for item in activity))
        self.assertTrue(
            any(item["params"].get("interactionInput") == "ping\\n" for item in activity)
        )
        self.assertTrue(
            any(item["params"].get("outputText") == "echo:ping\\n" for item in activity)
        )
        self.assertTrue(
            any(
                str(item["params"].get("outputText") or "")
                and base64.b64decode(str(item["params"].get("outputChunk") or ""))
                .decode("utf-8", errors="replace")
                .startswith(str(item["params"].get("outputText") or ""))
                for item in activity
                if item["params"].get("outputChunk")
            )
        )
        self.assertTrue(all("stdout" in item["params"] for item in activity))
        self.assertTrue(all("stderr" in item["params"] for item in activity))
        self.assertTrue(all("aggregatedOutput" in item["params"] for item in activity))
        self.assertTrue(terminate_result["result"]["ok"])
        self.assertEqual(terminate_result["result"]["processId"], "session_1")
        self.assertEqual(terminate_result["result"]["callId"], "call_1")
        self.assertEqual(terminate_result["result"]["lifecycle"]["phase"], "completed")
        self.assertEqual(terminate_result["result"]["phase"], "completed")
        self.assertEqual(terminate_result["result"]["eventKind"], "end")
        self.assertEqual(terminate_result["result"]["command"], "python -i")
        self.assertEqual(terminate_result["result"]["source"], "unified_exec_startup")
        self.assertEqual(terminate_result["result"]["status"], "interrupted")
        self.assertEqual(terminate_result["result"]["raw"]["call_id"], "call_1")
        self.assertIsNone(terminate_result["result"]["stdout"])
        self.assertIsNone(terminate_result["result"]["stderr"])
        self.assertIsNone(terminate_result["result"]["aggregatedOutput"])
        self.assertEqual(completed["params"]["sessionId"], "session_1")
        self.assertEqual(completed["params"]["processId"], "session_1")
        self.assertEqual(completed["params"]["callId"], "call_1")
        self.assertEqual(completed["params"]["lifecycle"]["phase"], "completed")
        self.assertEqual(completed["params"]["phase"], "completed")
        self.assertEqual(completed["params"]["eventKind"], "end")
        self.assertEqual(completed["params"]["command"], "python -i")
        self.assertEqual(completed["params"]["source"], "unified_exec_startup")
        self.assertEqual(completed["params"]["status"], "interrupted")
        self.assertEqual(completed["params"]["stdout"], "")
        self.assertEqual(completed["params"]["stderr"], "")
        self.assertEqual(completed["params"]["raw"]["session_id"], "session_1")
        self.assertEqual(
            dict(completed["params"].get("raw") or {}).get("process_id"),
            "session_1",
        )
        self.assertEqual(completed["params"]["raw"]["status"], "interrupted")

    def test_command_write_stdin_supports_yield_time_poll_semantics(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start",
                            "method": "command/start",
                            "params": {"command": "python -i", "stream": True},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "cmd-poll",
                            "method": "command/writeStdin",
                            "params": {"sessionId": "session_1", "chars": "", "yieldTimeMs": 450},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        poll = next(line for line in lines if line.get("id") == "cmd-poll")
        self.assertTrue(poll["result"]["accepted"])
        self.assertTrue(poll["result"]["isPoll"])
        self.assertEqual(poll["result"]["yieldTimeMs"], 450)
        self.assertEqual(poll["result"]["lifecycle"]["phase"], "input")
        self.assertEqual(poll["result"]["status"], "noop")
        self.assertEqual(dict(poll["result"].get("raw") or {}).get("yield_time_ms"), 450)

    def test_command_write_stdin_completed_payload_emits_command_completed_once(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_WriteCompletesSessionTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "python -i", "stream": True},
                },
                {
                    "id": "cmd-exit",
                    "method": "command/writeStdin",
                    "params": {"sessionId": "session_1", "chars": "exit\n", "yieldTimeMs": 200},
                },
            ],
        )
        write_result = next(line for line in lines if line.get("id") == "cmd-exit")
        completed = [line for line in lines if line.get("method") == "command/completed"]
        self.assertTrue(write_result["result"]["accepted"])
        self.assertEqual(write_result["result"]["phase"], "completed")
        self.assertEqual(write_result["result"]["eventKind"], "end")
        self.assertEqual(write_result["result"]["status"], "ok")
        self.assertEqual(write_result["result"]["yieldTimeMs"], 200)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["params"]["requestId"], "cmd-start")
        self.assertEqual(completed[0]["params"]["phase"], "completed")
        self.assertEqual(completed[0]["params"]["status"], "ok")

    def test_command_start_approval_decision_restores_session_for_write_stdin(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start",
                            "method": "command/start",
                            "params": {"command": "python -i", "stream": True},
                        }
                    ),
                ]
            )
            + "\n"
        )

        initial_code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(initial_code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        start_result = next(line for line in lines if line.get("id") == "cmd-start")
        approval_id = start_result["result"]["response"]["tool_events"][-1]["payload"][
            "approval_id"
        ]

        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "approval-1",
                            "method": "approval/decide",
                            "params": {"approvalId": approval_id, "decision": "approve"},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "cmd-write",
                            "method": "command/writeStdin",
                            "params": {"sessionId": "session_1", "chars": "ping\\n"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        approve_result = next(line for line in lines if line.get("id") == "approval-1")
        write_result = next(line for line in lines if line.get("id") == "cmd-write")
        activity = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        self.assertEqual(
            approve_result["result"]["actionResult"]["output"]["session_id"], "session_1"
        )
        self.assertEqual(approve_result["result"]["turnEvents"][0]["type"], "turn.started")
        self.assertEqual(approve_result["result"]["turnEvents"][-1]["type"], "turn.completed")
        self.assertTrue(write_result["result"]["accepted"])
        self.assertEqual(write_result["result"]["processId"], "session_1")
        self.assertEqual(write_result["result"]["callId"], "call_1")
        self.assertEqual(write_result["result"]["lifecycle"]["phase"], "input")
        self.assertEqual(write_result["result"]["command"], "python -i")
        self.assertEqual(write_result["result"]["source"], "unified_exec_interaction")
        self.assertEqual(write_result["result"]["status"], "written")
        self.assertEqual(write_result["result"]["toolEvent"]["payload"]["process_id"], "session_1")
        self.assertTrue(
            any(item["params"]["event"]["title"] == "Running python -i" for item in activity)
        )
        self.assertTrue(
            any(item["params"]["raw"]["session_id"] == "session_1" for item in activity)
        )
        self.assertTrue(any(item["params"]["sessionId"] == "session_1" for item in activity))
        self.assertTrue(any(item["params"]["callId"] == "call_1" for item in activity))
        self.assertTrue(
            any(
                dict(item["params"].get("lifecycle") or {}).get("phase") == "started"
                for item in activity
            )
        )
        self.assertTrue(any(item["params"].get("phase") == "input" for item in activity))
        self.assertTrue(any(item["params"].get("stdin") == "ping\\n" for item in activity))
        self.assertTrue(
            any(item["params"].get("interactionInput") == "ping\\n" for item in activity)
        )

    def test_command_start_activity_compacts_compound_command_title_for_protocol_clients(
        self,
    ) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        command = "cd /home/lyc/project/gemini-cli && git fetch upstream && git merge upstream/main --no-edit 2>&1"
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": command, "stream": True},
                },
            ],
        )
        activity = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]

        self.assertTrue(activity)
        self.assertTrue(
            any(
                item["params"]["event"]["title"]
                == "Running git fetch upstream / git merge upstream/main --no-edit"
                for item in activity
            )
        )
        self.assertTrue(any(item["params"].get("command") == command for item in activity))

    def test_command_start_approval_emits_session_activity_shape(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )
        command = (
            f"{sys.executable} -u -c "
            "\"print('approval session start'); import sys; sys.stdout.flush()\""
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start-approval-activity",
                            "method": "command/start",
                            "params": {"command": command, "stream": True},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        start_result = next(
            line for line in lines if line.get("id") == "cmd-start-approval-activity"
        )
        tool_event = start_result["result"]["response"]["tool_events"][-1]
        self.assertEqual(tool_event["name"], "shell_approval_requested")
        approval_id = tool_event["payload"]["approval_id"]

        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init2", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "approval-activity",
                            "method": "approval/decide",
                            "params": {"approvalId": approval_id, "decision": "approve"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        approval_lines = [
            json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()
        ]
        activity_notifications = [
            line
            for line in approval_lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start-approval-activity"
        ]
        self.assertTrue(activity_notifications)
        event = activity_notifications[0]["params"]["event"]
        self.assertEqual(activity_notifications[0]["params"]["turnEvent"]["type"], "item.started")
        self.assertEqual(event["status"], "running")
        self.assertEqual(event["kind"], "command")
        self.assertTrue(event["title"].startswith("Running"))
        self.assertEqual(event["detail"], "")

    def test_command_start_approval_replays_completed_session_when_subscribe_is_late(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_SubscribeCompletedAppServerTools(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
        )
        command = (
            f"{sys.executable} -u -c "
            "\"print('approval instant complete'); import sys; sys.stdout.flush()\""
        )
        initial_lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": command, "stream": True},
                },
            ],
        )
        start_result = next(line for line in initial_lines if line.get("id") == "cmd-start")
        approval_id = start_result["result"]["response"]["tool_events"][-1]["payload"][
            "approval_id"
        ]

        approval_lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init2", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "approval-complete",
                    "method": "approval/decide",
                    "params": {"approvalId": approval_id, "decision": "approve"},
                },
            ],
        )

        completed_line = next(
            line for line in approval_lines if line.get("method") == "command/completed"
        )
        activity_lines = [
            line
            for line in approval_lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        self.assertTrue(activity_lines)
        self.assertEqual(activity_lines[0]["params"]["phase"], "started")
        self.assertEqual(activity_lines[0]["params"]["status"], "started")
        self.assertEqual(completed_line["params"]["requestId"], "cmd-start")
        self.assertEqual(completed_line["params"]["status"], "ok")
        self.assertIn(
            "approval instant complete", str(completed_line["params"].get("stdout") or "")
        )
        completed_turn_events = list(completed_line["params"]["response"].get("turn_events") or [])
        self.assertTrue(any(item.get("type") == "item.started" for item in completed_turn_events))
        self.assertTrue(
            any(
                item.get("type") == "item.completed"
                and dict(item.get("item") or {}).get("type") == "function_call"
                and dict(item.get("item") or {}).get("name") == "shell"
                for item in completed_turn_events
            )
        )
        raw_payload = dict(activity_lines[0]["params"].get("raw") or {})
        self.assertEqual(activity_lines[0]["params"]["callId"], "call_1")
        self.assertEqual(activity_lines[0]["params"]["lifecycle"]["phase"], "started")
        self.assertEqual(activity_lines[0]["params"]["command"], command)
        self.assertEqual(activity_lines[0]["params"]["source"], "unified_exec_startup")
        self.assertEqual(activity_lines[0]["params"]["status"], "started")
        self.assertEqual(raw_payload.get("session_id"), "session_1")
        self.assertEqual(raw_payload.get("process_id"), "session_1")

    def test_command_write_stdin_unknown_session_returns_json_rpc_error(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_AppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-write-missing",
                            "method": "command/writeStdin",
                            "params": {"sessionId": "missing-session", "chars": "ping"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        error = next(line for line in lines if line.get("id") == "cmd-write-missing")
        self.assertEqual(error["error"]["code"], -32004)
        self.assertEqual(error["error"]["message"], "Unknown command session")
        self.assertEqual(error["error"]["data"]["detail"], "missing-session")

    def test_tools_list_returns_capability_catalog(self) -> None:
        # Pin the baseline app-server catalog to the Codex-style reference surface
        # instead of inheriting whichever planner profile is loaded locally.
        self.runtime.agent.set_planner_override(
            types.SimpleNamespace(config=self._codex_openai_config())
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "tools-1", "method": "tools/list", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "tools-1")
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(result["result"]["tools"][0]["name"], "exec_command")
        self.assertEqual(result["result"]["workspaceTrust"], "trusted")
        self.assertEqual(result["result"]["mcpServers"], {})
        self.assertEqual(result["result"]["mcpServerEntries"], [])
        self.assertEqual(result["result"]["appConnectors"], [])

    def test_tools_list_projects_provider_surface_when_runtime_has_planner_config(self) -> None:
        runtime = types.SimpleNamespace(
            agent=types.SimpleNamespace(
                _planner=types.SimpleNamespace(
                    config=ProviderConfig(
                        model="claude-sonnet-4-6",
                        api_key="test-key",
                        provider_name="anthropic",
                        planner_kind="anthropic_messages",
                        wire_api="anthropic_messages",
                        interaction_profile="claude_code",
                        interaction_profile_source="test",
                    )
                )
            ),
            tools=_AppServerTools(),
        )
        captured: dict[str, object] = {}

        class _Server:
            def __init__(self) -> None:
                self.runtime = runtime

            def _emit_result(self, request_id: object, result: object) -> None:
                captured["id"] = request_id
                captured["result"] = result

        app_server_helpers.handle_tools_list(
            _Server(),
            request_id="tools-projected",
            runtime_registry_mcp_server_entries_fn=lambda _plugin_manager, runtime_capabilities=None: [],
        )

        self.assertEqual(captured["id"], "tools-projected")
        result = dict(captured["result"])
        names = [item["name"] for item in result["tools"]]
        self.assertIn("Bash", names)
        self.assertIn("office_skills", names)
        self.assertNotIn("shell", names)

    def test_tools_list_preserves_mcp_server_status_fields(self) -> None:
        class _McpAwareTools(_AppServerTools):
            def capabilities(self) -> dict:
                payload = super().capabilities()
                payload["mcp_servers"] = {
                    "atlas": {"status": "connected", "enabled": True, "scope": "workspace"},
                    "ops": {"status": "needs-auth", "enabled": False, "scope": "plugin"},
                }
                return payload

        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_McpAwareTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "tools-2", "method": "tools/list", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "tools-2")
        servers = dict(result["result"]["mcpServers"])
        self.assertEqual(servers["atlas"]["status"], "connected")
        self.assertEqual(servers["atlas"]["enabled"], True)
        self.assertEqual(servers["ops"]["status"], "needs-auth")
        self.assertEqual(servers["ops"]["enabled"], False)
        entry_names = {item["name"] for item in result["result"]["mcpServerEntries"]}
        self.assertEqual(entry_names, {"atlas", "ops"})

    def test_tools_list_merges_runtime_mcp_entries_over_static_plugin_metadata(self) -> None:
        class _PluginManagerStub:
            @staticmethod
            def gui_bridge_metadata() -> dict[str, object]:
                return {
                    "mcpServers": [
                        {
                            "name": "atlas",
                            "source": "plugin",
                            "plugin_name": "atlas_plugin",
                            "config": {"url": "https://canonical.example/mcp"},
                        }
                    ]
                }

        class _McpAwareTools(_AppServerTools):
            def __init__(self) -> None:
                super().__init__()
                self._plugin_manager = _PluginManagerStub()

            def capabilities(self) -> dict:
                payload = super().capabilities()
                payload["mcp_server_entries"] = [
                    {
                        "name": "atlas",
                        "source": "workspace",
                        "status": "connected",
                        "enabled": True,
                        "scope": "workspace",
                        "projection_state": "ready",
                        "config": {"url": "https://runtime.example/mcp"},
                    }
                ]
                return payload

        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_McpAwareTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "tools-3", "method": "tools/list", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "tools-3")
        atlas = next(
            item for item in result["result"]["mcpServerEntries"] if item["name"] == "atlas"
        )
        self.assertEqual(atlas["status"], "connected")
        self.assertEqual(atlas["source"], "workspace")
        self.assertEqual(atlas["projection_state"], "ready")
        self.assertEqual(atlas["plugin_name"], "atlas_plugin")
        self.assertEqual(atlas["config"]["url"], "https://runtime.example/mcp")
        self.assertEqual(result["result"]["mcpServers"]["atlas"]["status"], "connected")

    def test_tools_list_merges_runtime_mcp_server_map_over_static_metadata(self) -> None:
        class _PluginManagerStub:
            @staticmethod
            def gui_bridge_metadata() -> dict[str, object]:
                return {
                    "mcpServers": [
                        {
                            "name": "atlas",
                            "source": "plugin",
                            "plugin_name": "atlas_plugin",
                            "config": {"url": "https://canonical.example/mcp"},
                        }
                    ]
                }

        class _McpAwareTools(_AppServerTools):
            def __init__(self) -> None:
                super().__init__()
                self._plugin_manager = _PluginManagerStub()

            def capabilities(self) -> dict:
                payload = super().capabilities()
                payload["mcp_servers"] = {
                    "atlas": {
                        "source": "runtime_dynamic",
                        "status": "connected",
                        "enabled": True,
                        "projection_state": "ready",
                        "url": "https://runtime.example/mcp",
                    }
                }
                return payload

        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_McpAwareTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "tools-4", "method": "tools/list", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "tools-4")
        atlas = next(
            item for item in result["result"]["mcpServerEntries"] if item["name"] == "atlas"
        )
        self.assertEqual(atlas["status"], "connected")
        self.assertEqual(atlas["source"], "runtime_dynamic")
        self.assertEqual(atlas["plugin_name"], "atlas_plugin")
        self.assertEqual(atlas["config"]["url"], "https://runtime.example/mcp")

    def test_browser_proxy_method_returns_proxy_payload(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "browser-proxy-1",
                            "method": "browser/proxy",
                            "params": {"method": "GET", "path": "/profiles", "profile": "openclaw"},
                        }
                    ),
                ]
            )
            + "\n"
        )

        with patch(
            "cli.agent_cli.app_server.dispatch_gateway_method",
        ) as gateway_mock:
            gateway_mock.return_value = type(
                "_Outcome",
                (),
                {
                    "ok": True,
                    "result": {"status": 200, "result": {"ok": True}, "files": []},
                    "transport_context": {},
                },
            )()
            code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = lines[-1]
        self.assertEqual(result["id"], "browser-proxy-1")
        self.assertEqual(result["result"]["status"], 200)
        self.assertTrue(result["result"]["result"]["ok"])
        gateway_mock.assert_called_once()

    def test_unknown_method_returns_json_rpc_error(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps({"id": "x", "method": "missing/method", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1]["id"], "x")
        self.assertEqual(lines[-1]["error"]["code"], -32601)
        self.assertEqual(lines[-1]["error"]["message"], "Method not found")
        self.assertEqual(lines[-1]["error"]["data"]["detail"], "missing/method")
        self.assertNotIn("compatibility", lines[-1]["error"]["data"])

    def test_unknown_method_detail_echo_guard(self) -> None:
        unknown_methods = [
            ("u1", "missing/method"),
            ("u2", "gateway.unknown.custom"),
            ("u3", "MISSING/Method"),
            ("u4", "feature/not-implemented"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": method_name, "params": {}}
                    for request_id, method_name in unknown_methods
                ],
            ],
        )
        by_id = {str(item.get("id")): item for item in lines if item.get("id") is not None}

        for request_id, method_name in unknown_methods:
            payload = by_id[request_id]
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(data.get("detail"), method_name)
            self.assertEqual(set(data.keys()), {"detail"})

    def test_unknown_method_case_echo_guard(self) -> None:
        case_variants = [
            ("uc1", "missing/method"),
            ("uc2", "Missing/Method"),
            ("uc3", "MISSING/METHOD"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": method_name, "params": {}}
                    for request_id, method_name in case_variants
                ],
            ],
        )

        echoed_detail_by_id = {
            str(item["id"]): str(item["error"]["data"]["detail"])
            for item in lines
            if item.get("id") in {request_id for request_id, _ in case_variants}
        }
        for request_id, method_name in case_variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(echoed_detail_by_id[request_id], method_name)
            self.assertEqual(set(dict(error["data"]).keys()), {"detail"})

        assert echoed_detail_by_id["uc1"] != echoed_detail_by_id["uc2"]
        assert echoed_detail_by_id["uc2"] != echoed_detail_by_id["uc3"]
        assert echoed_detail_by_id["uc1"] != echoed_detail_by_id["uc3"]

    def test_unknown_method_whitespace_echo_guard(self) -> None:
        whitespace_variants = [
            ("uw1", "  missing/method"),
            ("uw2", "missing/method  "),
            ("uw3", "\tmissing/method\t"),
            ("uw4", "  gateway.unknown.custom\t"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": method_name, "params": {}}
                    for request_id, method_name in whitespace_variants
                ],
            ],
        )

        for request_id, method_name in whitespace_variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(set(data.keys()), {"detail"})
            self.assertEqual(str(data.get("detail")), method_name.strip())
            self.assertNotEqual(method_name, method_name.strip())

    def test_unknown_method_trim_behavior_guard(self) -> None:
        variants = [
            ("utm-base", "missing/method", "missing/method"),
            ("utm-leading", "  missing/method", "missing/method"),
            ("utm-trailing", "missing/method\t", "missing/method"),
            ("utm-both", "\tmissing/method  ", "missing/method"),
            ("utm-inner-space", "missing /method", "missing /method"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": raw_method, "params": {}}
                    for request_id, raw_method, _ in variants
                ],
            ],
        )

        observed_detail: dict[str, str] = {}
        for request_id, raw_method, expected_detail in variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(set(data.keys()), {"detail"})
            self.assertEqual(str(data["detail"]), expected_detail)
            observed_detail[request_id] = str(data["detail"])
            if raw_method != raw_method.strip():
                self.assertNotEqual(raw_method, expected_detail)

        self.assertEqual(
            {
                observed_detail["utm-base"],
                observed_detail["utm-leading"],
                observed_detail["utm-trailing"],
                observed_detail["utm-both"],
            },
            {"missing/method"},
        )
        self.assertEqual(observed_detail["utm-inner-space"], "missing /method")

    def test_unknown_method_control_char_echo_guard(self) -> None:
        variants = [
            ("ucc-leading-tab", "\tmissing/method", "missing/method"),
            ("ucc-trailing-newline", "missing/method\n", "missing/method"),
            ("ucc-both", "\n\tmissing/method\t\n", "missing/method"),
            ("ucc-inner-tab", "missing\t/method", "missing\t/method"),
            ("ucc-inner-newline", "missing/\nmethod", "missing/\nmethod"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": raw_method, "params": {}}
                    for request_id, raw_method, _ in variants
                ],
            ],
        )

        for request_id, raw_method, expected_detail in variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(set(data.keys()), {"detail"})
            self.assertEqual(str(data["detail"]), expected_detail)
            if raw_method != raw_method.strip():
                self.assertEqual(expected_detail, raw_method.strip())

        observed = {
            request_id: str(
                next(item for item in lines if item.get("id") == request_id)["error"]["data"][
                    "detail"
                ]
            )
            for request_id, _, _ in variants
        }
        self.assertEqual(
            {observed["ucc-leading-tab"], observed["ucc-trailing-newline"], observed["ucc-both"]},
            {"missing/method"},
        )
        self.assertEqual(observed["ucc-inner-tab"], "missing\t/method")
        self.assertEqual(observed["ucc-inner-newline"], "missing/\nmethod")

    def test_unknown_method_boundary_char_guard(self) -> None:
        variants = [
            ("ubc-space", " missing/method ", "missing/method"),
            ("ubc-tab", "\tmissing/method\t", "missing/method"),
            ("ubc-newline", "\nmissing/method\n", "missing/method"),
            ("ubc-carriage-return", "\rmissing/method\r", "missing/method"),
            ("ubc-vertical-tab", "\x0bmissing/method\x0b", "missing/method"),
            ("ubc-form-feed", "\x0cmissing/method\x0c", "missing/method"),
            ("ubc-inner-control", "missing/\rmethod", "missing/\rmethod"),
            ("ubc-inner-mixed", "missing/\t\nmethod", "missing/\t\nmethod"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": raw_method, "params": {}}
                    for request_id, raw_method, _ in variants
                ],
            ],
        )

        observed: dict[str, str] = {}
        for request_id, _raw_method, expected_detail in variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(set(data.keys()), {"detail"})
            self.assertEqual(str(data["detail"]), expected_detail)
            observed[request_id] = str(data["detail"])

        # Guard: boundary-only control chars are trimmed; interior control chars are preserved.
        for request_id, raw_method, expected_detail in variants:
            if request_id.startswith("ubc-inner"):
                self.assertEqual(expected_detail, raw_method)
            else:
                self.assertEqual(expected_detail, raw_method.strip())

        self.assertEqual(
            {
                observed["ubc-space"],
                observed["ubc-tab"],
                observed["ubc-newline"],
                observed["ubc-carriage-return"],
                observed["ubc-vertical-tab"],
                observed["ubc-form-feed"],
            },
            {"missing/method"},
        )
        self.assertEqual(observed["ubc-inner-control"], "missing/\rmethod")
        self.assertEqual(observed["ubc-inner-mixed"], "missing/\t\nmethod")

    def test_unknown_method_boundary_only_chars_returns_method_required_contract(self) -> None:
        variants = [
            ("ubc-empty-space", " "),
            ("ubc-empty-tab", "\t"),
            ("ubc-empty-newline", "\n"),
            ("ubc-empty-crlf", "\r\n"),
            ("ubc-empty-vtab-formfeed", "\x0b\x0c"),
            ("ubc-empty-mixed", " \t\n\r "),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": raw_method, "params": {}}
                    for request_id, raw_method in variants
                ],
            ],
        )

        for request_id, _raw_method in variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32600)
            self.assertEqual(error["message"], "Invalid Request")
            self.assertEqual(data, {"detail": "method is required"})

    def test_unknown_method_unicode_boundary_whitespace_trim_guard(self) -> None:
        variants = [
            ("ubc-unicode-nbsp", "\u00a0missing/method\u00a0", "missing/method"),
            ("ubc-unicode-ideographic", "\u3000missing/method\u3000", "missing/method"),
            ("ubc-unicode-inner-nbsp", "missing/\u00a0method", "missing/\u00a0method"),
        ]
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                *[
                    {"id": request_id, "method": raw_method, "params": {}}
                    for request_id, raw_method, _ in variants
                ],
            ],
        )

        for request_id, _raw_method, expected_detail in variants:
            payload = next(item for item in lines if item.get("id") == request_id)
            error = dict(payload["error"])
            data = dict(error["data"])
            self.assertEqual(error["code"], -32601)
            self.assertEqual(error["message"], "Method not found")
            self.assertEqual(set(data.keys()), {"detail"})
            self.assertEqual(str(data["detail"]), expected_detail)

    def test_capability_method_surface_boundary_guard(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
            ],
        )
        init_result = next(item["result"] for item in lines if item.get("id") == "init")
        methods = list(init_result["capabilities"]["methods"])
        base_methods = list(APP_SERVER_BASE_METHODS)
        extension_methods = list(APP_SERVER_GATEWAY_EXTENSION_METHODS)

        self.assertEqual(methods, base_methods + extension_methods)
        self.assertEqual(
            app_server_gateway_extension_methods(),
            extension_methods,
        )
        self.assertEqual(len(methods), len(set(methods)))
        self.assertEqual(len(base_methods), len(set(base_methods)))
        self.assertEqual(len(extension_methods), len(set(extension_methods)))
        self.assertTrue(set(base_methods).isdisjoint(set(extension_methods)))

    def test_capability_method_family_guard_base_slash_extension_dot(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
            ],
        )
        init_result = next(item["result"] for item in lines if item.get("id") == "init")
        methods = list(init_result["capabilities"]["methods"])
        base_methods = methods[: len(APP_SERVER_BASE_METHODS)]
        extension_methods = methods[len(APP_SERVER_BASE_METHODS) :]

        assert base_methods == list(APP_SERVER_BASE_METHODS)
        assert extension_methods == list(APP_SERVER_GATEWAY_EXTENSION_METHODS)
        assert extension_methods == list(EXPECTED_APP_SERVER_GATEWAY_EXTENSION_METHODS)
        assert all(("." not in method) for method in base_methods)
        assert all((method == "initialize" or "/" in method) for method in base_methods)
        assert all(("." in method and "/" not in method) for method in extension_methods)

    def test_capability_method_name_uniqueness_casefold_guard(self) -> None:
        lines = self._run_app_server_requests(
            self.runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
            ],
        )
        init_result = next(item["result"] for item in lines if item.get("id") == "init")
        methods = [str(item or "") for item in list(init_result["capabilities"]["methods"])]
        casefolded = [item.casefold() for item in methods]

        assert len(methods) == len(set(methods))
        assert len(casefolded) == len(set(casefolded))

    def test_thread_start_list_and_resume_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            (workspace / ".git").write_text("", encoding="utf-8")
            (workspace / "AENGTHUB.md").write_text(
                "workspace guidance for app server test", encoding="utf-8"
            )
            runtime1 = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            stdout1 = io.StringIO()
            stdin1 = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "thread-start",
                                "method": "thread/start",
                                "params": {"name": "Morning", "cwd": str(workspace)},
                            }
                        ),
                        json.dumps(
                            {
                                "id": "run",
                                "method": "session/run",
                                "params": {"prompt": "list current directory"},
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code1 = app_server_main(runtime=runtime1, stdin=stdin1, stdout=stdout1)
            self.assertEqual(code1, 0)

            lines1 = [json.loads(line) for line in stdout1.getvalue().splitlines() if line.strip()]
            started = next(line for line in lines1 if line.get("id") == "thread-start")
            run = next(line for line in lines1 if line.get("id") == "run")
            thread_id = started["result"]["thread"]["thread_id"]
            self.assertTrue(thread_id)
            self.assertEqual(started["result"]["thread"]["cwd"], str(workspace.resolve()))
            self.assertFalse(started["result"]["thread"]["ephemeral"])
            self.assertTrue(Path(started["result"]["thread"]["path"]).is_absolute())
            self.assertEqual(started["result"]["thread"]["status"], "idle")
            self.assertIn("provider_status", started["result"]["thread"]["metadata"])
            self.assertIn("runtime_policy", started["result"]["thread"]["metadata"])
            self.assertEqual(started["result"]["approval_policy"], "never")
            self.assertEqual(started["result"]["sandbox_mode"], "workspace-write")
            self.assertIn("protocol_diagnostics", run["result"]["response"])
            self.assertIn("request_contract", run["result"]["response"]["protocol_diagnostics"])

            runtime2 = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            stdout2 = io.StringIO()
            stdin2 = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init2", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {"id": "thread-list", "method": "thread/list", "params": {"limit": 10}}
                        ),
                        json.dumps(
                            {
                                "id": "thread-resume",
                                "method": "thread/resume",
                                "params": {"threadId": thread_id},
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code2 = app_server_main(runtime=runtime2, stdin=stdin2, stdout=stdout2)
            self.assertEqual(code2, 0)

            lines2 = [json.loads(line) for line in stdout2.getvalue().splitlines() if line.strip()]
            listed = next(line for line in lines2 if line.get("id") == "thread-list")
            resumed = next(line for line in lines2 if line.get("id") == "thread-resume")
            self.assertEqual(listed["result"]["activeThreadId"], thread_id)
            self.assertEqual(listed["result"]["threads"][0]["thread_id"], thread_id)
            self.assertFalse(listed["result"]["threads"][0]["ephemeral"])
            self.assertEqual(listed["result"]["threads"][0]["status"], "not_loaded")
            self.assertEqual(resumed["result"]["thread"]["thread_id"], thread_id)
            self.assertEqual(resumed["result"]["thread"]["name"], "Morning")
            self.assertEqual(resumed["result"]["thread"]["cwd"], str(workspace.resolve()))
            self.assertEqual(resumed["result"]["thread"]["status"], "idle")
            self.assertEqual(resumed["result"]["model_provider"], "deepseek")
            self.assertEqual(resumed["result"]["approval_policy"], "never")
            self.assertEqual(resumed["result"]["sandbox_mode"], "workspace-write")
            self.assertEqual(
                resumed["result"]["resume_diagnostics"]["selected_source"], "thread_id"
            )
            self.assertEqual(
                resumed["result"]["resume_diagnostics"]["selected_thread_id"], thread_id
            )
            self.assertIn("protocol_diagnostics", resumed["result"]["turns"][0])
            self.assertIn("request_contract", resumed["result"]["turns"][0]["protocol_diagnostics"])
            self.assertEqual(
                resumed["result"]["history"],
                [
                    {"role": "user", "content": "list current directory"},
                    {
                        "role": "assistant",
                        "content": "Checking current workspace before execution.\n\nRecognized as a local directory query. Preparing shell execution.\n\nshell ok: Get-ChildItem -Force",
                    },
                ],
            )
            self.assertTrue(
                any(
                    item.get("item_type") == "workspace_context"
                    for item in resumed["result"]["context_items"]
                )
            )
            self.assertIn("workspace_context_snapshot", resumed["result"]["state"])
            self.assertIn("context_update_history", resumed["result"]["state"])

    def test_thread_resume_prefers_path_over_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            seed_runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            thread = seed_runtime.start_thread(name="Path Wins")
            seed_runtime.handle_prompt("list current directory")

            runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "thread-resume",
                                "method": "thread/resume",
                                "params": {
                                    "threadId": "not-a-valid-thread-id",
                                    "path": thread["rollout_path"],
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
            self.assertEqual(code, 0)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            resumed = next(line for line in lines if line.get("id") == "thread-resume")
            self.assertEqual(resumed["result"]["resume_source"], "path")
            self.assertEqual(resumed["result"]["thread"]["thread_id"], thread["thread_id"])
            self.assertEqual(resumed["result"]["thread"]["name"], "Path Wins")
            self.assertEqual(resumed["result"]["resume_diagnostics"]["selected_source"], "path")
            self.assertIn("thread_id", resumed["result"]["resume_diagnostics"]["ignored_sources"])
            self.assertEqual(
                resumed["result"]["resume_diagnostics"]["requested"]["thread_id"],
                "not-a-valid-thread-id",
            )
            self.assertTrue(Path(resumed["result"]["thread"]["path"]).is_absolute())

    def test_thread_resume_prefers_history_over_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            seed_runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            existing_thread = seed_runtime.start_thread(name="Existing Thread")
            seed_runtime.handle_prompt("original persisted turn")

            runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "thread-resume",
                                "method": "thread/resume",
                                "params": {
                                    "threadId": existing_thread["thread_id"],
                                    "history": [
                                        {
                                            "type": "message",
                                            "role": "user",
                                            "content": [
                                                {"type": "input_text", "text": "history override"}
                                            ],
                                        }
                                    ],
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)
            self.assertEqual(code, 0)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            resumed = next(line for line in lines if line.get("id") == "thread-resume")
            self.assertEqual(resumed["result"]["resume_source"], "history")
            self.assertNotEqual(
                resumed["result"]["thread"]["thread_id"], existing_thread["thread_id"]
            )
            self.assertEqual(
                resumed["result"]["history"],
                [{"role": "user", "content": "history override"}],
            )
            self.assertEqual(resumed["result"]["resume_diagnostics"]["selected_source"], "history")
            self.assertIn("thread_id", resumed["result"]["resume_diagnostics"]["ignored_sources"])
            self.assertEqual(
                resumed["result"]["resume_diagnostics"]["requested"]["history_count"], 1
            )

    def test_thread_resume_rejects_malformed_history_payload(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "thread-resume",
                            "method": "thread/resume",
                            "params": {
                                "history": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "input_text", "text": "missing type field"}
                                        ],
                                    }
                                ],
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "thread-resume")
        self.assertEqual(result["error"]["code"], -32602)
        self.assertEqual(result["error"]["data"]["detail"], "history[0]: type is required")

    def test_thread_resume_rejects_history_for_running_loaded_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            thread = runtime.start_thread(name="Running Thread")
            runtime.handle_prompt("list current directory")

            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "thread-resume",
                                "method": "thread/resume",
                                "params": {
                                    "threadId": thread["thread_id"],
                                    "history": [
                                        {
                                            "type": "message",
                                            "role": "user",
                                            "content": [
                                                {"type": "input_text", "text": "history override"}
                                            ],
                                        }
                                    ],
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            result = next(line for line in lines if line.get("id") == "thread-resume")
            self.assertEqual(result["error"]["code"], -32602)
            self.assertEqual(
                result["error"]["data"]["detail"],
                f"cannot resume thread {thread['thread_id']} with history while it is already running",
            )

    def test_thread_resume_rejects_path_mismatch_for_running_loaded_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ThreadStore(Path(temp_dir))
            runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            running_thread = runtime.start_thread(name="Running Thread")
            runtime.handle_prompt("list current directory")

            seed_runtime = AgentCliRuntime(
                agent=_AppServerAgent(),
                tools=_AppServerTools(),
                thread_store=store,
                runtime_policy=self._direct_exec_policy(),
            )
            other_thread = seed_runtime.start_thread(name="Other Thread")

            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "thread-resume",
                                "method": "thread/resume",
                                "params": {
                                    "threadId": running_thread["thread_id"],
                                    "path": other_thread["rollout_path"],
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            result = next(line for line in lines if line.get("id") == "thread-resume")
            self.assertEqual(result["error"]["code"], -32602)
            self.assertIn(
                f"cannot resume running thread {running_thread['thread_id']} with mismatched path",
                result["error"]["data"]["detail"],
            )
            self.assertIn(other_thread["rollout_path"], result["error"]["data"]["detail"])
            self.assertIn(running_thread["rollout_path"], result["error"]["data"]["detail"])

    def test_session_start_and_interrupt_emits_completed_notification(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "run-async",
                            "method": "session/start",
                            "params": {"prompt": "long running task", "stream": True},
                        }
                    ),
                    json.dumps({"id": "interrupt-1", "method": "session/interrupt", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        start_result = next(line for line in lines if line.get("id") == "run-async")
        interrupt_result = next(line for line in lines if line.get("id") == "interrupt-1")
        completed = next(line for line in lines if line.get("method") == "session/completed")
        self.assertTrue(start_result["result"]["accepted"])
        self.assertTrue(interrupt_result["result"]["ok"])
        self.assertEqual(completed["params"]["requestId"], "run-async")
        self.assertEqual(completed["params"]["response"]["turn_events"][0]["type"], "turn.started")
        self.assertEqual(
            completed["params"]["response"]["turn_events"][-1]["type"], "turn.completed"
        )
        self.assertIn(
            completed["params"]["response"]["tool_events"][-1]["name"],
            {"shell", "interrupted"},
        )

    def test_command_start_and_terminate_interrupts_shell(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "cmd-start",
                            "method": "command/start",
                            "params": {"command": "sleep", "stream": True},
                        }
                    ),
                    json.dumps({"id": "cmd-stop", "method": "command/terminate", "params": {}}),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        terminate_result = next(line for line in lines if line.get("id") == "cmd-stop")
        completed = next(line for line in lines if line.get("method") == "command/completed")
        self.assertTrue(terminate_result["result"]["ok"])
        self.assertEqual(completed["params"]["requestId"], "cmd-start")
        self.assertEqual(
            completed["params"]["response"]["tool_events"][-1]["summary"], "shell interrupted"
        )
        self.assertEqual(completed["params"]["exitCode"], 2)

    def test_command_activity_and_completed_continue_to_include_lifecycle_metadata(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_LifecycleAppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "python -i", "stream": True},
                },
                {
                    "id": "cmd-write",
                    "method": "command/writeStdin",
                    "params": {"sessionId": "session_1", "chars": "ping\n"},
                },
                {
                    "id": "cmd-stop",
                    "method": "command/terminate",
                    "params": {"sessionId": "session_1"},
                },
            ],
        )
        activity_lines = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        self.assertTrue(activity_lines)
        self.assertTrue(
            all(
                "lifecycle" in dict(item.get("params", {}).get("raw") or {})
                for item in activity_lines
            )
        )
        self.assertTrue(
            all("lifecycle" in dict(item.get("params") or {}) for item in activity_lines)
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("eventKind") == "input"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("lifecycleKind") == "input"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("lifecyclePhase") == "output"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(dict(item.get("params") or {}).get("stdin") == "ping\n" for item in activity_lines)
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("interactionInput") == "ping\n"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("source") == "unified_exec_startup"
                for item in activity_lines
                if dict(item.get("params") or {}).get("phase") == "output"
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("lifecycleSource") == "app_server_test"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("command") == "python -i"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("status") == "written"
                for item in activity_lines
                if dict(item.get("params") or {}).get("phase") == "input"
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("lifecycleStatus") == "written"
                for item in activity_lines
                if dict(item.get("params") or {}).get("phase") == "input"
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params") or {}).get("outputText") == "echo:ping"
                for item in activity_lines
            )
        )
        self.assertTrue(
            any(
                str(dict(item.get("params") or {}).get("outputChunk") or "").strip()
                for item in activity_lines
                if dict(item.get("params") or {}).get("phase") == "output"
            )
        )
        self.assertTrue(
            any(
                dict(item.get("params", {}).get("raw") or {}).get("lifecycle", {}).get("phase")
                == "output"
                for item in activity_lines
            )
        )
        self.assertTrue(
            all(
                dict(item.get("params", {}).get("lifecycle") or {}).get("call_id")
                == dict(item.get("params", {}).get("raw") or {}).get("lifecycle", {}).get("call_id")
                for item in activity_lines
            )
        )
        completed_line = next(line for line in lines if line.get("method") == "command/completed")
        completed_raw = dict(completed_line["params"].get("raw") or {})
        self.assertEqual(completed_line["params"]["callId"], "call_1")
        self.assertEqual(completed_line["params"]["lifecycle"]["call_id"], "call_1")
        self.assertEqual(completed_line["params"]["command"], "python -i")
        self.assertEqual(completed_line["params"]["source"], "unified_exec_startup")
        self.assertEqual(completed_line["params"]["status"], "interrupted")
        self.assertEqual(completed_line["params"]["lifecycleKind"], "end")
        self.assertEqual(completed_line["params"]["lifecyclePhase"], "completed")
        self.assertEqual(completed_line["params"]["lifecycleStatus"], "interrupted")
        self.assertEqual(completed_line["params"]["lifecycleSource"], "app_server_test")
        self.assertEqual(completed_line["params"]["aggregatedOutput"], "")
        self.assertEqual(completed_raw.get("lifecycle", {}).get("phase"), "completed")
        self.assertEqual(completed_raw.get("lifecycle", {}).get("source"), "app_server_test")

    def test_command_activity_defaults_event_kind_when_lifecycle_absent(self) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_NoLifecycleAppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "python -i", "stream": True},
                },
                {
                    "id": "cmd-write",
                    "method": "command/writeStdin",
                    "params": {"sessionId": "session_1", "chars": "ping\n"},
                },
                {
                    "id": "cmd-stop",
                    "method": "command/terminate",
                    "params": {"sessionId": "session_1"},
                },
            ],
        )
        start_result = next(line for line in lines if line.get("id") == "cmd-start")
        write_result = next(line for line in lines if line.get("id") == "cmd-write")
        terminate_result = next(line for line in lines if line.get("id") == "cmd-stop")
        activity_lines = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        self.assertEqual(start_result["result"]["lifecycle"]["kind"], "begin")
        self.assertEqual(start_result["result"]["lifecycle"]["phase"], "started")
        self.assertEqual(start_result["result"]["lifecycleKind"], "begin")
        self.assertEqual(start_result["result"]["lifecyclePhase"], "started")
        self.assertEqual(write_result["result"]["lifecycle"]["kind"], "input")
        self.assertEqual(write_result["result"]["lifecycle"]["phase"], "input")
        self.assertEqual(write_result["result"]["lifecycleKind"], "input")
        self.assertEqual(write_result["result"]["lifecyclePhase"], "input")
        self.assertEqual(terminate_result["result"]["lifecycle"]["kind"], "end")
        self.assertEqual(terminate_result["result"]["lifecycle"]["phase"], "completed")
        self.assertEqual(terminate_result["result"]["lifecycleKind"], "end")
        self.assertEqual(terminate_result["result"]["lifecyclePhase"], "completed")
        self.assertTrue(activity_lines)
        self.assertTrue(
            all(
                "lifecycle" not in dict(item.get("params", {}).get("raw") or {})
                for item in activity_lines
            )
        )
        kind_by_phase = {
            "input": "input",
            "output": "output",
            "completed": "end",
        }
        for phase, expected_kind in kind_by_phase.items():
            self.assertTrue(
                any(
                    item.get("params", {}).get("phase") == phase
                    and item.get("params", {}).get("eventKind") == expected_kind
                    for item in activity_lines
                ),
                msg=f"missing {expected_kind} event for phase {phase}",
            )

    def test_command_protocol_surfaces_io_mode_across_start_write_activity_and_completed(
        self,
    ) -> None:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=_IoModeAppServerTools(),
            runtime_policy=self._direct_exec_policy(),
        )
        lines = self._run_app_server_requests(
            runtime,
            [
                {"id": "init", "method": "initialize", "params": {}},
                {"method": "initialized", "params": {}},
                {
                    "id": "cmd-start",
                    "method": "command/start",
                    "params": {"command": "python -i", "stream": True},
                },
                {
                    "id": "cmd-write",
                    "method": "command/writeStdin",
                    "params": {"sessionId": "session_1", "chars": "ping\n"},
                },
                {
                    "id": "cmd-stop",
                    "method": "command/terminate",
                    "params": {"sessionId": "session_1"},
                },
            ],
        )
        start_result = next(line for line in lines if line.get("id") == "cmd-start")
        write_result = next(line for line in lines if line.get("id") == "cmd-write")
        completed_line = next(line for line in lines if line.get("method") == "command/completed")
        activity_lines = [
            line
            for line in lines
            if line.get("method") == "session/activity"
            and line.get("params", {}).get("requestId") == "cmd-start"
        ]
        self.assertEqual(start_result["result"]["ioMode"], "pty")
        self.assertEqual(write_result["result"]["ioMode"], "pty")
        self.assertEqual(completed_line["params"]["ioMode"], "pty")
        self.assertTrue(activity_lines)
        self.assertTrue(
            all(item.get("params", {}).get("ioMode") == "pty" for item in activity_lines)
        )
        self.assertEqual(dict(start_result["result"].get("raw") or {}).get("io_mode"), "pty")
        self.assertEqual(dict(write_result["result"].get("raw") or {}).get("io_mode"), "pty")
        self.assertEqual(dict(completed_line["params"].get("raw") or {}).get("io_mode"), "pty")

    def test_gateway_dispatch_routes_event_through_runtime_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_gateway_runtime(Path(tmpdir))
            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "gw-1",
                                "method": "gateway/dispatch",
                                "params": {
                                    "eventType": "demo.event",
                                    "sourceKind": "webhook",
                                    "sourceId": "demo:webhook",
                                    "connectorKey": "demo_webhook",
                                    "payload": {"ticket": "T-1"},
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            result = next(line for line in lines if line.get("id") == "gw-1")
            self.assertEqual(result["result"]["event"]["event_type"], "demo.event")
            self.assertEqual(result["result"]["decision"]["targetKind"], "plugin_workflow")
            self.assertEqual(result["result"]["decision"]["pluginName"], "demo_plugin")
            self.assertEqual(result["result"]["decision"]["workflowName"], "handle_demo_event")
            self.assertEqual(result["result"]["decision"]["trigger"]["trigger_key"], "demo_trigger")
            self.assertEqual(result["result"]["workflowRun"]["plugin_name"], "demo_plugin")
            self.assertEqual(
                [item["stage"] for item in result["result"]["auditRecords"]],
                ["ingress", "route"],
            )

    def test_gateway_dispatch_rejects_invalid_payload_shape(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "gw-invalid",
                            "method": "gateway/dispatch",
                            "params": {
                                "eventType": "demo.event",
                                "sourceKind": "manual",
                                "sourceId": "cli",
                                "payload": "not-an-object",
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "gw-invalid")
        self.assertEqual(result["error"]["code"], -32602)
        self.assertEqual(
            result["error"]["data"]["detail"],
            "params.payload must be an object when provided",
        )

    def test_gateway_webhook_verifies_signature_and_routes_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_gateway_runtime(Path(tmpdir))
            raw_body = json.dumps({"ticket": "T-2"})
            secret = "super-secret"
            signature = "sha256=" + compute_hmac_sha256_hex(secret, raw_body)
            stdout = io.StringIO()
            stdin = _PipedStringIO(
                "\n".join(
                    [
                        json.dumps({"id": "init", "method": "initialize", "params": {}}),
                        json.dumps({"method": "initialized", "params": {}}),
                        json.dumps(
                            {
                                "id": "gw-webhook",
                                "method": "gateway/webhook",
                                "params": {
                                    "connectorKey": "demo_webhook",
                                    "eventType": "demo.event",
                                    "sourceId": "demo:webhook",
                                    "rawBody": raw_body,
                                    "headers": {
                                        "X-Hub-Signature-256": signature,
                                        "Authorization": "Bearer secret-token",
                                        "X-GitHub-Event": "issues",
                                        "X-Token": "abc123",
                                    },
                                    "verifySignature": {"secret": secret},
                                },
                            }
                        ),
                    ]
                )
                + "\n"
            )

            code = app_server_main(runtime=runtime, stdin=stdin, stdout=stdout)

            lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(code, 0)
            result = next(line for line in lines if line.get("id") == "gw-webhook")
            self.assertTrue(result["result"]["verification"]["verified"])
            self.assertEqual(result["result"]["decision"]["targetKind"], "plugin_workflow")
            self.assertEqual(result["result"]["event"]["connector_key"], "demo_webhook")
            self.assertEqual(result["result"]["event"]["payload"], {"ticket": "T-2"})
            self.assertEqual(
                result["result"]["event"]["metadata"]["headers"]["X-Hub-Signature-256"], "***"
            )
            self.assertEqual(
                result["result"]["event"]["metadata"]["headers"]["Authorization"], "***"
            )
            self.assertEqual(result["result"]["event"]["metadata"]["headers"]["X-Token"], "***")
            self.assertEqual(
                result["result"]["event"]["metadata"]["headers"]["X-GitHub-Event"], "issues"
            )

    def test_gateway_webhook_rejects_invalid_signature(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "gw-bad-sig",
                            "method": "gateway/webhook",
                            "params": {
                                "connectorKey": "demo_webhook",
                                "eventType": "demo.event",
                                "rawBody": '{"ticket":"T-3"}',
                                "headers": {"X-Hub-Signature-256": "sha256=deadbeef"},
                                "verifySignature": {"secret": "super-secret"},
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "gw-bad-sig")
        self.assertEqual(result["error"]["code"], -32020)

    def test_gateway_webhook_rejects_payload_when_raw_body_is_present(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "gw-split",
                            "method": "gateway/webhook",
                            "params": {
                                "connectorKey": "demo_webhook",
                                "eventType": "demo.event",
                                "payload": {"ticket": "caller-version"},
                                "rawBody": '{"ticket":"signed-version"}',
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "gw-split")
        self.assertEqual(result["error"]["code"], -32602)
        self.assertEqual(
            result["error"]["data"]["detail"],
            "params.payload must not be provided when params.rawBody is present",
        )

    def test_action_execute_runs_controlled_worker(self) -> None:
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "action-1",
                            "method": "action/execute",
                            "params": {
                                "action": "noop",
                                "parameters": {"mode": "dry_run"},
                                "requestId": "req-1",
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(runtime=self.runtime, stdin=stdin, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "action-1")
        self.assertTrue(result["result"]["actionResult"]["ok"])
        self.assertEqual(result["result"]["actionResult"]["action"], "noop")
        self.assertEqual(result["result"]["actionResult"]["request_id"], "req-1")

    def test_action_execute_supports_http_request_via_worker(self) -> None:
        captured: dict[str, object] = {}

        class _FakeResponse:
            def __init__(self, *, url: str, status_code: int, body: str) -> None:
                self._url = url
                self._status_code = status_code
                self._body = body.encode("utf-8")
                self.headers = {"Content-Type": "application/json; charset=utf-8"}

            def read(self) -> bytes:
                return self._body

            def getcode(self) -> int:
                return self._status_code

            def geturl(self) -> str:
                return self._url

        def _open(request, *, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            return _FakeResponse(
                url=request.full_url,
                status_code=200,
                body=json.dumps({"ok": True, "ticket": "INC-9"}),
            )

        worker = ControlledActionWorker(http_client=HttpClient(open_url=_open))
        stdout = io.StringIO()
        stdin = _PipedStringIO(
            "\n".join(
                [
                    json.dumps({"id": "init", "method": "initialize", "params": {}}),
                    json.dumps({"method": "initialized", "params": {}}),
                    json.dumps(
                        {
                            "id": "action-http",
                            "method": "action/execute",
                            "params": {
                                "action": "http_request",
                                "parameters": {
                                    "method": "GET",
                                    "url": "https://api.example.com/tickets",
                                    "allowed_hosts": ["api.example.com"],
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n"
        )

        code = app_server_main(
            runtime=self.runtime, action_worker=worker, stdin=stdin, stdout=stdout
        )

        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(code, 0)
        result = next(line for line in lines if line.get("id") == "action-http")
        self.assertTrue(result["result"]["actionResult"]["ok"])
        self.assertEqual(captured["url"], "https://api.example.com/tickets")
        self.assertEqual(result["result"]["actionResult"]["output"]["json_data"]["ticket"], "INC-9")
