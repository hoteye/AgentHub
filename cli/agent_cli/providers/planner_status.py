from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, List

from cli.agent_cli.providers.availability_models import canonical_model_token, normalize_provider_name
from cli.agent_cli.providers.model_routing import (
    RouteResolution,
    STANDARD_DELEGATION_NAMES,
    resolve_delegation_config,
    resolve_route_config,
)
from cli.agent_cli.providers.availability_projection import (
    append_availability_surface,
    get_availability_registry,
)
from cli.agent_cli.providers.availability_feature_config_runtime import provider_availability_feature_settings
from cli.agent_cli.workspace_context import agent_cli_home_skill_roots, render_workspace_prompt_addendum


class PlannerStatusMixin:
    def _availability_status_for_config(self, config: Any | None) -> str:
        availability_registry = get_availability_registry(self)
        if availability_registry is None or config is None:
            return "unknown"
        provider_name = str(getattr(config, "provider_name", "") or "").strip()
        model = str(getattr(config, "model", "") or getattr(config, "model_key", "") or "").strip()
        if not provider_name or not model:
            return "unknown"
        try:
            record = availability_registry.get(provider_name, model)
        except Exception:
            record = None
        if record is not None:
            raw_status = getattr(record, "status", "unknown")
            return str(getattr(raw_status, "value", raw_status) or "unknown").strip().lower() or "unknown"
        try:
            raw_status = availability_registry.status(provider_name, model)
        except Exception:
            raw_status = "unknown"
        return str(getattr(raw_status, "value", raw_status) or "unknown").strip().lower() or "unknown"

    def _config_identity_matches_main(self, config: Any | None) -> bool:
        main_config = getattr(self, "config", None)
        if config is None or main_config is None:
            return False
        if normalize_provider_name(getattr(config, "provider_name", "")) != normalize_provider_name(
            getattr(main_config, "provider_name", "")
        ):
            return False
        left_model = canonical_model_token(str(getattr(config, "model", "") or getattr(config, "model_key", "") or ""))
        right_model = canonical_model_token(
            str(getattr(main_config, "model", "") or getattr(main_config, "model_key", "") or "")
        )
        if left_model or right_model:
            if left_model != right_model:
                return False
        elif str(getattr(config, "model", "") or "").strip() != str(getattr(main_config, "model", "") or "").strip():
            return False
        return str(getattr(config, "base_url", "") or "").strip() == str(getattr(main_config, "base_url", "") or "").strip()

    def _effective_route_resolution(
        self,
        route_name: str,
        resolution: RouteResolution,
    ) -> RouteResolution:
        effective, _metadata = self._effective_route_resolution_metadata(route_name, resolution)
        return effective

    def _effective_route_resolution_metadata(
        self,
        route_name: str,
        resolution: RouteResolution,
    ) -> tuple[RouteResolution, Dict[str, Any]]:
        config = getattr(resolution, "config", None)
        metadata: Dict[str, Any] = {
            "availability_fallback_to_main": False,
            "effective_route_name": str(route_name or ""),
            "effective_source": str(getattr(resolution, "source", "") or "missing"),
            "effective_provider_name": str(getattr(config, "provider_name", "") or "") if config is not None else "",
            "effective_model_key": str(getattr(config, "model_key", "") or "") if config is not None else "",
            "effective_model": str(getattr(config, "model", "") or "") if config is not None else "",
        }
        if config is None:
            return resolution, metadata
        if self._config_identity_matches_main(config):
            return resolution, metadata
        configured_status = self._availability_status_for_config(config)
        if configured_status != "unavailable":
            return resolution, metadata
        main_config = getattr(self, "config", None)
        if main_config is None:
            return resolution, metadata
        main_status = self._availability_status_for_config(main_config)
        if main_status == "unavailable":
            return resolution, metadata
        fallback_source = f"{str(getattr(resolution, 'source', '') or 'route')}_availability_fallback_main"
        try:
            effective = replace(
                resolution,
                config=main_config,
                source=fallback_source,
            )
        except TypeError:
            effective = RouteResolution(
                route_name=str(getattr(resolution, "route_name", "") or route_name),
                config=main_config,
                timeout=getattr(resolution, "timeout", None),
                source=fallback_source,
                selector=str(getattr(resolution, "selector", "") or ""),
                configured=bool(getattr(resolution, "configured", True)),
            )
        metadata.update(
            {
                "availability_fallback_to_main": True,
                "effective_source": str(getattr(effective, "source", "") or "missing"),
                "effective_provider_name": str(getattr(main_config, "provider_name", "") or ""),
                "effective_model_key": str(getattr(main_config, "model_key", "") or ""),
                "effective_model": str(getattr(main_config, "model", "") or ""),
            }
        )
        return effective, metadata

    def _plugin_skill_roots(self) -> List[str]:
        roots = list(agent_cli_home_skill_roots())
        if self.plugin_manager_factory is None:
            return roots
        try:
            manager = self.plugin_manager_factory()
        except Exception:
            return roots
        if manager is None:
            return roots
        getter = getattr(manager, "effective_skill_roots", None)
        if not callable(getter):
            return roots
        seen = {str(item) for item in roots}
        for item in list(getter() or []):
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            roots.append(text)
        return roots

    def workspace_prompt_addendum(self) -> str:
        return render_workspace_prompt_addendum(self.cwd, extra_skill_roots=self._plugin_skill_roots())

    def public_summary(self) -> Dict[str, Any]:
        summary = self.config.public_summary()
        availability_registry = get_availability_registry(self)
        stale_after_seconds = int(provider_availability_feature_settings(self).get("stale_after_seconds") or 0)
        append_availability_surface(
            summary,
            availability_registry,
            provider_name=str(summary.get("provider_name") or ""),
            model=str(summary.get("model") or ""),
            stale_after_seconds=stale_after_seconds,
        )
        route_specs = self._route_status_specs()
        if route_specs:
            route_summary = {}
            for route_name, spec in route_specs.items():
                resolved = self._resolve_route(
                    route_name,
                    legacy_selector=str(spec.get("legacy_selector") or "").strip() or None,
                    default_timeout=spec.get("default_timeout"),
                    fallback_to_main=bool(spec.get("fallback_to_main", True)),
                )
                item = resolved.public_summary()
                if isinstance(item, dict):
                    append_availability_surface(
                        item,
                        availability_registry,
                        provider_name=str(item.get("provider_name") or ""),
                        model=str(item.get("model") or ""),
                        stale_after_seconds=stale_after_seconds,
                    )
                    _effective, metadata = self._effective_route_resolution_metadata(route_name, resolved)
                    item.update(metadata)
                route_summary[route_name] = item
            summary["routes"] = route_summary
        delegation_specs = self._delegation_status_specs()
        if delegation_specs:
            delegation_summary = {}
            for role_name, spec in delegation_specs.items():
                resolved = self._resolve_delegation(
                    role_name,
                    default_timeout=spec.get("default_timeout"),
                    fallback_to_main=bool(spec.get("fallback_to_main", True)),
                )
                item = resolved.public_summary()
                if isinstance(item, dict):
                    append_availability_surface(
                        item,
                        availability_registry,
                        provider_name=str(item.get("provider_name") or ""),
                        model=str(item.get("model") or ""),
                        stale_after_seconds=stale_after_seconds,
                    )
                    _effective, metadata = self._effective_route_resolution_metadata(role_name, resolved)
                    item.update(metadata)
                delegation_summary[role_name] = item
            summary["delegation"] = delegation_summary
        return summary

    def _route_status_specs(self) -> Dict[str, Dict[str, Any]]:
        return {}

    def _delegation_status_specs(self) -> Dict[str, Dict[str, Any]]:
        return {
            role_name: {}
            for role_name in STANDARD_DELEGATION_NAMES
        }

    def _resolve_route(
        self,
        route_name: str,
        *,
        legacy_selector: str | None = None,
        default_timeout: int | None = None,
        fallback_to_main: bool = True,
    ) -> RouteResolution:
        cache_key = (
            str(route_name or "").strip(),
            str(legacy_selector or "").strip(),
            int(default_timeout) if isinstance(default_timeout, int) else None,
            bool(fallback_to_main),
        )
        cached = self._route_resolution_cache.get(cache_key)
        if cached is not None:
            return cached
        resolved = resolve_route_config(
            self.config,
            route_name,
            cwd=self.cwd,
            fallback_to_main=fallback_to_main,
            default_timeout=default_timeout,
            legacy_selector=legacy_selector,
        )
        self._route_resolution_cache[cache_key] = resolved
        return resolved

    def _resolve_delegation(
        self,
        role_name: str,
        *,
        default_timeout: int | None = None,
        fallback_to_main: bool = True,
    ) -> RouteResolution:
        cache_key = (
            str(role_name or "").strip(),
            int(default_timeout) if isinstance(default_timeout, int) else None,
            bool(fallback_to_main),
        )
        cached = self._delegation_resolution_cache.get(cache_key)
        if cached is not None:
            return cached
        resolved = resolve_delegation_config(
            self.config,
            role_name,
            cwd=self.cwd,
            fallback_to_main=fallback_to_main,
            default_timeout=default_timeout,
        )
        self._delegation_resolution_cache[cache_key] = resolved
        return resolved
