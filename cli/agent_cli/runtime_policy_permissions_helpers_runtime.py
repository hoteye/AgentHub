from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as normalization_service,
)


_PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts" / "reference_parity"
_APPROVAL_POLICY_TEMPLATE_PATHS = {
    "never": (
        _PROMPTS_ROOT / "permissions" / "approval_policy" / "never.md",
    ),
    "on-failure": (
        _PROMPTS_ROOT / "permissions" / "approval_policy" / "on_failure.md",
    ),
    "on-request": (
        _PROMPTS_ROOT / "permissions" / "approval_policy" / "on_request_rule.md",
    ),
    "on-request-request-permission": (
        _PROMPTS_ROOT / "permissions" / "approval_policy" / "on_request_rule_request_permission.md",
    ),
    "unless-trusted": (
        _PROMPTS_ROOT / "permissions" / "approval_policy" / "unless_trusted.md",
    ),
}
_SANDBOX_TEMPLATE_PATHS = {
    "read-only": (
        _PROMPTS_ROOT / "permissions" / "sandbox_mode" / "read_only.md",
    ),
    "workspace-write": (
        _PROMPTS_ROOT / "permissions" / "sandbox_mode" / "workspace_write.md",
    ),
    "danger-full-access": (
        _PROMPTS_ROOT / "permissions" / "sandbox_mode" / "danger_full_access.md",
    ),
}


@lru_cache(maxsize=None)
def _load_template(paths: tuple[Path, ...], fallback: str) -> str:
    for candidate in paths:
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return fallback.strip()


def _approval_template(*, approval_policy: str, request_permission_enabled: bool) -> str:
    normalized = normalization_service.normalize_token(approval_policy)
    if normalized == "untrusted":
        normalized = "unless-trusted"
    key = (
        "on-request-request-permission"
        if normalized == "on-request" and request_permission_enabled
        else normalized
    )
    fallbacks = {
        "never": "Approval policy is currently never. Do not provide the `sandbox_permissions` for any reason, commands will be rejected.",
        "on-failure": "Approvals are your mechanism to get user consent to run shell commands without the sandbox. `approval_policy` is `on-failure`: The harness will allow all commands to run in the sandbox (if enabled), and failures will be escalated to the user for approval to run again without the sandbox.",
        "on-request": "# Escalation Requests\n\nCommands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted.",
        "on-request-request-permission": "# Permission Requests\n\nCommands may require user approval before execution. Prefer requesting sandboxed additional permissions instead of asking to run fully outside the sandbox.",
        "unless-trusted": "Approvals are your mechanism to get user consent to run shell commands without the sandbox. `approval_policy` is `unless-trusted`: The harness will escalate most commands for user approval, apart from a limited allowlist of safe \"read\" commands.",
    }
    return _load_template(
        _APPROVAL_POLICY_TEMPLATE_PATHS.get(key, ()),
        fallbacks.get(key, fallbacks["on-request"]),
    )


def _sandbox_template(sandbox_mode: str) -> str:
    normalized = normalization_service.normalize_sandbox_mode(sandbox_mode)
    fallbacks = {
        "read-only": "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `read-only`: The sandbox only permits reading files. Network access is {network_access}.",
        "workspace-write": "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is {network_access}.",
        "danger-full-access": "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `danger-full-access`: No filesystem sandboxing - all commands are permitted. Network access is {network_access}.",
    }
    return _load_template(_SANDBOX_TEMPLATE_PATHS.get(normalized, ()), fallbacks[normalized])


def _render_writable_roots_text(writable_roots: list[str] | tuple[str, ...] | None) -> str:
    roots = [str(item).strip() for item in list(writable_roots or []) if str(item).strip()]
    if not roots:
        return ""
    rendered = [f"`{item}`" for item in roots]
    if len(rendered) == 1:
        return f" The writable root is {rendered[0]}."
    return f" The writable roots are {', '.join(rendered)}."


def render_permissions_instructions(
    *,
    sandbox_mode: str,
    approval_policy: str,
    network_access_enabled: bool,
    request_permission_enabled: bool = False,
    writable_roots: list[str] | tuple[str, ...] | None = None,
) -> str:
    sandbox_text = _sandbox_template(
        normalization_service.normalize_sandbox_mode(sandbox_mode)
    ).replace(
        "{network_access}",
        normalization_service.network_access_label(bool(network_access_enabled)),
    )
    writable_roots_text = _render_writable_roots_text(writable_roots)
    approval_text = _approval_template(
        approval_policy=normalization_service.normalize_approval_policy(approval_policy),
        request_permission_enabled=bool(request_permission_enabled),
    )
    return "\n".join(
        [
            "<permissions instructions>",
            f"{sandbox_text}{writable_roots_text}",
            approval_text,
            "</permissions instructions>",
        ]
    )
