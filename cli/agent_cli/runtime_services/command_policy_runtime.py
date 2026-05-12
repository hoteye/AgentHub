from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_services import command_policy_normalization_helpers_runtime
from cli.agent_cli.runtime_services import command_policy_projection_helpers_runtime
from cli.agent_cli.runtime_services import command_policy_pure_helpers_runtime

COMMAND_POLICY_MODE_ENV = "AGENT_CLI_COMMAND_POLICY_MODE"
TEST_POLICY_ENV = "AGENT_CLI_TEST_POLICY"
TEST_LOCK_PATH_ENV = "AGENT_CLI_TEST_LOCK_PATH"

_POLICY_DENIED_STATUS = "policy_denied"
_COMPOUND_OPERATORS = ("&&", "||", ";", "\n", "\r")
_DANGEROUS_BUILTINS = {"eval", "source", "."}
_PYTEST_OPTIONS_WITH_VALUE = {
    "-c",
    "-k",
    "-m",
    "-o",
    "--basetemp",
    "--confcutdir",
    "--cov",
    "--cov-config",
    "--cov-report",
    "--dist",
    "--durations",
    "--ignore",
    "--ignore-glob",
    "--import-mode",
    "--junitxml",
    "--lfnf",
    "--log-cli-format",
    "--log-cli-level",
    "--log-date-format",
    "--log-file",
    "--log-file-date-format",
    "--log-file-format",
    "--log-file-level",
    "--log-format",
    "--log-level",
    "--maxfail",
    "--override-ini",
    "--pastebin",
    "--pythonwarnings",
    "--report-log",
    "--rootdir",
    "--tb",
}
_BLOCKED_TEST_RUNNERS = {
    "tox",
    "nox",
    "nosetests",
}
_TEST_LOCK_RUNNER_PATH = Path(__file__).resolve().with_name("test_command_lock_runner.py")


@dataclass(slots=True)
class CommandPolicyDecision:
    command: str
    effective_command: str
    allowed: bool
    is_test_command: bool = False
    test_command_kind: str = ""
    policy_mode: str = ""
    test_policy: str = ""
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return command_policy_projection_helpers_runtime.command_policy_payload(
            self,
            policy_denied_status=_POLICY_DENIED_STATUS,
        )


class CommandPolicyError(RuntimeError):
    def __init__(self, decision: CommandPolicyDecision) -> None:
        self.decision = decision
        self.payload = decision.payload()
        super().__init__(decision.error_message or "command denied by policy")


@dataclass(slots=True)
class CompoundCommandValidation:
    segments: list[str]
    safe: bool
    error_code: str = ""
    error_message: str = ""
    dangerous_constructs: list[str] = field(default_factory=list)


def split_compound_command(command: str) -> list[str]:
    """Split compound command by &&, ||, ; operators (quote-aware).

    Pipe | is NOT split as it's part of a single command.
    Returns list of non-empty command segments.
    """
    return command_policy_pure_helpers_runtime.split_compound_command(command)


def validate_compound_command_segments(command: str) -> CompoundCommandValidation:
    """Validate compound command segments for dangerous constructs.

    Checks for:
    - Subshells: (...), $(...)
    - Variable expansion: $VAR, ${VAR} (outside quotes)
    - Command substitution: `...`
    - Dangerous builtins: eval, source

    Returns validation result with segments and safety status.
    """
    return CompoundCommandValidation(
        **command_policy_pure_helpers_runtime.validate_compound_command_segments(
            command,
            dangerous_builtins=_DANGEROUS_BUILTINS,
        )
    )


def evaluate_command_policy(
    command: str,
    *,
    environ: dict[str, str] | None = None,
) -> CommandPolicyDecision:
    context = command_policy_normalization_helpers_runtime.normalized_policy_context(
        command,
        environ=environ,
        command_policy_mode_env=COMMAND_POLICY_MODE_ENV,
        test_policy_env=TEST_POLICY_ENV,
        test_lock_path_env=TEST_LOCK_PATH_ENV,
    )
    return command_policy_normalization_helpers_runtime.evaluate_command_policy_decision(
        context["normalized_command"],
        policy_mode=context["policy_mode"],
        test_policy=context["test_policy"],
        lock_path=context["lock_path"],
        decision_cls=CommandPolicyDecision,
        contains_compound_operator_fn=_contains_compound_operator,
        safe_split_command_fn=_safe_split_command,
        test_command_info_fn=_test_command_info,
        validate_compound_command_segments_fn=validate_compound_command_segments,
        explicit_pytest_targets_fn=_explicit_pytest_targets,
        wrap_command_with_test_lock_fn=wrap_command_with_test_lock,
        denied_decision_fn=_denied_decision,
    )


def wrap_tool_event_with_policy(
    event: ToolEvent,
    *,
    decision: CommandPolicyDecision,
) -> ToolEvent:
    return command_policy_projection_helpers_runtime.wrap_tool_event_with_policy(
        event,
        decision=decision,
    )


def policy_denied_tool_event(
    *,
    tool_name: str,
    decision: CommandPolicyDecision,
) -> ToolEvent:
    return command_policy_projection_helpers_runtime.policy_denied_tool_event(
        tool_name=tool_name,
        decision=decision,
        policy_denied_status=_POLICY_DENIED_STATUS,
    )


def wrap_command_with_test_lock(argv: list[str], *, lock_path: str) -> str:
    return command_policy_normalization_helpers_runtime.wrap_command_with_test_lock(
        argv,
        lock_path=lock_path,
        test_lock_runner_path=_TEST_LOCK_RUNNER_PATH,
    )


def _denied_decision(
    command: str,
    *,
    policy_mode: str,
    test_policy: str,
    test_command_kind: str,
    error_code: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> CommandPolicyDecision:
    return command_policy_normalization_helpers_runtime.denied_command_policy_decision(
        command,
        policy_mode=policy_mode,
        test_policy=test_policy,
        test_command_kind=test_command_kind,
        error_code=error_code,
        error_message=error_message,
        metadata=metadata,
        decision_cls=CommandPolicyDecision,
    )


def _contains_compound_operator(command: str) -> bool:
    return command_policy_pure_helpers_runtime.contains_compound_operator(
        command,
        compound_operators=_COMPOUND_OPERATORS,
    )


def _safe_split_command(command: str) -> list[str]:
    return command_policy_pure_helpers_runtime.safe_split_command(command)


def _test_command_info(argv: list[str]) -> dict[str, Any]:
    return command_policy_pure_helpers_runtime.test_command_info(
        argv,
        blocked_test_runners=_BLOCKED_TEST_RUNNERS,
    )


def _looks_like_python_launcher(name: str) -> bool:
    return command_policy_pure_helpers_runtime.looks_like_python_launcher(name)


def _explicit_pytest_targets(argv: list[str], *, start_index: int) -> list[str]:
    return command_policy_pure_helpers_runtime.explicit_pytest_targets(
        argv,
        start_index=start_index,
        pytest_options_with_value=_PYTEST_OPTIONS_WITH_VALUE,
    )


def _pytest_option_consumes_value(token: str) -> bool:
    return command_policy_pure_helpers_runtime.pytest_option_consumes_value(
        token,
        pytest_options_with_value=_PYTEST_OPTIONS_WITH_VALUE,
    )


def _is_explicit_pytest_target(token: str) -> bool:
    return command_policy_pure_helpers_runtime.is_explicit_pytest_target(token)
