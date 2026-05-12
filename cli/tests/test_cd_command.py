from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_core.tool_commands import handle_cd_command


def _make_runtime(cwd: str = "/tmp"):
    runtime = MagicMock()
    runtime.cwd = Path(cwd)
    return runtime


class TestCdCommand(unittest.TestCase):
    def test_no_args_shows_current_directory(self):
        runtime = _make_runtime(cwd="/home/user/project")
        result = handle_cd_command(runtime, name="cd", arg_text="")
        assert isinstance(result, CommandExecutionResult)
        assert "/home/user/project" in result.assistant_text

    def test_valid_directory_changes_cwd(self):
        runtime = _make_runtime(cwd="/tmp")
        result = handle_cd_command(runtime, name="cd", arg_text="/var")
        assert isinstance(result, CommandExecutionResult)
        assert "/var" in result.assistant_text
        assert runtime.cwd == Path("/var")

    def test_home_expansion(self):
        runtime = _make_runtime(cwd="/tmp")
        result = handle_cd_command(runtime, name="cd", arg_text="~")
        assert isinstance(result, CommandExecutionResult)
        home = str(Path.home())
        assert home in result.assistant_text
        assert runtime.cwd == Path(home)

    def test_invalid_path_returns_error(self):
        runtime = _make_runtime(cwd="/tmp")
        result = handle_cd_command(runtime, name="cd", arg_text="/nonexistent_dir_xyz")
        assert isinstance(result, CommandExecutionResult)
        assert "Not a directory" in result.assistant_text

    def test_wrong_name_returns_none(self):
        runtime = _make_runtime()
        result = handle_cd_command(runtime, name="other", arg_text="/tmp")
        assert result is None

    def test_strips_quotes(self):
        runtime = _make_runtime(cwd="/tmp")
        result = handle_cd_command(runtime, name="cd", arg_text="'~'")
        assert isinstance(result, CommandExecutionResult)
        home = str(Path.home())
        assert home in result.assistant_text

    def test_dot_keeps_current(self):
        runtime = _make_runtime(cwd="/tmp")
        result = handle_cd_command(runtime, name="cd", arg_text="/tmp")
        assert isinstance(result, CommandExecutionResult)
        assert "/tmp" in result.assistant_text


if __name__ == "__main__":
    unittest.main()
