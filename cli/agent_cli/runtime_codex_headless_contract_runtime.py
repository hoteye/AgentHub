from __future__ import annotations

import shlex
from typing import Any

from cli.agent_cli import runtime_policy_normalization_helpers_runtime as normalization_service
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    configured_interaction_profile_for_config,
    resolved_tool_surface_profile_for_config,
)
from cli.agent_cli.runtime_tools_surface_runtime import runtime_provider_config

_CODEX_OPENAI_PROFILE = "codex_openai"
_CLAUDE_CODE_PROFILE = "claude_code"
_HEADLESS_MODE_PROMPT = "prompt"
_HEADLESS_MODE_SERVE = "serve"
_READ_ONLY_REJECTED_TEXT = (
    "writing is blocked by read-only sandbox; rejected by user approval settings"
)
_CLAUDE_NONINTERACTIVE_APPROVAL_DENIED_TEXT = (
    "Permission denied by non-interactive approval settings."
)


def set_runtime_headless_mode(runtime: Any, *, serve: bool) -> None:
    runtime._agenthub_headless_mode = _HEADLESS_MODE_SERVE if bool(serve) else _HEADLESS_MODE_PROMPT


def runtime_headless_mode(runtime: Any) -> str:
    return str(getattr(runtime, "_agenthub_headless_mode", "") or "").strip().lower()


def runtime_interaction_profile(runtime: Any) -> str:
    config = runtime_provider_config(runtime)
    if config is None:
        return ""
    try:
        configured_profile, _ = configured_interaction_profile_for_config(config)
    except Exception:
        configured_profile = ""
    normalized_configured = str(configured_profile or "").strip().lower()
    if normalized_configured:
        return normalized_configured
    try:
        return str(resolved_tool_surface_profile_for_config(config) or "").strip().lower()
    except Exception:
        return ""


def runtime_uses_codex_noninteractive_contract(runtime: Any) -> bool:
    return (
        runtime_headless_mode(runtime) == _HEADLESS_MODE_PROMPT
        and runtime_interaction_profile(runtime) == _CODEX_OPENAI_PROFILE
    )


def runtime_uses_claude_noninteractive_contract(runtime: Any) -> bool:
    return (
        runtime_headless_mode(runtime) == _HEADLESS_MODE_PROMPT
        and runtime_interaction_profile(runtime) == _CLAUDE_CODE_PROFILE
    )


def effective_model_runtime_policy(
    runtime: Any,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    normalized_approval_policy = normalization_service.normalize_approval_policy(
        approval_policy,
        default="on-request",
    )
    normalized_sandbox_mode = normalization_service.normalize_sandbox_mode(
        sandbox_mode,
        default="workspace-write",
    )
    codex_noninteractive_headless = runtime_uses_codex_noninteractive_contract(runtime)
    claude_noninteractive_headless = runtime_uses_claude_noninteractive_contract(runtime)
    return {
        "approval_policy": normalized_approval_policy,
        "sandbox_mode": normalized_sandbox_mode,
        "codex_noninteractive_headless": codex_noninteractive_headless,
        "claude_noninteractive_headless": claude_noninteractive_headless,
    }


def codex_noninteractive_exec_denial_text(
    *,
    sandbox_mode: str,
    reason_code: str,
    reason_text: str,
) -> str:
    normalized_sandbox_mode = str(sandbox_mode or "").strip().lower()
    normalized_reason_code = str(reason_code or "").strip().lower()
    normalized_reason_text = str(reason_text or "").strip()
    if normalized_reason_code.startswith("exec.dangerous."):
        return "blocked by policy"
    if normalized_sandbox_mode == "read-only":
        return _READ_ONLY_REJECTED_TEXT
    return normalized_reason_text or "blocked by policy"


def codex_noninteractive_read_only_exec_stderr(*, command: str, shell: str | None) -> str:
    normalized_shell = str(shell or "").strip() or "/bin/bash"
    target = ""
    try:
        tokens = shlex.split(str(command or "").strip(), posix=True)
    except ValueError:
        tokens = []
    redirect_prefixes = ("1>>", "1>", ">>", ">", "2>>", "2>")
    for index, token in enumerate(tokens):
        normalized_token = str(token or "").strip()
        if not normalized_token:
            continue
        if normalized_token in {">", ">>", "1>", "1>>", "2>", "2>>"}:
            if index + 1 < len(tokens):
                target = str(tokens[index + 1] or "").strip()
                break
            continue
        for prefix in redirect_prefixes:
            if normalized_token.startswith(prefix) and len(normalized_token) > len(prefix):
                target = normalized_token[len(prefix) :].strip()
                break
        if target:
            break
    if target:
        return f"{normalized_shell}: line 1: {target}: Permission denied"
    return "Permission denied"


def codex_noninteractive_apply_patch_denial_text(
    *,
    sandbox_mode: str,
    reason_code: str,
    reason_text: str,
) -> str:
    normalized_sandbox_mode = str(sandbox_mode or "").strip().lower()
    normalized_reason_code = str(reason_code or "").strip().lower()
    normalized_reason_text = str(reason_text or "").strip()
    if normalized_reason_code == "apply_patch_preview_invalid":
        return (
            normalized_reason_text
            or "Patch preview failed, so approval cannot be requested safely."
        )
    if normalized_sandbox_mode == "read-only":
        return _READ_ONLY_REJECTED_TEXT
    return normalized_reason_text or "patch rejected by user approval settings"


def claude_noninteractive_approval_denial_text(*, reason_text: str = "") -> str:
    return str(reason_text or "").strip() or _CLAUDE_NONINTERACTIVE_APPROVAL_DENIED_TEXT


__all__ = [
    "claude_noninteractive_approval_denial_text",
    "codex_noninteractive_apply_patch_denial_text",
    "codex_noninteractive_exec_denial_text",
    "codex_noninteractive_read_only_exec_stderr",
    "effective_model_runtime_policy",
    "runtime_headless_mode",
    "runtime_interaction_profile",
    "runtime_uses_codex_noninteractive_contract",
    "runtime_uses_claude_noninteractive_contract",
    "set_runtime_headless_mode",
]
