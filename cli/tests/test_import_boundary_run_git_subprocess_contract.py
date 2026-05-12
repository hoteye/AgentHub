from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from cli.scripts import import_boundary_guard


def test_run_git_invokes_subprocess_with_check_capture_and_text(monkeypatch) -> None:
    run_mock = Mock(return_value=SimpleNamespace(stdout="sha123\n"))
    monkeypatch.setattr(import_boundary_guard.subprocess, "run", run_mock)

    result = import_boundary_guard.run_git(["rev-parse", "HEAD"])

    assert result == "sha123"
    run_mock.assert_called_once_with(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
