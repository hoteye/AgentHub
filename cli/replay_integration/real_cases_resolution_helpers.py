from __future__ import annotations

from pathlib import Path

from cli.agent_cli.host_platform import HostPlatform, current_host_platform

from .cassette import load_replay_cassette
from .real_cases_catalog_helpers import _REAL_CASE_SPECS, get_real_case_spec
from .real_cases_model_helpers import LOG_ROOT, ResolvedRealReplayRecording
from .reference_baseline_logs import ReferenceBaselineTurnLog, build_cassette_from_reference_baseline_turn_logs
from .schema import ReplayCassette


def _resolved_log_root(log_root: str | Path | None = None) -> Path:
    if log_root is None:
        return LOG_ROOT
    return Path(log_root)


def _turn_log_paths(
    prefix: str,
    turn_count: int,
    *,
    log_root: str | Path | None = None,
) -> list[ReferenceBaselineTurnLog]:
    root = _resolved_log_root(log_root)
    return [
        ReferenceBaselineTurnLog(
            stdout_path=root / f"{prefix}_turn{turn_index}.stdout.jsonl",
            stderr_path=root / f"{prefix}_turn{turn_index}.stderr.jsonl",
        )
        for turn_index in range(1, turn_count + 1)
    ]


def _turn_logs_exist(turn_logs: list[ReferenceBaselineTurnLog]) -> bool:
    return all(item.stdout_path.exists() and item.stderr_path.exists() for item in list(turn_logs or []))


def _resolved_prefix(prefix: str, turn_count: int, *, log_root: str | Path | None = None) -> str:
    normalized = str(prefix or "").strip()
    if not normalized:
        return normalized
    if _turn_logs_exist(_turn_log_paths(normalized, turn_count, log_root=log_root)):
        return normalized
    wildcard = normalized.replace("reference", "*")
    if wildcard == normalized:
        return normalized
    root = _resolved_log_root(log_root)
    for stdout_path in sorted(root.glob(f"{wildcard}_turn1.stdout.jsonl")):
        name = stdout_path.name
        if not name.endswith("_turn1.stdout.jsonl"):
            continue
        candidate = name[: -len("_turn1.stdout.jsonl")]
        if _turn_logs_exist(_turn_log_paths(candidate, turn_count, log_root=log_root)):
            return candidate
    return normalized


def resolve_real_case_recording(
    case_id: str,
    *,
    host_platform: HostPlatform | None = None,
    prefer_host_variant: bool = False,
    log_root: str | Path | None = None,
) -> ResolvedRealReplayRecording:
    spec = get_real_case_spec(case_id)
    if spec.source_kind == "fixture_live":
        return ResolvedRealReplayRecording(
            case_id=spec.case_id,
            prefix=f"fixture:{spec.case_id}",
            source="fixture",
            exists=True,
        )
    if str(spec.cassette_dir or "").strip():
        cassette_root = Path(spec.cassette_dir).expanduser().resolve()
        return ResolvedRealReplayRecording(
            case_id=spec.case_id,
            prefix=str(cassette_root),
            source="recorded_cassette",
            exists=cassette_root.exists(),
        )
    host = host_platform or current_host_platform()
    ordered_candidates: list[tuple[str, str]] = []
    if prefer_host_variant:
        host_os_prefix = str(spec.recording_prefix_by_host_os.get(host.os) or "").strip()
        if host_os_prefix:
            ordered_candidates.append(("host_os", host_os_prefix))
        host_family_prefix = str(spec.recording_prefix_by_host_family.get(host.family) or "").strip()
        if host_family_prefix and all(prefix != host_family_prefix for _, prefix in ordered_candidates):
            ordered_candidates.append(("host_family", host_family_prefix))
    ordered_candidates.append(("base", spec.recording_prefix))

    if not prefer_host_variant:
        selected_source, selected_prefix = ordered_candidates[-1]
        resolved_prefix = _resolved_prefix(selected_prefix, spec.turn_count, log_root=log_root)
        return ResolvedRealReplayRecording(
            case_id=spec.case_id,
            prefix=resolved_prefix,
            source=selected_source,
            exists=_turn_logs_exist(_turn_log_paths(resolved_prefix, spec.turn_count, log_root=log_root)),
        )

    for source, prefix in ordered_candidates:
        resolved_prefix = _resolved_prefix(prefix, spec.turn_count, log_root=log_root)
        if _turn_logs_exist(_turn_log_paths(resolved_prefix, spec.turn_count, log_root=log_root)):
            return ResolvedRealReplayRecording(
                case_id=spec.case_id,
                prefix=resolved_prefix,
                source=source,
                exists=True,
            )

    selected_source, selected_prefix = ordered_candidates[0]
    resolved_prefix = _resolved_prefix(selected_prefix, spec.turn_count, log_root=log_root)
    return ResolvedRealReplayRecording(
        case_id=spec.case_id,
        prefix=resolved_prefix,
        source=selected_source,
        exists=False,
    )


def live_case_supported_for_host(
    case_id: str,
    host_platform: HostPlatform | None = None,
    *,
    log_root: str | Path | None = None,
) -> bool:
    spec = get_real_case_spec(case_id)
    host = host_platform or current_host_platform()
    family_allowed = not spec.live_supported_host_families or host.family in set(spec.live_supported_host_families)
    os_allowed = not spec.live_supported_host_oses or host.os in set(spec.live_supported_host_oses)
    if family_allowed and os_allowed:
        return True
    resolved = resolve_real_case_recording(
        case_id,
        host_platform=host,
        prefer_host_variant=True,
        log_root=log_root,
    )
    return resolved.exists and resolved.source in {"host_os", "host_family"}


def list_live_compatible_case_ids(
    host_platform: HostPlatform | None = None,
    *,
    log_root: str | Path | None = None,
) -> list[str]:
    host = host_platform or current_host_platform()
    return [
        item.case_id
        for item in _REAL_CASE_SPECS
        if live_case_supported_for_host(item.case_id, host, log_root=log_root)
    ]


def load_real_case_turn_logs(
    case_id: str,
    *,
    host_platform: HostPlatform | None = None,
    prefer_host_variant: bool = False,
    log_root: str | Path | None = None,
) -> list[ReferenceBaselineTurnLog]:
    spec = get_real_case_spec(case_id)
    if spec.source_kind == "fixture_live" or str(spec.cassette_dir or "").strip():
        raise FileNotFoundError(f"case {case_id!r} does not use reference turn logs")
    resolved = resolve_real_case_recording(
        case_id,
        host_platform=host_platform,
        prefer_host_variant=prefer_host_variant,
        log_root=log_root,
    )
    turn_logs = _turn_log_paths(resolved.prefix, spec.turn_count, log_root=log_root)
    if not _turn_logs_exist(turn_logs):
        raise FileNotFoundError(
            f"missing replay logs for case {case_id!r} using prefix {resolved.prefix!r} ({resolved.source})"
        )
    return turn_logs


def load_real_case_cassette(
    case_id: str,
    *,
    host_platform: HostPlatform | None = None,
    prefer_host_variant: bool = False,
    log_root: str | Path | None = None,
) -> ReplayCassette:
    spec = get_real_case_spec(case_id)
    if spec.source_kind == "fixture_live":
        if spec.fixture_builder is None:
            raise ValueError(f"fixture-backed case {case_id!r} is missing fixture_builder")
        return spec.fixture_builder()
    if str(spec.cassette_dir or "").strip():
        return load_replay_cassette(spec.cassette_dir)
    return build_cassette_from_reference_baseline_turn_logs(
        load_real_case_turn_logs(
            case_id,
            host_platform=host_platform,
            prefer_host_variant=prefer_host_variant,
            log_root=log_root,
        ),
        name=spec.cassette_name,
        case_id=spec.case_id,
        parity_targets=spec.parity_targets,
        coverage_tags=spec.coverage_tags,
    )
