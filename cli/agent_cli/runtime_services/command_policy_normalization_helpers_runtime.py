from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Callable


def normalized_policy_context(
    command: str,
    *,
    environ: dict[str, str] | None,
    command_policy_mode_env: str,
    test_policy_env: str,
    test_lock_path_env: str,
) -> dict[str, str]:
    env = dict(os.environ if environ is None else environ)
    return {
        "normalized_command": str(command or "").strip(),
        "policy_mode": str(env.get(command_policy_mode_env) or "").strip().lower(),
        "test_policy": str(env.get(test_policy_env) or "").strip().lower(),
        "lock_path": str(env.get(test_lock_path_env) or "").strip(),
    }


def allowed_command_policy_decision(
    command: str,
    *,
    policy_mode: str,
    test_policy: str,
    decision_cls: Callable[..., Any],
    effective_command: str | None = None,
    is_test_command: bool = False,
    test_command_kind: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any:
    return decision_cls(
        command=command,
        effective_command=command if effective_command is None else effective_command,
        allowed=True,
        is_test_command=is_test_command,
        test_command_kind=test_command_kind,
        policy_mode=policy_mode,
        test_policy=test_policy,
        metadata=dict(metadata or {}),
    )


def denied_command_policy_decision(
    command: str,
    *,
    policy_mode: str,
    test_policy: str,
    test_command_kind: str,
    error_code: str,
    error_message: str,
    decision_cls: Callable[..., Any],
    metadata: dict[str, Any] | None = None,
) -> Any:
    return decision_cls(
        command=command,
        effective_command=command,
        allowed=False,
        is_test_command=True,
        test_command_kind=test_command_kind,
        policy_mode=policy_mode,
        test_policy=test_policy,
        error_code=error_code,
        error_message=error_message,
        metadata=dict(metadata or {}),
    )


def evaluate_command_policy_decision(
    normalized_command: str,
    *,
    policy_mode: str,
    test_policy: str,
    lock_path: str,
    decision_cls: Callable[..., Any],
    contains_compound_operator_fn: Callable[[str], bool],
    safe_split_command_fn: Callable[[str], list[str]],
    test_command_info_fn: Callable[[list[str]], dict[str, Any]],
    validate_compound_command_segments_fn: Callable[[str], Any],
    explicit_pytest_targets_fn: Callable[..., list[str]],
    wrap_command_with_test_lock_fn: Callable[..., str],
    denied_decision_fn: Callable[..., Any],
) -> Any:
    if not normalized_command or (not policy_mode and not test_policy):
        return allowed_command_policy_decision(
            normalized_command,
            policy_mode=policy_mode,
            test_policy=test_policy,
            decision_cls=decision_cls,
        )

    if contains_compound_operator_fn(normalized_command):
        argv = safe_split_command_fn(normalized_command)
        info = test_command_info_fn(argv)
        if info["is_test_command"]:
            return denied_decision_fn(
                normalized_command,
                policy_mode=policy_mode,
                test_policy=test_policy,
                test_command_kind=str(info["kind"]),
                error_code="test_command_compound_denied",
                error_message="background teammate test commands cannot use shell chaining or multiple commands",
            )

        validation = validate_compound_command_segments_fn(normalized_command)
        if not validation.safe:
            return denied_decision_fn(
                normalized_command,
                policy_mode=policy_mode,
                test_policy=test_policy,
                test_command_kind="",
                error_code=validation.error_code,
                error_message=validation.error_message,
                metadata={
                    "compound_segments": validation.segments,
                    "dangerous_constructs": validation.dangerous_constructs,
                },
            )

        return allowed_command_policy_decision(
            normalized_command,
            policy_mode=policy_mode,
            test_policy=test_policy,
            decision_cls=decision_cls,
            metadata={
                "compound_segments": validation.segments,
                "compound_segments_count": len(validation.segments),
            },
        )

    argv = safe_split_command_fn(normalized_command)
    info = test_command_info_fn(argv)
    if not info["is_test_command"]:
        return allowed_command_policy_decision(
            normalized_command,
            policy_mode=policy_mode,
            test_policy=test_policy,
            decision_cls=decision_cls,
        )

    kind = str(info["kind"])
    metadata: dict[str, Any] = {"command_argv": list(argv)}
    if test_policy == "scoped_only":
        if kind != "pytest":
            return denied_decision_fn(
                normalized_command,
                policy_mode=policy_mode,
                test_policy=test_policy,
                test_command_kind=kind,
                error_code="test_runner_not_allowed",
                error_message="background teammate may only run scoped pytest commands during automated verification",
                metadata=metadata,
            )
        explicit_targets = explicit_pytest_targets_fn(argv, start_index=int(info["argv_start"]))
        metadata["explicit_targets"] = list(explicit_targets)
        if not explicit_targets:
            return denied_decision_fn(
                normalized_command,
                policy_mode=policy_mode,
                test_policy=test_policy,
                test_command_kind=kind,
                error_code="test_scope_required",
                error_message="background teammate test commands must target explicit test files or node ids",
                metadata=metadata,
            )

    effective_command = normalized_command
    if lock_path:
        metadata["test_lock_path"] = str(Path(lock_path).expanduser())
        effective_command = wrap_command_with_test_lock_fn(argv, lock_path=lock_path)

    return allowed_command_policy_decision(
        normalized_command,
        effective_command=effective_command,
        is_test_command=True,
        test_command_kind=kind,
        policy_mode=policy_mode,
        test_policy=test_policy,
        decision_cls=decision_cls,
        metadata=metadata,
    )


def wrap_command_with_test_lock(
    argv: list[str],
    *,
    lock_path: str,
    test_lock_runner_path: Path,
) -> str:
    normalized_lock_path = str(Path(lock_path).expanduser())
    wrapper_argv = [
        sys.executable,
        str(test_lock_runner_path),
        "--lock-path",
        normalized_lock_path,
        "--",
        *list(argv or []),
    ]
    if os.name == "nt":
        return subprocess.list2cmdline(wrapper_argv)
    return " ".join(shlex.quote(token) for token in wrapper_argv)
