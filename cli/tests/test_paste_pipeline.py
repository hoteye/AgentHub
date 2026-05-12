from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from cli.agent_cli.ui.paste_pipeline import read_clipboard_text, write_clipboard_text


class PastePipelineClipboardTest(unittest.TestCase):
    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which")
    @patch("cli.agent_cli.ui.paste_pipeline._is_probably_wsl", return_value=False)
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "linux")
    def test_read_clipboard_text_uses_linux_clipboard_backend(
        self, _wsl_mock, which_mock, run_mock
    ) -> None:
        which_mock.side_effect = lambda name: {  # noqa: ARG005
            "wl-paste": None,
            "xclip": "/usr/bin/xclip",
            "xsel": None,
        }.get(name)
        run_mock.return_value = subprocess.CompletedProcess(
            args=["xclip", "-selection", "clipboard", "-o"],
            returncode=0,
            stdout="line1\r\nline2\r\n",
            stderr="",
        )

        text = read_clipboard_text()

        self.assertEqual(text, "line1\nline2")
        run_mock.assert_called_once_with(
            ["xclip", "-selection", "clipboard", "-o"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which")
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "win32")
    def test_read_clipboard_text_uses_powershell_on_windows(self, which_mock, run_mock) -> None:
        which_mock.side_effect = lambda name: {  # noqa: ARG005
            "powershell.exe": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "pwsh": None,
            "powershell": None,
        }.get(name)
        run_mock.return_value = subprocess.CompletedProcess(
            args=["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            returncode=0,
            stdout="clipboard text\n",
            stderr="",
        )

        text = read_clipboard_text()

        self.assertEqual(text, "clipboard text")
        run_mock.assert_called_once_with(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which", return_value="/usr/bin/xclip")
    @patch("cli.agent_cli.ui.paste_pipeline._is_probably_wsl", return_value=False)
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "linux")
    def test_read_clipboard_text_returns_empty_when_clipboard_is_empty(
        self, _wsl_mock, _which_mock, run_mock
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["xclip", "-selection", "clipboard", "-o"],
            returncode=0,
            stdout="",
            stderr="",
        )

        self.assertEqual(read_clipboard_text(), "")
        run_mock.assert_called_once()

    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which", return_value=None)
    @patch("cli.agent_cli.ui.paste_pipeline._is_probably_wsl", return_value=False)
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "linux")
    def test_read_clipboard_text_returns_empty_when_no_backend_exists(
        self, _wsl_mock, _which_mock
    ) -> None:
        self.assertEqual(read_clipboard_text(), "")

    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which")
    @patch("cli.agent_cli.ui.paste_pipeline._is_probably_wsl", return_value=True)
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "linux")
    def test_read_clipboard_text_prefers_powershell_first_on_wsl(
        self, _wsl_mock, which_mock, run_mock
    ) -> None:
        which_mock.side_effect = lambda name: {  # noqa: ARG005
            "powershell.exe": "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "xclip": "/usr/bin/xclip",
            "xsel": None,
            "wl-paste": None,
            "pwsh": None,
            "powershell": None,
        }.get(name)
        run_mock.return_value = subprocess.CompletedProcess(
            args=["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            returncode=0,
            stdout="clipboard text\n",
            stderr="",
        )

        text = read_clipboard_text()

        self.assertEqual(text, "clipboard text")
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0][0], "powershell.exe")

    @patch.dict("cli.agent_cli.ui.paste_pipeline.os.environ", {"TMUX": "/tmp/tmux-1"}, clear=True)
    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which")
    def test_write_clipboard_text_prefers_tmux_clipboard_bridge(self, which_mock, run_mock) -> None:
        which_mock.side_effect = lambda name: "/usr/bin/tmux" if name == "tmux" else None
        run_mock.return_value = subprocess.CompletedProcess(
            args=["tmux", "load-buffer", "-w", "-"],
            returncode=0,
            stdout="",
            stderr="",
        )

        self.assertTrue(write_clipboard_text("copied text"))
        run_mock.assert_called_once_with(
            ["tmux", "load-buffer", "-w", "-"],
            input="copied text",
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @patch.dict("cli.agent_cli.ui.paste_pipeline.os.environ", {}, clear=True)
    @patch("cli.agent_cli.ui.paste_pipeline.subprocess.run")
    @patch("cli.agent_cli.ui.paste_pipeline.shutil.which")
    @patch("cli.agent_cli.ui.paste_pipeline._is_probably_wsl", return_value=False)
    @patch("cli.agent_cli.ui.paste_pipeline.sys.platform", "linux")
    def test_write_clipboard_text_falls_back_to_xclip(
        self, _wsl_mock, which_mock, run_mock
    ) -> None:
        which_mock.side_effect = lambda name: "/usr/bin/xclip" if name == "xclip" else None
        run_mock.return_value = subprocess.CompletedProcess(
            args=["xclip", "-selection", "clipboard", "-i"],
            returncode=0,
            stdout="",
            stderr="",
        )

        self.assertTrue(write_clipboard_text("copied text"))
        self.assertEqual(run_mock.call_args.args[0], ["xclip", "-selection", "clipboard", "-i"])
