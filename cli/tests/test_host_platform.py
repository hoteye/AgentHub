from __future__ import annotations

import sys
import unittest

from cli.agent_cli.host_platform import detect_host_platform

class HostPlatformTest(unittest.TestCase):
    def test_detect_windows_platform(self) -> None:
        platform = detect_host_platform(system_name="Windows", sys_platform="win32")

        self.assertEqual(platform.family, "windows")
        self.assertEqual(platform.os, "windows")
        self.assertEqual(platform.list_dir_command, "Get-ChildItem -Force")
        self.assertEqual(platform.print_working_dir_command, "Get-Location")

    def test_detect_linux_platform(self) -> None:
        platform = detect_host_platform(system_name="Linux", sys_platform="linux")

        self.assertEqual(platform.family, "unix")
        self.assertEqual(platform.os, "linux")
        self.assertEqual(platform.list_dir_command, "ls -la")
        self.assertEqual(platform.print_working_dir_command, "pwd")

    def test_detect_macos_platform(self) -> None:
        platform = detect_host_platform(system_name="Darwin", sys_platform="darwin")

        self.assertEqual(platform.family, "unix")
        self.assertEqual(platform.os, "macos")
        self.assertEqual(platform.python_version_command, "python3 -V")

    def test_windows_normalizes_unix_commands(self) -> None:
        platform = detect_host_platform(system_name="Windows", sys_platform="win32")

        self.assertEqual(platform.normalize_shell_command("ls -la"), "Get-ChildItem -Force")
        self.assertEqual(platform.normalize_shell_command("pwd"), "Get-Location")
        self.assertEqual(
            platform.shell_exec_args("ls -la"),
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-ChildItem -Force",
            ],
        )

    def test_linux_normalizes_windows_commands(self) -> None:
        platform = detect_host_platform(system_name="Linux", sys_platform="linux")

        self.assertEqual(platform.normalize_shell_command("Get-ChildItem -Force"), "ls -la")
        self.assertEqual(platform.normalize_shell_command("Get-Location"), "pwd")
        self.assertEqual(
            platform.shell_exec_args("Get-Location"),
            [platform.resolve_shell_program(), "-lc", "pwd"],
        )

    def test_linux_preserves_literal_printf_whitespace_sequences(self) -> None:
        platform = detect_host_platform(system_name="Linux", sys_platform="linux")

        command = "find . -mindepth 1 -maxdepth 1 -printf '%f\\t%y\\n' | sort"

        self.assertEqual(platform.normalize_shell_command(command), command)

    def test_linux_preserves_embedded_newlines_and_tabs_in_shell_command(self) -> None:
        platform = detect_host_platform(system_name="Linux", sys_platform="linux")

        command = "printf 'a\\tb\\n'"

        self.assertEqual(platform.normalize_shell_command(command), command)
