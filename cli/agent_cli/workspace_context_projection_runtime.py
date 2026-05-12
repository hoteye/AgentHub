from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from cli.agent_cli import workspace_context_prompt_runtime as workspace_context_prompt_runtime_service
from cli.agent_cli import workspace_context_reference_runtime as workspace_context_reference_runtime_service


def render_skills_section(skills: List[Any], *, skill_usage_rules: str) -> Optional[str]:
    return workspace_context_prompt_runtime_service.render_skills_section(
        skills,
        skill_usage_rules=skill_usage_rules,
    )


def build_workspace_prompt_context(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    read_project_docs_fn: Callable[..., Optional[str]],
    discover_workspace_skills_fn: Callable[[str | Path, Optional[Sequence[str | Path]]], List[Any]],
    render_skills_section_fn: Callable[[List[Any]], Optional[str]],
    context_factory: Callable[..., Any],
    empty_context_factory: Callable[[], Any],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> Any:
    context = workspace_context_prompt_runtime_service.build_workspace_prompt_context(
        cwd,
        safe_resolve=safe_resolve,
        read_project_docs=read_project_docs_fn,
        discover_workspace_skills=discover_workspace_skills_fn,
        render_skills_section=render_skills_section_fn,
        context_factory=context_factory,
        extra_skill_roots=extra_skill_roots,
    )
    return context if isinstance(context, context_factory) else empty_context_factory()


def render_workspace_prompt_addendum(
    cwd: str | Path | None,
    *,
    build_workspace_prompt_context_fn: Callable[..., Any],
    extra_skill_roots: Optional[Sequence[str | Path]] = None,
) -> str:
    if cwd is None:
        return ""
    return build_workspace_prompt_context_fn(cwd, extra_skill_roots=extra_skill_roots).instructions_text


def text_digest(value: str) -> str:
    return workspace_context_prompt_runtime_service.text_digest(value)


def json_digest(value: Dict[str, Any]) -> str:
    return workspace_context_prompt_runtime_service.json_digest(value)


def path_signature(path: Path, *, safe_resolve: Callable[[Path], Path]) -> Dict[str, Any]:
    return workspace_context_prompt_runtime_service.path_signature(path, safe_resolve=safe_resolve)


def workspace_context_marker_offset(text: str) -> int | None:
    source = str(text or "")
    indexes = [
        idx
        for idx in (
            source.find("REFERENCE_CONTEXT_BASELINE:"),
            source.find("REFERENCE_CONTEXT_UPDATE:"),
            source.find("# AENGTHUB.md instructions for "),
            source.find("# AGENTS.md instructions for "),
        )
        if idx >= 0
    ]
    return min(indexes) if indexes else None


def workspace_contract(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    return workspace_context_reference_runtime_service.workspace_contract(snapshot)


def workspace_reference_diff(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> Dict[str, Any]:
    return workspace_context_reference_runtime_service.workspace_reference_diff(previous, current)


def render_workspace_context_update_message(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> Optional[str]:
    return workspace_context_reference_runtime_service.render_workspace_context_update_message(
        previous,
        current,
        max_chars=max_chars,
    )


def workspace_instructions_excerpt(
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> str:
    return workspace_context_reference_runtime_service.workspace_instructions_excerpt(
        current,
        max_chars=max_chars,
    )


def build_workspace_reference_context_item(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> Optional[Dict[str, Any]]:
    return workspace_context_reference_runtime_service.build_workspace_reference_context_item(
        previous,
        current,
        max_chars=max_chars,
    )


def render_workspace_reference_context_item_message(item: Dict[str, Any]) -> Optional[str]:
    return workspace_context_reference_runtime_service.render_workspace_reference_context_item_message(item)


def explicitly_mentioned_skills(text: str, skills: List[Any]) -> List[Any]:
    return list(workspace_context_prompt_runtime_service.explicitly_mentioned_skills(text, skills))
