from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cli.agent_cli.tools_core.tool_capabilities import WEB_SEARCH_TOOL_KEY


BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH = "provider_native_openai_responses_web_search"
BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH = "provider_native_anthropic_web_search"
BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH = "provider_native_glm_web_search"
BACKEND_LOCAL_WEB_SEARCH = "local_web_search"


@dataclass(frozen=True, slots=True)
class ToolBackendSpec:
    tool: str
    backend_id: str
    backend_kind: str
    provider_names: tuple[str, ...] = ()
    planner_kinds: tuple[str, ...] = ()
    wire_apis: tuple[str, ...] = ()
    configurable_modes: tuple[str, ...] = ("disabled", "cached", "live")
    supported_modes: tuple[str, ...] = ("disabled", "cached", "live")
    default_mode: str = "live"
    mode_binding: str = "canonical_best_effort"
    mode_support_level: str = "explicit"
    cached_live_distinct: bool = True
    mode_fallback_semantics: str = "none"
    notes: str = ""


def web_search_backends() -> tuple[ToolBackendSpec, ...]:
    return (
        ToolBackendSpec(
            tool=WEB_SEARCH_TOOL_KEY,
            backend_id=BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
            backend_kind="provider_native",
            provider_names=("openai", "reference"),
            planner_kinds=("openai_responses",),
            default_mode="cached",
            mode_binding="explicit_external_web_access",
            mode_support_level="explicit",
            cached_live_distinct=True,
            mode_fallback_semantics="none",
            notes="OpenAI Responses native web_search backend",
        ),
        ToolBackendSpec(
            tool=WEB_SEARCH_TOOL_KEY,
            backend_id=BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
            backend_kind="provider_native",
            provider_names=("anthropic", "claude", "claude_code", "anthropic_claude"),
            planner_kinds=("anthropic_messages",),
            configurable_modes=("disabled", "cached", "live"),
            supported_modes=("disabled", "live"),
            mode_binding="native_live_only",
            mode_support_level="best_effort",
            cached_live_distinct=False,
            mode_fallback_semantics="cached_requests_downgrade_to_live",
            notes="Anthropic native web_search backend; native wire does not expose cached-vs-live mode control",
        ),
        ToolBackendSpec(
            tool=WEB_SEARCH_TOOL_KEY,
            backend_id=BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
            backend_kind="provider_native",
            provider_names=("glm", "zhipu"),
            planner_kinds=("openai_chat",),
            configurable_modes=("disabled", "cached", "live"),
            supported_modes=("disabled", "live"),
            mode_binding="provider_specific_live_only",
            mode_support_level="best_effort",
            cached_live_distinct=False,
            mode_fallback_semantics="cached_requests_downgrade_to_live",
            notes="GLM native web_search backend; provider-specific shape exists but runtime support remains best-effort until probed",
        ),
        ToolBackendSpec(
            tool=WEB_SEARCH_TOOL_KEY,
            backend_id=BACKEND_LOCAL_WEB_SEARCH,
            backend_kind="local_fallback",
            configurable_modes=("disabled", "cached", "live"),
            supported_modes=("disabled", "live"),
            mode_binding="local_live_only",
            mode_support_level="fallback_only",
            cached_live_distinct=False,
            mode_fallback_semantics="cached_requests_downgrade_to_live",
            notes="Local WebSearchTools fallback backend; cached-vs-live distinction is not provider-native",
        ),
    )


def backend_spec_by_id(
    backend_id: str,
    *,
    backends: Iterable[ToolBackendSpec] | None = None,
) -> ToolBackendSpec | None:
    token = str(backend_id or "").strip()
    if not token:
        return None
    candidates = tuple(backends or web_search_backends())
    for spec in candidates:
        if spec.backend_id == token:
            return spec
    return None
