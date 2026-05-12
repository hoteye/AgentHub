from __future__ import annotations

from types import SimpleNamespace

from cli.scripts import import_boundary_guard


def test_run_git_strips_subprocess_stdout(monkeypatch) -> None:
    def _fake_run(argv, check, capture_output, text):
        assert argv == ["git", "rev-parse", "HEAD"]
        assert check is True
        assert capture_output is True
        assert text is True
        return SimpleNamespace(stdout="  abc123  \n")

    monkeypatch.setattr(import_boundary_guard.subprocess, "run", _fake_run)

    result = import_boundary_guard.run_git(["rev-parse", "HEAD"])

    assert result == "abc123"
