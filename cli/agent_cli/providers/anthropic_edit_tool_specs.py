from __future__ import annotations

import json
from typing import Any, Callable, Dict


_PATCH_OPERATION_VALUES = ("patch", "file_write", "file_edit")
_WRITE_OPERATION_ALIASES = frozenset({"file_write", "write_file", "write"})
_EDIT_OPERATION_ALIASES = frozenset({"file_edit", "edit_file", "edit"})
_PATCH_OPERATION_ALIASES = frozenset({"patch", "apply_patch"})


def structured_apply_patch_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
) -> Dict[str, Any]:
    description = str(provider_description("apply_patch") or "").strip()
    if description:
        description = f"{description} Prefer structured operation=file_write/file_edit over raw patch text."
    else:
        description = "Apply workspace changes. Prefer structured operation=file_write/file_edit over raw patch text."
    spec = function_tool(
        name="apply_patch",
        description=description,
        properties={
            "patch": {
                "type": "string",
                "description": "Legacy raw patch text using *** Begin Patch / *** End Patch grammar.",
            },
            "operation": {
                "type": "string",
                "enum": list(_PATCH_OPERATION_VALUES),
                "description": "Preferred structured mode. Use file_write/file_edit instead of raw patch.",
            },
            "file_path": {
                "type": "string",
                "description": "Workspace-relative target path for operation=file_write or operation=file_edit.",
            },
            "content": {
                "type": "string",
                "description": "Full file content for operation=file_write.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to replace for operation=file_edit.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text for operation=file_edit.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Optional hint for operation=file_edit. Default false.",
            },
        },
    )
    # Anthropic accepts the same field set, but this provider rejects the
    # stronger combinator form (`anyOf` / `minProperties`) with a 400
    # "Improperly formed request". Keep the schema flat here and rely on the
    # existing apply_patch runtime parser for request-shape validation.
    return spec


def structured_write_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
) -> Dict[str, Any]:
    description = str(provider_description("apply_patch") or "").strip()
    if description:
        description = f"{description} Create or overwrite a file by providing the full file content."
    else:
        description = "Create or overwrite a workspace file by providing the full file content."
    return function_tool(
        name="Write",
        description=description,
        properties={
            "file_path": {
                "type": "string",
                "description": "Workspace-relative target path to create or overwrite.",
            },
            "content": {
                "type": "string",
                "description": "Full file content to write.",
            },
        },
        required=["file_path", "content"],
    )


def structured_edit_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
) -> Dict[str, Any]:
    description = str(provider_description("apply_patch") or "").strip()
    if description:
        description = f"{description} Edit an existing file by replacing an exact string."
    else:
        description = "Edit an existing workspace file by replacing an exact string."
    return function_tool(
        name="Edit",
        description=description,
        properties={
            "file_path": {
                "type": "string",
                "description": "Workspace-relative target path to edit.",
            },
            "old_string": {
                "type": "string",
                "description": (
                    "Exact text to replace. It should usually be the smallest unique span "
                    "and must match exactly once unless replace_all=true."
                ),
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Optional hint. Set true only when every occurrence should be replaced.",
            },
        },
        required=["file_path", "old_string", "new_string"],
    )


def structured_edit_tool_call_command(
    *,
    name: str,
    arguments: Dict[str, Any],
    quote_arg_fn: Callable[[Any], str],
) -> str | None:
    normalized_name = str(name or "").strip().lower()
    patch_value = _first_present(arguments, "patch", "input")
    if patch_value is not None:
        patch_text = str(patch_value).strip()
        if patch_text:
            return f"/apply_patch {quote_arg_fn(patch_text)}"

    operation = _normalize_operation(str(_first_present(arguments, "operation", "mode", "action") or "").strip())
    inferred_operation = _infer_operation(arguments)
    if not operation or (operation in _PATCH_OPERATION_ALIASES and inferred_operation):
        operation = inferred_operation
    if operation in _WRITE_OPERATION_ALIASES:
        return _build_write_command(arguments, quote_arg_fn=quote_arg_fn)
    if operation in _EDIT_OPERATION_ALIASES:
        return _build_edit_command(arguments, quote_arg_fn=quote_arg_fn)
    if normalized_name in {"file_write", "write"}:
        return _build_write_command(arguments, quote_arg_fn=quote_arg_fn)
    if normalized_name in {"file_edit", "edit"}:
        return _build_edit_command(arguments, quote_arg_fn=quote_arg_fn)
    if operation in _PATCH_OPERATION_ALIASES:
        return None
    return None


def _first_present(arguments: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in arguments and arguments.get(key) is not None:
            return arguments.get(key)
    return None


def _normalize_operation(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized in _WRITE_OPERATION_ALIASES:
        return "file_write"
    if normalized in _EDIT_OPERATION_ALIASES:
        return "file_edit"
    if normalized in _PATCH_OPERATION_ALIASES:
        return "patch"
    return ""


def _infer_operation(arguments: Dict[str, Any]) -> str:
    has_path = bool(_normalize_patch_path(str(_first_present(arguments, "file_path", "path") or "")))
    has_content = _first_present(arguments, "content") is not None
    has_old = _first_present(arguments, "old_string", "old", "target", "old_text") is not None
    has_new = _first_present(arguments, "new_string", "new", "replacement", "new_text") is not None
    if has_path and has_content and not has_old and not has_new:
        return "file_write"
    if has_path and has_old and has_new:
        return "file_edit"
    return ""


def _normalize_patch_path(raw_path: str) -> str:
    path = str(raw_path or "").strip()
    if not path:
        return ""
    if "\n" in path or "\r" in path:
        return ""
    if path.startswith("***"):
        return ""
    return path


def _apply_patch_command(payload: Dict[str, Any], *, quote_arg_fn: Callable[[Any], str]) -> str:
    normalized_payload = {
        key: value
        for key, value in dict(payload or {}).items()
        if value is not None
    }
    return f"/apply_patch {quote_arg_fn(json.dumps(normalized_payload, ensure_ascii=True, sort_keys=True))}"


def _build_write_command(arguments: Dict[str, Any], *, quote_arg_fn: Callable[[Any], str]) -> str | None:
    file_path = _normalize_patch_path(str(_first_present(arguments, "file_path", "path") or ""))
    content_value = _first_present(arguments, "content")
    if not file_path or content_value is None:
        return None
    source_tool_name = "Write" if str(arguments.get("__projected_tool_name") or "").strip() == "Write" else None
    payload: Dict[str, Any] = {
        "operation": "file_write",
        "file_path": file_path,
        "content": str(content_value),
    }
    if source_tool_name == "Write":
        payload["source_tool_name"] = "Write"
        payload["guard_profile"] = "claude_write"
    return _apply_patch_command(payload, quote_arg_fn=quote_arg_fn)


def _build_edit_command(arguments: Dict[str, Any], *, quote_arg_fn: Callable[[Any], str]) -> str | None:
    file_path = _normalize_patch_path(str(_first_present(arguments, "file_path", "path") or ""))
    old_value = _first_present(arguments, "old_string", "old", "target", "old_text")
    new_value = _first_present(arguments, "new_string", "new", "replacement", "new_text")
    if not file_path or old_value is None or new_value is None:
        return None
    source_tool_name = "Edit" if str(arguments.get("__projected_tool_name") or "").strip() == "Edit" else None
    payload: Dict[str, Any] = {
        "operation": "file_edit",
        "file_path": file_path,
        "old_string": str(old_value),
        "new_string": str(new_value),
    }
    if "replace_all" in arguments and arguments.get("replace_all") is not None:
        payload["replace_all"] = bool(arguments.get("replace_all"))
    if source_tool_name == "Edit":
        payload["source_tool_name"] = "Edit"
        payload["guard_profile"] = "claude_edit"
    return _apply_patch_command(payload, quote_arg_fn=quote_arg_fn)
