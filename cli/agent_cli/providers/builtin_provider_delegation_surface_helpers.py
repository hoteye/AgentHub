from __future__ import annotations

_DELEGATION_TOOL_SPEC_ORDER: tuple[str, ...] = (
    "spawn_agent",
    "request_orchestration",
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
    "send_input",
    "resume_agent",
    "wait_agent",
    "agent_workflow",
    "recover_agent",
    "close_agent",
)

_CODEX_OPENAI_PROFILE = "codex_openai"
_CLAUDE_CODE_PROFILE = "claude_code"
_CODEX_WAIT_TOOL_NAME = "wait"
_CLAUDE_AGENT_TOOL_NAME = "Agent"
_CLAUDE_SEND_MESSAGE_TOOL_NAME = "SendMessage"

_CANONICAL_TOOL_NAME_ALIASES = {
    _CODEX_WAIT_TOOL_NAME.lower(): "wait_agent",
    _CLAUDE_AGENT_TOOL_NAME.lower(): "spawn_agent",
    _CLAUDE_SEND_MESSAGE_TOOL_NAME.lower(): "send_input",
}

_PROFILE_VISIBLE_NAME_OVERRIDES = {
    _CODEX_OPENAI_PROFILE: {
        "wait_agent": _CODEX_WAIT_TOOL_NAME,
        "agent_workflow": "",
        "recover_agent": "",
    },
    _CLAUDE_CODE_PROFILE: {
        "spawn_agent": _CLAUDE_AGENT_TOOL_NAME,
        "send_input": _CLAUDE_SEND_MESSAGE_TOOL_NAME,
        "resume_agent": "",
        "wait_agent": "",
        "agent_workflow": "",
        "recover_agent": "",
        "close_agent": "",
    },
}

_PROFILE_SPEC_OVERRIDE_KINDS = {
    _CODEX_OPENAI_PROFILE: {
        "wait_agent": "codex_wait",
    },
    _CLAUDE_CODE_PROFILE: {
        "spawn_agent": "claude_agent",
        "send_input": "claude_send_message",
    },
}


def normalized_tool_surface_profile(tool_surface_profile: str) -> str:
    return str(tool_surface_profile or "").strip().lower()


def delegation_tool_spec_order() -> tuple[str, ...]:
    return _DELEGATION_TOOL_SPEC_ORDER


def canonical_delegation_tool_name(name: str) -> str:
    normalized = str(name or "").strip()
    lowered = normalized.lower()
    return _CANONICAL_TOOL_NAME_ALIASES.get(lowered, normalized)


def visible_delegation_tool_name(
    name: str,
    *,
    tool_surface_profile: str = "",
) -> str:
    canonical_name = canonical_delegation_tool_name(name)
    profile = normalized_tool_surface_profile(tool_surface_profile)
    if not profile:
        return canonical_name
    return _PROFILE_VISIBLE_NAME_OVERRIDES.get(profile, {}).get(canonical_name, canonical_name)


def visible_delegation_tool_name_pairs(
    *,
    tool_surface_profile: str = "",
) -> tuple[tuple[str, str], ...]:
    pairs = []
    for canonical_name in _DELEGATION_TOOL_SPEC_ORDER:
        visible_name = visible_delegation_tool_name(
            canonical_name,
            tool_surface_profile=tool_surface_profile,
        )
        if visible_name:
            pairs.append((canonical_name, visible_name))
    return tuple(pairs)


def visible_delegation_tool_order(*, tool_surface_profile: str = "") -> tuple[str, ...]:
    return tuple(
        visible_name
        for _, visible_name in visible_delegation_tool_name_pairs(
            tool_surface_profile=tool_surface_profile,
        )
    )


def delegation_tool_projection_override_kind(
    canonical_name: str,
    *,
    tool_surface_profile: str = "",
) -> str:
    canonical_tool_name = canonical_delegation_tool_name(canonical_name)
    profile = normalized_tool_surface_profile(tool_surface_profile)
    return _PROFILE_SPEC_OVERRIDE_KINDS.get(profile, {}).get(canonical_tool_name, "")
