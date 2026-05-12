from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from cli.agent_cli.environment_context import build_environment_context_snapshot
from cli.agent_cli.workspace_context import build_workspace_reference_snapshot


def capture_environment_snapshot(
    *,
    cwd: str | None,
    shell: str,
    network_access: bool,
    current_dt: datetime | None = None,
    allowed_domains: Optional[Sequence[str]] = None,
    denied_domains: Optional[Sequence[str]] = None,
    subagents: str | None = None,
) -> Dict[str, Any]:
    return build_environment_context_snapshot(
        cwd=cwd,
        shell=shell,
        network_access=network_access,
        current_dt=current_dt,
        allowed_domains=list(allowed_domains or []),
        denied_domains=list(denied_domains or []),
        subagents=subagents,
    )


def capture_workspace_snapshot(
    cwd: str,
    *,
    extra_skill_roots: Optional[Sequence[str]] = None,
    max_chars: int = 16 * 1024,
) -> Dict[str, Any]:
    return build_workspace_reference_snapshot(
        cwd,
        extra_skill_roots=list(extra_skill_roots or []),
        max_chars=max_chars,
    )
