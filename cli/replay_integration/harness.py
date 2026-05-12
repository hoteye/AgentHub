from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from .reference_baseline_logs import ReferenceBaselineTurnLog, build_cassette_from_reference_baseline_turn_logs
from .drift import DriftReport, build_drift_report
from .replay_client import ReplayOpenAIClient
from .schema import ReplayCassette
from .tool_replay import ReplayToolExecutor
from .workspace_snapshot import capture_environment_snapshot, capture_workspace_snapshot


@dataclass
class ReplayIntegrationHarness:
    cassette: ReplayCassette
    provider_client: ReplayOpenAIClient
    tool_executor: ReplayToolExecutor

    @classmethod
    def from_cassette(cls, cassette: ReplayCassette) -> "ReplayIntegrationHarness":
        return cls(
            cassette=cassette,
            provider_client=ReplayOpenAIClient(cassette),
            tool_executor=ReplayToolExecutor(cassette),
        )

    @classmethod
    def from_reference_baseline_turn_logs(
        cls,
        turn_logs: Sequence[ReferenceBaselineTurnLog],
        *,
        name: str,
        drift_policy: str = "warn",
    ) -> "ReplayIntegrationHarness":
        cassette = build_cassette_from_reference_baseline_turn_logs(
            turn_logs,
            name=name,
            drift_policy=drift_policy,
        )
        return cls.from_cassette(cassette)

    def reset(self) -> None:
        self.provider_client.reset()
        self.tool_executor.reset()

    def check_drift(
        self,
        *,
        cwd: str,
        shell: str,
        network_access: bool,
        current_dt: Optional[datetime] = None,
    ) -> DriftReport:
        current_environment = capture_environment_snapshot(
            cwd=cwd,
            shell=shell,
            network_access=network_access,
            current_dt=current_dt,
        )
        current_workspace = capture_workspace_snapshot(cwd)
        return build_drift_report(
            recorded_environment=self.cassette.manifest.environment_snapshot,
            current_environment=current_environment,
            recorded_workspace=self.cassette.manifest.workspace_snapshot,
            current_workspace=current_workspace,
            policy=self.cassette.manifest.drift_policy,
        )
