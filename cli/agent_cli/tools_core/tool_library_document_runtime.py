from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.media_content_runtime import normalized_image_detail
from cli.agent_cli.tools_core import document_tools_runtime, tool_library_adapter_runtime


def _view_image_detail(registry: Any) -> str | None:
    detail = normalized_image_detail(getattr(registry, "_view_image_detail", None))
    return detail or None


def _view_image_input_capable(registry: Any) -> bool:
    value = getattr(registry, "_view_image_input_capable", True)
    return bool(value) if isinstance(value, bool) else True


def office_skills(registry: Any) -> Any:
    return tool_library_adapter_runtime.call_office_tool(
        document_tools_runtime.office_skills,
        registry,
    )


def office_skills_result(registry: Any) -> Any:
    return tool_library_adapter_runtime.call_office_tool_result(
        document_tools_runtime.office_skills_result,
        registry,
        fallback_arg="office_skills_call",
        fallback_call=registry.office_skills,
    )


def office_run(registry: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> Any:
    return tool_library_adapter_runtime.call_office_tool(
        document_tools_runtime.office_run,
        registry,
        skill_name=skill_name,
        args=args,
    )


def office_run_result(registry: Any, skill_name: str, *, args: Optional[Dict[str, Any]] = None) -> Any:
    return tool_library_adapter_runtime.call_office_tool_result(
        document_tools_runtime.office_run_result,
        registry,
        fallback_arg="office_run_call",
        fallback_call=registry.office_run,
        skill_name=skill_name,
        args=args,
    )


def view_image(registry: Any, path: str) -> Any:
    return document_tools_runtime.view_image(
        path=path,
        detail=_view_image_detail(registry),
        image_input_capable=_view_image_input_capable(registry),
        workspace_root_factory=registry.workspace_root,
        event_factory=registry._event,
    )


def view_image_result(registry: Any, path: str) -> Any:
    return document_tools_runtime.view_image_result(
        path=path,
        result_from_event=registry._result_from_event,
        view_image_call=registry.view_image,
    )


__all__ = [
    "office_run",
    "office_run_result",
    "office_skills",
    "office_skills_result",
    "view_image",
    "view_image_result",
]
