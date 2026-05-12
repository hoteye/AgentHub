from __future__ import annotations

from dataclasses import dataclass, replace

from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as normalization_service,
)
from cli.agent_cli import (
    runtime_policy_permissions_helpers_runtime as permissions_service,
)
from cli.agent_cli import (
    runtime_policy_projection_helpers_runtime as projection_service,
)


APPROVAL_POLICIES = normalization_service.APPROVAL_POLICIES
SANDBOX_MODES = normalization_service.SANDBOX_MODES
WEB_SEARCH_MODES = normalization_service.WEB_SEARCH_MODES
SHELL_POLICY_DECISIONS = projection_service.SHELL_POLICY_DECISIONS

normalize_approval_policy = normalization_service.normalize_approval_policy
normalize_sandbox_mode = normalization_service.normalize_sandbox_mode
default_web_search_mode_for_sandbox = normalization_service.default_web_search_mode_for_sandbox
normalize_web_search_mode = normalization_service.normalize_web_search_mode
normalize_network_access = normalization_service.normalize_network_access
network_access_label = normalization_service.network_access_label
permission_mode_label = normalization_service.permission_mode_label

shell_policy_decision_contract = projection_service.shell_policy_decision_contract
shell_policy_contract_from_payload = projection_service.shell_policy_contract_from_payload
render_permissions_instructions = permissions_service.render_permissions_instructions


@dataclass(frozen=True)
class RuntimePolicy:
    approval_policy: str = "on-request"
    sandbox_mode: str = "workspace-write"
    web_search_mode: str = "cached"
    network_access_enabled: bool = True

    @classmethod
    def normalized(
        cls,
        *,
        permission_mode: str | None = None,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
        web_search_mode: str | None = None,
        network_access_enabled: str | bool | None = None,
    ) -> "RuntimePolicy":
        return cls(
            **normalization_service.normalized_runtime_policy_values(
                permission_mode=permission_mode,
                approval_policy=approval_policy,
                sandbox_mode=sandbox_mode,
                web_search_mode=web_search_mode,
                network_access_enabled=network_access_enabled,
            )
        )

    def with_updates(
        self,
        *,
        permission_mode: str | None = None,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
        web_search_mode: str | None = None,
        network_access_enabled: str | bool | None = None,
    ) -> "RuntimePolicy":
        return replace(
            self,
            **normalization_service.updated_runtime_policy_values(
                current_approval_policy=self.approval_policy,
                current_sandbox_mode=self.sandbox_mode,
                current_web_search_mode=self.web_search_mode,
                current_network_access_enabled=self.network_access_enabled,
                permission_mode=permission_mode,
                approval_policy=approval_policy,
                sandbox_mode=sandbox_mode,
                web_search_mode=web_search_mode,
                network_access_enabled=network_access_enabled,
            ),
        )

    def to_status(self) -> dict[str, str]:
        return projection_service.runtime_policy_status_payload(
            approval_policy=self.approval_policy,
            sandbox_mode=self.sandbox_mode,
            web_search_mode=self.web_search_mode,
            network_access_enabled=self.network_access_enabled,
        )

    def permission_mode(self) -> str:
        return normalization_service.permission_mode_label(
            approval_policy=self.approval_policy,
            sandbox_mode=self.sandbox_mode,
            network_access_enabled=self.network_access_enabled,
        )

    def to_status_with_permission_mode(self) -> dict[str, str]:
        return projection_service.runtime_policy_status_with_permission_mode_payload(
            approval_policy=self.approval_policy,
            sandbox_mode=self.sandbox_mode,
            web_search_mode=self.web_search_mode,
            network_access_enabled=self.network_access_enabled,
        )
