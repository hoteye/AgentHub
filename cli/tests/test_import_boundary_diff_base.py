from __future__ import annotations

import subprocess
from unittest.mock import Mock

from cli.scripts import import_boundary_guard


def test_diff_base_prefers_merge_base_when_base_ref_is_available(monkeypatch) -> None:
    fetch_mock = Mock()
    monkeypatch.setattr(import_boundary_guard.subprocess, "run", fetch_mock)
    monkeypatch.setattr(import_boundary_guard, "run_git", lambda args: "sha_merge" if args[:1] == ["merge-base"] else "sha_unused")

    result = import_boundary_guard.diff_base("main")

    assert result == "sha_merge"
    fetch_mock.assert_called_once_with(["git", "fetch", "--no-tags", "origin", "main"], check=False)


def test_diff_base_falls_back_to_head_prev_when_merge_base_fails(monkeypatch) -> None:
    fetch_mock = Mock()
    monkeypatch.setattr(import_boundary_guard.subprocess, "run", fetch_mock)

    def _run_git(args: list[str]) -> str:
        if args[:1] == ["merge-base"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=["git", *args])
        if args == ["rev-parse", "HEAD~1"]:
            return "sha_prev"
        return "sha_head"

    monkeypatch.setattr(import_boundary_guard, "run_git", _run_git)

    result = import_boundary_guard.diff_base("main")

    assert result == "sha_prev"
    fetch_mock.assert_called_once_with(["git", "fetch", "--no-tags", "origin", "main"], check=False)


def test_diff_base_falls_back_to_head_when_head_prev_is_unavailable(monkeypatch) -> None:
    fetch_mock = Mock()
    monkeypatch.setattr(import_boundary_guard.subprocess, "run", fetch_mock)

    def _run_git(args: list[str]) -> str:
        if args == ["rev-parse", "HEAD~1"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=["git", *args])
        if args == ["rev-parse", "HEAD"]:
            return "sha_head"
        return "sha_unused"

    monkeypatch.setattr(import_boundary_guard, "run_git", _run_git)

    result = import_boundary_guard.diff_base("")

    assert result == "sha_head"
    fetch_mock.assert_not_called()
