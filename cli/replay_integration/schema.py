from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


JsonDict = Dict[str, Any]


def _json_dict(value: Any) -> JsonDict:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _json_list(items: Any) -> List[Any]:
    if not isinstance(items, list):
        return []
    return list(items)


@dataclass(frozen=True)
class ReplaySessionMetadata:
    provider: str = ""
    model: str = ""
    transport_kind: str = ""
    thread_id: str = ""
    prompt_cache_key: str = ""
    git_commit: str = ""
    recorded_at: str = ""
    cwd: str = ""
    timezone: str = ""
    current_date: str = ""

    @classmethod
    def from_dict(cls, payload: JsonDict | None) -> "ReplaySessionMetadata":
        item = dict(payload or {})
        return cls(
            provider=str(item.get("provider") or "").strip(),
            model=str(item.get("model") or "").strip(),
            transport_kind=str(item.get("transport_kind") or "").strip(),
            thread_id=str(item.get("thread_id") or "").strip(),
            prompt_cache_key=str(item.get("prompt_cache_key") or "").strip(),
            git_commit=str(item.get("git_commit") or "").strip(),
            recorded_at=str(item.get("recorded_at") or "").strip(),
            cwd=str(item.get("cwd") or "").strip(),
            timezone=str(item.get("timezone") or "").strip(),
            current_date=str(item.get("current_date") or "").strip(),
        )

    def to_dict(self) -> JsonDict:
        return {
            "provider": self.provider,
            "model": self.model,
            "transport_kind": self.transport_kind,
            "thread_id": self.thread_id,
            "prompt_cache_key": self.prompt_cache_key,
            "git_commit": self.git_commit,
            "recorded_at": self.recorded_at,
            "cwd": self.cwd,
            "timezone": self.timezone,
            "current_date": self.current_date,
        }


@dataclass(frozen=True)
class ReplayManifest:
    name: str = ""
    case_id: str = ""
    format_version: str = "v1"
    drift_policy: str = "warn"
    notes: str = ""
    parity_targets: List[str] = field(default_factory=list)
    coverage_tags: List[str] = field(default_factory=list)
    session: ReplaySessionMetadata = field(default_factory=ReplaySessionMetadata)
    environment_snapshot: JsonDict = field(default_factory=dict)
    workspace_snapshot: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: JsonDict | None) -> "ReplayManifest":
        item = dict(payload or {})
        return cls(
            name=str(item.get("name") or "").strip(),
            case_id=str(item.get("case_id") or "").strip(),
            format_version=str(item.get("format_version") or "v1").strip() or "v1",
            drift_policy=str(item.get("drift_policy") or "warn").strip() or "warn",
            notes=str(item.get("notes") or "").strip(),
            parity_targets=[str(entry or "").strip() for entry in _json_list(item.get("parity_targets")) if str(entry or "").strip()],
            coverage_tags=[str(entry or "").strip() for entry in _json_list(item.get("coverage_tags")) if str(entry or "").strip()],
            session=ReplaySessionMetadata.from_dict(item.get("session")),
            environment_snapshot=_json_dict(item.get("environment_snapshot")),
            workspace_snapshot=_json_dict(item.get("workspace_snapshot")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "case_id": self.case_id,
            "format_version": self.format_version,
            "drift_policy": self.drift_policy,
            "notes": self.notes,
            "parity_targets": list(self.parity_targets),
            "coverage_tags": list(self.coverage_tags),
            "session": self.session.to_dict(),
            "environment_snapshot": dict(self.environment_snapshot),
            "workspace_snapshot": dict(self.workspace_snapshot),
        }


@dataclass(frozen=True)
class ReplayRound:
    index: int
    request_headers: JsonDict = field(default_factory=dict)
    request_fingerprint: str = ""
    request_item_inventory: List[str] = field(default_factory=list)
    request: JsonDict = field(default_factory=dict)
    response_headers: JsonDict = field(default_factory=dict)
    response_item_inventory: List[str] = field(default_factory=list)
    response_events: List[JsonDict] = field(default_factory=list)
    response: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: JsonDict | None) -> "ReplayRound":
        item = dict(payload or {})
        return cls(
            index=int(item.get("index") or 0),
            request_headers=_json_dict(item.get("request_headers")),
            request_fingerprint=str(item.get("request_fingerprint") or "").strip(),
            request_item_inventory=[str(entry or "").strip() for entry in _json_list(item.get("request_item_inventory")) if str(entry or "").strip()],
            request=_json_dict(item.get("request")),
            response_headers=_json_dict(item.get("response_headers")),
            response_item_inventory=[str(entry or "").strip() for entry in _json_list(item.get("response_item_inventory")) if str(entry or "").strip()],
            response_events=[_json_dict(entry) for entry in _json_list(item.get("response_events"))],
            response=_json_dict(item.get("response")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "index": self.index,
            "request_headers": dict(self.request_headers),
            "request_fingerprint": self.request_fingerprint,
            "request_item_inventory": list(self.request_item_inventory),
            "request": dict(self.request),
            "response_headers": dict(self.response_headers),
            "response_item_inventory": list(self.response_item_inventory),
            "response_events": [dict(item) for item in list(self.response_events or [])],
            "response": dict(self.response),
        }


@dataclass(frozen=True)
class ReplayToolCall:
    index: int
    round_index: int = 0
    tool_name: str = ""
    call_id: str = ""
    command_text: str = ""
    arguments: JsonDict = field(default_factory=dict)
    output_items: List[JsonDict] = field(default_factory=list)
    tool_events: List[JsonDict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: JsonDict | None) -> "ReplayToolCall":
        item = dict(payload or {})
        return cls(
            index=int(item.get("index") or 0),
            round_index=int(item.get("round_index") or 0),
            tool_name=str(item.get("tool_name") or "").strip(),
            call_id=str(item.get("call_id") or "").strip(),
            command_text=str(item.get("command_text") or "").strip(),
            arguments=_json_dict(item.get("arguments")),
            output_items=[_json_dict(entry) for entry in _json_list(item.get("output_items"))],
            tool_events=[_json_dict(entry) for entry in _json_list(item.get("tool_events"))],
        )

    def to_dict(self) -> JsonDict:
        return {
            "index": self.index,
            "round_index": self.round_index,
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "command_text": self.command_text,
            "arguments": dict(self.arguments),
            "output_items": [dict(item) for item in list(self.output_items or [])],
            "tool_events": [dict(item) for item in list(self.tool_events or [])],
        }


@dataclass(frozen=True)
class ReplayCassette:
    manifest: ReplayManifest
    rounds: List[ReplayRound] = field(default_factory=list)
    tool_calls: List[ReplayToolCall] = field(default_factory=list)
