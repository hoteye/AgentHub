from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.app import AgentCliApp, PromptComposer, TranscriptArea
from cli.agent_cli.ui.transcript_preview_pane import (
    PreviewTarget,
    PreviewTargetSpan,
    close_preview_pane,
    directory_opener_install_command,
    directory_opener_install_prompt_shell_command,
    directory_opener_package_commands,
    ensure_preview_pane,
    open_preview_pane,
    open_target_in_preview,
    preview_command_for_target,
    preview_pane_user_disabled,
    preview_shell_command,
    set_preview_pane_user_disabled,
    target_at_line_column,
    target_span_at_line_column,
    tmux_preview_ready_shell_command,
    update_hover_target_for_area,
    url_opener_install_command,
    url_opener_install_prompt_shell_command,
    url_opener_package_commands,
)


def test_target_at_line_column_resolves_relative_file_with_line(tmp_path) -> None:
    file_path = tmp_path / "cli" / "agent_cli" / "ui" / "preview.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('preview')\n", encoding="utf-8")
    line = "open cli/agent_cli/ui/preview.py:42 now"

    target = target_at_line_column(
        line,
        line.index("preview.py"),
        workspace_roots=[tmp_path],
    )

    assert target == PreviewTarget(kind="file", value=str(file_path.resolve()), line_number=42)


def test_target_span_at_line_column_returns_underlinable_file_range(tmp_path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("hello\n", encoding="utf-8")
    line = "open README.md:12 now"

    span = target_span_at_line_column(line, line.index("README"), workspace_roots=[tmp_path])

    assert span == PreviewTargetSpan(
        start=line.index("README.md"),
        end=line.index(" now"),
        target=PreviewTarget(kind="file", value=str(file_path.resolve()), line_number=12),
    )


def test_target_at_line_column_resolves_relative_directory(tmp_path) -> None:
    dir_path = tmp_path / "docs"
    dir_path.mkdir()
    line = "open docs now"

    target = target_at_line_column(line, line.index("docs"), workspace_roots=[tmp_path])

    assert target == PreviewTarget(kind="dir", value=str(dir_path.resolve()), line_number=None)


def test_target_at_line_column_strips_url_trailing_punctuation() -> None:
    line = "docs: https://example.com/a?b=1)."

    target = target_at_line_column(line, line.index("example"))

    assert target == PreviewTarget(kind="url", value="https://example.com/a?b=1", line_number=None)


def test_target_span_at_line_column_strips_url_punctuation_from_hover_range() -> None:
    line = "docs: https://example.com/a?b=1)."

    span = target_span_at_line_column(line, line.index("example"))

    assert span == PreviewTargetSpan(
        start=line.index("https://"),
        end=line.index(")."),
        target=PreviewTarget(kind="url", value="https://example.com/a?b=1"),
    )


def test_target_at_line_column_ignores_missing_file(tmp_path) -> None:
    line = "open cli/agent_cli/ui/missing.py:8"

    target = target_at_line_column(line, line.index("missing.py"), workspace_roots=[tmp_path])

    assert target is None


def test_update_hover_target_underlines_only_target_text(tmp_path, monkeypatch) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("hello\n", encoding="utf-8")
    monkeypatch.setenv("AGENTHUB_PREVIEW_WORKSPACE", str(tmp_path))
    area = TranscriptArea()
    line = "open README.md now"
    area.load_text(line)

    update_hover_target_for_area(area, (0, line.index("README")))
    rendered = area.get_line(0)

    start = line.index("README.md")
    end = start + len("README.md")
    assert str(area.text) == line
    assert any(
        span.start == start and span.end == end and span.style.underline for span in rendered.spans
    )


def test_update_hover_target_clears_when_target_missing() -> None:
    area = TranscriptArea()
    area.load_text("plain text")
    area._preview_hover_target_span = (0, 0, 5)

    update_hover_target_for_area(area, (0, 7))

    assert area._preview_hover_target_span is None


def test_preview_command_for_file_prefers_readonly_nvim(tmp_path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("hello\n", encoding="utf-8")

    command = preview_command_for_target(
        PreviewTarget(kind="file", value=str(file_path), line_number=3),
        opener_lookup=lambda name: "/usr/bin/nvim" if name == "nvim" else None,
    )

    assert command == (
        "/usr/bin/nvim",
        "-R",
        "-c",
        "set mouse=a",
        "-c",
        "set number",
        "+3",
        "--",
        str(file_path),
    )


def test_preview_command_for_file_enables_vim_mouse_without_line(tmp_path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("hello\n", encoding="utf-8")

    command = preview_command_for_target(
        PreviewTarget(kind="file", value=str(file_path), line_number=None),
        opener_lookup=lambda name: "/usr/bin/vim" if name == "vim" else None,
    )

    assert command == ("/usr/bin/vim", "-R", "-c", "set mouse=a", "--", str(file_path))


def test_preview_command_for_url_prefers_w3m_with_mouse() -> None:
    command = preview_command_for_target(
        PreviewTarget(kind="url", value="https://example.com"),
        opener_lookup=lambda name: "/usr/bin/w3m" if name == "w3m" else None,
    )

    assert command == ("/usr/bin/w3m", "-o", "use_mouse=1", "https://example.com")


def test_preview_command_for_url_falls_back_to_lynx_with_mouse() -> None:
    command = preview_command_for_target(
        PreviewTarget(kind="url", value="https://example.com"),
        opener_lookup=lambda name: "/usr/bin/lynx" if name == "lynx" else None,
    )

    assert command == ("/usr/bin/lynx", "-use_mouse", "https://example.com")


def test_preview_command_for_directory_prefers_yazi() -> None:
    command = preview_command_for_target(
        PreviewTarget(kind="dir", value="/workspace/docs"),
        opener_lookup=lambda name: "/usr/bin/yazi" if name == "yazi" else None,
    )

    assert command == ("/usr/bin/yazi", "/workspace/docs")


def test_preview_command_for_directory_falls_back_to_mc_then_ranger() -> None:
    mc_command = preview_command_for_target(
        PreviewTarget(kind="dir", value="/workspace/docs"),
        opener_lookup=lambda name: "/usr/bin/mc" if name == "mc" else None,
    )
    ranger_command = preview_command_for_target(
        PreviewTarget(kind="dir", value="/workspace/docs"),
        opener_lookup=lambda name: "/usr/bin/ranger" if name == "ranger" else None,
    )

    assert mc_command == ("/usr/bin/mc", "/workspace/docs")
    assert ranger_command == ("/usr/bin/ranger", "/workspace/docs")


def test_directory_opener_install_command_returns_empty() -> None:
    command = directory_opener_install_command(
        command_lookup=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    assert command == ""


def test_directory_opener_package_commands_return_empty() -> None:
    install_command, uninstall_command = directory_opener_package_commands(
        command_lookup=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    assert install_command == ""
    assert uninstall_command == ""


def test_directory_opener_install_prompt_shows_info_only() -> None:
    command = directory_opener_install_prompt_shell_command(shell="/bin/zsh")

    assert "terminal file manager" in command
    assert "yazi" in command
    assert "mc" in command
    assert "ranger" in command
    assert "yazi-rs.github.io" in command
    assert "exec /bin/zsh" in command
    assert "read -e -i" not in command


def test_url_opener_install_command_prefers_apt_w3m() -> None:
    command = url_opener_install_command(
        command_lookup=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    assert command == "sudo apt update && sudo apt install w3m"


def test_url_opener_package_commands_include_uninstall_hint() -> None:
    install_command, uninstall_command = url_opener_package_commands(
        command_lookup=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    assert install_command == "sudo apt update && sudo apt install w3m"
    assert uninstall_command == "sudo apt remove w3m"


def test_url_opener_install_prompt_prefills_command_without_running_it() -> None:
    command = url_opener_install_prompt_shell_command(
        "sudo apt update && sudo apt install w3m",
        uninstall_command="sudo apt remove w3m",
        shell="/bin/zsh",
    )

    assert "read -e -i" in command
    assert "sudo apt update && sudo apt install w3m" in command
    assert "Uninstall later: sudo apt remove w3m" in command
    assert "Press Enter to run the suggested command" in command
    assert "exec /bin/zsh" in command


def test_preview_shell_command_returns_to_shell_after_opener_exits() -> None:
    command = preview_shell_command(("/bin/less", "+7", "--", "/tmp/a file.py"), shell="/bin/zsh")

    assert command == "/bin/less +7 -- '/tmp/a file.py'; exec /bin/zsh"


def test_tmux_preview_ready_shell_command_returns_to_shell() -> None:
    command = tmux_preview_ready_shell_command(shell="/bin/zsh")

    assert "AgentHub Preview ready" in command
    assert command.endswith("exec /bin/zsh")


def test_open_target_in_preview_respawns_tmux_pane_with_quoted_command(tmp_path) -> None:
    file_path = tmp_path / "a file.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs) -> SimpleNamespace:
        calls.append((args, kwargs))
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=0, stdout="%3\n")
        return SimpleNamespace(returncode=0)

    result = open_target_in_preview(
        PreviewTarget(kind="file", value=str(file_path), line_number=7),
        pane="%3",
        opener_lookup=lambda name: "/bin/less" if name == "less" else None,
        run=fake_run,
    )

    assert result.opened
    assert len(calls) == 2
    args, kwargs = calls[-1]
    assert kwargs["check"] is False
    assert args[:6] == ["tmux", "respawn-pane", "-k", "-t", "%3", "--"]
    assert "/bin/less +7 --" in args[-1]
    assert shlex_quote(str(file_path)) in args[-1]
    assert "; exec " in args[-1]


def test_ensure_preview_pane_reuses_existing_pane() -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="%3\n")

    pane = ensure_preview_pane("%3", run=fake_run)

    assert pane == "%3"
    assert len(calls) == 1
    assert calls[0][:4] == ["tmux", "display-message", "-p", "-t"]


def test_ensure_preview_pane_recreates_when_display_message_resolves_other_pane() -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=0, stdout="%1\n")
        return SimpleNamespace(returncode=0, stdout="%9\n")

    pane = ensure_preview_pane("%3", run=fake_run)

    assert pane == "%9"
    assert calls[1][:2] == ["tmux", "split-window"]


def test_ensure_preview_pane_recreates_missing_pane(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_PREVIEW_WORKSPACE", "/tmp/workspace")
    monkeypatch.setenv("AGENTHUB_TUI_PANE", "%7")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="%9\n")

    pane = ensure_preview_pane("%3", run=fake_run)

    assert pane == "%9"
    assert calls[1][:8] == ["tmux", "split-window", "-d", "-h", "-l", "50%", "-P", "-F"]
    assert "-c" in calls[1]
    assert "-t" in calls[1]
    assert "%7" in calls[1]


def test_open_preview_pane_reuses_existing_pane(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_PREVIEW_PANE", "%3")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="%3\n")

    pane = open_preview_pane(run=fake_run)

    assert pane == "%3"
    assert calls == [["tmux", "display-message", "-p", "-t", "%3", "#{pane_id}"]]


def test_open_preview_pane_creates_missing_pane_and_marks_owned(monkeypatch) -> None:
    monkeypatch.delenv("AGENTHUB_PREVIEW_PANE", raising=False)
    monkeypatch.delenv("AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW", raising=False)
    monkeypatch.setenv("AGENTHUB_TUI_PANE", "%7")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="%9\n")

    pane = open_preview_pane(run=fake_run)

    assert pane == "%9"
    assert calls[0][:2] == ["tmux", "split-window"]
    assert os.environ["AGENTHUB_PREVIEW_PANE"] == "%9"
    assert os.environ["AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW"] == "1"


def test_preview_pane_user_disabled_env(monkeypatch) -> None:
    monkeypatch.delenv("AGENTHUB_PREVIEW_DISABLED", raising=False)
    assert preview_pane_user_disabled() is False

    set_preview_pane_user_disabled(True)
    assert preview_pane_user_disabled() is True
    assert os.environ["AGENTHUB_PREVIEW_DISABLED"] == "1"

    set_preview_pane_user_disabled(False)
    assert preview_pane_user_disabled() is False
    assert "AGENTHUB_PREVIEW_DISABLED" not in os.environ


def test_close_preview_pane_kills_recorded_tmux_pane(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_PREVIEW_PANE", "%3")
    monkeypatch.setenv("AGENTHUB_TUI_PANE", "%7")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=0, stdout="%3\n")
        return SimpleNamespace(returncode=0, stdout="")

    closed = close_preview_pane(run=fake_run)

    assert closed is True
    assert calls == [
        ["tmux", "display-message", "-p", "-t", "%3", "#{pane_id}"],
        ["tmux", "kill-pane", "-t", "%3"],
    ]
    assert "AGENTHUB_PREVIEW_PANE" not in os.environ


def test_close_preview_pane_does_not_kill_current_tui_pane(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_PREVIEW_PANE", "%7")
    monkeypatch.setenv("AGENTHUB_TUI_PANE", "%7")
    calls: list[list[str]] = []

    closed = close_preview_pane(run=lambda args, **_kwargs: calls.append(args))

    assert closed is False
    assert calls == []


def test_close_preview_pane_clears_missing_env_pane(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_PREVIEW_PANE", "%3")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="")

    closed = close_preview_pane(run=fake_run)

    assert closed is False
    assert calls == [["tmux", "display-message", "-p", "-t", "%3", "#{pane_id}"]]
    assert "AGENTHUB_PREVIEW_PANE" not in os.environ


def test_open_target_in_preview_recreates_missing_pane_and_opens(tmp_path) -> None:
    file_path = tmp_path / "a.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=1, stdout="")
        if args[:2] == ["tmux", "split-window"]:
            return SimpleNamespace(returncode=0, stdout="%9\n")
        return SimpleNamespace(returncode=0, stdout="")

    result = open_target_in_preview(
        PreviewTarget(kind="file", value=str(file_path), line_number=1),
        pane="%3",
        opener_lookup=lambda name: "/bin/less" if name == "less" else None,
        run=fake_run,
    )

    assert result.opened
    assert result.command[:4] == ("tmux", "respawn-pane", "-k", "-t")
    assert result.command[4] == "%9"


def test_open_url_without_opener_prompts_install_command_in_preview_pane() -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=0, stdout="%3\n")
        return SimpleNamespace(returncode=0, stdout="")

    result = open_target_in_preview(
        PreviewTarget(kind="url", value="https://example.com"),
        pane="%3",
        opener_lookup=lambda name: "/usr/bin/apt" if name == "apt" else None,
        run=fake_run,
    )

    assert result.opened
    assert result.reason == "preview_opener_install_prompted"
    assert result.command[:4] == ("tmux", "respawn-pane", "-k", "-t")
    assert "sudo apt update && sudo apt install w3m" in result.command[-1]
    assert "Uninstall later: sudo apt remove w3m" in result.command[-1]
    assert "read -e -i" in result.command[-1]
    assert calls[-1][-1] == result.command[-1]


def test_open_directory_without_opener_shows_info_prompt_in_preview_pane() -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> SimpleNamespace:
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return SimpleNamespace(returncode=0, stdout="%3\n")
        return SimpleNamespace(returncode=0, stdout="")

    result = open_target_in_preview(
        PreviewTarget(kind="dir", value="/workspace/docs"),
        pane="%3",
        opener_lookup=lambda name: None,
        run=fake_run,
    )

    assert result.opened
    assert result.reason == "preview_opener_install_prompted"
    assert result.command[:4] == ("tmux", "respawn-pane", "-k", "-t")
    assert "yazi" in result.command[-1]
    assert "mc" in result.command[-1]
    assert "ranger" in result.command[-1]
    assert "read -e -i" not in result.command[-1]
    assert calls[-1][-1] == result.command[-1]


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


class TranscriptPreviewPaneInteractionTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _left_click_event(*, x: int, y: int) -> SimpleNamespace:
        return SimpleNamespace(
            button=1,
            x=x,
            y=y,
            stop=lambda: None,
            prevent_default=lambda: None,
        )

    async def test_single_click_empty_selection_opens_preview_target(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        opened: list[tuple[int, int]] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        with patch(
            "cli.agent_cli.ui.transcript_preview_pane.open_preview_target_for_area",
            side_effect=lambda _area, location: opened.append(location) or True,
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                composer = app.query_one("#prompt_composer", PromptComposer)
                main_log = app.query_one("#main_log", TranscriptArea)
                main_log.load_text("see README.md")

                main_log.on_mouse_down(self._left_click_event(x=5, y=0))
                main_log.on_mouse_up(
                    SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None)
                )
                await pilot.pause()

                self.assertEqual(copied, [])
                self.assertEqual(len(opened), 1)
                self.assertIs(app.focused, composer)
