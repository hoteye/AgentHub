from __future__ import annotations

from pathlib import Path

import pytest

from cli.agent_cli.models import AgentIntent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.thread_store import ThreadStore


class _WorkspaceTools:
    def __init__(self, root: Path) -> None:
        self.PROJECT_ROOT = str(root)

    def set_workspace_root(self, path) -> Path:
        resolved = Path(path).resolve()
        self.PROJECT_ROOT = str(resolved)
        return resolved


class _OverflowRetryAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._overflow_raised = False

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "anthropic",
            "provider_model": "claude-sonnet-4-6",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        if text == "second turn" and not self._overflow_raised:
            self._overflow_raised = True
            raise RuntimeError("prompt is too long for the context window")
        return AgentIntent(assistant_text=f"echo: {text}")


class _NonOverflowAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "anthropic",
            "provider_model": "claude-sonnet-4-6",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        if text == "second turn":
            raise RuntimeError("provider unavailable")
        return AgentIntent(assistant_text=f"echo: {text}")


class _RepeatedOverflowAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "anthropic",
            "provider_model": "claude-sonnet-4-6",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        if text == "second turn":
            raise RuntimeError("prompt is too long for the context window")
        return AgentIntent(assistant_text=f"echo: {text}")


class _DiagnosticsOverflowRetryAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._overflow_raised = False

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "openai",
            "provider_model": "gpt-5.4",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        if text == "second turn" and not self._overflow_raised:
            self._overflow_raised = True
            exc = RuntimeError("provider rejected request")
            setattr(
                exc,
                "agenthub_provider_diagnostics",
                {
                    "classification": "prompt_too_long",
                    "status_code": 400,
                },
            )
            raise exc
        return AgentIntent(
            assistant_text=f"echo: {text}",
            protocol_diagnostics={"history_compaction": "provider_placeholder"},
        )


class _RetryFailureDiagnosticsAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._overflow_raised = False

    @staticmethod
    def provider_status() -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "anthropic",
            "provider_model": "claude-sonnet-4-6",
        }

    def plan(self, text, history=None, *, tool_executor=None, attachments=None, input_items=None):
        self.calls.append(
            {
                "text": text,
                "history": list(history or []),
                "input_items": list(input_items or []),
            }
        )
        if text != "second turn":
            return AgentIntent(assistant_text=f"echo: {text}")
        if not self._overflow_raised:
            self._overflow_raised = True
            raise RuntimeError("prompt is too long for the context window")
        exc = RuntimeError("provider unavailable after retry")
        setattr(
            exc,
            "agenthub_provider_diagnostics",
            {
                "classification": "provider_unavailable",
                "retryable": True,
            },
        )
        raise exc


def _input_item_texts(items: list[dict]) -> list[str]:
    texts: list[str] = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            if content.strip():
                texts.append(content.strip())
            continue
        if not isinstance(content, list):
            continue
        parts = [
            str(entry.get("text") or "").strip()
            for entry in content
            if isinstance(entry, dict) and str(entry.get("text") or "").strip()
        ]
        if parts:
            texts.append("\n".join(parts))
    return texts


def test_runtime_retries_once_after_context_overflow_with_reactive_compaction(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _OverflowRetryAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction retry")

    runtime.handle_prompt("first turn")
    response = runtime.handle_prompt("second turn")

    assert response.assistant_text == "echo: second turn"
    assert len(agent.calls) == 3
    assert runtime._base_history
    expected_summary = (
        "Previous conversation summary:\n"
        "1. user: first turn\n"
        "1. assistant: echo: first turn"
    )
    assert any(
        str(item.get("content") or "").strip() == expected_summary
        for item in list(runtime._base_history or [])
    )
    compacted = [item for item in runtime.rollout_items if str(item.get("type") or "") == "compacted"]
    assert len(compacted) == 1
    assert compacted[0]["reason"] == "provider_context_overflow_retry"
    assert compacted[0]["trigger_error_type"] == "RuntimeError"
    assert compacted[0]["trigger_error_text"] == "prompt is too long for the context window"
    assert compacted[0]["replacement_history"] == [
        {
            "role": "assistant",
            "content": expected_summary,
        }
    ]
    retry_texts = _input_item_texts(agent.calls[-1]["input_items"])
    assert expected_summary in retry_texts
    assert response.protocol_diagnostics["history_compaction"]["mode"] == "reactive_retry"
    assert response.protocol_diagnostics["history_compaction"]["reason"] == "provider_context_overflow_retry"
    assert response.protocol_diagnostics["history_compaction"]["trigger_error_type"] == "RuntimeError"
    assert (
        response.protocol_diagnostics["history_compaction"]["trigger_error_text"]
        == "prompt is too long for the context window"
    )


def test_runtime_retries_when_provider_diagnostics_classifies_prompt_too_long(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _DiagnosticsOverflowRetryAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction provider diagnostics overflow")

    runtime.handle_prompt("first turn")
    response = runtime.handle_prompt("second turn")

    assert response.assistant_text == "echo: second turn"
    assert len(agent.calls) == 3
    compacted = [item for item in runtime.rollout_items if str(item.get("type") or "") == "compacted"]
    assert len(compacted) == 1
    assert response.protocol_diagnostics["history_compaction"]["mode"] == "reactive_retry"
    assert response.protocol_diagnostics["history_compaction"]["reason"] == "provider_context_overflow_retry"
    assert response.protocol_diagnostics["history_compaction"]["trigger_error_type"] == "RuntimeError"
    assert response.protocol_diagnostics["history_compaction"]["trigger_error_text"] == "provider rejected request"


def test_runtime_raises_after_single_reactive_compaction_retry_if_overflow_persists(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _RepeatedOverflowAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction unrecoverable overflow")

    runtime.handle_prompt("first turn")

    with pytest.raises(RuntimeError, match="prompt is too long for the context window"):
        runtime.handle_prompt("second turn")

    assert len(agent.calls) == 3
    compacted = [item for item in runtime.rollout_items if str(item.get("type") or "") == "compacted"]
    assert len(compacted) == 1
    assert compacted[0]["reason"] == "provider_context_overflow_retry"
    retry_texts = _input_item_texts(agent.calls[-1]["input_items"])
    assert any(text.startswith("Previous conversation summary:\n") for text in retry_texts)


def test_runtime_attaches_history_compaction_diagnostics_to_retry_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _RetryFailureDiagnosticsAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction retry failure diagnostics")

    runtime.handle_prompt("first turn")

    with pytest.raises(RuntimeError, match="provider unavailable after retry") as exc_info:
        runtime.handle_prompt("second turn")

    assert len(agent.calls) == 3
    diagnostics = dict(getattr(exc_info.value, "agenthub_provider_diagnostics", {}) or {})
    assert diagnostics["classification"] == "provider_unavailable"
    assert diagnostics["history_compaction"] == {
        "mode": "reactive_retry",
        "reason": "provider_context_overflow_retry",
        "trigger_error_type": "RuntimeError",
        "trigger_error_text": "prompt is too long for the context window",
    }
    assert getattr(exc_info.value, "agenthub_history_compaction_diagnostics") == diagnostics["history_compaction"]
    compacted = [item for item in runtime.rollout_items if str(item.get("type") or "") == "compacted"]
    assert len(compacted) == 1


def test_runtime_does_not_retry_for_non_overflow_provider_errors(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _NonOverflowAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="non overflow provider error")

    runtime.handle_prompt("first turn")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        runtime.handle_prompt("second turn")

    assert len(agent.calls) == 2
    assert not any(str(item.get("type") or "") == "compacted" for item in runtime.rollout_items)


def test_runtime_does_not_retry_when_overflow_has_no_replacement_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _RepeatedOverflowAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction missing replacement history")

    runtime.handle_prompt("first turn")
    runtime._build_auto_compaction_replacement_history = lambda: []

    with pytest.raises(RuntimeError, match="prompt is too long for the context window"):
        runtime.handle_prompt("second turn")

    assert len(agent.calls) == 2
    assert not any(str(item.get("type") or "") == "compacted" for item in runtime.rollout_items)


def test_runtime_raises_for_invalid_reactive_compaction_replacement_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state")
    agent = _RepeatedOverflowAgent()
    runtime = AgentCliRuntime(
        agent=agent,
        tools=_WorkspaceTools(workspace),
        thread_store=store,
    )
    runtime.set_cwd(workspace)
    runtime.start_thread(name="reactive compaction invalid replacement history")

    runtime.handle_prompt("first turn")
    runtime._build_auto_compaction_replacement_history = lambda: [{"role": "user", "content": "bad summary"}]

    with pytest.raises(RuntimeError, match="invalid reactive compaction replacement history"):
        runtime.handle_prompt("second turn")

    assert len(agent.calls) == 2
    assert not any(str(item.get("type") or "") == "compacted" for item in runtime.rollout_items)
