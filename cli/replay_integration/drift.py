from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from cli.agent_cli.environment_context import EnvironmentContext
from cli.agent_cli.workspace_context import workspace_reference_diff


@dataclass(frozen=True)
class DriftIssue:
    scope: str
    field: str
    severity: str
    recorded: Any
    current: Any


@dataclass(frozen=True)
class DriftReport:
    issues: List[DriftIssue] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocking": self.blocking,
            "issues": [
                {
                    "scope": issue.scope,
                    "field": issue.field,
                    "severity": issue.severity,
                    "recorded": issue.recorded,
                    "current": issue.current,
                }
                for issue in list(self.issues or [])
            ],
        }


def _severity(*, policy: str, field: str) -> str:
    strict = str(policy or "warn").strip().lower() == "strict"
    if field in {"cwd", "instructions_digest", "docs", "skills"}:
        return "error" if strict else "warning"
    return "warning"


def _environment_issues(
    recorded_snapshot: Dict[str, Any] | None,
    current_snapshot: Dict[str, Any] | None,
    *,
    policy: str,
) -> List[DriftIssue]:
    recorded = EnvironmentContext.from_dict(recorded_snapshot)
    current = EnvironmentContext.from_dict(current_snapshot)
    issues: List[DriftIssue] = []
    field_pairs = (
        ("cwd", recorded.cwd, current.cwd),
        ("shell", recorded.shell, current.shell),
        ("current_date", recorded.current_date, current.current_date),
        ("timezone", recorded.timezone, current.timezone),
        ("network", None if recorded.network is None else recorded.network.to_dict(), None if current.network is None else current.network.to_dict()),
        ("subagents", recorded.subagents, current.subagents),
    )
    for field, recorded_value, current_value in field_pairs:
        if recorded_value == current_value:
            continue
        issues.append(
            DriftIssue(
                scope="environment",
                field=field,
                severity=_severity(policy=policy, field=field),
                recorded=recorded_value,
                current=current_value,
            )
        )
    return issues


def _workspace_issues(
    recorded_snapshot: Dict[str, Any] | None,
    current_snapshot: Dict[str, Any] | None,
    *,
    policy: str,
) -> List[DriftIssue]:
    diff = workspace_reference_diff(recorded_snapshot, current_snapshot or {})
    if not diff.get("changed"):
        return []
    issues: List[DriftIssue] = []
    current_item = dict(current_snapshot or {})
    recorded_item = dict(recorded_snapshot or {})
    tracked_fields = (
        "cwd",
        "trust_level",
        "instructions_digest",
        "docs",
        "skills",
    )
    for field in tracked_fields:
        recorded_value = recorded_item.get(field)
        current_value = current_item.get(field)
        if recorded_value == current_value:
            continue
        issues.append(
            DriftIssue(
                scope="workspace",
                field=field,
                severity=_severity(policy=policy, field=field),
                recorded=recorded_value,
                current=current_value,
            )
        )
    return issues


def build_drift_report(
    *,
    recorded_environment: Dict[str, Any] | None,
    current_environment: Dict[str, Any] | None,
    recorded_workspace: Dict[str, Any] | None,
    current_workspace: Dict[str, Any] | None,
    policy: str = "warn",
) -> DriftReport:
    issues = [
        *_environment_issues(recorded_environment, current_environment, policy=policy),
        *_workspace_issues(recorded_workspace, current_workspace, policy=policy),
    ]
    return DriftReport(issues=issues)
