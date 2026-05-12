from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli import agent_provider_probe_runtime


def probe_provider(
    agent: Any,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    load_provider_config_fn,
    build_planner_fn,
    writeback_availability: bool = True,
) -> Dict[str, Any]:
    return agent_provider_probe_runtime.probe_provider(
        agent,
        provider_name=provider_name,
        model=model,
        load_provider_config_fn=load_provider_config_fn,
        build_planner_fn=build_planner_fn,
        writeback_availability=writeback_availability,
    )


def probe_providers(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
    load_provider_config_fn,
    build_planner_fn,
    writeback_availability: bool = True,
) -> List[Dict[str, Any]]:
    return agent_provider_probe_runtime.probe_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
        load_provider_config_fn=load_provider_config_fn,
        build_planner_fn=build_planner_fn,
        writeback_availability=writeback_availability,
    )


def available_providers(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    return agent_provider_probe_runtime.available_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )


def expert_review_feature_settings(agent: Any) -> Dict[str, Any]:
    return agent_provider_probe_runtime.expert_review_feature_settings(agent)


def provider_review_gate(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
    min_eligible_providers: int | None = None,
    prefer_cross_vendor: bool | None = None,
    allow_same_vendor_fallback: bool | None = None,
) -> Dict[str, Any]:
    return agent_provider_probe_runtime.provider_review_gate(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
        min_eligible_providers=min_eligible_providers,
        prefer_cross_vendor=prefer_cross_vendor,
        allow_same_vendor_fallback=allow_same_vendor_fallback,
    )


def available_models(
    agent: Any,
    provider_name: Optional[str] = None,
    *,
    include_hidden: bool = False,
    load_provider_catalog_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    return agent_provider_probe_runtime.available_models(
        agent,
        provider_name=provider_name,
        include_hidden=include_hidden,
        load_provider_catalog_fn=load_provider_catalog_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )
