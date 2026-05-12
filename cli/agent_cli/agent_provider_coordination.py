from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli import agent_provider_runtime
from cli.agent_cli.agent_provider_resolution import (
    supplement_catalog_with_project_local_providers_with_overrides as _supplement_catalog_with_project_local_providers_with_overrides,
)
from cli.agent_cli.provider import (
    build_planner,
    load_claude_provider_config,
    load_provider_config,
    _project_claude_home_dir,
)
from cli.agent_cli.providers.model_routing import (
    STANDARD_DELEGATION_NAMES,
    STANDARD_ROUTE_NAMES,
)


SESSION_MODEL_DEFAULT_TOKENS = {"default", "auto", "inherit"}
SESSION_ROUTE_OVERRIDE_SOURCE = "session_override"


def _supplement_catalog_with_project_local_providers(
    catalog: Any,
    *,
    project_claude_home_dir_fn: Callable[[], Path] | None = None,
    load_claude_provider_config_fn: Callable[..., Any] | None = None,
) -> Any:
    return _supplement_catalog_with_project_local_providers_with_overrides(
        catalog,
        project_claude_home_dir_fn=project_claude_home_dir_fn or _project_claude_home_dir,
        load_claude_provider_config_fn=load_claude_provider_config_fn or load_claude_provider_config,
    )


class AgentProviderRuntimeMixin:
    def configure_model_selection(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        persist: bool = False,
        write_scope: str | None = None,
    ) -> Dict[str, str]:
        return agent_provider_runtime.configure_model_selection(
            self,
            model=model,
            reasoning_effort=reasoning_effort,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
            load_provider_catalog_fn=self._load_provider_catalog,
            persist=persist,
            write_scope=write_scope,
        )

    def set_reasoning_effort(self, reasoning_effort: str) -> Dict[str, str]:
        return agent_provider_runtime.set_reasoning_effort(
            self,
            reasoning_effort,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
        )

    def available_providers(self) -> list[Dict[str, str]]:
        return agent_provider_runtime.available_providers(
            self,
            load_provider_catalog_fn=self._load_provider_catalog,
            load_provider_inputs_fn=self._load_provider_inputs,
            supplement_catalog_fn=self._supplement_provider_catalog,
        )

    def available_models(
        self,
        provider_name: str | None = None,
        *,
        include_hidden: bool = False,
    ) -> list[Dict[str, str]]:
        return agent_provider_runtime.available_models(
            self,
            provider_name=provider_name,
            include_hidden=include_hidden,
            load_provider_catalog_fn=self._load_provider_catalog,
            supplement_catalog_fn=self._supplement_provider_catalog,
        )

    def provider_review_gate(self) -> Dict[str, Any]:
        return agent_provider_runtime.provider_review_gate(
            self,
            load_provider_catalog_fn=self._load_provider_catalog,
            load_provider_inputs_fn=self._load_provider_inputs,
            supplement_catalog_fn=self._supplement_provider_catalog,
        )

    def expert_review_feature_settings(self) -> Dict[str, Any]:
        return agent_provider_runtime.expert_review_feature_settings(self)

    def probe_provider(
        self,
        *,
        provider_name: str | None = None,
        model: str | None = None,
        writeback_availability: bool = True,
    ) -> Dict[str, Any]:
        return agent_provider_runtime.probe_provider(
            self,
            provider_name=provider_name,
            model=model,
            load_provider_config_fn=load_provider_config,
            build_planner_fn=build_planner,
            writeback_availability=writeback_availability,
        )

    def probe_providers(
        self,
        *,
        writeback_availability: bool = True,
    ) -> list[Dict[str, Any]]:
        return agent_provider_runtime.probe_providers(
            self,
            load_provider_catalog_fn=self._load_provider_catalog,
            load_provider_inputs_fn=self._load_provider_inputs,
            supplement_catalog_fn=self._supplement_provider_catalog,
            load_provider_config_fn=load_provider_config,
            build_planner_fn=build_planner,
            writeback_availability=writeback_availability,
        )

    def switch_provider(
        self,
        provider_name: str,
        *,
        persist: bool = False,
        write_scope: str | None = None,
    ) -> Dict[str, str]:
        return agent_provider_runtime.switch_provider(
            self,
            provider_name,
            persist=persist,
            write_scope=write_scope,
            load_provider_catalog_fn=self._load_provider_catalog,
            supplement_catalog_fn=self._supplement_provider_catalog,
        )

    def switch_model(self, selector: str) -> Dict[str, str]:
        return agent_provider_runtime.switch_model(
            self,
            selector,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
        )

    def _supplement_provider_catalog(self, catalog: Any) -> Any:
        return _supplement_catalog_with_project_local_providers(
            catalog,
            project_claude_home_dir_fn=self._project_claude_home_dir,
            load_claude_provider_config_fn=self._load_claude_provider_config,
        )

    def configure_route_selection(
        self,
        route_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
        clear: bool = False,
    ) -> Dict[str, str]:
        return agent_provider_runtime.configure_route_selection(
            self,
            route_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )

    def session_route_overrides(self) -> Dict[str, Dict[str, Any]]:
        return agent_provider_runtime.session_route_overrides(self)

    def set_session_route_overrides(self, overrides: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
        return agent_provider_runtime.set_session_route_overrides(self, overrides)

    def configure_delegate_selection(
        self,
        role_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
        clear: bool = False,
    ) -> Dict[str, str]:
        return agent_provider_runtime.configure_delegate_selection(
            self,
            role_name,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            clear=clear,
        )

    def session_delegate_overrides(self) -> Dict[str, Dict[str, Any]]:
        return agent_provider_runtime.session_delegate_overrides(self)

    def set_session_delegate_overrides(self, overrides: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
        return agent_provider_runtime.set_session_delegate_overrides(self, overrides)

    def switch_provider_line(self, line: str) -> Dict[str, str]:
        return agent_provider_runtime.switch_provider_line(self, line)

    def provider_status(self) -> Dict[str, str]:
        return agent_provider_runtime.provider_status(self)


__all__ = [
    "AgentProviderRuntimeMixin",
    "SESSION_MODEL_DEFAULT_TOKENS",
    "SESSION_ROUTE_OVERRIDE_SOURCE",
    "STANDARD_DELEGATION_NAMES",
    "STANDARD_ROUTE_NAMES",
    "_supplement_catalog_with_project_local_providers",
]
