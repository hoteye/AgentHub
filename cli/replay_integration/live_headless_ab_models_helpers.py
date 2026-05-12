from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_PROTOCOL_COMPARED_FIELDS = [
    "assistant_text",
    "tool_events",
    "command_execution",
    "response_item_inventory",
    "response_item_signatures",
    "request_contract.environment",
    "request_contract.workspace",
    "request_contract.prelude.section_order",
    "protocol_path.kind",
]
_PROTOCOL_NOT_COMPARED_FIELDS = [
    "response_items.id",
    "response_items.call_id",
    "response_items.provider_item_id",
    "response_items.encrypted_content_value",
    "request_contract.prelude.items",
]


@dataclass
class LiveHeadlessTurnResult:
    turn_index: int
    prompt: str
    exit_code: int
    stdout_path: str
    stderr_path: str
    timeline_path: str
    requested_resume_thread_id: str = ""
    stdout_text: str = ""
    stderr_text: str = ""
    json_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.json_payload or {})
        protocol_diagnostics = payload.get("protocol_diagnostics")
        return {
            "turn_index": self.turn_index,
            "prompt": self.prompt,
            "exit_code": self.exit_code,
            "requested_resume_thread_id": self.requested_resume_thread_id,
            "assistant_text": str(payload.get("assistant_text") or ""),
            "commentary_text": str(payload.get("commentary_text") or ""),
            "protocol_diagnostics": dict(protocol_diagnostics) if isinstance(protocol_diagnostics, dict) else {},
            "response_items": list(payload.get("response_items") or []),
            "status": dict(payload.get("status") or {}),
            "tool_events": list(payload.get("tool_events") or []),
            "turn_events": list(payload.get("turn_events") or []),
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "timeline_path": self.timeline_path,
            "stderr_text": self.stderr_text,
            "stdout_text": self.stdout_text if not payload else "",
        }


@dataclass
class TurnDiff:
    turn_index: int
    prompt: str
    mismatches: list[str] = field(default_factory=list)
    behavioral_mismatches: list[str] = field(default_factory=list)
    protocol_mismatches: list[str] = field(default_factory=list)
    protocol_path_verdict: str = "passed"
    replay_assistant_text: str = ""
    live_assistant_text: str = ""
    replay_tool_names: list[str] = field(default_factory=list)
    live_tool_names: list[str] = field(default_factory=list)
    replay_thread_id: str = ""
    live_thread_id: str = ""
    replay_response_item_inventory: list[str] = field(default_factory=list)
    live_response_item_inventory: list[str] = field(default_factory=list)
    replay_provider_extension_inventory: list[str] = field(default_factory=list)
    live_provider_extension_inventory: list[str] = field(default_factory=list)
    expected_environment_contract: dict[str, Any] = field(default_factory=dict)
    live_environment_contract: dict[str, Any] = field(default_factory=dict)
    expected_workspace_contract: dict[str, Any] = field(default_factory=dict)
    live_workspace_contract: dict[str, Any] = field(default_factory=dict)
    expected_prelude_contract: dict[str, Any] = field(default_factory=dict)
    live_prelude_contract: dict[str, Any] = field(default_factory=dict)
    live_protocol_path: dict[str, Any] = field(default_factory=dict)
    compared_fields: list[str] = field(default_factory=lambda: list(_PROTOCOL_COMPARED_FIELDS))
    not_compared_fields: list[str] = field(default_factory=lambda: list(_PROTOCOL_NOT_COMPARED_FIELDS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "prompt": self.prompt,
            "mismatches": list(self.mismatches or []),
            "behavioral_mismatches": list(self.behavioral_mismatches or []),
            "protocol_mismatches": list(self.protocol_mismatches or []),
            "protocol_path_verdict": self.protocol_path_verdict,
            "replay_assistant_text": self.replay_assistant_text,
            "live_assistant_text": self.live_assistant_text,
            "replay_tool_names": list(self.replay_tool_names or []),
            "live_tool_names": list(self.live_tool_names or []),
            "replay_thread_id": self.replay_thread_id,
            "live_thread_id": self.live_thread_id,
            "replay_response_item_inventory": list(self.replay_response_item_inventory or []),
            "live_response_item_inventory": list(self.live_response_item_inventory or []),
            "replay_provider_extension_inventory": list(self.replay_provider_extension_inventory or []),
            "live_provider_extension_inventory": list(self.live_provider_extension_inventory or []),
            "expected_environment_contract": dict(self.expected_environment_contract or {}),
            "live_environment_contract": dict(self.live_environment_contract or {}),
            "expected_workspace_contract": dict(self.expected_workspace_contract or {}),
            "live_workspace_contract": dict(self.live_workspace_contract or {}),
            "expected_prelude_contract": dict(self.expected_prelude_contract or {}),
            "live_prelude_contract": dict(self.live_prelude_contract or {}),
            "live_protocol_path": dict(self.live_protocol_path or {}),
            "compared_fields": list(self.compared_fields or []),
            "not_compared_fields": list(self.not_compared_fields or []),
        }


@dataclass
class LiveHeadlessAbReport:
    case_id: str
    case_source_kind: str
    surface_family: str
    case_pack: str
    out_dir: str
    approval_policy: str
    sandbox_mode: str
    replay_path: str
    live_results_path: str
    diff_report_path: str
    summary_path: str
    passed: bool
    mismatch_count: int
    behavioral_passed: bool
    protocol_path_passed: bool
    protocol_path_verdict: str
    behavioral_mismatch_count: int
    protocol_mismatch_count: int
    expected_environment_contract: dict[str, Any] = field(default_factory=dict)
    expected_workspace_contract: dict[str, Any] = field(default_factory=dict)
    host_platform_family: str = ""
    host_platform_os: str = ""
    recording_prefix_used: str = ""
    recording_variant_source: str = ""
    working_cwd: str = ""
    live_thread_id: str = ""
    turn_diffs: list[TurnDiff] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_source_kind": self.case_source_kind,
            "surface_family": self.surface_family,
            "case_pack": self.case_pack,
            "out_dir": self.out_dir,
            "approval_policy": self.approval_policy,
            "sandbox_mode": self.sandbox_mode,
            "replay_path": self.replay_path,
            "live_results_path": self.live_results_path,
            "diff_report_path": self.diff_report_path,
            "summary_path": self.summary_path,
            "passed": self.passed,
            "mismatch_count": self.mismatch_count,
            "behavioral_passed": self.behavioral_passed,
            "protocol_path_passed": self.protocol_path_passed,
            "protocol_path_verdict": self.protocol_path_verdict,
            "behavioral_mismatch_count": self.behavioral_mismatch_count,
            "protocol_mismatch_count": self.protocol_mismatch_count,
            "expected_environment_contract": dict(self.expected_environment_contract or {}),
            "expected_workspace_contract": dict(self.expected_workspace_contract or {}),
            "host_platform_family": self.host_platform_family,
            "host_platform_os": self.host_platform_os,
            "recording_prefix_used": self.recording_prefix_used,
            "recording_variant_source": self.recording_variant_source,
            "working_cwd": self.working_cwd,
            "live_thread_id": self.live_thread_id,
            "turn_diffs": [item.to_dict() for item in list(self.turn_diffs or [])],
        }
