from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Protocol


MEMORY_SYNC_OPT_IN_ENV = "AGENTHUB_MEMORY_SYNC_ENABLED"
DEFAULT_SOURCE_PRIORITY: dict[str, int] = {
    "local": 10,
    "remote": 20,
}


class MemorySyncContractError(ValueError):
    """Raised when sync payloads violate contract assumptions."""


@dataclass(frozen=True)
class MemorySyncScope:
    tenant_id: str
    user_id: str
    project_id: str

    @classmethod
    def from_values(cls, *, tenant_id: str, user_id: str, project_id: str) -> "MemorySyncScope":
        scope = cls(
            tenant_id=str(tenant_id or "").strip(),
            user_id=str(user_id or "").strip(),
            project_id=str(project_id or "").strip(),
        )
        if not scope.tenant_id:
            raise MemorySyncContractError("tenant_id is required")
        if not scope.user_id:
            raise MemorySyncContractError("user_id is required")
        if not scope.project_id:
            raise MemorySyncContractError("project_id is required")
        return scope


@dataclass(frozen=True)
class MemorySyncPushRequest:
    scope: MemorySyncScope
    records: List[Dict[str, Any]]
    source: str = "local"
    dry_run: bool = False


@dataclass(frozen=True)
class MemorySyncPushResult:
    accepted_ids: List[str]
    rejected_ids: List[str]


@dataclass(frozen=True)
class MemorySyncPullRequest:
    scope: MemorySyncScope
    since_cursor: str = ""
    limit: int = 100
    source: str = "remote"


@dataclass(frozen=True)
class MemorySyncPullResult:
    records: List[Dict[str, Any]]
    next_cursor: str = ""


class MemorySyncAdapter(Protocol):
    def push(self, request: MemorySyncPushRequest) -> MemorySyncPushResult:
        ...

    def pull(self, request: MemorySyncPullRequest) -> MemorySyncPullResult:
        ...


class NoopMemorySyncAdapter:
    """Contract-only adapter; validates requests but does not call a real remote."""

    def push(self, request: MemorySyncPushRequest) -> MemorySyncPushResult:
        validate_push_request(request)
        accepted_ids = [str(item.get("memory_id") or "").strip() for item in request.records]
        accepted_ids = [item for item in accepted_ids if item]
        return MemorySyncPushResult(accepted_ids=accepted_ids, rejected_ids=[])

    def pull(self, request: MemorySyncPullRequest) -> MemorySyncPullResult:
        validate_pull_request(request)
        return MemorySyncPullResult(records=[], next_cursor=request.since_cursor)


def memory_sync_opt_in_enabled(value: bool | str | None = None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        value = os.environ.get(MEMORY_SYNC_OPT_IN_ENV)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def validate_push_request(request: MemorySyncPushRequest) -> None:
    if not isinstance(request, MemorySyncPushRequest):
        raise TypeError("request must be a MemorySyncPushRequest")
    _validate_scope(request.scope)
    if request.records is None:
        raise MemorySyncContractError("push records cannot be None")
    for row in list(request.records):
        if not isinstance(row, dict):
            raise MemorySyncContractError("push records must be dictionaries")
        validate_record_scope(record=row, scope=request.scope)


def validate_pull_request(request: MemorySyncPullRequest) -> None:
    if not isinstance(request, MemorySyncPullRequest):
        raise TypeError("request must be a MemorySyncPullRequest")
    _validate_scope(request.scope)
    if int(request.limit or 0) <= 0:
        raise MemorySyncContractError("pull limit must be > 0")


def validate_record_scope(*, record: Mapping[str, Any], scope: MemorySyncScope) -> None:
    _validate_scope(scope)
    tenant_id = str(record.get("tenant_id") or "").strip()
    user_id = str(record.get("user_id") or "").strip()
    project_id = str(record.get("project_id") or "").strip()
    if tenant_id != scope.tenant_id:
        raise PermissionError("record tenant_id mismatch")
    if user_id != scope.user_id:
        raise PermissionError("record user_id mismatch")
    if project_id != scope.project_id:
        raise PermissionError("record project_id mismatch")


def resolve_memory_conflict(
    *,
    local_record: Mapping[str, Any] | None,
    remote_record: Mapping[str, Any] | None,
    source_priority: Mapping[str, int] | None = None,
) -> Dict[str, Any]:
    if local_record is None and remote_record is None:
        return {"winner": None, "reason": "empty"}
    if local_record is None:
        winner = dict(remote_record or {})
        return {"winner": winner, "reason": "remote_only"}
    if remote_record is None:
        winner = dict(local_record or {})
        return {"winner": winner, "reason": "local_only"}

    local = dict(local_record)
    remote = dict(remote_record)
    local_updated = _parse_iso_datetime(str(local.get("updated_at") or ""))
    remote_updated = _parse_iso_datetime(str(remote.get("updated_at") or ""))

    if remote_updated > local_updated:
        return {"winner": remote, "reason": "last_write_wins_remote"}
    if local_updated > remote_updated:
        return {"winner": local, "reason": "last_write_wins_local"}

    priority = dict(DEFAULT_SOURCE_PRIORITY)
    for key, value in dict(source_priority or {}).items():
        priority[str(key or "").strip().lower()] = int(value)

    local_source = str(local.get("source") or "local").strip().lower() or "local"
    remote_source = str(remote.get("source") or "remote").strip().lower() or "remote"
    local_score = int(priority.get(local_source, 0))
    remote_score = int(priority.get(remote_source, 0))

    if remote_score > local_score:
        return {"winner": remote, "reason": "source_priority_remote"}
    if local_score > remote_score:
        return {"winner": local, "reason": "source_priority_local"}

    local_tombstone = _is_tombstone(local)
    remote_tombstone = _is_tombstone(remote)
    if remote_tombstone and not local_tombstone:
        return {"winner": remote, "reason": "tombstone_remote"}
    if local_tombstone and not remote_tombstone:
        return {"winner": local, "reason": "tombstone_local"}

    return {"winner": remote, "reason": "tie_breaker_remote"}


def _validate_scope(scope: MemorySyncScope) -> None:
    if not isinstance(scope, MemorySyncScope):
        raise TypeError("scope must be a MemorySyncScope")
    if not scope.tenant_id:
        raise MemorySyncContractError("tenant_id is required")
    if not scope.user_id:
        raise MemorySyncContractError("user_id is required")
    if not scope.project_id:
        raise MemorySyncContractError("project_id is required")


def _parse_iso_datetime(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_tombstone(record: Mapping[str, Any]) -> bool:
    if bool(record.get("tombstone")):
        return True
    return str(record.get("status") or "").strip().lower() == "deleted"
