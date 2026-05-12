from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "changed_files_test_gate.py"
SPEC = importlib.util.spec_from_file_location("changed_files_test_gate_diff_base", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_diff_base_prefers_merge_base_when_base_ref_available() -> None:
    fetch_calls: list[tuple[list[str], bool]] = []

    def _fake_subprocess_run(argv, check=False, **kwargs):
        del kwargs
        fetch_calls.append((list(argv), bool(check)))
        return SimpleNamespace(returncode=0)

    with patch("subprocess.run", side_effect=_fake_subprocess_run), patch.object(
        MODULE, "run_git", return_value="sha_merge_base"
    ) as run_git_mock:
        base = MODULE.diff_base("main")

    assert base == "sha_merge_base"
    assert fetch_calls == [(["git", "fetch", "--no-tags", "origin", "main"], False)]
    run_git_mock.assert_called_once_with(["merge-base", "HEAD", "origin/main"])


def test_diff_base_falls_back_to_head_parent_when_merge_base_fails() -> None:
    with patch("subprocess.run", return_value=SimpleNamespace(returncode=0)), patch.object(
        MODULE,
        "run_git",
        side_effect=[
            subprocess.CalledProcessError(1, ["git", "merge-base"]),
            "sha_head_parent",
        ],
    ) as run_git_mock:
        base = MODULE.diff_base("release/2026-04")

    assert base == "sha_head_parent"
    assert run_git_mock.call_args_list[0].args[0] == ["merge-base", "HEAD", "origin/release/2026-04"]
    assert run_git_mock.call_args_list[1].args[0] == ["rev-parse", "HEAD~1"]


def test_diff_base_falls_back_to_head_when_head_parent_missing() -> None:
    with patch.object(
        MODULE,
        "run_git",
        side_effect=[
            subprocess.CalledProcessError(1, ["git", "rev-parse", "HEAD~1"]),
            "sha_head",
        ],
    ) as run_git_mock:
        base = MODULE.diff_base("")

    assert base == "sha_head"
    assert run_git_mock.call_args_list[0].args[0] == ["rev-parse", "HEAD~1"]
    assert run_git_mock.call_args_list[1].args[0] == ["rev-parse", "HEAD"]


def test_changed_files_uses_diff_base_and_strips_empty_lines() -> None:
    with patch.object(MODULE, "diff_base", return_value="sha_base"), patch.object(
        MODULE,
        "run_git",
        return_value="\ncli/agent_cli/runtime.py\n\ncli/agent_cli/ui/panel.py\n",
    ) as run_git_mock:
        files = MODULE.changed_files("main")

    assert files == ["cli/agent_cli/runtime.py", "cli/agent_cli/ui/panel.py"]
    run_git_mock.assert_called_once_with(["diff", "--name-only", "sha_base...HEAD"])
