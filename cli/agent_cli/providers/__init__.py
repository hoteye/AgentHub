"""Provider internals split out from the legacy provider module."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .anthropic_claude import AnthropicClaudePlanner, load_claude_provider_config, should_use_claude_provider
    from .chat_completions_planner import ChatCompletionsPlanner, DeepSeekPlanner
    from .config_catalog import (
        ModelCatalogEntry,
        ProviderCatalog,
        ProviderCatalogEntry,
        ProviderConfig,
        ProviderPathResolution,
        build_provider_catalog,
        candidate_api_key_names,
        default_model_entry,
        find_model_entry,
        first_configured_key,
        infer_planner_kind,
        optional_bool,
        read_json_file,
        read_toml_file,
        resolve_provider_paths,
        select_provider_config,
    )
    from .openai_planner import OpenAIPlanner
    from .registry import (
        build_planner,
        infer_vendor,
        model_selector_for_line,
        normalize_planner_kind,
        planner_class_for_kind,
        registered_vendors,
        vendor_for_config,
        vendor_for_name,
    )
    from .vendors import ANTHROPIC_VENDOR, DEEPSEEK_VENDOR, GLM_VENDOR, OPENAI_VENDOR


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ANTHROPIC_VENDOR": (".vendors", "ANTHROPIC_VENDOR"),
    "AnthropicClaudePlanner": (".anthropic_claude", "AnthropicClaudePlanner"),
    "ChatCompletionsPlanner": (".chat_completions_planner", "ChatCompletionsPlanner"),
    "DEEPSEEK_VENDOR": (".vendors", "DEEPSEEK_VENDOR"),
    "DeepSeekPlanner": (".chat_completions_planner", "DeepSeekPlanner"),
    "GLM_VENDOR": (".vendors", "GLM_VENDOR"),
    "ModelCatalogEntry": (".config_catalog", "ModelCatalogEntry"),
    "OPENAI_VENDOR": (".vendors", "OPENAI_VENDOR"),
    "OpenAIPlanner": (".openai_planner", "OpenAIPlanner"),
    "ProviderCatalog": (".config_catalog", "ProviderCatalog"),
    "ProviderCatalogEntry": (".config_catalog", "ProviderCatalogEntry"),
    "ProviderConfig": (".config_catalog", "ProviderConfig"),
    "ProviderPathResolution": (".config_catalog", "ProviderPathResolution"),
    "build_planner": (".registry", "build_planner"),
    "build_provider_catalog": (".config_catalog", "build_provider_catalog"),
    "candidate_api_key_names": (".config_catalog", "candidate_api_key_names"),
    "default_model_entry": (".config_catalog", "default_model_entry"),
    "find_model_entry": (".config_catalog", "find_model_entry"),
    "first_configured_key": (".config_catalog", "first_configured_key"),
    "infer_planner_kind": (".config_catalog", "infer_planner_kind"),
    "infer_vendor": (".registry", "infer_vendor"),
    "load_claude_provider_config": (".anthropic_claude", "load_claude_provider_config"),
    "model_selector_for_line": (".registry", "model_selector_for_line"),
    "normalize_planner_kind": (".registry", "normalize_planner_kind"),
    "optional_bool": (".config_catalog", "optional_bool"),
    "planner_class_for_kind": (".registry", "planner_class_for_kind"),
    "read_json_file": (".config_catalog", "read_json_file"),
    "read_toml_file": (".config_catalog", "read_toml_file"),
    "registered_vendors": (".registry", "registered_vendors"),
    "resolve_provider_paths": (".config_catalog", "resolve_provider_paths"),
    "select_provider_config": (".config_catalog", "select_provider_config"),
    "should_use_claude_provider": (".anthropic_claude", "should_use_claude_provider"),
    "vendor_for_config": (".registry", "vendor_for_config"),
    "vendor_for_name": (".registry", "vendor_for_name"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
