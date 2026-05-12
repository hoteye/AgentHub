from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.providers.adapters.chat_completions import ChatCompletionsSession
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_client import build_openai_client
from cli.agent_cli.providers import openai_planner_routing_runtime
from cli.agent_cli.providers.system_prompts import build_chat_completions_system_prompt
from cli.agent_cli.providers.tool_specs import (
    merged_provider_tool_specs as _merged_provider_tool_specs_impl,
    supports_glm_native_web_search as _supports_glm_native_web_search_impl,
)


class OpenAIPlannerRoutingMixin:
    @staticmethod
    def _route_uses_chat_completions(route_config: ProviderConfig) -> bool:
        return openai_planner_routing_runtime.route_uses_chat_completions(route_config)

    def _route_status_specs(self) -> Dict[str, Dict[str, Any]]:
        return {
            "tool_followup": {},
            "final_synthesis": {},
        }

    def _route_client(self, route_name: str, route_config: ProviderConfig) -> Any:
        build_client = getattr(self, "_route_build_client", build_openai_client)
        return openai_planner_routing_runtime.route_client(
            planner=self,
            route_name=route_name,
            route_config=route_config,
            build_client_fn=build_client,
        )

    def _route_request_client(self, route_name: str, route_config: ProviderConfig, timeout: int | None = None) -> Any:
        return openai_planner_routing_runtime.route_request_client(
            planner=self,
            route_name=route_name,
            route_config=route_config,
            timeout=timeout,
            route_client_fn=self._route_client,
        )

    def _reasoning_request_for_config(self, config: ProviderConfig) -> Optional[Dict[str, Any]]:
        return openai_planner_routing_runtime.reasoning_request_for_config(config)

    def _reasoning_request(self) -> Optional[Dict[str, Any]]:
        return self._reasoning_request_for_config(self.config)

    @staticmethod
    def _chat_route_extra_body(config: ProviderConfig) -> Dict[str, Any]:
        return openai_planner_routing_runtime.chat_route_extra_body(config)

    @staticmethod
    def _chat_message_text(content: Any) -> str:
        return openai_planner_routing_runtime.chat_message_text(content)

    def _chat_route_tool_specs(self, route_config: ProviderConfig) -> List[Dict[str, Any]]:
        return _merged_provider_tool_specs_impl(
            route_config,
            self.host_platform,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def _chat_route_system_prompt(self, route_config: ProviderConfig) -> str:
        return build_chat_completions_system_prompt(
            host_platform=self.host_platform,
            use_glm_native_web_search=_supports_glm_native_web_search_impl(route_config),
            config=route_config,
            plugin_manager_factory=self.plugin_manager_factory,
        )

    def _chat_route_supports_tools(self, route_config: ProviderConfig) -> bool:
        return self._optional_bool((route_config.raw_model or {}).get("supports_tools"), True)

    def _chat_route_supports_parallel_tool_calls(self, route_config: ProviderConfig) -> bool:
        return self._optional_bool((route_config.raw_model or {}).get("supports_parallel_tool_calls"), False)

    def _chat_route_supports_reasoning(self, route_config: ProviderConfig) -> bool:
        return openai_planner_routing_runtime.chat_route_supports_reasoning(
            route_config,
            optional_bool_fn=self._optional_bool,
        )

    def _chat_route_reasoning_output_field(self, route_config: ProviderConfig) -> str:
        return openai_planner_routing_runtime.chat_route_reasoning_output_field(route_config)

    def _chat_route_create_fn(self, *, route_name: str, route_config: ProviderConfig, request_client: Any):
        return openai_planner_routing_runtime.chat_route_create_fn(
            route_name=route_name,
            route_config=route_config,
            request_client=request_client,
            timeline_debug_enabled_fn=timeline_debug_enabled,
            log_timeline_fn=log_timeline,
            json_ready_fn=json_ready,
        )

    def _chat_route_session(
        self,
        *,
        route_name: str,
        route_config: ProviderConfig,
        timeout: int | None,
    ) -> ChatCompletionsSession:
        request_client = self._route_request_client(route_name, route_config, timeout)
        return openai_planner_routing_runtime.chat_route_session(
            request_client=request_client,
            route_name=route_name,
            route_config=route_config,
            timeout=timeout,
            tool_specs=self._chat_route_tool_specs(route_config),
            supports_tools=self._chat_route_supports_tools(route_config),
            supports_parallel_tool_calls=self._chat_route_supports_parallel_tool_calls(route_config),
            extra_body=self._chat_route_extra_body(route_config) or None,
            supports_reasoning=self._chat_route_supports_reasoning(route_config),
            reasoning_output_field=self._chat_route_reasoning_output_field(route_config),
            create_fn=self._chat_route_create_fn(
                route_name=route_name,
                route_config=route_config,
                request_client=request_client,
            ),
        )
