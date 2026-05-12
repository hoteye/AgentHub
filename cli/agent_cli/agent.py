from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from cli.agent_cli import (
    agent_config_runtime,
    agent_fallback_runtime,
    agent_plan_runtime,
    agent_plan_runtime_helpers,
    agent_provider_runtime,
    agent_runtime,
    agent_runtime_helpers,
)
from cli.agent_cli.agent_constants import (
    LIST_DIR_KEYS,
    PWD_KEYS,
    PYTHON_VERSION_KEYS,
)
from cli.agent_cli.agent_constants import (
    REASONING_EFFORT_LEVELS as _REASONING_EFFORT_LEVELS,
)
from cli.agent_cli.agent_provider_coordination import (
    SESSION_MODEL_DEFAULT_TOKENS,
    SESSION_ROUTE_OVERRIDE_SOURCE,
    STANDARD_DELEGATION_NAMES,
    STANDARD_ROUTE_NAMES,
    AgentProviderRuntimeMixin,
)
from cli.agent_cli.agent_selection_runtime import (
    config_with_session_delegation_overrides as _config_with_session_delegation_overrides,
)
from cli.agent_cli.agent_selection_runtime import (
    config_with_session_route_overrides as _config_with_session_route_overrides,
)
from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.provider import (
    Planner,
    build_planner,
    load_provider_config,
    resolve_provider_paths,
)
from cli.agent_cli.provider import (
    _load_provider_inputs as _load_provider_inputs_fn,
)
from cli.agent_cli.provider import (
    _project_claude_home_dir as _project_claude_home_dir_fn,
)
from cli.agent_cli.provider import (
    load_provider_catalog as _load_provider_catalog,
)
from cli.agent_cli.providers.protocols.anthropic_messages import (
    load_claude_provider_config as _load_claude_provider_config,
)

load_provider_catalog = _load_provider_catalog
load_provider_inputs = _load_provider_inputs_fn
_project_claude_home_dir = _project_claude_home_dir_fn
load_claude_provider_config = _load_claude_provider_config


def _reference_aligned_current_dir_command(host_platform: HostPlatform) -> str:
    return agent_runtime.reference_aligned_current_dir_command(host_platform)


class RuleBasedAgent(AgentProviderRuntimeMixin):
    """Rule-first router with LLM fallback."""

    _PLANNER_UNAVAILABLE_FALLBACK_TEXT = "无法继续：未检测到可用的 LLM provider。"
    _PLANNER_RUNTIME_FALLBACK_TEXT = "无法继续："

    def __init__(self, *, host_platform: HostPlatform | None = None) -> None:
        self.host_platform = host_platform or current_host_platform()
        self.cwd: Path | None = None
        self._plugin_manager_factory: Callable[[], Any] | None = None
        self._provider_availability_registry: Any | None = None
        self._planner: Planner | None = None
        self._planner_managed: bool = False
        self._planner_error: str | None = None
        self._planner_runtime_error: str | None = None
        self._planner_runtime_error_diagnostics: dict[str, Any] | None = None
        self._runtime_policy_overrides: dict[str, Any] = {}
        self._session_provider_env_overrides: dict[str, str | None] = {}
        self._session_route_overrides: dict[str, dict[str, Any]] = {}
        self._session_delegation_overrides: dict[str, dict[str, Any]] = {}
        self._provider_paths = resolve_provider_paths()
        self._reload_planner()

    def _provider_loader_kwargs(self) -> dict[str, Path]:
        return agent_config_runtime.provider_loader_kwargs(self)

    def _reload_planner(self) -> None:
        agent_config_runtime.reload_planner(
            self,
            resolve_provider_paths_fn=resolve_provider_paths,
            load_provider_config_fn=load_provider_config,
            build_planner_fn=build_planner,
        )
        self._sync_provider_availability_registry()

    def _sync_provider_availability_registry(self) -> None:
        if self._planner is None:
            return
        self._planner._provider_availability_registry = self._provider_availability_registry

    def set_availability_registry(self, registry: Any | None) -> None:
        self._provider_availability_registry = registry
        self._sync_provider_availability_registry()

    @staticmethod
    def _validated_reasoning_effort(reasoning_effort: str) -> str:
        return agent_provider_runtime.validated_reasoning_effort(
            reasoning_effort, reasoning_effort_levels=_REASONING_EFFORT_LEVELS
        )

    @staticmethod
    def _validated_route_name(route_name: str) -> str:
        return agent_provider_runtime.validated_route_name(
            route_name, standard_route_names=STANDARD_ROUTE_NAMES
        )

    @staticmethod
    def _validated_delegation_name(role_name: str) -> str:
        return agent_provider_runtime.validated_delegation_name(
            role_name, standard_delegation_names=STANDARD_DELEGATION_NAMES
        )

    @staticmethod
    def _selection_override_payload(override: dict[str, Any]) -> dict[str, Any]:
        return agent_runtime_helpers.selection_override_payload(
            override,
            validate_reasoning_effort=RuleBasedAgent._validated_reasoning_effort,
            override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
        )

    @staticmethod
    def _route_override_payload(route_name: str, override: dict[str, Any]) -> dict[str, Any]:
        return agent_runtime_helpers.route_override_payload(
            route_name,
            override,
            validate_reasoning_effort=RuleBasedAgent._validated_reasoning_effort,
            override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
        )

    @staticmethod
    def _delegation_override_payload(role_name: str, override: dict[str, Any]) -> dict[str, Any]:
        return agent_runtime_helpers.delegation_override_payload(
            role_name,
            override,
            validate_reasoning_effort=RuleBasedAgent._validated_reasoning_effort,
            override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
        )

    @staticmethod
    def _config_with_session_block_overrides(
        config: Any,
        *,
        block_key: str,
        allowed_names: tuple[str, ...],
        overrides: dict[str, dict[str, Any]],
    ) -> Any:
        return agent_runtime_helpers.config_with_session_block_overrides(
            config,
            block_key=block_key,
            allowed_names=allowed_names,
            overrides=overrides,
            config_with_session_route_overrides_fn=_config_with_session_route_overrides,
            config_with_session_delegation_overrides_fn=_config_with_session_delegation_overrides,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
        )

    @staticmethod
    def _config_with_session_route_overrides(
        config: Any, overrides: dict[str, dict[str, Any]]
    ) -> Any:
        return agent_runtime_helpers.config_with_session_route_overrides(
            config,
            overrides,
            standard_route_names=STANDARD_ROUTE_NAMES,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
            config_with_session_route_overrides_fn=_config_with_session_route_overrides,
        )

    @staticmethod
    def _config_with_session_delegation_overrides(
        config: Any, overrides: dict[str, dict[str, Any]]
    ) -> Any:
        return agent_runtime_helpers.config_with_session_delegation_overrides(
            config,
            overrides,
            standard_delegation_names=STANDARD_DELEGATION_NAMES,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
            config_with_session_delegation_overrides_fn=_config_with_session_delegation_overrides,
        )

    def _load_provider_catalog(self, **kwargs):
        return load_provider_catalog(**kwargs)

    def _load_provider_inputs(self, **kwargs):
        return load_provider_inputs(**kwargs)

    def _load_claude_provider_config(self, **kwargs):
        return load_claude_provider_config(**kwargs)

    def _project_claude_home_dir(self) -> Path | None:
        return _project_claude_home_dir()

    def set_cwd(self, cwd: str | Path) -> Path:
        return agent_config_runtime.set_cwd(self, cwd, reload_planner_fn=self._reload_planner)

    def set_plugin_manager_factory(self, factory: Callable[[], Any] | None) -> None:
        agent_config_runtime.set_plugin_manager_factory(
            self,
            factory,
            reload_planner_fn=self._reload_planner,
        )

    def set_runtime_policy_overrides(self, overrides: dict[str, Any] | None) -> None:
        agent_config_runtime.set_runtime_policy_overrides(
            self,
            overrides,
            reload_planner_fn=self._reload_planner,
        )

    def set_planner_override(self, planner: Planner | None, *, managed: bool = False) -> None:
        agent_config_runtime.set_planner_override(self, planner, managed=managed)

    def _planner_fallback_text(self) -> str:
        return agent_fallback_runtime.planner_fallback_text(
            planner_runtime_error=self._planner_runtime_error,
            planner_error=self._planner_error,
            provider_status=self.provider_status(),
            planner_runtime_error_diagnostics=self._planner_runtime_error_diagnostics,
            planner_runtime_fallback_text=self._PLANNER_RUNTIME_FALLBACK_TEXT,
            planner_unavailable_fallback_text=self._PLANNER_UNAVAILABLE_FALLBACK_TEXT,
        )

    def _planner_runtime_error_diagnostic_lines(self) -> list[str]:
        return agent_fallback_runtime.planner_runtime_error_diagnostic_lines(
            self._planner_runtime_error_diagnostics
        )

    @staticmethod
    def _provider_runtime_error_hints(
        error_text: str, *, has_request_diagnostics: bool = False
    ) -> list[str]:
        return agent_fallback_runtime.provider_runtime_error_hints(
            error_text, has_request_diagnostics=has_request_diagnostics
        )

    @staticmethod
    def _protocol_path_payload(
        *,
        kind: str,
        source: str,
        provider_used: bool,
        parity_evaluable: bool,
        reason: str,
    ) -> dict[str, Any]:
        return agent_runtime.protocol_path_payload(
            kind=kind,
            source=source,
            provider_used=provider_used,
            parity_evaluable=parity_evaluable,
            reason=reason,
        )

    @classmethod
    def _intent_with_protocol_path(
        cls,
        intent: AgentIntent,
        *,
        kind: str,
        source: str,
        provider_used: bool,
        parity_evaluable: bool,
        reason: str,
    ) -> AgentIntent:
        return agent_runtime.intent_with_protocol_path(
            intent,
            kind=kind,
            source=source,
            provider_used=provider_used,
            parity_evaluable=parity_evaluable,
            reason=reason,
        )

    @staticmethod
    def _set_env_value(name: str, value: str | None) -> None:
        agent_runtime_helpers.set_env_value(name, value)

    @staticmethod
    def _filter_callable_kwargs(
        handler: Callable[..., Any], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        return agent_runtime_helpers.filter_callable_kwargs(handler, kwargs)

    def resolve_delegate_execution(
        self,
        role_name: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        timeout: Any = None,
    ):
        return agent_runtime_helpers.resolve_delegate_execution(
            role_name=role_name,
            planner=self._planner,
            cwd=str(self.cwd) if self.cwd is not None else None,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            standard_delegation_names=STANDARD_DELEGATION_NAMES,
            validate_reasoning_effort=self._validated_reasoning_effort,
            session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
            session_override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
        )

    def switch_provider_line(self, line: str) -> dict[str, str]:
        return agent_provider_runtime.switch_provider_line(self, line)

    def provider_status(self) -> dict[str, str]:
        return agent_provider_runtime.provider_status(self)

    def _match_shell_intent(self, text: str, normalized: str) -> AgentIntent | None:
        return agent_runtime_helpers.match_shell_intent(
            text=text,
            normalized=normalized,
            host_platform=self.host_platform,
            list_dir_keys=LIST_DIR_KEYS,
            pwd_keys=PWD_KEYS,
            python_version_keys=PYTHON_VERSION_KEYS,
        )

    def _planner_is_replay_runtime(self) -> bool:
        return agent_plan_runtime.planner_is_replay_runtime(self._planner)

    @staticmethod
    def _summarize_live_web_result(query: str, event: ToolEvent) -> str:
        return agent_runtime_helpers.summarize_live_web_result(query, event)

    def _live_web_fallback_intent(
        self,
        text: str,
        *,
        tool_executor: Callable[[str], tuple[str, list[ToolEvent]]] | None = None,
    ) -> AgentIntent | None:
        return agent_plan_runtime.live_web_fallback_intent(
            text,
            tool_executor=tool_executor,
            summarize_live_web_result=self._summarize_live_web_result,
        )

    def interrupt_active_provider_stream(self) -> bool:
        return agent_runtime_helpers.interrupt_active_provider_stream(self._planner)

    def plan(
        self,
        text: str,
        history: list[dict[str, str]] | None = None,
        *,
        tool_executor: Callable[[str], tuple[str, list[ToolEvent]]] | None = None,
        attachments: list[PromptAttachment] | None = None,
        input_items: list[dict[str, Any]] | None = None,
        prompt_cache_key: str | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
        current_dt: datetime | None = None,
        environment_snapshot: dict[str, Any] | None = None,
        provider_session_id: str | None = None,
        provider_turn_id: str | None = None,
        provider_sandbox_mode: str | None = None,
        initial_previous_response_id: str | None = None,
    ) -> AgentIntent:
        return agent_plan_runtime_helpers.plan_with_provider_and_fallback(
            self,
            text,
            history=history,
            tool_executor=tool_executor,
            attachments=attachments,
            input_items=input_items,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            provider_session_id=provider_session_id,
            provider_turn_id=provider_turn_id,
            provider_sandbox_mode=provider_sandbox_mode,
            initial_previous_response_id=initial_previous_response_id,
        )
