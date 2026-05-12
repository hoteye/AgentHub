from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.runtime_kernels.base import StartSessionRequest
from cli.agent_cli.slash_parser import (
    is_slash_command_text,
    parse_slash_invocation,
    slash_keyword_map,
    slash_switch_set,
)

_SIDECAR_COMMANDS = {
    "provider",
    "models",
    "model",
    "codex_threads",
    "codex_thread",
    "codex_rollback",
    "codex_compact",
}


def handle_sidecar_slash_command(runtime: Any, text: str) -> PromptResponse | None:
    if not is_slash_command_text(text):
        return None
    invocation = parse_slash_invocation(text, source="codex_sidecar")
    name = invocation.command_name
    if name not in _SIDECAR_COMMANDS:
        return None
    if name == "provider":
        return _response(text, _provider_text(runtime, invocation), command_name=name)
    if name == "models":
        include_hidden = _flag_enabled(invocation, "include-hidden", "hidden", "all")
        force_refresh = _flag_enabled(invocation, "refresh", "force-refresh")
        return _response(
            text,
            _models_text(runtime, include_hidden=include_hidden, force_refresh=force_refresh),
            command_name=name,
        )
    if name == "model":
        return _response(text, _model_text(runtime, invocation), command_name=name)
    if name == "codex_threads":
        return _response(text, _codex_threads_text(runtime, invocation), command_name=name)
    if name == "codex_thread":
        return _response(text, _codex_thread_text(runtime, invocation), command_name=name)
    if name == "codex_rollback":
        return _response(text, _codex_rollback_text(runtime, invocation), command_name=name)
    if name == "codex_compact":
        return _response(text, _codex_compact_text(runtime), command_name=name)
    return None


def _provider_text(runtime: Any, invocation: Any) -> str:
    provider_selector = _first_position(invocation)
    if provider_selector:
        previous_thread_id = runtime.kernel_session.thread_id
        provider = _sidecar_provider_id(runtime, provider_selector)
        session = _start_new_sidecar_thread(
            runtime,
            model=str(runtime.kernel_session.model or "").strip() or None,
            provider=provider,
        )
        status = dict(runtime.agent.provider_status() or {})
        return "\n".join(
            [
                f"updated session provider={status.get('provider_name') or provider_selector}",
                f"model={status.get('provider_model') or '-'}",
                "runtime_kernel=codex_sidecar",
                "switch_semantics=new_thread",
                f"previous_thread_id={previous_thread_id or '-'}",
                f"thread_id={session.thread_id or '-'}",
                "note=provider switch starts a fresh Codex sidecar thread; runtime history cache is reset.",
            ]
        )

    status = dict(runtime.agent.provider_status() or {})
    lines = [
        "provider status",
        f"provider_label={status.get('provider_label') or '-'}",
        f"provider_name={status.get('provider_name') or '-'}",
        f"provider_model={status.get('provider_model') or '-'}",
        f"provider_source={status.get('provider_source') or 'codex_sidecar'}",
        f"provider_tools={status.get('provider_tools') or 'codex-sidecar'}",
        f"provider_config_path={status.get('provider_config_path') or '-'}",
        f"provider_auth_path={status.get('provider_auth_path') or '-'}",
        f"runtime_kernel={status.get('kernel_engine') or 'codex_sidecar'}",
        f"thread_id={status.get('thread_id') or '-'}",
        "switch_semantics=new_thread",
    ]
    for key in (
        "codex_sidecar_source",
        "codex_sidecar_version",
        "codex_sidecar_config_source",
        "codex_sidecar_codex_home",
        "codex_sidecar_config_path",
        "codex_sidecar_source_config_path",
        "codex_sidecar_agenthub_provider",
        "codex_sidecar_model_provider",
        "codex_sidecar_config_model",
        "codex_sidecar_auth_path",
        "codex_sidecar_source_auth_path",
        "codex_sidecar_auth_key_names",
        "codex_sidecar_auth_source",
        "codex_sidecar_auth_transport",
        "codex_model_catalog_source",
        "codex_model_count",
        "codex_provider_capabilities",
        "codex_model_catalog_error",
    ):
        value = str(status.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    return "\n".join(lines)


def _models_text(
    runtime: Any,
    *,
    include_hidden: bool = False,
    force_refresh: bool = False,
) -> str:
    payload = runtime.model_catalog.list_models(
        include_hidden=include_hidden,
        force_refresh=force_refresh,
    )
    data = payload.get("data")
    models = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    lines = [f"models={len(models)}"]
    error = str(payload.get("error") or "").strip()
    if error:
        lines.append(f"error={error}")
    for item in models:
        model_id = str(item.get("model") or item.get("id") or "").strip() or "-"
        display = str(item.get("displayName") or item.get("display_name") or model_id).strip()
        hidden = bool(item.get("hidden"))
        suffix = " hidden=true" if hidden else ""
        if display and display != model_id:
            lines.append(f"- {model_id}: {display}{suffix}")
        else:
            lines.append(f"- {model_id}{suffix}")
    return "\n".join(lines)


def _model_text(runtime: Any, invocation: Any) -> str:
    model_selector = _first_position(invocation)
    options = slash_keyword_map(invocation)
    reasoning_effort = str(options.get("reasoning-effort") or "").strip()
    if not model_selector:
        status = dict(runtime.agent.provider_status() or {})
        return "\n".join(
            [
                f"current_model={status.get('provider_model') or '-'}",
                f"model_key={status.get('model_key') or '-'}",
                f"provider={status.get('provider_name') or '-'}",
                f"current_reasoning_effort={status.get('provider_reasoning_effort') or '-'}",
                "runtime_kernel=codex_sidecar",
                "switch_semantics=new_thread",
            ]
        )

    provider = str(
        _keyword_like_positional_option(invocation, "provider")
        or options.get("provider")
        or runtime.kernel_session.model_provider
        or "openai"
    ).strip()
    previous_thread_id = runtime.kernel_session.thread_id
    session = _start_new_sidecar_thread(
        runtime,
        model=model_selector,
        provider=_sidecar_provider_id(runtime, provider),
    )
    status = dict(runtime.agent.provider_status() or {})
    lines = [
        f"updated session model={status.get('provider_model') or model_selector}",
        f"provider={status.get('provider_name') or provider or '-'}",
        "runtime_kernel=codex_sidecar",
        "switch_semantics=new_thread",
        f"previous_thread_id={previous_thread_id or '-'}",
        f"thread_id={session.thread_id or '-'}",
        "note=model switch starts a fresh Codex sidecar thread; runtime history cache is reset.",
    ]
    if reasoning_effort:
        lines.append(
            "reasoning_effort_note=Codex app-server thread/start does not expose an in-place "
            "reasoning-effort switch through this bridge yet."
        )
    return "\n".join(lines)


def _start_new_sidecar_thread(
    runtime: Any,
    *,
    model: str | None,
    provider: str | None,
) -> Any:
    session = _run_async(
        runtime.kernel.start_session(
            StartSessionRequest(
                cwd=runtime.cwd,
                model=str(model or "").strip() or None,
                model_provider=provider or None,
                metadata=dict(runtime.kernel_session.metadata or {}),
            )
        )
    )
    runtime.replace_kernel_session(session)
    runtime.history = []
    runtime.history_turns = []
    runtime.turn_results = []
    return session


def _sidecar_provider_id(runtime: Any, provider: str | None) -> str | None:
    normalized = str(provider or "").strip()
    mapper = getattr(getattr(runtime, "agent", None), "sidecar_provider_id_for", None)
    if callable(mapper):
        mapped = str(mapper(normalized) or "").strip()
        if mapped:
            return mapped
    return normalized or None


def _codex_threads_text(runtime: Any, invocation: Any) -> str:
    options = slash_keyword_map(invocation)
    limit = _int_option(options.get("limit"), default=10, minimum=1)
    include_archived = _flag_enabled(invocation, "archived")
    result = runtime.kernel.list_threads(limit=limit, archived=True if include_archived else None)
    data = result.get("data")
    threads = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    lines = [
        f"codex_threads={len(threads)}",
        f"active_thread_id={runtime.kernel_session.thread_id or '-'}",
    ]
    for item in threads:
        thread_id = str(item.get("id") or item.get("threadId") or "").strip() or "-"
        name = str(item.get("name") or item.get("title") or "").strip() or "-"
        model = str(item.get("model") or "").strip()
        archived = bool(item.get("archived"))
        suffix = []
        if model:
            suffix.append(f"model={model}")
        if archived:
            suffix.append("archived=true")
        tail = f" - {', '.join(suffix)}" if suffix else ""
        lines.append(f"- {thread_id} - name={name}{tail}")
    return "\n".join(lines)


def _codex_thread_text(runtime: Any, invocation: Any) -> str:
    thread_id = _first_position(invocation) or runtime.kernel_session.thread_id
    result = runtime.kernel.read_thread(thread_id, include_turns=True)
    thread = result.get("thread") if isinstance(result.get("thread"), dict) else result
    turns = thread.get("turns") if isinstance(thread, dict) else []
    turn_count = len(turns) if isinstance(turns, list) else 0
    return "\n".join(
        [
            "codex_thread",
            f"thread_id={str(thread.get('id') or thread_id) if isinstance(thread, dict) else thread_id}",
            f"name={str(thread.get('name') or thread.get('title') or '-') if isinstance(thread, dict) else '-'}",
            f"turns={turn_count}",
        ]
    )


def _codex_rollback_text(runtime: Any, invocation: Any) -> str:
    options = slash_keyword_map(invocation)
    turns = _int_option(options.get("turns") or options.get("num-turns"), default=1, minimum=1)
    result = runtime.kernel.rollback_thread(runtime.kernel_session.thread_id, num_turns=turns)
    thread = result.get("thread") if isinstance(result.get("thread"), dict) else {}
    raw_turns = thread.get("turns") if isinstance(thread, dict) else []
    runtime.history_turns = []
    runtime.history = []
    runtime.turn_results = []
    return "\n".join(
        [
            "codex rollback complete",
            f"thread_id={runtime.kernel_session.thread_id or '-'}",
            f"num_turns={turns}",
            f"remaining_turns={len(raw_turns) if isinstance(raw_turns, list) else '-'}",
        ]
    )


def _codex_compact_text(runtime: Any) -> str:
    runtime.kernel.compact_thread(runtime.kernel_session.thread_id)
    return "\n".join(
        [
            "codex compact requested",
            f"thread_id={runtime.kernel_session.thread_id or '-'}",
        ]
    )


def _response(text: str, assistant_text: str, *, command_name: str) -> PromptResponse:
    return PromptResponse(
        user_text=text,
        assistant_text=assistant_text,
        status={
            "runtime_kernel": "codex_sidecar",
            "command": command_name,
        },
        handled_as_command=True,
    )


def _first_position(invocation: Any) -> str:
    for item in tuple(getattr(invocation, "positionals", ()) or ()):
        text = str(item or "").strip()
        if text:
            return text
    return ""


def _keyword_like_positional_option(invocation: Any, name: str) -> str:
    normalized_name = str(name or "").strip().lower()
    positionals = [str(item or "").strip() for item in getattr(invocation, "positionals", ()) or ()]
    for index, token in enumerate(positionals[:-1]):
        if token.lower() == normalized_name:
            return positionals[index + 1]
    return ""


def _flag_enabled(invocation: Any, *names: str) -> bool:
    switches = {str(item or "").strip().lower() for item in slash_switch_set(invocation)}
    options = {
        str(key or "").strip().lower(): value
        for key, value in slash_keyword_map(invocation).items()
    }
    for name in names:
        normalized = name.strip().lower()
        if normalized in switches:
            return True
        if _truthy(options.get(normalized)):
            return True
    return False


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int_option(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _run_async(awaitable: Awaitable[Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # pragma: no cover - re-raised on caller thread
            error["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in error:
        raise error["error"]
    return result.get("value")
