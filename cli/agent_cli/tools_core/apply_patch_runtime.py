from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path
import shlex
from typing import Any

from cli.agent_cli.tools_core import apply_patch_structured_runtime

BEGIN_PATCH_MARKER = "*** Begin Patch"
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "*** Move to: "
EOF_MARKER = "*** End of File"
_STRUCTURED_REQUEST_FIELDS = apply_patch_structured_runtime._STRUCTURED_REQUEST_FIELDS
ApplyPatchError = apply_patch_structured_runtime.ApplyPatchError


@dataclass
class UpdateChunk:
    change_context: str | None
    old_lines: list[str]
    new_lines: list[str]
    is_end_of_file: bool = False


@dataclass
class ParsedHunk:
    kind: str
    path: str
    content: str = ""
    move_path: str | None = None
    chunks: list[UpdateChunk] | None = None


StructuredPatchRequest = apply_patch_structured_runtime.StructuredPatchRequest
_compact_request_metadata = apply_patch_structured_runtime.compact_request_metadata
_structured_request_metadata = apply_patch_structured_runtime.structured_request_metadata


def request_metadata(patch_text: str) -> dict[str, Any]:
    normalized_patch = normalize_patch_text(patch_text)
    if not normalized_patch:
        return {}
    try:
        request = parse_structured_request(normalized_patch)
    except ApplyPatchError:
        request = None
    if request is not None:
        return _structured_request_metadata(request)
    if normalized_patch.startswith(BEGIN_PATCH_MARKER):
        return {
            "request_kind": "raw_patch",
            "function_call_name": "apply_patch",
            "function_call_arguments": {"patch": normalized_patch},
        }
    return {}


def normalize_patch_text(patch_text: str) -> str:
    raw = str(patch_text or "").strip()
    if not raw:
        return ""
    if raw[0] in {"'", '"'}:
        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            return raw
        if len(tokens) == 1:
            return tokens[0]
    return raw


def parse_patch_text(patch_text: str) -> list[ParsedHunk]:
    lines = normalize_patch_text(patch_text).splitlines()
    if len(lines) < 2:
        raise ApplyPatchError("patch is empty")
    if lines[0].strip() != BEGIN_PATCH_MARKER:
        raise ApplyPatchError("the first line of the patch must be '*** Begin Patch'")
    if lines[-1].strip() != END_PATCH_MARKER:
        raise ApplyPatchError("the last line of the patch must be '*** End Patch'")

    hunks: list[ParsedHunk] = []
    index = 1
    while index < len(lines) - 1:
        line = lines[index].strip()
        if line.startswith(ADD_FILE_MARKER):
            path = line[len(ADD_FILE_MARKER) :].strip()
            index += 1
            added_lines: list[str] = []
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                current = lines[index]
                if not current.startswith("+"):
                    raise ApplyPatchError(f"invalid add-file line: {current}")
                added_lines.append(current[1:])
                index += 1
            if not added_lines:
                raise ApplyPatchError(f"add-file hunk for {path} is empty")
            hunks.append(ParsedHunk(kind="add", path=path, content="\n".join(added_lines) + "\n"))
            continue

        if line.startswith(DELETE_FILE_MARKER):
            path = line[len(DELETE_FILE_MARKER) :].strip()
            hunks.append(ParsedHunk(kind="delete", path=path))
            index += 1
            continue

        if line.startswith(UPDATE_FILE_MARKER):
            path = line[len(UPDATE_FILE_MARKER) :].strip()
            index += 1
            move_path: str | None = None
            if index < len(lines) - 1 and lines[index].strip().startswith(MOVE_TO_MARKER):
                move_path = lines[index].strip()[len(MOVE_TO_MARKER) :].strip()
                index += 1
            chunks: list[UpdateChunk] = []
            while index < len(lines) - 1:
                current = lines[index]
                stripped = current.strip()
                if stripped.startswith((ADD_FILE_MARKER, DELETE_FILE_MARKER, UPDATE_FILE_MARKER)) or stripped == END_PATCH_MARKER:
                    break
                change_context: str | None = None
                if stripped == "@@":
                    index += 1
                elif stripped.startswith("@@ "):
                    change_context = stripped[3:]
                    index += 1
                old_lines: list[str] = []
                new_lines: list[str] = []
                is_end_of_file = False
                while index < len(lines) - 1:
                    change_line = lines[index]
                    stripped_change = change_line.strip()
                    if stripped_change == EOF_MARKER:
                        is_end_of_file = True
                        index += 1
                        break
                    if stripped_change == "@@" or stripped_change.startswith("@@ "):
                        break
                    if stripped_change.startswith((ADD_FILE_MARKER, DELETE_FILE_MARKER, UPDATE_FILE_MARKER)) or stripped_change == END_PATCH_MARKER:
                        break
                    if not change_line:
                        raise ApplyPatchError("blank change lines must still carry a patch prefix")
                    prefix = change_line[0]
                    content = change_line[1:]
                    if prefix == " ":
                        old_lines.append(content)
                        new_lines.append(content)
                    elif prefix == "-":
                        old_lines.append(content)
                    elif prefix == "+":
                        new_lines.append(content)
                    else:
                        raise ApplyPatchError(f"invalid patch line: {change_line}")
                    index += 1
                if old_lines or new_lines or change_context is not None or is_end_of_file:
                    chunks.append(
                        UpdateChunk(
                            change_context=change_context,
                            old_lines=old_lines,
                            new_lines=new_lines,
                            is_end_of_file=is_end_of_file,
                        )
                    )
                else:
                    break
            hunks.append(ParsedHunk(kind="update", path=path, move_path=move_path, chunks=chunks))
            continue

        raise ApplyPatchError(f"invalid patch header: {lines[index]}")
    return hunks


def parse_structured_request(patch_text: str) -> StructuredPatchRequest | None:
    return apply_patch_structured_runtime.parse_structured_request(
        patch_text,
        begin_patch_marker=BEGIN_PATCH_MARKER,
        normalize_patch_text_fn=normalize_patch_text,
    )


def resolve_workspace_path(workspace_root: Path, raw_path: str) -> Path:
    candidate = Path(str(raw_path or "").strip())
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ApplyPatchError(f"path escapes workspace root: {raw_path}") from exc
    return resolved


def load_lines(path: Path) -> tuple[list[str], bool]:
    text = path.read_text(encoding="utf-8")
    return text.splitlines(), text.endswith("\n")


def write_lines(path: Path, lines: list[str], *, trailing_newline: bool) -> None:
    text = "\n".join(lines)
    if trailing_newline and (lines or text):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_line(lines: list[str], target: str, start: int) -> int:
    for index in range(max(0, start), len(lines)):
        if lines[index] == target:
            return index
    raise ApplyPatchError(f"failed to locate context line: {target}")


def find_sequence(lines: list[str], target: list[str], start: int) -> int:
    if not target:
        return max(0, start)
    end = len(lines) - len(target) + 1
    for index in range(max(0, start), max(0, end)):
        if lines[index : index + len(target)] == target:
            return index
    raise ApplyPatchError("failed to locate patch hunk in target file")


def apply_update_chunks(original_lines: list[str], chunks: list[UpdateChunk]) -> list[str]:
    lines = list(original_lines)
    search_start = 0
    for chunk in chunks:
        if chunk.change_context is not None:
            context_index = find_line(lines, chunk.change_context, search_start)
            search_start = context_index + 1
        if chunk.is_end_of_file:
            if chunk.old_lines:
                start = len(lines) - len(chunk.old_lines)
                if start < search_start or lines[start : start + len(chunk.old_lines)] != chunk.old_lines:
                    raise ApplyPatchError("failed to match end-of-file patch hunk")
            else:
                start = len(lines)
        else:
            start = find_sequence(lines, chunk.old_lines, search_start)
        end = start + len(chunk.old_lines)
        lines[start:end] = chunk.new_lines
        search_start = start + len(chunk.new_lines)
    return lines


def _preview_structured_request(request: StructuredPatchRequest, *, workspace_root: Path) -> dict[str, Any]:
    return apply_patch_structured_runtime.preview_structured_request(
        request,
        workspace_root=workspace_root,
        resolve_workspace_path_fn=resolve_workspace_path,
    )


def _execute_structured_request(request: StructuredPatchRequest, *, workspace_root: Path) -> dict[str, Any]:
    return apply_patch_structured_runtime.execute_structured_request(
        request,
        workspace_root=workspace_root,
        resolve_workspace_path_fn=resolve_workspace_path,
    )


def summarize_preview(*, patch_text: str, workspace_root: Path) -> dict[str, Any]:
    root = workspace_root.resolve()
    structured_request = parse_structured_request(patch_text)
    if structured_request is not None:
        return _preview_structured_request(structured_request, workspace_root=root)
    hunks = parse_patch_text(patch_text)
    changes: list[dict[str, Any]] = []
    added = 0
    deleted = 0
    updated = 0
    moved = 0
    for hunk in hunks:
        path = resolve_workspace_path(root, hunk.path)
        rel_path = str(path.relative_to(root))
        if hunk.kind == "add":
            if path.exists():
                raise ApplyPatchError(f"cannot add existing file: {hunk.path}")
            added += 1
            changes.append({"path": rel_path, "change_type": "add"})
            continue
        if hunk.kind == "delete":
            if not path.exists():
                raise ApplyPatchError(f"cannot delete missing file: {hunk.path}")
            deleted += 1
            changes.append({"path": rel_path, "change_type": "delete"})
            continue
        if not path.exists():
            raise ApplyPatchError(f"cannot update missing file: {hunk.path}")
        target_path = resolve_workspace_path(root, hunk.move_path) if hunk.move_path else path
        rel_target_path = str(target_path.relative_to(root))
        if target_path != path:
            moved += 1
        updated += 1
        changes.append(
            {
                "path": rel_target_path,
                "change_type": "update",
                "moved_from": rel_path if target_path != path else None,
            }
        )
    return {
        "workspace_root": str(root),
        "request_kind": "raw_patch",
        "file_count": len(changes),
        "added_count": added,
        "deleted_count": deleted,
        "updated_count": updated,
        "moved_count": moved,
        "changes": changes,
    }


def execute_patch(*, patch_text: str, workspace_root: Path) -> dict[str, Any]:
    root = workspace_root.resolve()
    structured_request = parse_structured_request(patch_text)
    if structured_request is not None:
        return _execute_structured_request(structured_request, workspace_root=root)
    hunks = parse_patch_text(patch_text)
    changes: list[dict[str, Any]] = []
    added = 0
    deleted = 0
    updated = 0
    moved = 0
    for hunk in hunks:
        path = resolve_workspace_path(root, hunk.path)
        if hunk.kind == "add":
            if path.exists():
                raise ApplyPatchError(f"cannot add existing file: {hunk.path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(hunk.content, encoding="utf-8")
            added += 1
            changes.append({"path": str(path), "change_type": "add"})
            continue
        if hunk.kind == "delete":
            if not path.exists():
                raise ApplyPatchError(f"cannot delete missing file: {hunk.path}")
            path.unlink()
            deleted += 1
            changes.append({"path": str(path), "change_type": "delete"})
            continue
        if not path.exists():
            raise ApplyPatchError(f"cannot update missing file: {hunk.path}")
        original_lines, had_trailing_newline = load_lines(path)
        new_lines = apply_update_chunks(original_lines, hunk.chunks or [])
        target_path = resolve_workspace_path(root, hunk.move_path) if hunk.move_path else path
        write_lines(target_path, new_lines, trailing_newline=had_trailing_newline or bool(new_lines))
        if target_path != path:
            path.unlink()
            moved += 1
        updated += 1
        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=str(path),
                tofile=str(target_path),
                lineterm="",
            )
        )
        changes.append(
            {
                "path": str(target_path),
                "change_type": "update",
                "moved_from": str(path) if target_path != path else None,
                "diff": "\n".join(diff_lines[:200]),
            }
        )
    return {
        "ok": True,
        "workspace_root": str(root),
        "request_kind": "raw_patch",
        "file_count": len(changes),
        "added_count": added,
        "deleted_count": deleted,
        "updated_count": updated,
        "moved_count": moved,
        "changes": changes,
    }
