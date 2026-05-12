from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Type

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.config.catalog import ProviderConfig
from cli.agent_cli.providers.protocols.anthropic_messages import AnthropicClaudePlanner
from cli.agent_cli.providers.protocols.openai_chat import ChatCompletionsPlanner
from cli.agent_cli.providers.protocols.openai_responses import OpenAIPlanner
from cli.agent_cli.providers.types import PlannerRuntimeFamily, ProviderVendorSpec
from cli.agent_cli.providers.vendors import ANTHROPIC_VENDOR, DEEPSEEK_VENDOR, GLM_VENDOR, OPENAI_VENDOR

PluginManagerFactory = Callable[[], Optional[PluginManager]]

OPENAI_RESPONSES_FAMILY = PlannerRuntimeFamily(
    name="openai_responses",
    planner_kinds=("openai_responses",),
    description="OpenAI Responses / Reference-style item loop",
)
OPENAI_CHAT_FAMILY = PlannerRuntimeFamily(
    name="openai_chat",
    planner_kinds=("openai_chat", "deepseek_chat", "deepseek_reasoner"),
    description="OpenAI-compatible chat completions family",
)
ANTHROPIC_MESSAGES_FAMILY = PlannerRuntimeFamily(
    name="anthropic_messages",
    planner_kinds=("anthropic_messages",),
    description="Anthropic messages family",
)

_PLANNER_KIND_TO_CLASS: dict[str, Type[object]] = {
    **{kind: OpenAIPlanner for kind in OPENAI_RESPONSES_FAMILY.planner_kinds},
    **{kind: ChatCompletionsPlanner for kind in OPENAI_CHAT_FAMILY.planner_kinds},
    **{kind: AnthropicClaudePlanner for kind in ANTHROPIC_MESSAGES_FAMILY.planner_kinds},
}
_REGISTERED_VENDORS: tuple[ProviderVendorSpec, ...] = (
    OPENAI_VENDOR,
    ANTHROPIC_VENDOR,
    DEEPSEEK_VENDOR,
    GLM_VENDOR,
)


def normalize_planner_kind(planner_kind: str) -> str:
    normalized = str(planner_kind or "").strip().lower()
    return normalized or OPENAI_RESPONSES_FAMILY.name


def planner_class_for_kind(planner_kind: str) -> Type[object]:
    normalized = normalize_planner_kind(planner_kind)
    return _PLANNER_KIND_TO_CLASS.get(normalized, OpenAIPlanner)


def registered_vendors() -> tuple[ProviderVendorSpec, ...]:
    return _REGISTERED_VENDORS


def vendor_for_name(name: str) -> ProviderVendorSpec | None:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return None
    for vendor in _REGISTERED_VENDORS:
        aliases = {vendor.name.lower(), *(alias.lower() for alias in vendor.aliases)}
        if normalized in aliases:
            return vendor
    return None


def infer_vendor(
    *,
    provider_name: str = "",
    model: str = "",
    base_url: str = "",
    planner_kind: str = "",
) -> ProviderVendorSpec | None:
    direct = vendor_for_name(provider_name)
    if direct is not None:
        return direct
    fingerprint = " ".join(
        str(token or "").strip().lower()
        for token in (provider_name, model, base_url, planner_kind)
        if str(token or "").strip()
    )
    if not fingerprint:
        return None
    for vendor in _REGISTERED_VENDORS:
        aliases = {vendor.name.lower(), *(alias.lower() for alias in vendor.aliases)}
        if any(alias and alias in fingerprint for alias in aliases):
            return vendor
    if "anthropic_messages" in fingerprint:
        return ANTHROPIC_VENDOR
    if "openai_responses" in fingerprint or "gpt-" in fingerprint:
        return OPENAI_VENDOR
    if "openai_chat" in fingerprint:
        return OPENAI_VENDOR
    return None


def vendor_for_config(config: ProviderConfig) -> ProviderVendorSpec | None:
    return infer_vendor(
        provider_name=str(config.provider_name or ""),
        model=str(config.model or ""),
        base_url=str(config.base_url or ""),
        planner_kind=str(config.planner_kind or ""),
    )


def model_selector_for_line(
    *,
    line: str,
    provider_name: str = "",
    model: str = "",
    base_url: str = "",
    planner_kind: str = "",
) -> str | None:
    vendor = infer_vendor(
        provider_name=provider_name,
        model=model,
        base_url=base_url,
        planner_kind=planner_kind,
    )
    if vendor is None:
        return None
    return vendor.model_selector_for_line(line)


def build_planner(
    config: ProviderConfig,
    *,
    host_platform: HostPlatform | None = None,
    cwd: str | Path | None = None,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> object:
    planner_cls = planner_class_for_kind(config.planner_kind)
    return planner_cls(
        config,
        host_platform=host_platform,
        cwd=str(cwd) if cwd is not None else None,
        plugin_manager_factory=plugin_manager_factory,
    )


__all__ = [
    "ANTHROPIC_MESSAGES_FAMILY",
    "OPENAI_CHAT_FAMILY",
    "OPENAI_RESPONSES_FAMILY",
    "build_planner",
    "infer_vendor",
    "model_selector_for_line",
    "normalize_planner_kind",
    "planner_class_for_kind",
    "registered_vendors",
    "vendor_for_config",
    "vendor_for_name",
]
