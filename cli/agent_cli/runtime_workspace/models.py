from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ThreadWorkspaceContext:
    thread_id: str
    cwd: str
    workspace_root: str
    approval_policy: str
    sandbox_mode: str
    network_access_enabled: bool | None = None
    web_search_mode: str | None = None
    runtime_cwd_source: str = "runtime_cwd"
    workspace_root_source: str = "runtime_cwd"
    policy_source: str = "runtime_policy"

    def with_overrides(self, **overrides: Any) -> "ThreadWorkspaceContext":
        updates = {key: value for key, value in dict(overrides).items() if value is not None}
        if not updates:
            return self
        return replace(self, **updates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "cwd": self.cwd,
            "workspace_root": self.workspace_root,
            "approval_policy": self.approval_policy,
            "sandbox_mode": self.sandbox_mode,
            "network_access_enabled": self.network_access_enabled,
            "web_search_mode": self.web_search_mode,
            "runtime_cwd_source": self.runtime_cwd_source,
            "workspace_root_source": self.workspace_root_source,
            "policy_source": self.policy_source,
        }
