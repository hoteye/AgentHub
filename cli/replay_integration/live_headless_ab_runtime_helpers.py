from __future__ import annotations

import io
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from cli.agent_cli.environment_context import environment_contract
from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.workspace_context import workspace_contract

from .live_headless_ab_models_helpers import LiveHeadlessTurnResult
from .live_headless_ab_payload_helpers import _safe_json_loads
from .real_cases import get_real_case_spec, live_case_supported_for_host
from .runtime_replay import recorded_user_prompt
from .schema import ReplayCassette, ReplayRound
from .workspace_snapshot import capture_environment_snapshot, capture_workspace_snapshot


_CLEARED_PROVIDER_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "AGENT_CLI_API_KEY",
    "AGENT_CLI_BASE_URL",
    "AGENT_CLI_PROVIDER",
    "AGENT_CLI_MODEL",
    "AGENT_CLI_REASONING_EFFORT",
)

_TIMELINE_FIRST_EVENT_STAGES = frozenset({"responses.stream.event", "turn_engine.round.provider_result"})
_TIMELINE_FIRST_TOOL_STAGES = frozenset(
    {"turn_engine.tool.provisional_started.emit", "turn_engine.tool.execute.begin"}
)


def _manifest_environment_contract(cassette: ReplayCassette) -> dict[str, Any]:
    snapshot = dict(cassette.manifest.environment_snapshot or {})
    if not snapshot:
        snapshot = {
            "cwd": str(cassette.manifest.session.cwd or "").strip(),
            "current_date": str(cassette.manifest.session.current_date or "").strip(),
            "timezone": str(cassette.manifest.session.timezone or "").strip(),
        }
    return environment_contract(snapshot)


def _manifest_workspace_contract(cassette: ReplayCassette) -> dict[str, Any]:
    return workspace_contract(cassette.manifest.workspace_snapshot)


def _current_environment_contract(
    *,
    working_cwd: str,
    host_platform: HostPlatform,
    current_dt: datetime | None,
) -> dict[str, Any]:
    snapshot = capture_environment_snapshot(
        cwd=working_cwd,
        shell=host_platform.shell_kind,
        network_access=True,
        current_dt=current_dt,
    )
    return environment_contract(snapshot)


def _current_workspace_contract(working_cwd: str) -> dict[str, Any]:
    return workspace_contract(capture_workspace_snapshot(working_cwd))


def _resolve_working_cwd(
    cassette: ReplayCassette,
    *,
    cwd: str | Path | None,
    cwd_policy: str,
    configured_cwd: str = "",
) -> str:
    if cwd is not None and str(cwd).strip():
        return str(Path(cwd).expanduser().resolve())
    if str(configured_cwd or "").strip():
        return str(Path(configured_cwd).expanduser().resolve())
    policy = str(cwd_policy or "recorded").strip().lower()
    if policy == "current":
        return str(Path.cwd().resolve())
    recorded = (
        str(cassette.manifest.environment_snapshot.get("cwd") or "").strip()
        or str(cassette.manifest.session.cwd or "").strip()
    )
    if recorded:
        return str(Path(recorded).expanduser())
    return str(Path.cwd().resolve())


def _expected_environment_contract_for_live_case(
    cassette: ReplayCassette,
    *,
    working_cwd: str,
    host_platform: HostPlatform,
    current_dt: datetime | None,
    mode: str,
) -> dict[str, Any]:
    normalized_mode = str(mode or "recorded").strip().lower()
    if normalized_mode == "none":
        return {}
    if normalized_mode == "current":
        return _current_environment_contract(
            working_cwd=working_cwd,
            host_platform=host_platform,
            current_dt=current_dt,
        )
    return _manifest_environment_contract(cassette)


def _expected_workspace_contract_for_live_case(
    cassette: ReplayCassette,
    *,
    working_cwd: str,
    mode: str,
) -> dict[str, Any]:
    normalized_mode = str(mode or "recorded").strip().lower()
    if normalized_mode == "none":
        return {}
    if normalized_mode == "current":
        return _current_workspace_contract(working_cwd)
    return _manifest_workspace_contract(cassette)


def _validate_live_case_host_support(case_id: str, host_platform: HostPlatform | None = None):
    spec = get_real_case_spec(case_id)
    host = host_platform or current_host_platform()
    if live_case_supported_for_host(case_id, host):
        return spec
    supported_families = ", ".join(spec.live_supported_host_families) or "-"
    supported_oses = ", ".join(spec.live_supported_host_oses) or "-"
    raise ValueError(
        f"live headless ab case {case_id!r} is not supported on host "
        f"{host.os} ({host.family}); supported families={supported_families}; supported oses={supported_oses}"
    )


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _coerce_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _load_timeline_records(path: str | Path) -> list[dict[str, Any]]:
    timeline_path = Path(path)
    if not timeline_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in timeline_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(dict(payload))
    return records


def _timeline_stage_matches_first_event(stage: str) -> bool:
    normalized = str(stage or "").strip()
    return normalized in _TIMELINE_FIRST_EVENT_STAGES or normalized.endswith(".response_raw")


def _timeline_first_relative_ms(
    records: Sequence[dict[str, Any]],
    *,
    stage_match: Callable[[str], bool],
) -> int | None:
    first_match: int | None = None
    for record in list(records or []):
        if not isinstance(record, dict):
            continue
        if not stage_match(str(record.get("stage") or "").strip()):
            continue
        relative_ms = _coerce_nonnegative_int(record.get("t_rel_ms"))
        if relative_ms is None:
            continue
        if first_match is None or relative_ms < first_match:
            first_match = relative_ms
    return first_match


def _timeline_metrics_from_path(path: str | Path) -> dict[str, int | None]:
    records = _load_timeline_records(path)
    return {
        "time_to_first_event_ms": _timeline_first_relative_ms(
            records,
            stage_match=_timeline_stage_matches_first_event,
        ),
        "time_to_first_tool_ms": _timeline_first_relative_ms(
            records,
            stage_match=lambda stage: stage in _TIMELINE_FIRST_TOOL_STAGES,
        ),
    }


def _enrich_payload_with_timeline_metrics(payload: dict[str, Any] | None, *, timeline_path: str | Path) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    status = dict(normalized.get("status") or {})
    metrics = _timeline_metrics_from_path(timeline_path)
    if metrics["time_to_first_event_ms"] is None:
        metrics["time_to_first_event_ms"] = _coerce_nonnegative_int(status.get("timing_initial_model_ms"))
    for key, value in metrics.items():
        if _coerce_nonnegative_int(status.get(key)) is not None:
            continue
        if value is not None:
            status[key] = value
    normalized["status"] = status
    return normalized


def _clear_directory_contents(root: Path) -> None:
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_directory_contents(source: Path, destination: Path) -> None:
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _prepare_live_workspace(working_cwd: str, *, seed_dir: str = "", allow_reset: bool = False) -> None:
    if not allow_reset:
        return
    target = Path(working_cwd).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    _clear_directory_contents(target)
    normalized_seed = str(seed_dir or "").strip()
    if not normalized_seed:
        return
    source = Path(normalized_seed).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"live workspace seed dir does not exist: {source}")
    _copy_directory_contents(source, target)


@contextmanager
def _temporary_env(*, set_values: dict[str, str], unset_keys: Sequence[str] = ()) -> Iterator[None]:
    original_values: dict[str, str | None] = {}
    for key in set(set_values).union({str(item) for item in unset_keys}):
        original_values[key] = os.environ.get(key)
    try:
        for key in unset_keys:
            os.environ.pop(str(key), None)
        for key, value in set_values.items():
            os.environ[str(key)] = str(value)
        yield
    finally:
        for key, old_value in original_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def _temporary_cwd(path: str) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run_live_turn(
    *,
    round_item: ReplayRound,
    out_dir: Path,
    requested_resume_thread_id: str,
    approval_policy: str,
    sandbox_mode: str,
    invoke_headless: Callable[..., int],
    clear_provider_overrides: bool,
    runtime: AgentCliRuntime | None = None,
) -> LiveHeadlessTurnResult:
    turn_index = int(round_item.index or 0)
    prompt = recorded_user_prompt(round_item)
    stdout_path = out_dir / f"agenthub.live.turn{turn_index}.stdout.json"
    stderr_path = out_dir / f"agenthub.live.turn{turn_index}.stderr.txt"
    timeline_path = out_dir / f"agenthub.live.turn{turn_index}.timeline.jsonl"

    argv = [
        "--headless",
        "--prompt",
        prompt,
        "--json",
        "--approval-policy",
        str(approval_policy or "never"),
        "--sandbox-mode",
        str(sandbox_mode or "read-only"),
    ]
    if str(requested_resume_thread_id or "").strip():
        argv.extend(["--resume", str(requested_resume_thread_id).strip()])

    stdout = io.StringIO()
    stderr = io.StringIO()
    env_unsets = _CLEARED_PROVIDER_ENV_KEYS if clear_provider_overrides else ()
    with _temporary_env(
        set_values={"AGENTHUB_DEBUG_RESPONSES_TIMELINE": str(timeline_path)},
        unset_keys=env_unsets,
    ):
        exit_code = invoke_headless(
            argv,
            runtime=runtime,
            stdout=stdout,
            stderr=stderr,
        )

    stdout_text = stdout.getvalue()
    stderr_text = stderr.getvalue()
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    if not timeline_path.exists():
        _write_text(timeline_path, "")

    return LiveHeadlessTurnResult(
        turn_index=turn_index,
        prompt=prompt,
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        timeline_path=str(timeline_path),
        requested_resume_thread_id=str(requested_resume_thread_id or "").strip(),
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        json_payload=_enrich_payload_with_timeline_metrics(_safe_json_loads(stdout_text), timeline_path=timeline_path),
    )
