from __future__ import annotations

from dataclasses import dataclass
import difflib
import json
from pathlib import Path
from typing import Any, Callable


_STRUCTURED_REQUEST_FIELDS = frozenset(
    {"operation", "file_path", "content", "old_string", "new_string", "replace_all"}
)


class ApplyPatchError(ValueError):
    pass


@dataclass
class StructuredPatchRequest:
    kind: str
    file_path: str
    content: str | None = None
    old_string: str | None = None
    new_string: str | None = None
    replace_all: bool = False
    source_tool_name: str | None = None
    guard_profile: str | None = None


def compact_request_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in ("", None, {}, [])
    }


def structured_request_metadata(request: StructuredPatchRequest) -> dict[str, Any]:
    if request.kind == "write":
        arguments = {
            "file_path": str(request.file_path),
            "content": str(request.content or ""),
        }
        tool_name = str(request.source_tool_name or "apply_patch")
        request_kind = "structured_write"
    else:
        arguments = {
            "file_path": str(request.file_path),
            "old_string": str(request.old_string or ""),
            "new_string": str(request.new_string or ""),
        }
        if request.replace_all:
            arguments["replace_all"] = True
        tool_name = str(request.source_tool_name or "apply_patch")
        request_kind = "structured_edit"
    return compact_request_metadata(
        {
            "request_kind": request_kind,
            "structured_request_kind": str(request.kind),
            "source_tool_name": str(request.source_tool_name or ""),
            "guard_profile": str(request.guard_profile or ""),
            "function_call_name": tool_name,
            "function_call_arguments": arguments,
        }
    )


def parse_structured_request(
    patch_text: str,
    *,
    begin_patch_marker: str,
    normalize_patch_text_fn: Callable[[str], str],
) -> StructuredPatchRequest | None:
    raw = normalize_patch_text_fn(patch_text)
    if not raw:
        return None
    if raw.startswith(begin_patch_marker):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        if raw.startswith("{"):
            raise ApplyPatchError(f"invalid structured apply_patch payload: {exc.msg}") from exc
        return None
    if not isinstance(payload, dict):
        raise ApplyPatchError("structured apply_patch payload must be an object")
    if not any(key in payload for key in _STRUCTURED_REQUEST_FIELDS):
        raise ApplyPatchError(
            "structured apply_patch payload must include file_path plus content or old_string/new_string"
        )

    operation = str(payload.get("operation") or "").strip().lower()
    file_path = str(payload.get("file_path") or "").strip()
    if not file_path:
        raise ApplyPatchError("structured apply_patch payload requires file_path")

    has_content = "content" in payload
    has_old = "old_string" in payload
    has_new = "new_string" in payload
    has_replace_all = "replace_all" in payload

    if operation == "file_write":
        if has_old or has_new or has_replace_all:
            raise ApplyPatchError("structured file_write cannot mix content with old_string/new_string")
        if not has_content or payload.get("content") is None:
            raise ApplyPatchError("structured file_write requires content")
        return StructuredPatchRequest(
            kind="write",
            file_path=file_path,
            content=str(payload.get("content")),
            source_tool_name=str(payload.get("source_tool_name") or "").strip() or None,
            guard_profile=str(payload.get("guard_profile") or "").strip() or None,
        )

    if operation == "file_edit":
        if has_content:
            raise ApplyPatchError("structured file_edit cannot mix content with old_string/new_string")
        if not has_old or not has_new:
            raise ApplyPatchError("structured file_edit requires old_string and new_string")
        old_string = payload.get("old_string")
        new_string = payload.get("new_string")
        if old_string is None or new_string is None:
            raise ApplyPatchError("structured file_edit requires old_string and new_string")
        normalized_old = str(old_string)
        normalized_new = str(new_string)
        if not normalized_old:
            raise ApplyPatchError("structured file_edit requires non-empty old_string")
        if normalized_old == normalized_new:
            raise ApplyPatchError("structured file_edit requires old_string and new_string to differ")
        return StructuredPatchRequest(
            kind="edit",
            file_path=file_path,
            old_string=normalized_old,
            new_string=normalized_new,
            replace_all=bool(payload.get("replace_all")),
            source_tool_name=str(payload.get("source_tool_name") or "").strip() or None,
            guard_profile=str(payload.get("guard_profile") or "").strip() or None,
        )

    if operation == "patch":
        raise ApplyPatchError("structured apply_patch payload with operation=patch must use the patch field instead")

    if has_content and (has_old or has_new or has_replace_all):
        raise ApplyPatchError("structured apply_patch cannot mix content with old_string/new_string")
    if has_content:
        if payload.get("content") is None:
            raise ApplyPatchError("structured file_write requires content")
        return StructuredPatchRequest(
            kind="write",
            file_path=file_path,
            content=str(payload.get("content")),
            source_tool_name=str(payload.get("source_tool_name") or "").strip() or None,
            guard_profile=str(payload.get("guard_profile") or "").strip() or None,
        )
    if has_old or has_new or has_replace_all:
        if not has_old or not has_new:
            raise ApplyPatchError("structured file_edit requires old_string and new_string")
        old_string = payload.get("old_string")
        new_string = payload.get("new_string")
        if old_string is None or new_string is None:
            raise ApplyPatchError("structured file_edit requires old_string and new_string")
        normalized_old = str(old_string)
        normalized_new = str(new_string)
        if not normalized_old:
            raise ApplyPatchError("structured file_edit requires non-empty old_string")
        if normalized_old == normalized_new:
            raise ApplyPatchError("structured file_edit requires old_string and new_string to differ")
        return StructuredPatchRequest(
            kind="edit",
            file_path=file_path,
            old_string=normalized_old,
            new_string=normalized_new,
            replace_all=bool(payload.get("replace_all")),
            source_tool_name=str(payload.get("source_tool_name") or "").strip() or None,
            guard_profile=str(payload.get("guard_profile") or "").strip() or None,
        )
    raise ApplyPatchError("structured apply_patch payload requires content or old_string/new_string")


def diff_text(*, before_text: str, after_text: str, before_path: str, after_path: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=before_path,
            tofile=after_path,
            lineterm="",
        )
    )
    return "\n".join(diff_lines[:200])


def ensure_file_target(path: Path, *, action: str, raw_path: str) -> None:
    if path.exists() and path.is_dir():
        raise ApplyPatchError(f"cannot {action} directory: {raw_path}")


def edit_replacement(original_text: str, *, old_string: str, new_string: str, replace_all: bool) -> tuple[str, int]:
    match_count = original_text.count(old_string)
    if match_count == 0:
        raise ApplyPatchError("old_string not found in target file")
    if not replace_all and match_count != 1:
        raise ApplyPatchError(f"old_string must appear exactly once; found {match_count} occurrences")
    if replace_all:
        return original_text.replace(old_string, new_string), match_count
    return original_text.replace(old_string, new_string, 1), 1


def preview_structured_request(
    request: StructuredPatchRequest,
    *,
    workspace_root: Path,
    resolve_workspace_path_fn: Callable[[Path, str], Path],
) -> dict[str, Any]:
    path = resolve_workspace_path_fn(workspace_root, request.file_path)
    rel_path = str(path.relative_to(workspace_root))
    if request.kind == "write":
        ensure_file_target(path, action="write", raw_path=request.file_path)
        change_type = "update" if path.exists() else "add"
        return {
            "workspace_root": str(workspace_root),
            "request_kind": "structured_write",
            "file_count": 1,
            "added_count": 1 if change_type == "add" else 0,
            "deleted_count": 0,
            "updated_count": 1 if change_type == "update" else 0,
            "moved_count": 0,
            "changes": [
                {
                    "path": rel_path,
                    "change_type": change_type,
                    "operation": "write",
                    "write_mode": "create" if change_type == "add" else "replace",
                }
            ],
        }

    if not path.exists():
        raise ApplyPatchError(f"cannot edit missing file: {request.file_path}")
    ensure_file_target(path, action="edit", raw_path=request.file_path)
    original_text = path.read_text(encoding="utf-8")
    _, match_count = edit_replacement(
        original_text,
        old_string=str(request.old_string or ""),
        new_string=str(request.new_string or ""),
        replace_all=bool(request.replace_all),
    )
    return {
        "workspace_root": str(workspace_root),
        "request_kind": "structured_edit",
        "file_count": 1,
        "added_count": 0,
        "deleted_count": 0,
        "updated_count": 1,
        "moved_count": 0,
        "changes": [
            {
                "path": rel_path,
                "change_type": "update",
                "operation": "edit",
                "replace_all": bool(request.replace_all),
                "match_count": match_count,
            }
        ],
    }


def execute_structured_request(
    request: StructuredPatchRequest,
    *,
    workspace_root: Path,
    resolve_workspace_path_fn: Callable[[Path, str], Path],
) -> dict[str, Any]:
    path = resolve_workspace_path_fn(workspace_root, request.file_path)
    if request.kind == "write":
        ensure_file_target(path, action="write", raw_path=request.file_path)
        existed = path.exists()
        original_text = path.read_text(encoding="utf-8") if existed else ""
        content = str(request.content or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        change_type = "update" if existed else "add"
        change: dict[str, Any] = {
            "path": str(path),
            "change_type": change_type,
            "operation": "write",
            "write_mode": "replace" if existed else "create",
        }
        if existed:
            change["diff"] = diff_text(
                before_text=original_text,
                after_text=content,
                before_path=str(path),
                after_path=str(path),
            )
        return {
            "ok": True,
            "workspace_root": str(workspace_root),
            "request_kind": "structured_write",
            "file_count": 1,
            "added_count": 1 if change_type == "add" else 0,
            "deleted_count": 0,
            "updated_count": 1 if change_type == "update" else 0,
            "moved_count": 0,
            "changes": [change],
        }

    if not path.exists():
        raise ApplyPatchError(f"cannot edit missing file: {request.file_path}")
    ensure_file_target(path, action="edit", raw_path=request.file_path)
    original_text = path.read_text(encoding="utf-8")
    new_text, match_count = edit_replacement(
        original_text,
        old_string=str(request.old_string or ""),
        new_string=str(request.new_string or ""),
        replace_all=bool(request.replace_all),
    )
    path.write_text(new_text, encoding="utf-8")
    return {
        "ok": True,
        "workspace_root": str(workspace_root),
        "request_kind": "structured_edit",
        "file_count": 1,
        "added_count": 0,
        "deleted_count": 0,
        "updated_count": 1,
        "moved_count": 0,
        "changes": [
            {
                "path": str(path),
                "change_type": "update",
                "operation": "edit",
                "replace_all": bool(request.replace_all),
                "match_count": match_count,
                "diff": diff_text(
                    before_text=original_text,
                    after_text=new_text,
                    before_path=str(path),
                    after_path=str(path),
                ),
            }
        ],
    }
