from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.model_routing import RouteResolution
from cli.agent_cli.providers.openai_client import build_openai_client


class ChatProtocolRoutingMixin:
    def _route_status_specs(self) -> Dict[str, Dict[str, Any]]:
        return {
            "policy_helper": {
                "legacy_selector": self._policy_llm_legacy_helper_model,
                "default_timeout": self.policy_llm_timeout,
            }
        }

    def _policy_helper_route(self):
        has_explicit_route_block = False
        raw_routes = self.config.raw_model.get("routes") if isinstance(self.config.raw_model, dict) else None
        if isinstance(raw_routes, dict):
            block = raw_routes.get("policy_helper")
            if isinstance(block, dict):
                has_explicit_route_block = True
        if has_explicit_route_block:
            return self._resolve_route(
                "policy_helper",
                legacy_selector=self._policy_llm_legacy_helper_model,
                default_timeout=self.policy_llm_timeout,
            )
        same_provider_route = self._policy_helper_same_provider_route()
        if same_provider_route is not None:
            return same_provider_route
        return self._resolve_route(
            "policy_helper",
            legacy_selector=self._policy_llm_legacy_helper_model,
            default_timeout=self.policy_llm_timeout,
        )

    def _policy_helper_same_provider_route(self) -> RouteResolution | None:
        helper_selector = str(self._policy_llm_legacy_helper_model or "").strip()
        if not helper_selector:
            return None
        provider_name = str(self.config.provider_name or "").strip().lower()
        normalized_selector = helper_selector.lower().replace("_", "-")
        if provider_name != "deepseek" or normalized_selector != "deepseek-chat":
            return None
        route_config = replace(
            self.config,
            model="deepseek-chat",
            model_key="deepseek_chat",
            planner_kind="deepseek_chat",
            wire_api=str(self.config.wire_api or "openai_chat").strip() or "openai_chat",
        )
        return RouteResolution(
            route_name="policy_helper",
            config=route_config,
            timeout=self.policy_llm_timeout,
            source="legacy_same_provider",
            selector=helper_selector,
            configured=True,
        )

    def _route_client(self, route_name: str, route_config: ProviderConfig) -> Any:
        if (
            str(route_config.provider_name or "") == str(self.config.provider_name or "")
            and str(route_config.base_url or "") == str(self.config.base_url or "")
            and str(route_config.api_key or "") == str(self.config.api_key or "")
        ):
            return self.client
        build_client = getattr(self, "_chat_protocol_build_client", build_openai_client)
        cache_key = "|".join(
            [
                str(route_name or "").strip(),
                str(route_config.provider_name or "").strip(),
                str(route_config.model or "").strip(),
                str(route_config.base_url or "").strip(),
            ]
        )
        cached = self._route_client_cache.get(cache_key)
        if cached is not None:
            return cached
        client = build_client(
            route_config,
            fallback_base_url="https://api.deepseek.com",
        )
        self._route_client_cache[cache_key] = client
        return client

    def public_summary(self) -> Dict[str, Any]:
        summary = super().public_summary()
        summary.setdefault("routes", {})
        summary["routes"]["policy_helper"] = self._policy_helper_route().public_summary()
        return summary
