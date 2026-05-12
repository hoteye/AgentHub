from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cli.scripts import run_multiturn_coding_ab_evaluation_helpers as coding_eval


def test_multiturn_coding_ab_validation_runs_pytest_with_current_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    results = coding_eval._run_validation(tmp_path, tmp_path / "validation")

    assert calls[0] == ["python3", "task_stats.py", "sample_tasks.txt"]
    assert calls[1] == ["python3", "task_stats.py", "sample_tasks.txt", "--json"]
    assert calls[2] == [sys.executable, "-m", "pytest", "-q"]
    assert results[2]["cmd"] == ["pytest", "-q"]
    assert results[2]["effective_cmd"] == [sys.executable, "-m", "pytest", "-q"]
