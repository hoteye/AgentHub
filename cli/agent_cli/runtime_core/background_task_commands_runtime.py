from __future__ import annotations

import shlex
from typing import Any, Callable

from cli.agent_cli.slash_parser import SlashInvocation, legacy_handler_arg_text, slash_keyword_map, slash_switch_set


def parse_option_tokens(
    raw_args: str,
    *,
    value_flags: set[str],
) -> tuple[list[str], dict[str, str]]:
    try:
        tokens = shlex.split(str(raw_args or "").strip(), posix=True)
    except ValueError as exc:
        raise ValueError(f"failed to parse args: {exc}") from exc
    positionals: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in value_flags:
            if index + 1 >= len(tokens):
                raise ValueError(f"missing value for {token}")
            options[token[2:]] = tokens[index + 1]
            index += 2
            continue
        positionals.append(token)
        index += 1
    return positionals, options


def _slash_parsed_args(slash_invocation: SlashInvocation | None) -> tuple[list[str], dict[str, Any]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, Any] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def _parsed_args(runtime: Any, arg_text: str, slash_invocation: SlashInvocation | None) -> tuple[list[str], dict[str, Any]]:
    slash_args = _slash_parsed_args(slash_invocation)
    if slash_args is not None:
        return slash_args
    return runtime._parse_args(arg_text)


def _compat_arg_text(arg_text: str, slash_invocation: SlashInvocation | None) -> str:
    if slash_invocation is None:
        return arg_text
    return legacy_handler_arg_text(slash_invocation)


def parse_background_worker_run_once_args(
    raw_args: str,
    *,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
) -> tuple[int, float]:
    _, options = parse_option_tokens_fn(
        raw_args,
        value_flags={"--max-jobs", "--stale-after-seconds"},
    )
    try:
        max_jobs = max(1, int(options.get("max-jobs") or 1))
    except (TypeError, ValueError):
        raise ValueError("invalid --max-jobs for background_worker_run_once") from None
    try:
        stale_after_seconds = max(1.0, float(options.get("stale-after-seconds") or 30.0))
    except (TypeError, ValueError):
        raise ValueError("invalid --stale-after-seconds for background_worker_run_once") from None
    return max_jobs, stale_after_seconds


def parse_background_worker_start_args(
    raw_args: str,
    *,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
) -> tuple[int, float, float]:
    _, options = parse_option_tokens_fn(
        raw_args,
        value_flags={"--max-jobs", "--poll-interval", "--stale-after-seconds"},
    )
    try:
        max_jobs = max(1, int(options.get("max-jobs") or 1))
    except (TypeError, ValueError):
        raise ValueError("invalid --max-jobs for background_worker_start") from None
    try:
        poll_interval = max(0.1, float(options.get("poll-interval") or 1.0))
    except (TypeError, ValueError):
        raise ValueError("invalid --poll-interval for background_worker_start") from None
    try:
        stale_after_seconds = max(1.0, float(options.get("stale-after-seconds") or 30.0))
    except (TypeError, ValueError):
        raise ValueError("invalid --stale-after-seconds for background_worker_start") from None
    return max_jobs, poll_interval, stale_after_seconds


def parse_background_worker_stop_args(raw_args: str) -> bool:
    try:
        tokens = shlex.split(str(raw_args or "").strip(), posix=True)
    except ValueError as exc:
        raise ValueError(f"failed to parse background worker stop args: {exc}") from exc
    return any(str(token).strip() == "--force" for token in tokens)


def handle_background_teammate_command(
    runtime: Any,
    *,
    arg_text: str,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
    parse_csv_paths_fn: Callable[[Any], list[str]],
    parse_positive_float_fn: Callable[..., float],
    submit_background_teammate_fn: Callable[..., str],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[Any]]:
    slash_args = _slash_parsed_args(slash_invocation)
    if slash_args is not None:
        positionals, options = slash_args
    else:
        positionals, options = parse_option_tokens_fn(
            arg_text,
            value_flags={
                "--provider",
                "--model",
                "--reasoning-effort",
                "--cwd",
                "--approval-policy",
                "--sandbox-mode",
                "--allowed-paths",
                "--blocked-paths",
                "--timeout-seconds",
            },
        )
    task_text = " ".join(positionals).strip()
    if not task_text:
        return ("background teammate requires a task prompt", [])
    sandbox_mode = str(options.get("sandbox-mode") or "read-only").strip() or "read-only"
    allowed_paths = parse_csv_paths_fn(options.get("allowed-paths"))
    blocked_paths = parse_csv_paths_fn(options.get("blocked-paths"))
    timeout_seconds = str(options.get("timeout-seconds") or "").strip()
    timeout_payload: dict[str, Any] = {}
    if timeout_seconds:
        timeout_payload["timeout_seconds"] = parse_positive_float_fn(
            timeout_seconds,
            option_name="--timeout-seconds",
        )
    if sandbox_mode == "workspace-write":
        event = runtime.request_background_teammate_approval(
            task_text,
            requested_by="cli",
            provider=str(options.get("provider") or "").strip(),
            model=str(options.get("model") or "").strip(),
            reasoning_effort=str(options.get("reasoning-effort") or "").strip(),
            task_cwd=str(options.get("cwd") or getattr(runtime, "cwd", "") or "").strip(),
            queue_cwd=str(getattr(runtime, "cwd", "") or "").strip(),
            approval_policy=str(options.get("approval-policy") or "never").strip() or "never",
            sandbox_mode=sandbox_mode,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            timeout_seconds=timeout_payload.get("timeout_seconds"),
        )
        return (str((event.payload or {}).get("summary_text") or "background teammate approval requested"), [event])
    return (submit_background_teammate_fn(runtime, raw_args=arg_text), [])


def handle_background_task_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
    int_option: Callable[..., int | None],
    workflows_text_fn: Callable[..., str],
    background_tasks_text_fn: Callable[..., str],
    background_worker_status_text_fn: Callable[..., str],
    background_worker_start_text_fn: Callable[..., str],
    background_worker_stop_text_fn: Callable[..., str],
    background_worker_run_once_text_fn: Callable[..., str],
    submit_background_benchmark_fn: Callable[..., str],
    submit_background_smoke_fn: Callable[..., str],
    handle_background_teammate_fn: Callable[..., tuple[str, list[Any]]],
    background_task_status_text_fn: Callable[..., str],
    background_task_cancel_text_fn: Callable[..., str],
    background_task_retry_text_fn: Callable[..., str],
    background_task_apply_text_fn: Callable[..., str],
    background_task_reject_text_fn: Callable[..., str],
) -> tuple[str, list[Any]] | None:
    if name == "workflows":
        _, options = _parsed_args(runtime, arg_text, slash_invocation)
        try:
            limit = int_option(options.get("limit"), default=20) or 20
        except ValueError as exc:
            return (str(exc), [])
        return (workflows_text_fn(runtime, limit=max(1, limit)), [])
    if name == "background_tasks":
        _, options = _parsed_args(runtime, arg_text, slash_invocation)
        try:
            limit = int_option(options.get("limit"), default=20) or 20
        except ValueError as exc:
            return (str(exc), [])
        return (background_tasks_text_fn(runtime, limit=max(1, limit)), [])
    if name == "background_worker_status":
        return (background_worker_status_text_fn(runtime), [])
    if name == "background_worker_start":
        return (background_worker_start_text_fn(runtime, raw_args=_compat_arg_text(arg_text, slash_invocation)), [])
    if name == "background_worker_stop":
        return (background_worker_stop_text_fn(runtime, raw_args=_compat_arg_text(arg_text, slash_invocation)), [])
    if name == "background_worker_run_once":
        return (background_worker_run_once_text_fn(runtime, raw_args=_compat_arg_text(arg_text, slash_invocation)), [])
    if name == "background_benchmark":
        return (submit_background_benchmark_fn(runtime, raw_args=_compat_arg_text(arg_text, slash_invocation)), [])
    if name == "background_smoke":
        return (submit_background_smoke_fn(runtime, raw_args=_compat_arg_text(arg_text, slash_invocation)), [])
    if name == "background_teammate":
        return handle_background_teammate_fn(
            runtime,
            arg_text=_compat_arg_text(arg_text, slash_invocation),
            slash_invocation=slash_invocation,
        )
    if name == "background_task_status":
        positionals, _ = _parsed_args(runtime, arg_text, slash_invocation)
        task_id = str(positionals[0] if positionals else "").strip()
        if not task_id:
            return ("background_task_status requires a task_id", [])
        return (background_task_status_text_fn(runtime, task_id=task_id), [])
    if name == "background_task_cancel":
        positionals, _ = _parsed_args(runtime, arg_text, slash_invocation)
        task_id = str(positionals[0] if positionals else "").strip()
        if not task_id:
            return ("background_task_cancel requires a task_id", [])
        return (background_task_cancel_text_fn(runtime, task_id=task_id), [])
    if name == "background_task_retry":
        positionals, _ = _parsed_args(runtime, arg_text, slash_invocation)
        task_id = str(positionals[0] if positionals else "").strip()
        if not task_id:
            return ("background_task_retry requires a task_id", [])
        return (background_task_retry_text_fn(runtime, task_id=task_id), [])
    if name == "background_task_apply":
        positionals, _ = _parsed_args(runtime, arg_text, slash_invocation)
        task_id = str(positionals[0] if positionals else "").strip()
        if not task_id:
            return ("background_task_apply requires a task_id", [])
        return (background_task_apply_text_fn(runtime, task_id=task_id), [])
    if name == "background_task_reject":
        positionals, _ = _parsed_args(runtime, arg_text, slash_invocation)
        task_id = str(positionals[0] if positionals else "").strip()
        if not task_id:
            return ("background_task_reject requires a task_id", [])
        return (background_task_reject_text_fn(runtime, task_id=task_id), [])
    return None
