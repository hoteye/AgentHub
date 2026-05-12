from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from cli.agent_cli.models_tool_io import MediaIngestResult


_VIEW_IMAGE_UNSUPPORTED_MESSAGE = (
    "view_image is not allowed because the current model/session does not support image inputs."
)


def load_cached_tool(
    *,
    cached_tools: Any | None,
    load_project_tool_module: Callable[[str], Any],
    module_name: str,
    class_name: str,
) -> Any:
    if cached_tools is not None:
        return cached_tools
    tool_cls = getattr(load_project_tool_module(module_name), class_name)
    return tool_cls()


def office_skills_summary(payload: Mapping[str, Any]) -> str:
    return f"office_skills={int(payload.get('count') or 0)}"


def office_run_summary(*, skill_name: str, payload: Mapping[str, Any]) -> str:
    return skill_name if bool(payload.get("ok")) else f"{skill_name} failed"


def view_image_success_summary(*, resolved_name: str) -> str:
    return f"image artifact ready: {resolved_name}"


def view_image_failure_payload(
    *,
    requested_path: str,
    resolved_path: Path | None,
    detail: str | None,
) -> dict[str, Any]:
    return MediaIngestResult.failure(
        error_code="unsupported_image_input_capability",
        display_message=_VIEW_IMAGE_UNSUPPORTED_MESSAGE,
        requested_path=requested_path,
        path=str(resolved_path) if requested_path and resolved_path is not None else "",
        detail=detail,
    ).to_dict()


def view_image_arguments(path: str) -> dict[str, Any]:
    return {"path": path}


def view_document_arguments(
    *,
    path: str,
    mode: str,
    max_chars: int,
    offset: int,
) -> dict[str, Any]:
    return {
        "path": path,
        "mode": mode,
        "max_chars": int(max_chars),
        "offset": int(offset),
    }


def office_run_arguments(skill_name: str, args: Mapping[str, Any] | None) -> dict[str, Any]:
    return {"skill_name": skill_name, "args": dict(args or {}) or None}


def policy_doc_import_summary(payload: Mapping[str, Any]) -> str:
    imported_count = int(payload.get("imported_count") or 0)
    return f"policy docs imported={imported_count}" if bool(payload.get("ok")) else "policy import failed"


def policy_doc_list_summary(payload: Mapping[str, Any]) -> str:
    return f"policy docs={int(payload.get('count') or 0)}"


def policy_doc_search_summary(payload: Mapping[str, Any]) -> str:
    return f"policy matches={int(payload.get('count') or 0)}" if bool(payload.get("ok")) else "policy search failed"


def policy_doc_read_summary(payload: Mapping[str, Any]) -> str:
    return "policy markdown loaded" if bool(payload.get("ok")) else "policy markdown read failed"


def policy_doc_import_arguments(
    *,
    path: str,
    library_root: str | None,
    recursive: bool,
) -> dict[str, Any]:
    return {"path": path, "library_root": library_root, "recursive": bool(recursive)}


def policy_doc_list_arguments(
    *,
    library_root: str | None,
    limit: int,
) -> dict[str, Any]:
    return {"library_root": library_root, "limit": limit}


def policy_doc_search_arguments(
    *,
    query: str,
    library_root: str | None,
    limit: int,
) -> dict[str, Any]:
    return {"query": query, "library_root": library_root, "limit": limit}


def policy_doc_read_arguments(
    *,
    doc_id: str | None,
    path: str | None,
    library_root: str | None,
    max_chars: int,
) -> dict[str, Any]:
    return {"doc_id": doc_id, "path": path, "library_root": library_root, "max_chars": max_chars}


__all__ = [
    "_VIEW_IMAGE_UNSUPPORTED_MESSAGE",
    "load_cached_tool",
    "office_run_arguments",
    "office_run_summary",
    "office_skills_summary",
    "policy_doc_import_arguments",
    "policy_doc_import_summary",
    "policy_doc_list_arguments",
    "policy_doc_list_summary",
    "policy_doc_read_arguments",
    "policy_doc_read_summary",
    "policy_doc_search_arguments",
    "policy_doc_search_summary",
    "view_document_arguments",
    "view_image_arguments",
    "view_image_failure_payload",
    "view_image_success_summary",
]
