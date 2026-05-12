from __future__ import annotations

import os
import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.chat_completions_planner import ChatCompletionsPlanner
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_planner import OpenAIPlanner
from cli.agent_cli.providers.tool_calls import command_for_tool_call
from cli.agent_cli.tools_core.shell_bridge import _shell_exec_args

def _build_config() -> ProviderConfig:
    return ProviderConfig(model="gpt-5.4", api_key="test")

def _build_openai_planner(host_platform):
    with patch("cli.agent_cli.providers.openai_planner.build_openai_client", return_value=MagicMock()):
        return OpenAIPlanner(_build_config(), host_platform=host_platform, plugin_manager_factory=lambda: None)

def _build_chat_planner(host_platform):
    with patch("cli.agent_cli.providers.chat_completions_planner.build_openai_client", return_value=MagicMock()):
        return ChatCompletionsPlanner(_build_config(), host_platform=host_platform, plugin_manager_factory=lambda: None)

def test_detect_host_platform_regression_matrix() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    macos = detect_host_platform(system_name="Darwin", sys_platform="darwin")
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")

    assert (linux.family, linux.os, linux.shell_program) == ("unix", "linux", "/bin/sh")
    assert (macos.family, macos.os, macos.shell_program) == ("unix", "macos", "/bin/sh")
    assert (windows.family, windows.os, windows.shell_program) == ("windows", "windows", "powershell.exe")

def test_shell_exec_args_use_powershell_normalization_on_windows() -> None:
    host = detect_host_platform(system_name="Windows", sys_platform="win32")

    assert _shell_exec_args(host, "pwd", login=False, shell=None) == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Get-Location",
    ]

def test_shell_exec_args_use_cmd_compatible_commands_on_windows() -> None:
    host = detect_host_platform(system_name="Windows", sys_platform="win32")

    pwd_args = _shell_exec_args(host, "pwd", login=True, shell="cmd.exe")
    get_location_args = _shell_exec_args(host, "Get-Location", login=True, shell="cmd.exe")
    list_args = _shell_exec_args(host, "ls -la", login=True, shell="cmd.exe")

    assert Path(pwd_args[0]).name.lower() in {"cmd", "cmd.exe"}
    assert pwd_args[1:] == ["/d", "/s", "/c", "cd"]
    assert Path(get_location_args[0]).name.lower() in {"cmd", "cmd.exe"}
    assert get_location_args[1:] == ["/d", "/s", "/c", "cd"]
    assert Path(list_args[0]).name.lower() in {"cmd", "cmd.exe"}
    assert list_args[1:] == ["/d", "/s", "/c", "dir /a"]

def test_shell_exec_args_keep_posix_login_flags() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    macos = detect_host_platform(system_name="Darwin", sys_platform="darwin")

    with patch.dict(os.environ, {}, clear=True):
        assert _shell_exec_args(linux, "pwd", login=True, shell=None) == ["/bin/sh", "-lc", "pwd"]
        assert _shell_exec_args(macos, "pwd", login=False, shell=None) == ["/bin/sh", "-c", "pwd"]

def test_shell_exec_args_prefer_user_shell_when_unspecified() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    real_is_file = Path.is_file

    def fake_is_file(candidate: Path) -> bool:
        normalized = str(candidate).replace("\\", "/")
        if normalized == "/custom/bin/bash":
            return True
        return real_is_file(candidate)

    with patch.dict(os.environ, {"SHELL": "/custom/bin/bash"}, clear=True), patch(
        "cli.agent_cli.host_platform.shutil.which",
        return_value=None,
    ), patch.object(Path, "is_file", fake_is_file):
        assert linux.resolve_shell_program(None) == "/custom/bin/bash"
        assert _shell_exec_args(linux, "pwd", login=True, shell=None) == ["/custom/bin/bash", "-lc", "pwd"]

def test_shell_exec_args_normalize_reference_style_shell_resolution() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")

    assert linux.resolve_shell_program("posix") == "/bin/sh"
    assert linux.resolve_shell_program("bogus") == "/bin/sh"
    assert _shell_exec_args(linux, "pwd", login=True, shell="posix") == ["/bin/sh", "-lc", "pwd"]
    assert _shell_exec_args(linux, "pwd", login=False, shell="shell") == ["/bin/sh", "-c", "pwd"]

    resolved_powershell = windows.resolve_shell_program("powershell")
    resolved_cmd = windows.resolve_shell_program("cmd")
    assert Path(resolved_powershell).name.lower() in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
    assert Path(resolved_cmd).name.lower() in {"cmd", "cmd.exe"}
    assert windows.resolve_shell_program("posix") == "cmd.exe"
    assert windows.resolve_shell_program("bogus") == "cmd.exe"

    powershell_args = _shell_exec_args(windows, "pwd", login=False, shell="powershell")
    assert Path(powershell_args[0]).name.lower() in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
    assert powershell_args[1:] == [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Get-Location",
    ]

    cmd_args = _shell_exec_args(windows, "pwd", login=True, shell="cmd")
    assert Path(cmd_args[0]).name.lower() in {"cmd", "cmd.exe"}
    assert cmd_args[1:] == ["/d", "/s", "/c", "cd"]

def test_resolve_shell_program_matches_reference_lookup_order() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    real_is_file = Path.is_file

    def fake_is_file(candidate: Path) -> bool:
        normalized = str(candidate).replace("\\", "/")
        if normalized in {"/custom/bin/bash", "/tmp/not-a-shell"}:
            return True
        return real_is_file(candidate)

    with patch.dict(os.environ, {"SHELL": "/custom/bin/bash"}, clear=False), patch(
        "cli.agent_cli.host_platform.shutil.which",
        return_value=None,
    ), patch.object(Path, "is_file", fake_is_file):
        assert linux.resolve_shell_program("bash") == "/custom/bin/bash"
        assert linux.resolve_shell_program("/tmp/not-a-shell") == "/bin/sh"

def test_command_for_tool_call_keeps_one_layer_snapshot_platform_specific() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    macos = detect_host_platform(system_name="Darwin", sys_platform="darwin")
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")

    for unix_host in (linux, macos):
        list_command = command_for_tool_call(
            "list_dir",
            {"dir_path": ".", "limit": 50, "depth": 1},
            unix_host,
            optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
            quote_arg_fn=shlex.quote,
            plugin_manager_factory=lambda: None,
        )
        assert list_command == "/list_dir . --limit 50 --depth 1"

    windows_command = command_for_tool_call(
        "list_dir",
        {"dir_path": ".", "limit": 50, "depth": 1},
        windows,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        quote_arg_fn=shlex.quote,
        plugin_manager_factory=lambda: None,
    )
    assert windows_command == "/list_dir . --limit 50 --depth 1"

def test_planner_prompts_branch_for_windows_vs_unix() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")

    unix_openai = _build_openai_planner(linux)
    unix_chat = _build_chat_planner(linux)
    windows_openai = _build_openai_planner(windows)
    windows_chat = _build_chat_planner(windows)

    assert "prefer list_dir with depth 1 over shell directory listings" in unix_openai.system_prompt
    assert "prefer list_dir with depth 1 over shell directory listings" in unix_chat.system_prompt
    assert "prefer list_dir with depth 1 over shell directory listings" in windows_openai.system_prompt
    assert "prefer list_dir with depth 1 over shell directory listings" in windows_chat.system_prompt
    assert "prefer exec_command with a shell find command over list_dir" not in windows_openai.system_prompt
    assert "prefer exec_command with a shell find command over list_dir" not in windows_chat.system_prompt

    assert "prefer list_dir with depth 1 over shell directory listings" in unix_openai.native_tool_system_prompt
    assert "Use exec_command only when the user explicitly asks for shell metadata" in unix_openai.native_tool_system_prompt
    assert "prefer list_dir with depth 1 over shell directory listings" in windows_openai.native_tool_system_prompt
    assert "Use exec_command only when the user explicitly asks for shell metadata" in windows_openai.native_tool_system_prompt
