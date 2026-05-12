from __future__ import annotations

from typing import Any

from cli.agent_cli.provider import extract_current_turn_prelude_contract

from .live_headless_ab_models_helpers import LiveHeadlessAbReport, LiveHeadlessTurnResult, TurnDiff
from .live_headless_ab_payload_helpers import (
    _command_event_records,
    _payload_assistant_text,
    _payload_command_event_records,
    _payload_environment_contract,
    _payload_prelude_contract,
    _payload_protocol_path,
    _payload_provider_runtime_state,
    _payload_response_item_signatures,
    _payload_response_items,
    _payload_thread_id,
    _payload_tool_event_records,
    _payload_tool_names,
    _payload_workspace_contract,
    _provider_extension_inventory,
    _response_item_inventory,
    _tool_event_records,
)
from .schema import ReplayRound


def _compare_turn(
    replay_turn: dict[str, Any],
    replay_round: ReplayRound,
    live_turn: LiveHeadlessTurnResult,
    *,
    previous_live_thread_id: str,
    expected_environment_contract: dict[str, Any],
    expected_workspace_contract: dict[str, Any],
) -> TurnDiff:
    live_payload = live_turn.json_payload
    replay_payload = replay_turn
    diff = TurnDiff(
        turn_index=int(replay_turn.get("turn_index") or live_turn.turn_index),
        prompt=str(replay_turn.get("prompt") or live_turn.prompt),
        replay_assistant_text=str(replay_turn.get("assistant_text") or ""),
        live_assistant_text=_payload_assistant_text(live_payload),
        replay_tool_names=[
            str(item.get("name") or "").strip()
            for item in list(replay_turn.get("tool_events") or [])
            if isinstance(item, dict)
        ],
        live_tool_names=_payload_tool_names(live_payload),
        replay_thread_id=str((replay_turn.get("status") or {}).get("thread_id") or ""),
        live_thread_id=_payload_thread_id(live_payload),
        replay_response_item_inventory=_response_item_inventory(_payload_response_items(replay_payload)),
        live_response_item_inventory=_response_item_inventory(_payload_response_items(live_payload)),
        replay_provider_extension_inventory=_provider_extension_inventory(_payload_response_items(replay_payload)),
        live_provider_extension_inventory=_provider_extension_inventory(_payload_response_items(live_payload)),
        expected_environment_contract=dict(expected_environment_contract or {}),
        live_environment_contract=_payload_environment_contract(live_payload),
        expected_workspace_contract=dict(expected_workspace_contract or {}),
        live_workspace_contract=_payload_workspace_contract(live_payload),
        expected_prelude_contract=extract_current_turn_prelude_contract(list(replay_round.request.get("input") or [])),
        live_prelude_contract=_payload_prelude_contract(live_payload),
        live_protocol_path=_payload_protocol_path(live_payload),
    )

    expected_exit_code = int(replay_turn.get("exit_code") or 0)
    if live_turn.exit_code != expected_exit_code:
        diff.behavioral_mismatches.append(
            f"live exit_code mismatch: expected {expected_exit_code}, got {live_turn.exit_code}"
        )
    if live_payload is None:
        diff.behavioral_mismatches.append("live stdout is not valid headless JSON")
        diff.mismatches = [*diff.behavioral_mismatches, *diff.protocol_mismatches]
        return diff
    if diff.replay_assistant_text != diff.live_assistant_text:
        diff.behavioral_mismatches.append(
            f"assistant_text mismatch: expected {diff.replay_assistant_text!r}, got {diff.live_assistant_text!r}"
        )

    replay_tool_records = _tool_event_records(list(replay_turn.get("tool_events") or []))
    live_tool_records = _payload_tool_event_records(live_payload)
    if replay_tool_records != live_tool_records:
        diff.behavioral_mismatches.append(
            f"tool_events mismatch: expected {replay_tool_records!r}, got {live_tool_records!r}"
        )

    replay_command_records = _command_event_records(list(replay_turn.get("turn_events") or []))
    live_command_records = _payload_command_event_records(live_payload)
    if replay_command_records != live_command_records:
        diff.behavioral_mismatches.append(
            f"command_execution mismatch: expected {replay_command_records!r}, got {live_command_records!r}"
        )

    replay_response_signatures = _payload_response_item_signatures(replay_payload)
    live_response_signatures = _payload_response_item_signatures(live_payload)
    if diff.replay_response_item_inventory != diff.live_response_item_inventory:
        diff.protocol_mismatches.append(
            "response_item_inventory mismatch: "
            f"expected {diff.replay_response_item_inventory!r}, got {diff.live_response_item_inventory!r}"
        )
    if diff.replay_provider_extension_inventory != diff.live_provider_extension_inventory:
        diff.protocol_mismatches.append(
            "provider_extension_inventory mismatch: "
            f"expected {diff.replay_provider_extension_inventory!r}, got {diff.live_provider_extension_inventory!r}"
        )
    if replay_response_signatures != live_response_signatures:
        diff.protocol_mismatches.append(
            f"response_item_signatures mismatch: expected {replay_response_signatures!r}, got {live_response_signatures!r}"
        )
    if diff.expected_environment_contract and diff.expected_environment_contract != diff.live_environment_contract:
        diff.protocol_mismatches.append(
            "environment_contract mismatch: "
            f"expected {diff.expected_environment_contract!r}, got {diff.live_environment_contract!r}"
        )
    if diff.expected_workspace_contract and diff.expected_workspace_contract != diff.live_workspace_contract:
        diff.protocol_mismatches.append(
            "workspace_contract mismatch: "
            f"expected {diff.expected_workspace_contract!r}, got {diff.live_workspace_contract!r}"
        )
    expected_prelude_order = list(diff.expected_prelude_contract.get("section_order") or [])
    live_prelude_order = list(diff.live_prelude_contract.get("section_order") or [])
    if expected_prelude_order != live_prelude_order:
        diff.protocol_mismatches.append(
            "request_prelude.section_order mismatch: "
            f"expected {expected_prelude_order!r}, got {live_prelude_order!r}"
        )

    live_thread_id = _payload_thread_id(live_payload)
    if not live_thread_id:
        diff.behavioral_mismatches.append("live thread_id is empty")
    if previous_live_thread_id and live_thread_id and live_thread_id != previous_live_thread_id:
        diff.behavioral_mismatches.append(
            f"live thread continuity mismatch: expected {previous_live_thread_id!r}, got {live_thread_id!r}"
        )
    if previous_live_thread_id and live_turn.requested_resume_thread_id != previous_live_thread_id:
        diff.behavioral_mismatches.append(
            "resume thread_id mismatch: "
            f"expected resume {previous_live_thread_id!r}, got {live_turn.requested_resume_thread_id!r}"
        )

    provider_runtime_state = _payload_provider_runtime_state(live_payload)
    if provider_runtime_state and provider_runtime_state != "ready":
        diff.behavioral_mismatches.append(
            f"provider_runtime_state mismatch: expected 'ready', got {provider_runtime_state!r}"
        )
    live_protocol_path = dict(diff.live_protocol_path or {})
    protocol_unverified_reason = ""
    if not live_protocol_path:
        protocol_unverified_reason = "protocol_path unverified: live payload is missing protocol diagnostics"
    elif not bool(live_protocol_path.get("provider_used")) or str(live_protocol_path.get("source") or "").strip() == "host":
        protocol_unverified_reason = (
            "protocol_path unverified: expected provider-backed Reference path, got "
            f"{str(live_protocol_path.get('kind') or 'unknown')!r}"
        )
    if protocol_unverified_reason:
        diff.protocol_mismatches.append(protocol_unverified_reason)
    if diff.protocol_mismatches:
        diff.protocol_path_verdict = (
            "unverified"
            if protocol_unverified_reason and len(diff.protocol_mismatches) == 1
            else "failed"
        )
    else:
        diff.protocol_path_verdict = "passed"
    diff.mismatches = [*diff.behavioral_mismatches, *diff.protocol_mismatches]
    return diff


def _render_summary(
    report: LiveHeadlessAbReport,
    *,
    live_results: list[LiveHeadlessTurnResult],
) -> str:
    lines = [
        "# Live Headless A/B Summary",
        "",
        f"- case_id: `{report.case_id}`",
        f"- case_source_kind: `{report.case_source_kind}`",
        f"- surface_family: `{report.surface_family or '-'}`",
        f"- case_pack: `{report.case_pack or '-'}`",
        f"- passed: `{str(report.passed).lower()}`",
        f"- mismatch_count: `{report.mismatch_count}`",
        f"- behavioral_passed: `{str(report.behavioral_passed).lower()}`",
        f"- protocol_path_passed: `{str(report.protocol_path_passed).lower()}`",
        f"- protocol_path_verdict: `{report.protocol_path_verdict}`",
        f"- behavioral_mismatch_count: `{report.behavioral_mismatch_count}`",
        f"- protocol_mismatch_count: `{report.protocol_mismatch_count}`",
        f"- approval_policy: `{report.approval_policy}`",
        f"- sandbox_mode: `{report.sandbox_mode}`",
        f"- host_platform_family: `{report.host_platform_family}`",
        f"- host_platform_os: `{report.host_platform_os}`",
        f"- recording_prefix_used: `{report.recording_prefix_used}`",
        f"- recording_variant_source: `{report.recording_variant_source}`",
        f"- working_cwd: `{report.working_cwd}`",
        f"- replay_path: `{report.replay_path}`",
        f"- live_results_path: `{report.live_results_path}`",
        f"- diff_report_path: `{report.diff_report_path}`",
        f"- live_thread_id: `{report.live_thread_id or '-'}`",
        f"- expected_environment_contract: `{report.expected_environment_contract}`",
        f"- expected_workspace_contract: `{report.expected_workspace_contract}`",
        "",
    ]
    for diff in report.turn_diffs:
        lines.append(f"## Turn {diff.turn_index}")
        lines.append("")
        lines.append(f"- prompt: `{diff.prompt}`")
        lines.append(f"- replay assistant: `{diff.replay_assistant_text}`")
        lines.append(f"- live assistant: `{diff.live_assistant_text}`")
        lines.append(f"- replay response_items: `{diff.replay_response_item_inventory}`")
        lines.append(f"- live response_items: `{diff.live_response_item_inventory}`")
        lines.append(f"- replay provider extensions: `{diff.replay_provider_extension_inventory}`")
        lines.append(f"- live provider extensions: `{diff.live_provider_extension_inventory}`")
        lines.append(f"- protocol_path_verdict: `{diff.protocol_path_verdict}`")
        lines.append(f"- expected environment: `{diff.expected_environment_contract}`")
        lines.append(f"- live environment: `{diff.live_environment_contract}`")
        lines.append(f"- expected workspace: `{diff.expected_workspace_contract}`")
        lines.append(f"- live workspace: `{diff.live_workspace_contract}`")
        lines.append(f"- expected prelude: `{diff.expected_prelude_contract}`")
        lines.append(f"- live prelude: `{diff.live_prelude_contract}`")
        lines.append(f"- live protocol path: `{diff.live_protocol_path}`")
        lines.append(f"- compared_fields: `{diff.compared_fields}`")
        lines.append(f"- not_compared_fields: `{diff.not_compared_fields}`")
        lines.append(f"- behavioral_mismatches: `{len(diff.behavioral_mismatches)}`")
        for item in diff.behavioral_mismatches:
            lines.append(f"  - {item}")
        lines.append(f"- protocol_mismatches: `{len(diff.protocol_mismatches)}`")
        for item in diff.protocol_mismatches:
            lines.append(f"  - {item}")
        if diff.mismatches:
            lines.append(f"- mismatches: `{len(diff.mismatches)}`")
            for item in diff.mismatches:
                lines.append(f"  - {item}")
        else:
            lines.append("- mismatches: `0`")
        matching_live = next((item for item in live_results if item.turn_index == diff.turn_index), None)
        if matching_live is not None:
            lines.append(f"- stdout: `{matching_live.stdout_path}`")
            lines.append(f"- stderr: `{matching_live.stderr_path}`")
            lines.append(f"- timeline: `{matching_live.timeline_path}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
