from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli.scripts.apply_patch_wave01_acceptance_model_helpers import (
    CaseSpec,
    _case_report,
    _registry,
    _step_report,
)


def _case_raw_multi_file_patch(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("hello\n", encoding="utf-8")
    registry = _registry(workspace)
    patch_text = """*** Begin Patch
*** Add File: notes.txt
+first line
*** Update File: demo.txt
@@
-hello
+hello world
*** End Patch"""
    result = registry.apply_patch_result(patch_text)
    return _case_report(
        case=DEFAULT_CASES_BY_ID["raw_multi_file_patch"],
        workspace_root=workspace,
        steps=[_step_report("apply_patch", result)],
        expected_ok=True,
        expected_files={
            "demo.txt": "hello world",
            "notes.txt": "first line",
        },
    )


def _case_raw_forced_create(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    registry = _registry(workspace)
    patch_text = """*** Begin Patch
*** Add File: created_via_patch.txt
+created directly by apply_patch
*** End Patch"""
    result = registry.apply_patch_result(patch_text)
    return _case_report(
        case=DEFAULT_CASES_BY_ID["raw_forced_create"],
        workspace_root=workspace,
        steps=[_step_report("apply_patch", result)],
        expected_ok=True,
        expected_files={
            "created_via_patch.txt": "created directly by apply_patch",
        },
    )


def _case_path_traversal_rejection(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    registry = _registry(workspace)
    patch_text = """*** Begin Patch
*** Add File: ../escape.txt
+oops
*** End Patch"""
    result = registry.apply_patch_result(patch_text)
    return _case_report(
        case=DEFAULT_CASES_BY_ID["path_traversal_rejection"],
        workspace_root=workspace,
        steps=[_step_report("apply_patch", result)],
        expected_ok=False,
        expected_error_substring="path escapes workspace root",
        absent_files=("../escape.txt",),
    )


def _case_verification_failure_no_side_effects(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("before\n", encoding="utf-8")
    registry = _registry(workspace)
    patch_text = """*** Begin Patch
*** Update File: demo.txt
@@
-missing
+after
*** End Patch"""
    result = registry.apply_patch_result(patch_text)
    return _case_report(
        case=DEFAULT_CASES_BY_ID["verification_failure_no_side_effects"],
        workspace_root=workspace,
        steps=[_step_report("apply_patch", result)],
        expected_ok=False,
        expected_error_substring="failed to locate patch hunk in target file",
        expected_files={"demo.txt": "before"},
    )


def _write_payload(file_path: str, content: str) -> str:
    return json.dumps(
        {
            "operation": "file_write",
            "file_path": file_path,
            "content": content,
            "source_tool_name": "Write",
            "guard_profile": "claude_write",
        }
    )


def _edit_payload(file_path: str, old_string: str, new_string: str, *, replace_all: bool = False) -> str:
    payload: dict[str, Any] = {
        "operation": "file_edit",
        "file_path": file_path,
        "old_string": old_string,
        "new_string": new_string,
        "source_tool_name": "Edit",
        "guard_profile": "claude_edit",
    }
    if replace_all:
        payload["replace_all"] = True
    return json.dumps(payload)


def _case_write_create(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    registry = _registry(workspace)
    result = registry.apply_patch_result(_write_payload("src/new_file.txt", "created\n"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["write_create"],
        workspace_root=workspace,
        steps=[_step_report("Write", result)],
        expected_ok=True,
        expected_files={"src/new_file.txt": "created"},
    )


def _case_write_requires_read_before_overwrite(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("before\n", encoding="utf-8")
    registry = _registry(workspace)
    result = registry.apply_patch_result(_write_payload("demo.txt", "after\n"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["write_requires_read_before_overwrite"],
        workspace_root=workspace,
        steps=[_step_report("Write", result)],
        expected_ok=False,
        expected_error_substring="reading the current file first",
        expected_files={"demo.txt": "before"},
    )


def _case_write_overwrite_after_read(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("before\n", encoding="utf-8")
    registry = _registry(workspace)
    read_result = registry.read_file_result(str((workspace / "demo.txt").resolve()), offset=1, limit=50)
    write_result = registry.apply_patch_result(_write_payload("demo.txt", "after\n"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["write_overwrite_after_read"],
        workspace_root=workspace,
        steps=[
            _step_report("read_file", read_result),
            _step_report("Write", write_result),
        ],
        expected_ok=True,
        expected_files={"demo.txt": "after"},
    )


def _case_write_stale_rejection_after_read(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "demo.txt"
    target.write_text("before\n", encoding="utf-8")
    registry = _registry(workspace)
    read_result = registry.read_file_result(str(target.resolve()), offset=1, limit=50)
    target.write_text("external change\n", encoding="utf-8")
    write_result = registry.apply_patch_result(_write_payload("demo.txt", "after\n"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["write_stale_rejection_after_read"],
        workspace_root=workspace,
        steps=[
            _step_report("read_file", read_result),
            _step_report("Write", write_result),
        ],
        expected_ok=False,
        expected_error_substring="changed since it was read",
        expected_files={"demo.txt": "external change"},
    )


def _case_edit_requires_read_before_edit(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("Status: TODO\n", encoding="utf-8")
    registry = _registry(workspace)
    result = registry.apply_patch_result(_edit_payload("demo.txt", "TODO", "DONE"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["edit_requires_read_before_edit"],
        workspace_root=workspace,
        steps=[_step_report("Edit", result)],
        expected_ok=False,
        expected_error_substring="reading the current file first",
        expected_files={"demo.txt": "Status: TODO"},
    )


def _case_edit_unique_after_read(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("Status: TODO\n", encoding="utf-8")
    registry = _registry(workspace)
    read_result = registry.read_file_result(str((workspace / "demo.txt").resolve()), offset=1, limit=50)
    edit_result = registry.apply_patch_result(_edit_payload("demo.txt", "TODO", "DONE"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["edit_unique_after_read"],
        workspace_root=workspace,
        steps=[
            _step_report("read_file", read_result),
            _step_report("Edit", edit_result),
        ],
        expected_ok=True,
        expected_files={"demo.txt": "Status: DONE"},
    )


def _case_edit_replace_all_after_read(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "demo.txt").write_text("TODO\nTODO\n", encoding="utf-8")
    registry = _registry(workspace)
    read_result = registry.read_file_result(str((workspace / "demo.txt").resolve()), offset=1, limit=50)
    edit_result = registry.apply_patch_result(_edit_payload("demo.txt", "TODO", "DONE", replace_all=True))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["edit_replace_all_after_read"],
        workspace_root=workspace,
        steps=[
            _step_report("read_file", read_result),
            _step_report("Edit", edit_result),
        ],
        expected_ok=True,
        expected_files={"demo.txt": "DONE\nDONE"},
    )


def _case_edit_stale_rejection_after_read(case_root: Path) -> dict[str, Any]:
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "demo.txt"
    target.write_text("Status: TODO\n", encoding="utf-8")
    registry = _registry(workspace)
    read_result = registry.read_file_result(str(target.resolve()), offset=1, limit=50)
    target.write_text("Status: external\n", encoding="utf-8")
    edit_result = registry.apply_patch_result(_edit_payload("demo.txt", "TODO", "DONE"))
    return _case_report(
        case=DEFAULT_CASES_BY_ID["edit_stale_rejection_after_read"],
        workspace_root=workspace,
        steps=[
            _step_report("read_file", read_result),
            _step_report("Edit", edit_result),
        ],
        expected_ok=False,
        expected_error_substring="changed since it was read",
        expected_files={"demo.txt": "Status: external"},
    )


DEFAULT_CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="raw_multi_file_patch",
        family="raw_apply_patch",
        description="Codex-style raw patch keeps multi-file add+update semantics and item-event identity.",
        execute=_case_raw_multi_file_patch,
    ),
    CaseSpec(
        case_id="raw_forced_create",
        family="raw_apply_patch",
        description="Direct apply_patch file creation remains in the patch family instead of projecting to Write.",
        execute=_case_raw_forced_create,
    ),
    CaseSpec(
        case_id="path_traversal_rejection",
        family="raw_apply_patch",
        description="Path traversal attempts are rejected without writing outside the workspace.",
        execute=_case_path_traversal_rejection,
    ),
    CaseSpec(
        case_id="verification_failure_no_side_effects",
        family="raw_apply_patch",
        description="Verification/application failure leaves existing files unchanged.",
        execute=_case_verification_failure_no_side_effects,
    ),
    CaseSpec(
        case_id="write_create",
        family="claude_write",
        description="Claude-style Write can create a new file without a prior read.",
        execute=_case_write_create,
    ),
    CaseSpec(
        case_id="write_requires_read_before_overwrite",
        family="claude_write",
        description="Claude-style Write rejects overwriting an existing file before it is read.",
        execute=_case_write_requires_read_before_overwrite,
    ),
    CaseSpec(
        case_id="write_overwrite_after_read",
        family="claude_write",
        description="Claude-style Write succeeds after an explicit read of the target file.",
        execute=_case_write_overwrite_after_read,
    ),
    CaseSpec(
        case_id="write_stale_rejection_after_read",
        family="claude_write",
        description="Claude-style Write rejects stale overwrites after the file changes externally.",
        execute=_case_write_stale_rejection_after_read,
    ),
    CaseSpec(
        case_id="edit_requires_read_before_edit",
        family="claude_edit",
        description="Claude-style Edit rejects modifying an unread file.",
        execute=_case_edit_requires_read_before_edit,
    ),
    CaseSpec(
        case_id="edit_unique_after_read",
        family="claude_edit",
        description="Claude-style Edit preserves exact replacement after a read.",
        execute=_case_edit_unique_after_read,
    ),
    CaseSpec(
        case_id="edit_replace_all_after_read",
        family="claude_edit",
        description="Claude-style Edit preserves replace_all semantics after a read.",
        execute=_case_edit_replace_all_after_read,
    ),
    CaseSpec(
        case_id="edit_stale_rejection_after_read",
        family="claude_edit",
        description="Claude-style Edit rejects stale edits after the file changes externally.",
        execute=_case_edit_stale_rejection_after_read,
    ),
)
DEFAULT_CASES_BY_ID = {case.case_id: case for case in DEFAULT_CASES}
