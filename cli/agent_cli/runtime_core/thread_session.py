from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.models_turn_events_runtime import normalized_plan_payload
from cli.agent_cli.startup_debug import startup_timer


def _history_validation_error(index: int, message: str) -> ValueError:
    return ValueError(f"history[{index}]: {message}")


def _validated_history_content_blocks(index: int, content: Any) -> None:
    if isinstance(content, str):
        return
    if isinstance(content, dict):
        block_type = str(content.get("type") or content.get("item_type") or "").strip()
        if not block_type:
            raise _history_validation_error(index, "content.type is required")
        return
    if not isinstance(content, list):
        raise _history_validation_error(index, "content must be a string, object, or array")
    for block_index, block in enumerate(list(content or [])):
        if not isinstance(block, dict):
            raise _history_validation_error(index, f"content[{block_index}] must be an object")
        block_type = str(block.get("type") or block.get("item_type") or "").strip()
        if not block_type:
            raise _history_validation_error(index, f"content[{block_index}].type is required")
        if (
            block_type in {"input_text", "output_text", "text", "summary_text"}
            and "text" not in block
        ):
            raise _history_validation_error(index, f"content[{block_index}].text is required")


def validate_resume_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        raise ValueError("history must be an array")
    normalized_history: list[dict[str, Any]] = []
    for index, raw_item in enumerate(list(history or [])):
        if not isinstance(raw_item, dict):
            raise _history_validation_error(index, "item must be an object")
        item = (
            dict(raw_item.get("item") or raw_item)
            if isinstance(raw_item.get("item"), dict)
            else dict(raw_item)
        )
        item_type = str(item.get("type") or item.get("item_type") or "").strip()
        if not item_type:
            raise _history_validation_error(index, "type is required")
        if item_type == "message":
            role = str(item.get("role") or "").strip()
            if not role:
                raise _history_validation_error(index, "message.role is required")
            if "content" not in item:
                raise _history_validation_error(index, "message.content is required")
            _validated_history_content_blocks(index, item.get("content"))
        elif item_type == "reasoning":
            summary = item.get("summary")
            if summary is not None:
                if not isinstance(summary, list):
                    raise _history_validation_error(
                        index, "reasoning.summary must be an array when provided"
                    )
                for block_index, block in enumerate(list(summary or [])):
                    if not isinstance(block, dict):
                        raise _history_validation_error(
                            index, f"reasoning.summary[{block_index}] must be an object"
                        )
                    block_type = str(block.get("type") or block.get("item_type") or "").strip()
                    if not block_type:
                        raise _history_validation_error(
                            index, f"reasoning.summary[{block_index}].type is required"
                        )
        elif item_type == "function_call":
            if not str(item.get("call_id") or "").strip():
                raise _history_validation_error(index, "function_call.call_id is required")
            if not str(item.get("name") or "").strip():
                raise _history_validation_error(index, "function_call.name is required")
            if "arguments" not in item:
                raise _history_validation_error(index, "function_call.arguments is required")
        elif item_type == "function_call_output":
            if not str(item.get("call_id") or "").strip():
                raise _history_validation_error(index, "function_call_output.call_id is required")
            if "output" not in item:
                raise _history_validation_error(index, "function_call_output.output is required")
        normalized_history.append(item)
    return normalized_history


def start_thread(
    runtime: Any, *, name: str | None = None, cwd: str | None = None
) -> dict[str, Any]:
    with startup_timer("runtime_core.start_thread"):
        if runtime.thread_store is None:
            raise RuntimeError("thread store not configured")
        if cwd:
            runtime.set_cwd(Path(cwd))
        reset_delegated_state = getattr(runtime, "_reset_delegated_agent_state", None)
        if callable(reset_delegated_state):
            try:
                reset_delegated_state()
            except Exception:
                pass
        with startup_timer("runtime_core.start_thread.provider_status"):
            provider_status = runtime.agent.provider_status()
        with startup_timer("runtime_core.start_thread.store"):
            record = runtime.thread_store.start_thread(
                name=name,
                cwd=(
                    str(getattr(runtime, "cwd", ""))
                    if getattr(runtime, "cwd", None) is not None
                    else None
                ),
                provider_status=provider_status,
                runtime_policy_status=runtime.runtime_policy_status(),
            )
        runtime.thread_id = record.thread_id
        runtime.thread_name = record.name
        runtime.history = []
        runtime._base_history = []
        runtime.history_turns = []
        runtime.rollout_items = []
        runtime.reference_context_items = []
        runtime._planner_input_items = []
        runtime._environment_context_snapshot = {}
        runtime._environment_context_history = []
        runtime._workspace_context_snapshot = {}
        runtime._memory_context_snapshot = {}
        runtime._context_update_history = []
        runtime.latest_task_plan = None
        runtime.selected_conversation = None
        runtime.pending_send_text = ""
        runtime.send_ready = False
        return record.to_dict()


def list_threads(runtime: Any, *, limit: int = 50, cwd: str | None = None) -> list[dict[str, Any]]:
    if runtime.thread_store is None:
        raise RuntimeError("thread store not configured")
    return runtime.thread_store.list_threads(limit=limit, cwd=cwd)


def _normalized_resume_path(value: str | None) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Path(text).expanduser().resolve(strict=False)
    except OSError:
        return Path(text).expanduser()


def _current_loaded_thread_rollout_path(runtime: Any, thread_id: str) -> Path | None:
    thread_store = getattr(runtime, "thread_store", None)
    if thread_store is None:
        return None
    try:
        record = thread_store.get_thread(thread_id)
    except Exception:
        record = None
    if not isinstance(record, dict):
        return None
    resolver = getattr(thread_store, "_resolve_rollout_path", None)
    if callable(resolver):
        try:
            return Path(resolver(thread_id, record)).expanduser().resolve(strict=False)
        except Exception:
            pass
    rollout_path = str(record.get("rollout_path") or "").strip()
    return _normalized_resume_path(rollout_path)


def _validate_running_thread_resume_conflicts(
    runtime: Any,
    *,
    thread_id: str | None,
    path: str | None,
    history: list[dict[str, Any]] | None,
) -> None:
    current_thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    requested_thread_id = str(thread_id or "").strip()
    if not current_thread_id or not requested_thread_id or requested_thread_id != current_thread_id:
        return
    if history is not None:
        raise ValueError(
            f"cannot resume thread {current_thread_id} with history while it is already running"
        )
    requested_path = _normalized_resume_path(path)
    if requested_path is None:
        return
    active_path = _current_loaded_thread_rollout_path(runtime, current_thread_id)
    if active_path is None:
        return
    if requested_path != active_path:
        raise ValueError(
            "cannot resume running thread "
            f"{current_thread_id} with mismatched path: requested `{requested_path}`, active `{active_path}`"
        )


def resume_thread(
    runtime: Any,
    thread_id: str | None = None,
    *,
    path: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with startup_timer("runtime_core.resume_thread"):
        if runtime.thread_store is None:
            raise RuntimeError("thread store not configured")
        _validate_running_thread_resume_conflicts(
            runtime,
            thread_id=thread_id,
            path=path,
            history=history,
        )
        if history is not None:
            validated_history = validate_resume_history(history)
            provider_status = {}
            try:
                provider_status = dict(runtime.agent.provider_status() or {})
            except Exception:
                provider_status = {}
            with startup_timer("runtime_core.resume_thread.store_from_history"):
                payload = runtime.thread_store.resume_thread_from_history(
                    validated_history,
                    cwd=(
                        str(getattr(runtime, "cwd", ""))
                        if getattr(runtime, "cwd", None) is not None
                        else None
                    ),
                    provider_status=provider_status,
                    runtime_policy_status=runtime.runtime_policy_status(),
                )
        elif str(path or "").strip():
            with startup_timer("runtime_core.resume_thread.store_from_path"):
                payload = runtime.thread_store.resume_thread_from_path(str(path or "").strip())
        else:
            normalized_thread_id = str(thread_id or "").strip()
            if not normalized_thread_id:
                raise ValueError("thread_id is required when history and path are absent")
            with startup_timer("runtime_core.resume_thread.store"):
                payload = runtime.thread_store.resume_thread(normalized_thread_id)
        record = payload.get("thread") or {}
        state = payload.get("state") or {}
        reset_delegated_state = getattr(runtime, "_reset_delegated_agent_state", None)
        if callable(reset_delegated_state):
            try:
                reset_delegated_state()
            except Exception:
                pass
        runtime.thread_id = str(record.get("thread_id") or thread_id)
        runtime.thread_name = str(record.get("name") or runtime.thread_id)
        record_cwd = str(record.get("cwd") or "").strip()
        if record_cwd:
            with startup_timer("runtime_core.resume_thread.set_cwd"):
                try:
                    runtime.set_cwd(record_cwd)
                except Exception:
                    pass
        with startup_timer("runtime_core.resume_thread.assign_history"):
            runtime.history = list(payload.get("history") or [])
            runtime._base_history = list(payload.get("base_history") or [])
            runtime.history_turns = list(payload.get("turns") or [])
            runtime.rollout_items = list(payload.get("rollout_items") or [])
            runtime._planner_input_items = list(payload.get("planner_input_items") or [])
            runtime.reference_context_items = list(payload.get("context_items") or [])
        runtime.selected_conversation = runtime._state_value(state, "selected_conversation")
        runtime.pending_send_text = runtime._state_value(state, "pending_send_text") or ""
        runtime.send_ready = str(state.get("send_ready") or "").strip().lower() == "true"
        restored_task_plan = normalized_plan_payload(state.get("latest_task_plan"))
        runtime.latest_task_plan = restored_task_plan or None
        restore_workspace_context = getattr(runtime, "_restore_workspace_context_state", None)
        if callable(restore_workspace_context):
            with startup_timer("runtime_core.resume_thread.restore_workspace_context"):
                try:
                    restore_workspace_context(state, runtime.reference_context_items)
                except Exception:
                    pass
        restore_environment_context = getattr(runtime, "_restore_environment_context_state", None)
        if callable(restore_environment_context):
            with startup_timer("runtime_core.resume_thread.restore_environment_context"):
                try:
                    restore_environment_context(state)
                except Exception:
                    pass
        restore_memory_context = getattr(runtime, "_restore_memory_context_state", None)
        if callable(restore_memory_context):
            with startup_timer("runtime_core.resume_thread.restore_memory_context"):
                try:
                    restore_memory_context(state)
                except Exception:
                    pass
        restore_file_read_guard = getattr(runtime, "_restore_file_read_guard_state", None)
        if callable(restore_file_read_guard):
            with startup_timer("runtime_core.resume_thread.restore_file_read_guard"):
                try:
                    restore_file_read_guard(state)
                except Exception:
                    pass
        with startup_timer("runtime_core.resume_thread.restore_runtime_policy"):
            restore_runtime_policy(runtime, state)
        with startup_timer("runtime_core.resume_thread.restore_provider_state"):
            restore_provider_state(runtime, state)
        restore_delegated_state = getattr(runtime, "_restore_delegated_agent_state", None)
        if callable(restore_delegated_state):
            with startup_timer("runtime_core.resume_thread.restore_delegated_state"):
                try:
                    restore_delegated_state(state)
                except Exception:
                    pass
        return payload


def restore_runtime_policy(runtime: Any, state: dict[str, Any]) -> None:
    configure = getattr(runtime, "configure_runtime_policy", None)
    if not callable(configure):
        return
    approval_policy = runtime._state_value(state, "approval_policy")
    sandbox_mode = runtime._state_value(state, "sandbox_mode")
    web_search_mode = runtime._state_value(state, "web_search_mode")
    raw_network_access = state.get("network_access")
    if isinstance(raw_network_access, bool):
        network_access = raw_network_access
    else:
        network_access = runtime._state_value(state, "network_access")
        if isinstance(network_access, str):
            lowered = network_access.strip().lower()
            if lowered in {"true", "enabled"}:
                network_access = True
            elif lowered in {"false", "disabled", "restricted"}:
                network_access = False
    if not any(
        value is not None
        for value in (approval_policy, sandbox_mode, web_search_mode, network_access)
    ):
        return
    try:
        configure(
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            web_search_mode=web_search_mode,
            network_access_enabled=network_access,
        )
    except Exception:
        return


def restore_provider_state(runtime: Any, state: dict[str, Any]) -> None:
    route_overrides = state.get("session_route_overrides")
    if isinstance(route_overrides, dict):
        setter = getattr(runtime.agent, "set_session_route_overrides", None)
        if callable(setter):
            try:
                setter(route_overrides)
            except Exception:
                pass
    delegation_overrides = state.get("session_delegation_overrides")
    if isinstance(delegation_overrides, dict):
        setter = getattr(runtime.agent, "set_session_delegate_overrides", None)
        if callable(setter):
            try:
                setter(delegation_overrides)
            except Exception:
                pass
    current_status = {}
    try:
        current_status = dict(runtime.agent.provider_status() or {})
    except Exception:
        current_status = {}
    if str(current_status.get("provider_ready") or "").strip().lower() == "true":
        return
    model_key = runtime._state_value(state, "model_key")
    provider_name = runtime._state_value(state, "provider_name")
    session_line = runtime._state_value(state, "session_line")
    try:
        if model_key:
            runtime.agent.switch_model(model_key)
            return
        if provider_name:
            runtime.agent.switch_provider(provider_name)
            return
        if session_line in {"reasoner", "chat-tools"}:
            runtime.agent.switch_provider_line("reasoner" if session_line == "reasoner" else "chat")
    except Exception:
        return
