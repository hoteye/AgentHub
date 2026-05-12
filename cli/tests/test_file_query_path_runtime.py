"""Path contract tests for resolve_workspace_path."""
from __future__ import annotations

from pathlib import Path

import pytest

from cli.agent_cli.tools_core.file_query_path_runtime import resolve_workspace_path


class _ToolError(Exception):
    pass


_WS = Path("/fake/project/repo/cli")
_PROJECT_ROOT = Path("/fake/project/repo")


def _resolve(raw_path):
    return resolve_workspace_path(_WS, raw_path, file_tool_error_cls=_ToolError)


def _resolve_with_project_root(raw_path):
    return resolve_workspace_path(
        _PROJECT_ROOT,
        raw_path,
        default_root=_WS,
        file_tool_error_cls=_ToolError,
    )


def test_empty_path_returns_workspace_root() -> None:
    assert _resolve("") == _WS
    assert _resolve(None) == _WS


def test_workspace_root_itself_returns_workspace_root() -> None:
    assert _resolve(str(_WS)) == _WS


def test_parent_of_workspace_root_raises() -> None:
    with pytest.raises(_ToolError, match="path escapes workspace root"):
        _resolve("/fake/project/repo")


def test_grandparent_raises() -> None:
    with pytest.raises(_ToolError, match="path escapes workspace root"):
        _resolve("/fake/project")


def test_subdir_within_workspace_allowed() -> None:
    result = _resolve("agent_cli")
    assert result == _WS / "agent_cli"


def test_absolute_subdir_within_workspace_allowed() -> None:
    result = _resolve(str(_WS / "agent_cli"))
    assert result == _WS / "agent_cli"


def test_unrelated_absolute_path_raises() -> None:
    with pytest.raises(_ToolError, match="path escapes workspace root"):
        _resolve("/tmp/other")


def test_sibling_directory_raises() -> None:
    with pytest.raises(_ToolError, match="path escapes workspace root"):
        _resolve("/fake/project/repo/other_sibling")


def test_empty_path_returns_default_root_when_provided() -> None:
    assert _resolve_with_project_root("") == _WS
    assert _resolve_with_project_root(None) == _WS


def test_project_root_itself_allowed_when_default_root_is_nested() -> None:
    assert _resolve_with_project_root(str(_PROJECT_ROOT)) == _PROJECT_ROOT


def test_relative_paths_still_resolve_from_default_root_when_boundary_is_project_root() -> None:
    assert _resolve_with_project_root("agent_cli") == _WS / "agent_cli"
