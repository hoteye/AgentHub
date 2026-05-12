from __future__ import annotations

import shlex
from io import StringIO
from types import SimpleNamespace

import pytest

from cli.agent_cli.subcommands import plugin as plugin_subcommand


class _FakeRuntime:
    def __init__(self, assistant_text: str = "ok") -> None:
        self.assistant_text = assistant_text
        self.prompts: list[str] = []

    def handle_prompt(self, text: str):
        self.prompts.append(text)
        return SimpleNamespace(assistant_text=self.assistant_text)


@pytest.mark.parametrize(
    ("argv", "expected_command"),
    [
        (["plugin", "list"], "/plugins"),
        (["list"], "/plugins"),
        (["plugin", "enable", "demo"], "/plugin_enable demo"),
        (["plugin", "disable", "demo"], "/plugin_disable demo"),
        (["plugin", "disable", "--all"], "/plugin_disable --all"),
        (["plugin", "reload"], "/plugin_reload"),
        (["plugin", "install", "/tmp/demo.zip"], "/plugin_install /tmp/demo.zip"),
        (
            ["plugin", "install", "/tmp/demo plugin.zip", "--replace"],
            f"/plugin_install {shlex.quote('/tmp/demo plugin.zip')} replace",
        ),
        (
            ["plugin", "install", "/tmp/demo.zip", "--scope", "project"],
            "/plugin_install /tmp/demo.zip scope project",
        ),
        (["plugin", "remove", "demo"], "/plugin_remove demo"),
        (["plugin", "uninstall", "demo"], "/plugin_remove demo"),
        (["plugin", "marketplace", "list"], "/plugin_marketplace list"),
        (["plugin", "marketplace", "plugins"], "/plugin_marketplace plugins"),
        (
            ["plugin", "marketplace", "add", "demo@test", "/tmp/demo plugin.zip", "--scope", "project"],
            f"/plugin_marketplace add demo@test {shlex.quote('/tmp/demo plugin.zip')} scope project",
        ),
        (
            ["plugin", "marketplace", "install", "demo@test"],
            "/plugin_marketplace install demo@test",
        ),
        (
            ["plugin", "marketplace", "install", "demo@test", "--replace"],
            "/plugin_marketplace install demo@test replace",
        ),
        (
            ["plugin", "marketplace", "uninstall", "demo@test"],
            "/plugin_marketplace uninstall demo@test",
        ),
        (
            ["plugin", "marketplace", "enable", "demo@test"],
            "/plugin_marketplace enable demo@test",
        ),
        (
            ["plugin", "marketplace", "disable", "demo@test"],
            "/plugin_marketplace disable demo@test",
        ),
        (
            ["plugin", "marketplace", "update", "demo@test", "--path", "/tmp/next.zip"],
            "/plugin_marketplace update demo@test path /tmp/next.zip",
        ),
        (["plugin", "marketplace", "remove", "demo@test"], "/plugin_marketplace remove demo@test"),
    ],
)
def test_plugin_subcommand_maps_actions_to_slash_commands(argv: list[str], expected_command: str) -> None:
    runtime = _FakeRuntime("plugin ok")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = plugin_subcommand.run_plugin_subcommand(
        argv,
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert runtime.prompts == [expected_command]
    assert stdout.getvalue() == "plugin ok\n"
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["plugin"],
        ["plugin", "unknown"],
        ["plugin", "list", "extra"],
        ["plugin", "enable"],
        ["plugin", "disable"],
        ["plugin", "reload", "extra"],
        ["plugin", "install"],
        ["plugin", "install", "--replace"],
        ["plugin", "install", "/tmp/demo.zip", "--bad-flag"],
        ["plugin", "remove"],
        ["plugin", "uninstall"],
        ["plugin", "marketplace"],
        ["plugin", "marketplace", "unknown"],
        ["plugin", "marketplace", "list", "a", "b"],
        ["plugin", "marketplace", "remove"],
        ["plugin", "marketplace", "plugins", "extra"],
        ["plugin", "marketplace", "add"],
        ["plugin", "marketplace", "update"],
        ["plugin", "marketplace", "install"],
        ["plugin", "marketplace", "uninstall"],
        ["plugin", "marketplace", "enable"],
        ["plugin", "marketplace", "disable"],
        ["plugin", "marketplace", "disable", "a", "b"],
    ],
)
def test_plugin_subcommand_usage_errors_return_nonzero(argv: list[str]) -> None:
    runtime = _FakeRuntime()
    stdout = StringIO()
    stderr = StringIO()

    exit_code = plugin_subcommand.run_plugin_subcommand(
        argv,
        runtime=runtime,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert runtime.prompts == []
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == f"{plugin_subcommand.plugin_usage_text()}\n"


def test_plugin_subcommand_builds_default_runtime_when_runtime_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _FakeRuntime("plugins: 1")
    monkeypatch.setattr(plugin_subcommand, "AgentCliRuntime", lambda: fake_runtime)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = plugin_subcommand.run_plugin_subcommand(
        ["plugin", "list"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert fake_runtime.prompts == ["/plugins"]
    assert stdout.getvalue() == "plugins: 1\n"
    assert stderr.getvalue() == ""


def test_plugin_subcommand_runtime_error_returns_nonzero() -> None:
    class _FailRuntime:
        def handle_prompt(self, _text: str):
            raise RuntimeError("boom")

    stdout = StringIO()
    stderr = StringIO()
    exit_code = plugin_subcommand.run_plugin_subcommand(
        ["plugin", "list"],
        runtime=_FailRuntime(),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "plugin error: boom\n"


def test_has_plugin_subcommand_request_requires_plugin_prefix() -> None:
    assert plugin_subcommand.has_plugin_subcommand_request(["plugin", "list"]) is True
    assert plugin_subcommand.has_plugin_subcommand_request(["list"]) is False
    assert plugin_subcommand.has_plugin_subcommand_request([]) is False
    assert plugin_subcommand.has_plugin_subcommand_request(None) is False
