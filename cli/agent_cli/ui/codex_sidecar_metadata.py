from __future__ import annotations

from typing import Any


def runtime_policy_metadata_for_sidecar(runtime_policy: Any | None = None) -> dict[str, Any]:
    from cli.agent_cli.runtime_kernels.codex_sidecar.dynamic_tools import (
        codex_visible_child_dynamic_tool_metadata,
    )
    from cli.agent_cli.runtime_policy import RuntimePolicy

    if runtime_policy is None:
        runtime_policy = RuntimePolicy.normalized()
    try:
        runtime_policy_status = dict(runtime_policy.to_status())
    except Exception:
        runtime_policy_status = {}
    metadata: dict[str, Any] = {
        "runtime_policy": runtime_policy_status,
    }
    approval_policy = str(runtime_policy_status.get("approval_policy") or "").strip()
    sandbox_mode = str(runtime_policy_status.get("sandbox_mode") or "").strip()
    if approval_policy:
        metadata["approvalPolicy"] = approval_policy
    if sandbox_mode:
        metadata["sandbox"] = sandbox_mode
    metadata.update(codex_visible_child_dynamic_tool_metadata())
    return metadata
