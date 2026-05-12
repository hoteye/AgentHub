from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration import taskbook_runtime as taskbook_runtime_service


class CodexSidecarRuntimeOrchestrationMixin:
    """Orchestration and runtime-policy helpers extracted from CodexSidecarRuntimeAdapter."""

    def preview_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, Any] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, Any]:
        return taskbook_runtime_service.preview_orchestration_run(
            self,
            source_text,
            planning_adjustments=planning_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )

    def create_orchestration_run(
        self,
        source_text: str,
        *,
        planning_adjustments: dict[str, Any] | None = None,
        relaxed_taskbook: bool = False,
    ) -> dict[str, Any]:
        return taskbook_runtime_service.create_orchestration_run(
            self,
            source_text,
            planning_adjustments=planning_adjustments,
            relaxed_taskbook=relaxed_taskbook,
        )

    def dispatch_orchestration_run(self, run_id: str) -> dict[str, Any]:
        return taskbook_runtime_service.dispatch_orchestration_run(self, run_id)

    def progress_orchestration_run(
        self,
        run_id: str,
        *,
        dispatch_ready: bool = True,
    ) -> dict[str, Any]:
        return taskbook_runtime_service.progress_orchestration_run(
            self,
            run_id,
            dispatch_ready=dispatch_ready,
        )

    def continue_orchestration_run(
        self,
        run_id: str,
        *,
        max_passes: int = 8,
        dispatch_ready: bool = True,
    ) -> dict[str, Any]:
        return taskbook_runtime_service.continue_orchestration_run(
            self,
            run_id,
            max_passes=max_passes,
            dispatch_ready=dispatch_ready,
        )

    def apply_orchestration_card(self, run_id: str, card_id: str) -> dict[str, Any]:
        return taskbook_runtime_service.apply_orchestration_card(self, run_id, card_id)

    def reject_orchestration_card(self, run_id: str, card_id: str) -> dict[str, Any]:
        return taskbook_runtime_service.reject_orchestration_card(self, run_id, card_id)

    def runtime_policy_status(self) -> dict[str, str]:
        raw = self.kernel_session.metadata.get("runtime_policy")
        if isinstance(raw, dict):
            return {str(key): str(value) for key, value in raw.items()}
        return {}

    def response_runtime_snapshot(self) -> dict[str, Any]:
        from cli.agent_cli import runtime_runtime

        return runtime_runtime.response_runtime_snapshot(
            cwd=getattr(self, "cwd", "") or "",
            provider_status=dict(self.agent.provider_status() or {}),
            runtime_policy=self.runtime_policy_status(),
        )

    def configure_runtime_policy(self, **kwargs: Any) -> dict[str, str]:
        raw = self.kernel_session.metadata.get("runtime_policy")
        status = dict(raw) if isinstance(raw, dict) else {}
        for key, value in kwargs.items():
            if value is None:
                continue
            status[str(key)] = str(value)
        self.kernel_session.metadata["runtime_policy"] = status
        return {str(key): str(value) for key, value in status.items()}
