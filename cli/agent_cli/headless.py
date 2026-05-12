from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from cli.agent_cli import headless_entry_runtime as headless_entry_runtime_service
from cli.agent_cli import headless_helpers as headless_helpers_service
from cli.agent_cli import headless_runtime as headless_runtime_service
from cli.agent_cli import (
    headless_shell_projection_runtime as headless_shell_projection_runtime_service,
)
from cli.agent_cli import headless_stream_runtime as headless_stream_runtime_service
from cli.agent_cli import headless_wiring_runtime as headless_wiring_runtime_service
from cli.agent_cli import (
    runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service,
)
from cli.agent_cli.models import (
    PromptResponse,
    response_items_to_text,
    tool_event_is_soft_failure,
)
from cli.agent_cli.resume_support import (
    apply_runtime_resume_request,
    has_explicit_resume_request,
    resolve_resume_request,
)
from cli.agent_cli.runtime_kernels.base import KernelEngine, StartSessionRequest
from cli.agent_cli.runtime_kernels.codex_sidecar import CodexSidecarKernel
from cli.agent_cli.runtime_kernels.codex_sidecar.runtime_adapter import (
    CodexSidecarRuntimeAdapter,
)
from cli.agent_cli.runtime_kernels.routing import normalize_kernel_engine
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.startup_cwd import resolve_startup_cwd
from cli.agent_cli.ui.theme import builtin_theme_ids

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime

    HeadlessRuntime = AgentCliRuntime | CodexSidecarRuntimeAdapter
else:
    HeadlessRuntime = Any


def build_parser() -> argparse.ArgumentParser:
    return headless_helpers_service.build_parser(
        theme_ids_provider=builtin_theme_ids,
    )


def has_headless_request(args: argparse.Namespace) -> bool:
    return headless_helpers_service.has_headless_request(args)


def prompt_response_to_dict(response: PromptResponse) -> dict[str, Any]:
    return headless_wiring_runtime_service.prompt_response_to_dict(
        response,
        service=headless_stream_runtime_service,
        canonical_turn_events_fn=_canonical_turn_events,
        tool_event_to_dict_fn=_tool_event_to_dict,
        activity_event_to_dict_fn=_activity_event_to_dict,
    )


def run_headless(
    args: argparse.Namespace,
    *,
    runtime: AgentCliRuntime | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr

    output_normalization_error = headless_helpers_service.normalize_headless_output_args(args)
    if output_normalization_error:
        print(f"headless error: {output_normalization_error}", file=error_stream)
        return 1

    validation_error = _validate_args(args)
    if validation_error:
        print(f"headless error: {validation_error}", file=error_stream)
        return 1

    runtime_policy = _runtime_policy_from_args(args)
    build_request = headless_entry_runtime_service.runtime_build_request(
        args=args,
        runtime_policy=runtime_policy,
        requires_persistent_runtime_fn=headless_runtime_service.requires_persistent_runtime,
        has_explicit_resume_request_fn=has_explicit_resume_request,
    )
    engine = normalize_kernel_engine(getattr(args, "engine", None))
    if engine == "codex_sidecar" and has_explicit_resume_request(
        thread_id=build_request.resume.thread_id,
        rollout_path=build_request.resume.rollout_path,
        resume_last=build_request.resume.resume_last,
    ):
        print(
            "headless error: --engine codex_sidecar does not support resume flags yet",
            file=error_stream,
        )
        return 1

    runner: HeadlessRuntime | None = None
    created_runtime = runtime is None
    try:
        runner = runtime or build_headless_runtime(
            runtime_policy=build_request.runtime_policy,
            persistent=build_request.persistent,
            resume_thread_id=build_request.resume.thread_id,
            resume_rollout_path=build_request.resume.rollout_path,
            resume_last=build_request.resume.resume_last,
            engine=engine,
        )
        resume_error = _resume_headless_runtime(
            runner,
            build_request.resume.thread_id,
            resume_rollout_path=build_request.resume.rollout_path,
            resume_last=build_request.resume.resume_last,
        )
        if resume_error:
            print(f"headless error: {resume_error}", file=error_stream)
            return 1
        codex_headless_contract_runtime_service.set_runtime_headless_mode(
            runner,
            serve=bool(args.serve),
        )
        _configure_runtime_for_headless_args(runner, runtime_policy=runtime_policy)
        if args.serve:
            return _run_serve_loop(runner, input_stream=input_stream, output_stream=output_stream)

        return headless_entry_runtime_service.handle_headless_prompt(
            args=args,
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
            execute_prompt_fn=lambda prompt, *, output_stream, stream_json, codex_jsonl=False: _execute_prompt(
                runner,
                prompt,
                output_stream=output_stream,
                jsonl=stream_json,
                codex_jsonl=codex_jsonl,
            ),
            resolve_prompt_fn=_resolve_prompt,
            render_text_output_fn=_render_text_output,
            prompt_response_to_dict_fn=prompt_response_to_dict,
            exit_code_for_response_fn=_exit_code_for_response,
        )
    finally:
        if created_runtime and runner is not None:
            _close_created_headless_runtime(runner)


def build_headless_runtime(
    *,
    runtime_policy: RuntimePolicy,
    persistent: bool,
    resume_thread_id: str | None = None,
    resume_rollout_path: str | None = None,
    resume_last: bool = False,
    engine: KernelEngine | None = None,
) -> HeadlessRuntime:
    if engine == "codex_sidecar":
        return build_codex_sidecar_headless_runtime(
            runtime_policy=runtime_policy,
            cwd=resolve_startup_cwd(),
        )
    from cli.agent_cli.runtime import AgentCliRuntime

    return headless_entry_runtime_service.build_headless_runtime(
        runtime_policy=runtime_policy,
        persistent=persistent,
        resume_thread_id=resume_thread_id,
        resume_rollout_path=resume_rollout_path,
        resume_last=resume_last,
        requires_persistent_runtime_fn=headless_runtime_service.requires_persistent_runtime,
        has_explicit_resume_request_fn=has_explicit_resume_request,
        build_persistent_runtime_fn=build_persistent_runtime,
        runtime_cls=AgentCliRuntime,
        cwd_fn=resolve_startup_cwd,
    )


def build_codex_sidecar_headless_runtime(
    *,
    runtime_policy: RuntimePolicy,
    cwd: Path | None = None,
    codex_bin: str | Path | None = None,
) -> CodexSidecarRuntimeAdapter:
    resolved_cwd = (cwd or resolve_startup_cwd()).resolve()
    kernel = CodexSidecarKernel(codex_bin=codex_bin, cwd=resolved_cwd)
    try:
        policy_status = runtime_policy.to_status()
        metadata: dict[str, Any] = {
            "runtime_policy": policy_status,
            "approvalPolicy": policy_status.get("approval_policy", ""),
            "sandbox": policy_status.get("sandbox_mode", ""),
        }
        session = asyncio.run(
            kernel.start_session(
                StartSessionRequest(
                    cwd=str(resolved_cwd),
                    metadata=metadata,
                )
            )
        )
    except Exception:
        asyncio.run(kernel.aclose())
        raise
    return CodexSidecarRuntimeAdapter(kernel=kernel, session=session)


def build_persistent_runtime(
    *,
    runtime_policy: RuntimePolicy | None = None,
    resume_active_thread: bool = True,
    start_thread_if_unavailable: bool = True,
    cleanup_stale_pending_approvals: bool = True,
    stale_pending_approval_seconds: int | None = None,
) -> AgentCliRuntime:
    from cli.agent_cli.runtime_factory import build_persistent_runtime as _build_persistent_runtime

    kwargs = {}
    if stale_pending_approval_seconds is not None:
        kwargs["stale_pending_approval_seconds"] = stale_pending_approval_seconds
    return _build_persistent_runtime(
        runtime_policy=runtime_policy,
        resume_active_thread=resume_active_thread,
        start_thread_if_unavailable=start_thread_if_unavailable,
        cleanup_stale_pending_approvals=cleanup_stale_pending_approvals,
        **kwargs,
    )


def _close_created_headless_runtime(runner: HeadlessRuntime) -> None:
    if isinstance(runner, CodexSidecarRuntimeAdapter):
        asyncio.run(runner.kernel.aclose())


def _resume_headless_runtime(
    runner: HeadlessRuntime,
    resume_thread_id: str | None,
    *,
    resume_rollout_path: str | None = None,
    resume_last: bool = False,
) -> str | None:
    return headless_entry_runtime_service.resume_headless_runtime(
        runner,
        resume_thread_id,
        resume_rollout_path=resume_rollout_path,
        resume_last=resume_last,
        resolve_resume_request_fn=resolve_resume_request,
        apply_runtime_resume_request_fn=apply_runtime_resume_request,
        path_cls=Path,
    )


def _validate_args(args: argparse.Namespace) -> str | None:
    return headless_runtime_service.validate_headless_args(args)


def _runtime_policy_from_args(args: argparse.Namespace) -> RuntimePolicy:
    return headless_helpers_service.runtime_policy_from_args(args)


def _configure_runtime_for_headless_args(
    runner: HeadlessRuntime,
    *,
    runtime_policy: RuntimePolicy,
) -> None:
    headless_wiring_runtime_service.configure_runtime_for_policy(
        runner,
        runtime_policy=runtime_policy,
    )


def _execute_prompt(
    runner: HeadlessRuntime,
    prompt: str,
    *,
    output_stream: TextIO,
    jsonl: bool,
    request_id: str | None = None,
    codex_jsonl: bool = False,
) -> PromptResponse:
    return headless_wiring_runtime_service.execute_prompt(
        runner,
        prompt,
        output_stream=output_stream,
        jsonl=jsonl,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        service=headless_stream_runtime_service,
        headless_thread_id_fn=_headless_thread_id,
        emit_reference_jsonl_event_fn=_emit_reference_jsonl_event,
        turn_event_signature_fn=_turn_event_signature,
        turn_event_backfill_signature_fn=_turn_event_backfill_signature,
        temporary_turn_event_callback_fn=_temporary_turn_event_callback,
        canonical_turn_events_fn=_canonical_turn_events,
    )


def _run_serve_loop(
    runner: HeadlessRuntime,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> int:
    return headless_wiring_runtime_service.run_serve_loop(
        runner,
        input_stream=input_stream,
        output_stream=output_stream,
        service=headless_stream_runtime_service,
        emit_json_line_fn=_emit_json_line,
        request_id_for_payload_fn=_request_id_for_payload,
        resolve_serve_prompt_fn=_resolve_serve_prompt,
        execute_prompt_fn=_execute_prompt,
        prompt_response_to_dict_fn=prompt_response_to_dict,
        exit_code_for_response_fn=_exit_code_for_response,
    )


def _resolve_prompt(args: argparse.Namespace, input_stream: TextIO) -> str | None:
    return headless_runtime_service.resolve_prompt(
        args,
        input_stream,
        has_piped_input_fn=_has_piped_input,
    )


def _render_text_output(response: PromptResponse) -> str:
    from cli.agent_cli.runtime_core.command_dispatch import tool_result_fallback_text

    return headless_wiring_runtime_service.render_text_output(
        response,
        service=headless_runtime_service,
        response_items_to_text_fn=response_items_to_text,
        tool_result_fallback_text_fn=tool_result_fallback_text,
    )


def _exit_code_for_response(response: PromptResponse) -> int:
    return headless_wiring_runtime_service.exit_code_for_response(
        response,
        service=headless_runtime_service,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure,
    )


def _emit_reference_jsonl_event(
    output_stream: TextIO,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    codex_jsonl: bool = False,
) -> None:
    headless_stream_runtime_service.emit_reference_jsonl_event(
        output_stream,
        payload,
        request_id=request_id,
        codex_jsonl=codex_jsonl,
        emit_json_line_fn=_emit_json_line,
    )


def _turn_event_backfill_signature(event: dict[str, Any]) -> str:
    return headless_wiring_runtime_service.turn_event_backfill_signature(
        event,
        service=headless_stream_runtime_service,
        normalized_turn_event_value_fn=_normalized_turn_event_value,
    )


def _temporary_activity_callback(
    runner: HeadlessRuntime,
    callback,
):
    return headless_stream_runtime_service.temporary_activity_callback(runner, callback)


def _temporary_turn_event_callback(
    runner: HeadlessRuntime,
    callback,
):
    return headless_stream_runtime_service.temporary_turn_event_callback(runner, callback)


_headless_thread_id = headless_stream_runtime_service.headless_thread_id
_request_id_for_payload = headless_stream_runtime_service.request_id_for_payload
_resolve_serve_prompt = headless_stream_runtime_service.resolve_serve_prompt
_tool_event_to_dict = headless_stream_runtime_service.tool_event_to_dict
_activity_event_to_dict = headless_stream_runtime_service.activity_event_to_dict
_has_piped_input = headless_runtime_service.has_piped_input
_emit_json_line = headless_stream_runtime_service.emit_json_line
_turn_event_signature = headless_stream_runtime_service.turn_event_signature
_normalized_turn_event_value = headless_stream_runtime_service.normalized_turn_event_value
_canonical_turn_events = headless_shell_projection_runtime_service.canonical_turn_events
_shell_turn_events_from_tool_events = (
    headless_shell_projection_runtime_service.shell_turn_events_from_tool_events
)
_shell_item_events_from_payload = (
    headless_shell_projection_runtime_service.shell_item_events_from_payload
)
_shell_activity_to_turn_event = (
    headless_shell_projection_runtime_service.shell_activity_to_turn_event
)
_shell_phase = headless_shell_projection_runtime_service.shell_phase
_shell_status = headless_shell_projection_runtime_service.shell_status
_shell_interaction_input = headless_shell_projection_runtime_service.shell_interaction_input
_shell_output_text = headless_shell_projection_runtime_service.shell_output_text
_shell_turn_item = headless_shell_projection_runtime_service.shell_turn_item
_shell_call_id = headless_shell_projection_runtime_service.shell_call_id
