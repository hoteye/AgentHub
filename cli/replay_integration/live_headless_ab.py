from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence, TextIO
from zoneinfo import ZoneInfo

from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.main import main as agenthub_main
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.thread_store import ThreadStore

from .headless_replay import run_headless_replay_case
from .live_headless_ab_models_helpers import (
    LiveHeadlessAbReport,
    LiveHeadlessTurnResult,
    TurnDiff,
    _PROTOCOL_COMPARED_FIELDS,
    _PROTOCOL_NOT_COMPARED_FIELDS,
)
from .live_headless_ab_payload_helpers import (
    _CANONICAL_RESPONSE_ITEM_TYPES,
    _IGNORED_PROTOCOL_METADATA_KEYS,
    _canonical_function_call_output_value,
    _command_event_records,
    _is_semantically_empty_protocol_value,
    _normalize_protocol_value,
    _normalized_tool_payload,
    _payload_assistant_text,
    _payload_command_event_records,
    _payload_environment_contract,
    _payload_prelude_contract,
    _payload_protocol_diagnostics,
    _payload_protocol_path,
    _payload_provider_runtime_state,
    _payload_request_contract,
    _payload_response_item_signatures,
    _payload_response_items,
    _payload_thread_id,
    _payload_tool_event_records,
    _payload_tool_names,
    _payload_tool_signatures,
    _payload_workspace_contract,
    _provider_extension_inventory,
    _response_item_inventory,
    _response_item_protocol_signature,
    _response_item_text,
    _safe_json_loads,
    _tool_event_records,
)
from .live_headless_ab_reporting_helpers import _compare_turn, _render_summary
from .live_headless_ab_runtime_helpers import (
    _CLEARED_PROVIDER_ENV_KEYS,
    _TIMELINE_FIRST_EVENT_STAGES,
    _TIMELINE_FIRST_TOOL_STAGES,
    _clear_directory_contents,
    _coerce_nonnegative_int,
    _copy_directory_contents,
    _current_environment_contract,
    _current_workspace_contract,
    _enrich_payload_with_timeline_metrics,
    _expected_environment_contract_for_live_case,
    _expected_workspace_contract_for_live_case,
    _load_timeline_records,
    _manifest_environment_contract,
    _manifest_workspace_contract,
    _prepare_live_workspace,
    _resolve_working_cwd,
    _run_live_turn,
    _temporary_cwd,
    _temporary_env,
    _timeline_first_relative_ms,
    _timeline_metrics_from_path,
    _timeline_stage_matches_first_event,
    _validate_live_case_host_support,
    _write_json,
    _write_text,
)
from .real_cases import (
    list_live_compatible_case_ids,
    list_real_case_ids,
    load_real_case_cassette,
    resolve_real_case_recording,
)


for _exported_dataclass in (LiveHeadlessTurnResult, TurnDiff, LiveHeadlessAbReport):
    _exported_dataclass.__module__ = __name__
del _exported_dataclass


def run_live_headless_ab_case(
    case_id: str,
    *,
    out_dir: str | Path,
    approval_policy: str = "never",
    sandbox_mode: str = "read-only",
    invoke_headless: Callable[..., int] = agenthub_main,
    clear_provider_overrides: bool = True,
    cwd: str | Path | None = None,
    host_platform: HostPlatform | None = None,
) -> LiveHeadlessAbReport:
    live_host_platform = host_platform or current_host_platform()
    case_spec = _validate_live_case_host_support(case_id, live_host_platform)
    resolved_recording = resolve_real_case_recording(
        case_id,
        host_platform=live_host_platform,
        prefer_host_variant=True,
    )
    cassette = load_real_case_cassette(
        case_id,
        host_platform=live_host_platform,
        prefer_host_variant=True,
    )
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    replay_results = run_headless_replay_case(
        cassette,
        output_format="json",
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
    )
    replay_payload = [item.to_dict() for item in replay_results]
    replay_path = _write_json(target_dir / "expected.replay.json", replay_payload)

    live_results: list[LiveHeadlessTurnResult] = []
    working_cwd = _resolve_working_cwd(
        cassette,
        cwd=cwd,
        cwd_policy=case_spec.live_working_cwd_policy,
        configured_cwd=str(getattr(case_spec, "live_working_cwd", "") or ""),
    )
    if cwd is None and bool(getattr(case_spec, "live_reset_workspace", False)):
        _prepare_live_workspace(
            working_cwd,
            seed_dir=str(getattr(case_spec, "live_workspace_seed_dir", "") or ""),
            allow_reset=True,
        )
    if not Path(working_cwd).exists():
        raise FileNotFoundError(f"live headless ab working_cwd does not exist: {working_cwd}")
    current_live_thread_id = ""
    frozen_current_dt_text = str(case_spec.frozen_current_dt or "").strip()
    frozen_current_dt = datetime.fromisoformat(frozen_current_dt_text) if frozen_current_dt_text else None
    frozen_timezone = str(case_spec.frozen_timezone or "").strip()
    if frozen_current_dt is not None and frozen_timezone:
        frozen_current_dt = frozen_current_dt.astimezone(ZoneInfo(frozen_timezone))
    env_unsets = _CLEARED_PROVIDER_ENV_KEYS if clear_provider_overrides else ()
    with _temporary_env(set_values={}, unset_keys=env_unsets):
        live_runtime = AgentCliRuntime(
            thread_store=ThreadStore(target_dir / ".runtime_threads"),
            runtime_policy=RuntimePolicy.normalized(
                approval_policy=approval_policy,
                sandbox_mode=sandbox_mode,
            ),
            current_dt_provider=(lambda: frozen_current_dt) if frozen_current_dt is not None else None,
        )
        forced_environment_snapshot = (
            dict(cassette.manifest.environment_snapshot or {})
            if str(case_spec.live_environment_contract_mode or "recorded").strip().lower() == "recorded"
            else {}
        )
        forced_workspace_snapshot = (
            dict(cassette.manifest.workspace_snapshot or {})
            if str(case_spec.live_workspace_contract_mode or "recorded").strip().lower() == "recorded"
            else {}
        )
        live_runtime.set_context_snapshot_overrides(
            environment_snapshot=forced_environment_snapshot,
            workspace_snapshot=forced_workspace_snapshot,
        )
        live_runtime.set_cwd(working_cwd)
        live_runtime.start_thread(name=f"live headless ab {case_id}", cwd=working_cwd)
        with _temporary_cwd(working_cwd):
            for round_item in list(cassette.rounds or []):
                live_result = _run_live_turn(
                    round_item=round_item,
                    out_dir=target_dir,
                    requested_resume_thread_id=current_live_thread_id,
                    approval_policy=approval_policy,
                    sandbox_mode=sandbox_mode,
                    invoke_headless=invoke_headless,
                    clear_provider_overrides=clear_provider_overrides,
                    runtime=live_runtime,
                )
                live_results.append(live_result)
                parsed_thread_id = _payload_thread_id(live_result.json_payload)
                if parsed_thread_id:
                    current_live_thread_id = parsed_thread_id
                elif str(getattr(live_runtime, "thread_id", "") or "").strip():
                    current_live_thread_id = str(live_runtime.thread_id).strip()

    live_results_path = _write_json(
        target_dir / "agenthub.live.json",
        [item.to_dict() for item in live_results],
    )
    _write_text(target_dir / "agenthub.live.thread_id.txt", current_live_thread_id)

    expected_environment = _expected_environment_contract_for_live_case(
        cassette,
        working_cwd=working_cwd,
        host_platform=live_host_platform,
        current_dt=frozen_current_dt,
        mode=case_spec.live_environment_contract_mode,
    )
    expected_workspace = _expected_workspace_contract_for_live_case(
        cassette,
        working_cwd=working_cwd,
        mode=case_spec.live_workspace_contract_mode,
    )
    diffs: list[TurnDiff] = []
    previous_live_thread_id = ""
    for replay_turn, replay_round, live_turn in zip(replay_payload, cassette.rounds, live_results):
        diff = _compare_turn(
            replay_turn,
            replay_round,
            live_turn,
            previous_live_thread_id=previous_live_thread_id,
            expected_environment_contract=expected_environment,
            expected_workspace_contract=expected_workspace,
        )
        diffs.append(diff)
        live_thread_id = _payload_thread_id(live_turn.json_payload)
        if live_thread_id:
            previous_live_thread_id = live_thread_id

    behavioral_mismatch_count = sum(len(item.behavioral_mismatches) for item in diffs)
    protocol_mismatch_count = sum(len(item.protocol_mismatches) for item in diffs)
    mismatch_count = sum(len(item.mismatches) for item in diffs)
    if any(item.protocol_path_verdict == "failed" for item in diffs):
        protocol_path_verdict = "failed"
    elif any(item.protocol_path_verdict == "unverified" for item in diffs):
        protocol_path_verdict = "unverified"
    else:
        protocol_path_verdict = "passed"
    report = LiveHeadlessAbReport(
        case_id=str(case_id or "").strip(),
        case_source_kind=str(case_spec.source_kind or "recorded").strip() or "recorded",
        surface_family=str(case_spec.surface_family or "").strip(),
        case_pack=str(case_spec.case_pack or "").strip(),
        out_dir=str(target_dir),
        approval_policy=str(approval_policy or "never"),
        sandbox_mode=str(sandbox_mode or "read-only"),
        replay_path=str(replay_path),
        live_results_path=str(live_results_path),
        diff_report_path=str(target_dir / "diff_report.json"),
        summary_path=str(target_dir / "summary.md"),
        passed=mismatch_count == 0,
        mismatch_count=mismatch_count,
        behavioral_passed=behavioral_mismatch_count == 0,
        protocol_path_passed=protocol_path_verdict == "passed",
        protocol_path_verdict=protocol_path_verdict,
        behavioral_mismatch_count=behavioral_mismatch_count,
        protocol_mismatch_count=protocol_mismatch_count,
        expected_environment_contract=expected_environment,
        expected_workspace_contract=expected_workspace,
        host_platform_family=live_host_platform.family,
        host_platform_os=live_host_platform.os,
        recording_prefix_used=resolved_recording.prefix,
        recording_variant_source=resolved_recording.source,
        working_cwd=working_cwd,
        live_thread_id=current_live_thread_id,
        turn_diffs=diffs,
    )
    _write_json(Path(report.diff_report_path), report.to_dict())
    _write_text(Path(report.summary_path), _render_summary(report, live_results=live_results))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.replay_integration.live_headless_ab",
        description="Run replay-vs-live AgentHub headless A/B against formal replay cases.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="list supported formal replay case ids and exit",
    )
    parser.add_argument(
        "--list-live-compatible-cases",
        action="store_true",
        help="list formal replay case ids that can run on the current host in live A/B mode and exit",
    )
    parser.add_argument(
        "--case",
        choices=list_real_case_ids(),
        help="formal real replay case id to run",
    )
    parser.add_argument(
        "--out-dir",
        help="directory for replay/live artifacts and diff output",
    )
    parser.add_argument(
        "--approval-policy",
        default="never",
        choices=("never", "on-request", "on-failure", "untrusted"),
        help="approval policy used for both replay baseline and live headless runs",
    )
    parser.add_argument(
        "--sandbox-mode",
        default="read-only",
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="sandbox mode used for both replay baseline and live headless runs",
    )
    parser.add_argument(
        "--keep-env-overrides",
        action="store_true",
        help="do not clear OPENAI_* and AGENT_CLI_* provider override env vars during live runs",
    )
    parser.add_argument(
        "--cwd",
        help="override working directory used for the live headless run",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    invoke_headless: Callable[..., int] = agenthub_main,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_cases:
        print("\n".join(list_real_case_ids()), file=output_stream)
        return 0
    if args.list_live_compatible_cases:
        print("\n".join(list_live_compatible_case_ids()), file=output_stream)
        return 0
    if not args.case:
        parser.print_usage(error_stream)
        print("live headless ab error: --case is required unless --list-cases is used", file=error_stream)
        return 2
    if not args.out_dir:
        parser.print_usage(error_stream)
        print("live headless ab error: --out-dir is required", file=error_stream)
        return 2

    report = run_live_headless_ab_case(
        args.case,
        out_dir=args.out_dir,
        approval_policy=args.approval_policy,
        sandbox_mode=args.sandbox_mode,
        invoke_headless=invoke_headless,
        clear_provider_overrides=not bool(args.keep_env_overrides),
        cwd=args.cwd,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), file=output_stream)
    return 0 if report.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
