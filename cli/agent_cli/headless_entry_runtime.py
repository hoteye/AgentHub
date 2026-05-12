from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

_HEADLESS_RESPONSE_PATH_ENV = "AGENT_CLI_HEADLESS_RESPONSE_PATH"


@dataclass(frozen=True)
class HeadlessResumeRequest:
    thread_id: str | None
    rollout_path: str | None
    resume_last: bool


@dataclass(frozen=True)
class HeadlessRuntimeBuildRequest:
    runtime_policy: Any
    persistent: bool
    resume: HeadlessResumeRequest


def resume_request_from_args(args: Any) -> HeadlessResumeRequest:
    return HeadlessResumeRequest(
        thread_id=getattr(args, "resume", None),
        rollout_path=getattr(args, "resume_path", None),
        resume_last=bool(getattr(args, "resume_last", False)),
    )


def runtime_build_request(
    *,
    args: Any,
    runtime_policy: Any,
    requires_persistent_runtime_fn: Callable[..., bool],
    has_explicit_resume_request_fn: Callable[..., bool],
) -> HeadlessRuntimeBuildRequest:
    resume = resume_request_from_args(args)
    persistent = requires_persistent_runtime_fn(
        persistent=bool(getattr(args, "serve", False)),
        resume_thread_id=resume.thread_id,
        resume_rollout_path=resume.rollout_path,
        resume_last=resume.resume_last,
        has_explicit_resume_request_fn=has_explicit_resume_request_fn,
    )
    return HeadlessRuntimeBuildRequest(
        runtime_policy=runtime_policy,
        persistent=persistent,
        resume=resume,
    )


def build_headless_runtime(
    *,
    runtime_policy: Any,
    persistent: bool,
    resume_thread_id: str | None,
    resume_rollout_path: str | None,
    resume_last: bool,
    requires_persistent_runtime_fn: Callable[..., bool],
    has_explicit_resume_request_fn: Callable[..., bool],
    build_persistent_runtime_fn: Callable[..., Any],
    runtime_cls: type[Any],
    cwd_fn: Callable[[], Path],
) -> Any:
    if requires_persistent_runtime_fn(
        persistent=persistent,
        resume_thread_id=resume_thread_id,
        resume_rollout_path=resume_rollout_path,
        resume_last=resume_last,
        has_explicit_resume_request_fn=has_explicit_resume_request_fn,
    ):
        runtime = build_persistent_runtime_fn(
            runtime_policy=runtime_policy,
            resume_active_thread=False,
            start_thread_if_unavailable=False,
        )
    else:
        runtime = runtime_cls(runtime_policy=runtime_policy)
    if not has_explicit_resume_request_fn(
        thread_id=resume_thread_id,
        rollout_path=resume_rollout_path,
        resume_last=resume_last,
    ):
        runtime.set_cwd(cwd_fn())
        start_thread = getattr(runtime, "start_thread", None)
        if (
            persistent
            and callable(start_thread)
            and getattr(runtime, "thread_store", None) is not None
        ):
            start_thread()
    return runtime


def resume_headless_runtime(
    runner: Any,
    resume_thread_id: str | None,
    *,
    resume_rollout_path: str | None,
    resume_last: bool,
    resolve_resume_request_fn: Callable[..., tuple[str | None, str | None]],
    apply_runtime_resume_request_fn: Callable[..., None],
    path_cls: type[Path],
) -> str | None:
    try:
        requested_thread_id, rollout_path = resolve_resume_request_fn(
            runner,
            thread_id=resume_thread_id,
            rollout_path=resume_rollout_path,
            resume_last=resume_last,
        )
    except Exception as exc:
        return str(exc)
    if rollout_path:
        current_thread_id = str(getattr(runner, "thread_id", "") or "").strip()
        thread_store = getattr(runner, "thread_store", None)
        if current_thread_id and thread_store is not None:
            try:
                current = thread_store.get_thread(current_thread_id)
            except Exception:
                current = None
            if isinstance(current, dict):
                current_rollout_path = str(current.get("rollout_path") or "").strip()
                if current_rollout_path:
                    try:
                        if (
                            path_cls(current_rollout_path).expanduser().resolve()
                            == path_cls(rollout_path).expanduser().resolve()
                        ):
                            return None
                    except OSError:
                        pass
        try:
            apply_runtime_resume_request_fn(runner, rollout_path=rollout_path)
        except Exception as exc:
            return f"failed to resume rollout path {rollout_path}: {exc}"
        return None
    thread_id = str(requested_thread_id or "").strip()
    if not thread_id:
        return None
    current_thread_id = str(getattr(runner, "thread_id", "") or "").strip()
    if current_thread_id == thread_id:
        return None
    try:
        apply_runtime_resume_request_fn(runner, thread_id=thread_id)
    except Exception as exc:
        return f"failed to resume thread {thread_id}: {exc}"
    return None


def handle_headless_prompt(
    *,
    args: Any,
    input_stream: TextIO,
    output_stream: TextIO,
    error_stream: TextIO,
    execute_prompt_fn: Callable[..., Any],
    resolve_prompt_fn: Callable[[Any, TextIO], str | None],
    render_text_output_fn: Callable[[Any], str],
    prompt_response_to_dict_fn: Callable[[Any], dict[str, Any]],
    exit_code_for_response_fn: Callable[[Any], int],
) -> int:
    prompt = resolve_prompt_fn(args, input_stream)
    if prompt is None:
        print("headless error: provide --prompt, --provider-status, or --stdin", file=error_stream)
        return 1
    prompt = prompt.strip()
    if not prompt:
        print("headless error: prompt is empty", file=error_stream)
        return 1

    output_format = _output_format_from_args(args)
    response = execute_prompt_fn(
        prompt,
        output_stream=output_stream,
        stream_json=(output_format in {"stream-json", "codex-jsonl"}),
        codex_jsonl=(output_format == "codex-jsonl"),
    )
    _write_headless_response_snapshot_if_requested(
        response,
        prompt_response_to_dict_fn=prompt_response_to_dict_fn,
    )
    exit_code = exit_code_for_response_fn(response)
    if output_format in {"stream-json", "codex-jsonl"}:
        return exit_code
    if output_format == "json":
        import json

        print(
            json.dumps(prompt_response_to_dict_fn(response), ensure_ascii=False, indent=2),
            file=output_stream,
        )
    else:
        print(render_text_output_fn(response), file=output_stream)
    return exit_code


def _write_headless_response_snapshot_if_requested(
    response: Any,
    *,
    prompt_response_to_dict_fn: Callable[[Any], dict[str, Any]],
) -> None:
    destination = str(os.environ.get(_HEADLESS_RESPONSE_PATH_ENV) or "").strip()
    if not destination:
        return
    path = Path(destination).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = prompt_response_to_dict_fn(response)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _output_format_from_args(args: Any) -> str:
    value = str(getattr(args, "output_format", "") or "").strip().lower()
    if value:
        return value
    if bool(getattr(args, "jsonl", False)):
        return "stream-json"
    if bool(getattr(args, "json", False)):
        return "json"
    return "text"
