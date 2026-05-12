from __future__ import annotations

import shlex

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.scripts.run_multi_llm_live_cases_catalog import LiveCase


class RuntimeToolExecutor:
    def __init__(self, runtime: AgentCliRuntime) -> None:
        self.runtime = runtime

    def __call__(self, text: str) -> tuple[str, list[ToolEvent]]:
        result = self.run_structured(text)
        return result.assistant_text, list(result.tool_events or [])

    def run_structured(self, text: str) -> CommandExecutionResult:
        return self.runtime._run_command_text_result(text)

    @staticmethod
    def interrupt_requested() -> bool:
        return False

    @staticmethod
    def interrupt_result() -> tuple[str, list[ToolEvent]]:
        return "Execution interrupted.", [
            ToolEvent(
                name="interrupted",
                ok=False,
                summary="execution interrupted",
                payload={"reason": "user_interrupt", "interrupt_requested": True},
            )
        ]


def _command_text(command: str, *, workdir: str) -> str:
    command = str(command or "").strip()
    if not command:
        raise RuntimeError("tool command is empty")
    return f"/command {shlex.quote(command)} --cwd {shlex.quote(str(workdir))} --timeout 30"


def _run_tool_command(executor: RuntimeToolExecutor, *, command: str, workdir: str) -> list[ToolEvent]:
    text = _command_text(command, workdir=workdir)
    _, events = executor(text)
    return list(events or [])


def _run_setup_command(executor: RuntimeToolExecutor, *, command_text: str) -> CommandExecutionResult:
    command_text = str(command_text or "").strip()
    if not command_text:
        raise RuntimeError("setup command is empty")
    return executor.run_structured(command_text)


def _spawn_agent_command(case: LiveCase) -> str:
    role = str(case.role or "").strip() or "subagent"
    overrides = dict(case.spawn_overrides or {})
    provider = str(overrides.get("provider") or "").strip()
    model = str(overrides.get("model") or "").strip()
    reasoning_effort = str(overrides.get("reasoning_effort") or "").strip()
    timeout = int(overrides.get("timeout") or 0)
    reason = str(overrides.get("reason") or "").strip()
    flags = " ".join(
        item
        for item in (
            f"--provider {provider}" if provider else "",
            f"--model {model}" if model else "",
            f"--reasoning-effort {reasoning_effort}" if reasoning_effort else "",
            f"--timeout {timeout}" if timeout > 0 else "",
            f"--reason {shlex.quote(reason)}" if reason else "",
        )
        if item
    )
    return f"/spawn_agent {role} {shlex.quote(case.prompt)} {flags}".strip()


def _wait_agent_command(
    agent_id: str,
    *,
    timeout_ms: int,
    reason: str = "",
    wait_required: bool | None = None,
) -> str:
    extras: list[str] = []
    if timeout_ms > 0:
        extras.append(f"--timeout-ms {int(timeout_ms)}")
    if str(reason or "").strip():
        extras.append(f"--reason {shlex.quote(str(reason).strip())}")
    if wait_required is True:
        extras.append("--wait-required")
    elif wait_required is False:
        extras.append("--no-wait-required")
    return f"/wait_agent {agent_id} {' '.join(extras)}".strip()


def _line_value(text: str, key: str) -> str:
    needle = f"{key}="
    for line in str(text or "").splitlines():
        if line.strip().startswith(needle):
            return line.strip()[len(needle) :].strip()
    return ""


def _line_items(text: str, key: str) -> list[str]:
    value = _line_value(text, key)
    if not value or value == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
