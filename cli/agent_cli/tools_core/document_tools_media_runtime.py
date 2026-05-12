from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    document_tools_normalization_helpers_runtime,
    document_tools_projection_helpers_runtime,
    document_tools_pure_helpers_runtime,
    document_tools_view_document_helpers_runtime,
)
from cli.agent_cli.tools_core.media_ingest_runtime import ingest_local_image


def view_image(
    *,
    path: str,
    detail: str | None = None,
    image_input_capable: bool = True,
    workspace_root_factory: Callable[[], Path],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
) -> ToolEvent:
    workspace_root = workspace_root_factory()
    request = document_tools_normalization_helpers_runtime.prepare_view_image_request(
        path=path,
        workspace_root=workspace_root,
    )
    if not image_input_capable:
        payload = document_tools_pure_helpers_runtime.view_image_failure_payload(
            requested_path=request.requested_path,
            resolved_path=request.resolved_path,
            detail=detail,
        )
        return document_tools_projection_helpers_runtime.build_view_image_event(
            ok=False,
            payload=payload,
            resolved_name=request.resolved_path.name,
            event_factory=event_factory,
        )
    ingest_result = ingest_local_image(request.requested_path, workspace_root=workspace_root, detail=detail)
    payload = ingest_result.to_dict()
    return document_tools_projection_helpers_runtime.build_view_image_event(
        ok=bool(ingest_result.ok),
        payload=payload,
        resolved_name=request.resolved_path.name,
        event_factory=event_factory,
    )


def view_image_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_image_call: Callable[[str], ToolEvent],
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_view_image_result(
        path=path,
        result_from_event=result_from_event,
        view_image_call=view_image_call,
    )


def view_document(
    *,
    path: str,
    workspace_root_factory: Callable[[], Path],
    event_factory: Callable[[str, bool, str, Dict[str, Any]], ToolEvent],
    mode: str,
    max_chars: int,
    offset: int,
) -> ToolEvent:
    return document_tools_view_document_helpers_runtime.build_view_document_event(
        path=path,
        workspace_root_factory=workspace_root_factory,
        event_factory=event_factory,
        mode=mode,
        max_chars=max_chars,
        offset=offset,
    )


def view_document_result(
    *,
    path: str,
    result_from_event: Callable[..., CommandExecutionResult],
    view_document_call: Callable[..., ToolEvent],
    mode: str,
    max_chars: int,
    offset: int,
) -> CommandExecutionResult:
    return document_tools_projection_helpers_runtime.build_view_document_result(
        path=path,
        mode=mode,
        max_chars=max_chars,
        offset=offset,
        result_from_event=result_from_event,
        view_document_call=view_document_call,
    )
