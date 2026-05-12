from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
)
from cli.agent_cli.tools_core.tool_capabilities import (
    WEB_SEARCH_TOOL_KEY,
    ToolCapabilitySnapshot,
    capability_snapshot,
)
from cli.agent_cli.tools_core.tool_capability_resolver_normalization_helpers_runtime import (
    NormalizedWebSearchResolverInput,
)


OPENAI_RESPONSES_WIRE_APIS = frozenset({"responses", "openai_responses"})
ANTHROPIC_PROVIDER_NAMES = frozenset({"anthropic", "claude", "claude_code", "anthropic_claude"})
GLM_PROVIDER_NAMES = frozenset({"glm", "zhipu"})


@dataclass(frozen=True, slots=True)
class StaticWebSearchCapabilityRule:
    predicate: Callable[[NormalizedWebSearchResolverInput], bool]
    selected_backend: str
    availability: str
    confidence: str
    decision_source: str
    reason: str


@dataclass(frozen=True, slots=True)
class NativeWebSearchDefaults:
    openai_runtime_default: bool = False
    anthropic_runtime_default: bool = False
    glm_main_loop_default: bool = False


@dataclass(frozen=True, slots=True)
class NativeWebSearchSupportState:
    supports_runtime_native: bool = False
    supports_mixed_tools_native: bool = False
    main_loop_spec_kind: str = "function"
    native_tool_type: str = ""


def _matches_openai_native(selection: NormalizedWebSearchResolverInput) -> bool:
    return selection.planner_kind == "openai_responses" or selection.wire_api in OPENAI_RESPONSES_WIRE_APIS


def _matches_anthropic_native(selection: NormalizedWebSearchResolverInput) -> bool:
    return (
        selection.planner_kind == "anthropic_messages"
        or selection.provider_name in ANTHROPIC_PROVIDER_NAMES
        or selection.model.startswith("claude")
    )


def _matches_deepseek_local_fallback(selection: NormalizedWebSearchResolverInput) -> bool:
    return selection.provider_name == "deepseek" or selection.planner_kind.startswith("deepseek")


STATIC_WEB_SEARCH_CAPABILITY_RULES: tuple[StaticWebSearchCapabilityRule, ...] = (
    StaticWebSearchCapabilityRule(
        predicate=_matches_openai_native,
        selected_backend=BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
        availability="supported",
        confidence="high",
        decision_source="static_rule",
        reason="openai_responses_native_supported",
    ),
    StaticWebSearchCapabilityRule(
        predicate=_matches_anthropic_native,
        selected_backend=BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
        availability="supported",
        confidence="high",
        decision_source="static_rule",
        reason="anthropic_native_supported",
    ),
    StaticWebSearchCapabilityRule(
        predicate=_matches_deepseek_local_fallback,
        selected_backend=BACKEND_LOCAL_WEB_SEARCH,
        availability="unsupported",
        confidence="high",
        decision_source="static_rule",
        reason="deepseek_native_unsupported",
    ),
)


def resolve_static_web_search_capability(
    selection: NormalizedWebSearchResolverInput,
) -> ToolCapabilitySnapshot | None:
    for rule in STATIC_WEB_SEARCH_CAPABILITY_RULES:
        if not rule.predicate(selection):
            continue
        return capability_snapshot(
            tool=WEB_SEARCH_TOOL_KEY,
            selected_backend=rule.selected_backend,
            availability=rule.availability,
            confidence=rule.confidence,
            decision_source=rule.decision_source,
            reason=rule.reason,
        )
    return None


def resolve_fallback_web_search_capability(
    selection: NormalizedWebSearchResolverInput,
) -> ToolCapabilitySnapshot:
    if selection.provider_name in GLM_PROVIDER_NAMES:
        return capability_snapshot(
            tool=WEB_SEARCH_TOOL_KEY,
            selected_backend=BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
            availability="unknown",
            confidence="low",
            decision_source="fallback",
            reason="glm_best_effort_native_reserved",
        )

    if selection.wire_api == "anthropic_messages":
        return capability_snapshot(
            tool=WEB_SEARCH_TOOL_KEY,
            selected_backend=BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
            availability="supported",
            confidence="medium",
            decision_source="static_rule",
            reason="anthropic_wire_api_inferred",
        )

    return capability_snapshot(
        tool=WEB_SEARCH_TOOL_KEY,
        selected_backend=BACKEND_LOCAL_WEB_SEARCH,
        availability="unknown",
        confidence="low",
        decision_source="fallback",
        reason="default_local_fallback",
    )


def resolve_native_web_search_defaults(
    *,
    selection: NormalizedWebSearchResolverInput,
    selected_backend: str,
) -> NativeWebSearchDefaults:
    return NativeWebSearchDefaults(
        openai_runtime_default=_matches_openai_native(selection),
        anthropic_runtime_default=(
            selection.provider_name in ANTHROPIC_PROVIDER_NAMES or selection.model.startswith("claude")
        ),
        glm_main_loop_default=(
            selection.provider_name in GLM_PROVIDER_NAMES
            or selected_backend == BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH
        ),
    )


def resolve_provider_family(
    *,
    selection: NormalizedWebSearchResolverInput,
    selected_backend: str,
    defaults: NativeWebSearchDefaults,
) -> str:
    if selected_backend == BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH or selection.provider_name in GLM_PROVIDER_NAMES:
        return "glm"
    if selected_backend == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH or defaults.openai_runtime_default:
        return "openai_responses"
    if selected_backend == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH or defaults.anthropic_runtime_default:
        return "anthropic"
    if selected_backend == BACKEND_LOCAL_WEB_SEARCH:
        return "local"
    return "unknown"


def resolve_native_web_search_support_state(
    *,
    selected_backend: str,
    native_override: bool | None,
    mixed_tools_opt_in: bool,
    effective_mode: str,
    defaults: NativeWebSearchDefaults,
) -> NativeWebSearchSupportState:
    supports_openai_runtime = defaults.openai_runtime_default
    if native_override is not None and (
        defaults.openai_runtime_default
        or selected_backend == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    ):
        supports_openai_runtime = native_override

    supports_anthropic_runtime = defaults.anthropic_runtime_default
    if native_override is not None and (
        defaults.anthropic_runtime_default
        or selected_backend == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
    ):
        supports_anthropic_runtime = native_override

    supports_glm_main_loop = defaults.glm_main_loop_default
    if native_override is not None and defaults.glm_main_loop_default:
        supports_glm_main_loop = native_override

    supports_runtime_native = bool(
        (
            selected_backend == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
            and supports_openai_runtime
        )
        or (
            selected_backend == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
            and supports_anthropic_runtime
        )
    )
    supports_openai_main_loop = (
        selected_backend == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
        and supports_openai_runtime
        and mixed_tools_opt_in
    )
    supports_anthropic_main_loop = (
        selected_backend == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
        and supports_anthropic_runtime
        and mixed_tools_opt_in
    )
    supports_mixed_tools_native = bool(
        supports_openai_main_loop or supports_anthropic_main_loop or supports_glm_main_loop
    )
    main_loop_spec_kind = resolve_native_main_loop_spec_kind(
        supports_openai_main_loop=supports_openai_main_loop,
        supports_anthropic_main_loop=supports_anthropic_main_loop,
        supports_glm_main_loop=supports_glm_main_loop,
    )
    native_tool_type = resolve_native_tool_type(
        selected_backend=selected_backend,
        supports_openai_runtime=supports_openai_runtime,
        supports_anthropic_runtime=supports_anthropic_runtime,
        main_loop_spec_kind=main_loop_spec_kind,
    )

    if effective_mode == "disabled":
        return NativeWebSearchSupportState(
            supports_runtime_native=False,
            supports_mixed_tools_native=False,
            main_loop_spec_kind="function",
            native_tool_type="",
        )

    return NativeWebSearchSupportState(
        supports_runtime_native=supports_runtime_native,
        supports_mixed_tools_native=supports_mixed_tools_native,
        main_loop_spec_kind=main_loop_spec_kind,
        native_tool_type=native_tool_type,
    )


def resolve_native_main_loop_spec_kind(
    *,
    supports_openai_main_loop: bool,
    supports_anthropic_main_loop: bool,
    supports_glm_main_loop: bool,
) -> str:
    if supports_openai_main_loop:
        return "openai_responses_native"
    if supports_anthropic_main_loop:
        return "anthropic_native"
    if supports_glm_main_loop:
        return "glm_native"
    return "function"


def resolve_native_tool_type(
    *,
    selected_backend: str,
    supports_openai_runtime: bool,
    supports_anthropic_runtime: bool,
    main_loop_spec_kind: str,
) -> str:
    if (
        selected_backend == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
        and supports_openai_runtime
    ) or main_loop_spec_kind in {"openai_responses_native", "glm_native"}:
        return "web_search"
    if (
        selected_backend == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
        and supports_anthropic_runtime
    ) or main_loop_spec_kind == "anthropic_native":
        return "web_search_20250305"
    return ""


__all__ = [
    "ANTHROPIC_PROVIDER_NAMES",
    "GLM_PROVIDER_NAMES",
    "NativeWebSearchDefaults",
    "NativeWebSearchSupportState",
    "OPENAI_RESPONSES_WIRE_APIS",
    "STATIC_WEB_SEARCH_CAPABILITY_RULES",
    "StaticWebSearchCapabilityRule",
    "resolve_fallback_web_search_capability",
    "resolve_native_main_loop_spec_kind",
    "resolve_native_tool_type",
    "resolve_native_web_search_defaults",
    "resolve_native_web_search_support_state",
    "resolve_provider_family",
    "resolve_static_web_search_capability",
]
