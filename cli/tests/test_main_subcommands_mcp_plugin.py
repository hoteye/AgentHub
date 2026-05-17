from __future__ import annotations

import io
import sys
import types
from types import SimpleNamespace

import pytest

from cli.agent_cli import __version__
from cli.agent_cli import main as main_module
from cli.agent_cli import subcommands as subcommands_module
from cli.agent_cli.app_runtime_flow import AppRuntimeFlowMixin
from cli.agent_cli.models import PromptResponse, ToolEvent


def test_dispatch_subcommand_routes_mcp_module_main(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    fake_module = types.ModuleType("cli.agent_cli.subcommands.mcp")

    def _fake_main(argv, *, runtime=None, stdin=None, stdout=None, stderr=None) -> int:
        captured["argv"] = list(argv)
        captured["runtime"] = runtime
        captured["streams"] = (stdin, stdout, stderr)
        return 19

    fake_module.main = _fake_main
    monkeypatch.setitem(sys.modules, "cli.agent_cli.subcommands.mcp", fake_module)

    runtime = object()
    stdin = io.StringIO()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = subcommands_module.dispatch_subcommand(
        ["mcp", "list"],
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 19
    assert captured["argv"] == ["list"]
    assert captured["runtime"] is runtime
    assert captured["streams"] == (stdin, stdout, stderr)


def test_dispatch_subcommand_returns_none_for_non_subcommand() -> None:
    assert subcommands_module.dispatch_subcommand(["resume"]) is None


def test_dispatch_subcommand_reports_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subcommands_module, "_load_subcommand_entrypoint", lambda command_name: None
    )
    stderr = io.StringIO()

    exit_code = subcommands_module.dispatch_subcommand(["plugin", "list"], stderr=stderr)

    assert exit_code == 1
    assert "subcommand 'plugin' is not available" in stderr.getvalue()


def test_main_prints_version_without_runtime_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_startup(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("--version should not enter full startup")

    monkeypatch.setattr(main_module, "_configure_startup_debug", _unexpected_startup)
    monkeypatch.setattr(main_module, "_ensure_import_paths", _unexpected_startup)
    monkeypatch.setattr(main_module, "_ensure_git_dependency", _unexpected_startup)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main_module.main(["--version"], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stdout.getvalue() == f"agenthub-cli {__version__}\n"
    assert stderr.getvalue() == ""


def test_main_prints_version_even_with_launcher_default_args() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main_module.main(
        [
            "--sandbox-mode",
            "workspace-write",
            "--approval-policy",
            "on-request",
            "--version",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == f"agenthub-cli {__version__}\n"
    assert stderr.getvalue() == ""


def test_main_requires_git_before_runtime_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(main_module.shutil, "which", lambda command: None)
    stderr = io.StringIO()

    exit_code = main_module.main(["--provider-status"], stdout=io.StringIO(), stderr=stderr)

    assert exit_code == 1
    assert "AgentHub requires git" in stderr.getvalue()
    assert "sudo apt install git" in stderr.getvalue()


def test_main_packaged_tui_warns_when_tmux_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(main_module.sys, "frozen", True, raising=False)
    monkeypatch.delenv("AGENTHUB_TMUX_DEPENDENCY_CHECKED", raising=False)

    def _fake_which(command: str) -> str | None:
        return "/usr/bin/git" if command == "git" else None

    monkeypatch.setattr(main_module.shutil, "which", _fake_which)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self._exit_requested = False
            self._exit_summary_requires_post_run_print = False

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stderr = io.StringIO()
    exit_code = main_module.main([], stdout=io.StringIO(), stderr=stderr)

    assert exit_code == 0
    assert "AgentHub file/URL preview panes need tmux" in stderr.getvalue()


def test_main_packaged_tui_does_not_warn_about_tmux_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(main_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.delenv("AGENTHUB_TMUX_DEPENDENCY_CHECKED", raising=False)

    def _fake_which(command: str) -> str | None:
        return "C:\\Program Files\\Git\\cmd\\git.exe" if command == "git" else None

    monkeypatch.setattr(main_module.shutil, "which", _fake_which)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self._exit_requested = False
            self._exit_summary_requires_post_run_print = False

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stderr = io.StringIO()
    exit_code = main_module.main([], stdout=io.StringIO(), stderr=stderr)

    assert exit_code == 0
    assert "tmux" not in stderr.getvalue().lower()


def test_main_keeps_mcp_serve_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)

    def _unexpected_dispatch(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dispatch_subcommand should not run for `mcp serve`")

    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", _unexpected_dispatch)

    captured: dict[str, object] = {}
    fake_module = types.ModuleType("cli.agent_cli.mcp.serve")

    def _fake_mcp_serve_main(argv, *, runtime=None, stdin=None, stdout=None, stderr=None) -> int:
        captured["argv"] = list(argv)
        captured["runtime"] = runtime
        captured["streams"] = (stdin, stdout, stderr)
        return 17

    fake_module.main = _fake_mcp_serve_main
    monkeypatch.setitem(sys.modules, "cli.agent_cli.mcp.serve", fake_module)

    runtime = object()
    stdin = io.StringIO()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main(
        ["mcp", "serve", "--allow-tool", "agenthub.file_read"],
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 17
    assert captured["argv"] == ["serve", "--allow-tool", "agenthub.file_read"]
    assert captured["runtime"] is runtime
    assert captured["streams"] == (stdin, stdout, stderr)


@pytest.mark.parametrize(
    "argv",
    [
        ["mcp", "list"],
        ["plugin", "list"],
        ["mcp", "tool-call", "--projected-name", "atlas.echo"],
    ],
)
def test_main_dispatches_top_level_mcp_plugin_subcommands(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)

    captured: dict[str, object] = {}

    def _fake_dispatch(argv, *, runtime=None, stdin=None, stdout=None, stderr=None) -> int:
        captured["argv"] = list(argv)
        captured["runtime"] = runtime
        captured["streams"] = (stdin, stdout, stderr)
        return 23

    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", _fake_dispatch)

    runtime = object()
    stdin = io.StringIO()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main(
        argv,
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 23
    assert captured["argv"] == argv
    assert captured["runtime"] is runtime
    assert captured["streams"] == (stdin, stdout, stderr)


def test_main_keeps_non_subcommand_headless_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)

    from cli.agent_cli import headless as headless_module
    from cli.agent_cli import resume_support as resume_support_module

    captured: dict[str, object] = {}
    parsed_args = SimpleNamespace(prompt="hello", json=False, jsonl=False)

    class _ParserStub:
        def parse_args(self, argv):
            captured["parsed_argv"] = list(argv)
            return parsed_args

    monkeypatch.setattr(resume_support_module, "normalize_resume_cli_args", lambda argv: list(argv))
    monkeypatch.setattr(headless_module, "build_parser", lambda: _ParserStub())
    monkeypatch.setattr(headless_module, "has_headless_request", lambda args: True)

    def _fake_run_headless(args, *, runtime=None, stdin=None, stdout=None, stderr=None) -> int:
        captured["args"] = args
        captured["runtime"] = runtime
        captured["streams"] = (stdin, stdout, stderr)
        return 9

    monkeypatch.setattr(headless_module, "run_headless", _fake_run_headless)

    runtime = object()
    stdin = io.StringIO()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main(
        ["--print", "hello"],
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 9
    assert captured["parsed_argv"] == ["--print", "hello"]
    assert captured["args"] is parsed_args
    assert captured["runtime"] is runtime
    assert captured["streams"] == (stdin, stdout, stderr)


def test_main_tui_prints_resume_hint_after_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self._exit_requested = True
            self._exit_thread_id = "thread_exit_123"
            self._exit_resume_command = "agenthub resume thread_exit_123"
            self._exit_summary_requires_post_run_print = True

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main([], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stdout.getvalue() == "resume thread_exit_123\n"


def test_main_tui_prints_resume_hint_after_slash_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self._exit_requested = True
            self._exit_thread_id = "thread_exit_123"
            self._exit_resume_command = "agenthub resume thread_exit_123"
            self._exit_summary_requires_post_run_print = True

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main([], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stdout.getvalue() == "resume thread_exit_123\n"


def test_main_tui_ignores_terminal_stop_signals_before_app_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())
    called = []
    monkeypatch.setattr(
        main_module,
        "_prepare_interactive_tui_terminal_signals",
        lambda: called.append("prepare"),
    )

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            assert called == ["prepare"]
            self._exit_requested = False
            self._exit_thread_id = ""
            self._exit_resume_command = ""
            self._exit_summary_requires_post_run_print = False

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    exit_code = main_module.main([], stdout=io.StringIO(), stderr=io.StringIO())

    assert exit_code == 0
    assert called == ["prepare"]


def test_main_tui_handles_keyboard_interrupt_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    runtime = SimpleNamespace(thread_id="thread_keyboard_interrupt")
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime_arg: runtime)

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self.runtime = runtime
            self._exit_requested = False
            self._exit_thread_id = ""
            self._exit_resume_command = ""
            self._exit_summary_requires_post_run_print = False
            self.shutdown_called = False

        def _begin_shutdown(self) -> None:
            self.shutdown_called = True

        def run(self) -> None:
            raise KeyboardInterrupt

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main([], stdout=stdout, stderr=stderr)

    assert exit_code == 130
    assert stdout.getvalue() == "resume thread_keyboard_interrupt\n"
    assert stderr.getvalue() == ""


def test_app_runtime_flow_marks_slash_exit_for_post_run_resume_hint() -> None:
    class _Flow(AppRuntimeFlowMixin):
        def __init__(self) -> None:
            self._exit_requested = False
            self._exit_thread_id = ""
            self._exit_resume_command = ""
            self._exit_summary_requires_post_run_print = False
            self.scheduled = []

        def call_after_refresh(self, callback) -> None:
            self.scheduled.append(callback)

        def _exit_after_command(self) -> None:
            return None

    flow = _Flow()
    flow._handle_runtime_response(
        PromptResponse(
            user_text="/exit",
            assistant_text="exiting session",
            tool_events=[
                ToolEvent(
                    name="app_exit_requested",
                    ok=True,
                    summary="exit requested",
                    payload={
                        "thread_id": "thread_exit_123",
                        "resume_command": "agenthub resume thread_exit_123",
                    },
                )
            ],
        )
    )

    assert flow._exit_requested is True
    assert flow._exit_thread_id == "thread_exit_123"
    assert flow._exit_resume_command == "agenthub resume thread_exit_123"
    assert flow._exit_summary_requires_post_run_print is True
    assert flow.scheduled == [flow._exit_after_command]


def test_main_tui_skips_post_run_resume_hint_for_explicit_resume_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "_configure_stdio", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_import_paths", lambda: None)
    monkeypatch.setattr(subcommands_module, "dispatch_subcommand", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_tui_runtime", lambda args, runtime: object())

    fake_module = types.ModuleType("cli.agent_cli.app")

    class _FakeApp:
        def __init__(self, *, runtime=None, language=None, theme_id=None) -> None:
            self._exit_requested = True
            self._exit_thread_id = "thread_exit_123"
            self._exit_resume_command = "agenthub resume thread_exit_123"
            self._exit_summary_requires_post_run_print = True

        def run(self) -> None:
            return None

    fake_module.AgentCliApp = _FakeApp
    monkeypatch.setitem(sys.modules, "cli.agent_cli.app", fake_module)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main_module.main(["resume", "thread_exit_123"], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stdout.getvalue() == ""
