from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .schema import ReplayCassette


ROOT = Path(__file__).resolve().parents[2]


def _default_log_root() -> Path:
    base = ROOT / "docs" / "ab_acceptance"
    preferred = base / "reference_logs"
    if preferred.exists():
        return preferred
    candidates = sorted(path for path in base.iterdir() if path.is_dir() and path.name.endswith("_logs"))
    if candidates:
        return candidates[0]
    return preferred


LOG_ROOT = _default_log_root()
_OPERATOR_LIVE_CASE_PACK = "operator_live_surface_v1"
_RECORDED_CASE_ROOT = ROOT / "cli" / "replay_integration" / "recorded_cases"


@dataclass(frozen=True)
class RealReplayCasePackUpgradeCandidate:
    case_id: str
    recording_prefix: str
    turn_count: int
    notes: str


@dataclass(frozen=True)
class RealReplayCasePackSpec:
    pack_id: str
    title: str
    current_state: str
    target_state: str
    notes: str
    upgrade_candidates: tuple[RealReplayCasePackUpgradeCandidate, ...] = ()


@dataclass(frozen=True)
class RealReplayCaseSpec:
    case_id: str
    recording_prefix: str
    turn_count: int
    cassette_name: str
    parity_targets: tuple[str, ...] = ("behavioral_parity_required",)
    coverage_tags: tuple[str, ...] = ()
    frozen_current_dt: str = ""
    frozen_timezone: str = ""
    live_supported_host_families: tuple[str, ...] = ("unix", "windows")
    live_supported_host_oses: tuple[str, ...] = ()
    live_working_cwd_policy: str = "recorded"
    live_environment_contract_mode: str = "recorded"
    live_workspace_contract_mode: str = "recorded"
    recording_prefix_by_host_os: dict[str, str] = field(default_factory=dict)
    recording_prefix_by_host_family: dict[str, str] = field(default_factory=dict)
    cassette_dir: str = ""
    source_kind: str = "recorded"
    surface_family: str = ""
    case_pack: str = ""
    source_description: str = ""
    live_working_cwd: str = ""
    live_workspace_seed_dir: str = ""
    live_reset_workspace: bool = False
    fixture_builder: Callable[[], ReplayCassette] | None = None


@dataclass(frozen=True)
class ResolvedRealReplayRecording:
    case_id: str
    prefix: str
    source: str
    exists: bool
