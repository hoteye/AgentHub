from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest

from cli.agent_cli.subcommands import mcp as mcp_subcommand


class _FakeRuntime:
    def __init__(
        self,
        *,
        responses: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._error = error
        self.commands: list[str] = []

    def handle_prompt(self, text: str):  # noqa: ANN201
        self.commands.append(text)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(assistant_text=self._responses.get(text, "ok"))


@pytest.mark.parametrize(
    ("argv", "expected_slash", "assistant_text"),
    [
        (["list"], "/mcp list", "servers: 2"),
        (["inspect", "atlas"], "/mcp inspect atlas", "atlas is connected"),
        (["reconnect", "all"], "/mcp reconnect all", "reconnected"),
        (["enable", "atlas"], "/mcp enable atlas", "enabled"),
        (["disable", "atlas"], "/mcp disable atlas", "disabled"),
        (["auth", "--server", "atlas", "--token", "token-1"], "/mcp auth server atlas token token-1", "auth updated"),
        (["channel"], "/mcp channel", "channels: 1"),
        (["permission", "list", "--server", "atlas"], "/mcp permission list server atlas", "permissions: 1"),
        (["resource", "list", "--server", "atlas"], "/mcp_resource list server atlas", "resources: 3"),
        (
            ["tool-call", "--projected-name", "atlas.echo", "--arguments-json", '{"text":"hello"}'],
            '/mcp_tool_call projected-name atlas.echo arguments-json \'{"text":"hello"}\'',
            "tool call ok",
        ),
    ],
)
def test_main_dispatches_subcommands_and_prints_assistant_text(
    argv: list[str],
    expected_slash: str,
    assistant_text: str,
) -> None:
    runtime = _FakeRuntime(responses={expected_slash: assistant_text})
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(argv, runtime=runtime, stdout=output, stderr=error)

    assert exit_code == 0
    assert runtime.commands == [expected_slash]
    assert output.getvalue() == f"{assistant_text}\n"
    assert error.getvalue() == ""


def test_main_accepts_leading_mcp_token() -> None:
    runtime = _FakeRuntime(responses={"/mcp list": "servers: 1"})
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(["mcp", "list"], runtime=runtime, stdout=output, stderr=error)

    assert exit_code == 0
    assert runtime.commands == ["/mcp list"]
    assert output.getvalue() == "servers: 1\n"
    assert error.getvalue() == ""


def test_main_quotes_server_name_when_building_slash_command() -> None:
    runtime = _FakeRuntime(responses={"/mcp inspect 'atlas docs'": "atlas docs"})
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(["inspect", "atlas docs"], runtime=runtime, stdout=output, stderr=error)

    assert exit_code == 0
    assert runtime.commands == ["/mcp inspect 'atlas docs'"]
    assert output.getvalue() == "atlas docs\n"
    assert error.getvalue() == ""


def test_main_accepts_tool_call_alias_and_quotes_values() -> None:
    runtime = _FakeRuntime(
        responses={"/mcp_tool_call projected-name atlas.echo arguments-json '{\"message\":\"atlas docs\"}'": "ok"}
    )
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(
        ["tool_call", "--projected-name", "atlas.echo", "--arguments-json", '{"message":"atlas docs"}'],
        runtime=runtime,
        stdout=output,
        stderr=error,
    )

    assert exit_code == 0
    assert runtime.commands == ["/mcp_tool_call projected-name atlas.echo arguments-json '{\"message\":\"atlas docs\"}'"]
    assert output.getvalue() == "ok\n"
    assert error.getvalue() == ""


@pytest.mark.parametrize(
    ("argv", "expected_usage"),
    [
        ([], mcp_subcommand.TOP_LEVEL_USAGE),
        (["unknown"], mcp_subcommand.TOP_LEVEL_USAGE),
        (["list", "extra"], mcp_subcommand.SUBCOMMAND_USAGES["list"]),
        (["inspect"], mcp_subcommand.SUBCOMMAND_USAGES["inspect"]),
        (["reconnect"], mcp_subcommand.SUBCOMMAND_USAGES["reconnect"]),
        (["enable"], mcp_subcommand.SUBCOMMAND_USAGES["enable"]),
        (["disable"], mcp_subcommand.SUBCOMMAND_USAGES["disable"]),
    ],
)
def test_main_returns_usage_and_non_zero_for_invalid_or_missing_args(
    argv: list[str],
    expected_usage: str,
) -> None:
    runtime = _FakeRuntime()
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(argv, runtime=runtime, stdout=output, stderr=error)

    assert exit_code == 2
    assert runtime.commands == []
    assert output.getvalue() == ""
    assert error.getvalue() == f"{expected_usage}\n"


def test_main_surfaces_runtime_error_with_non_zero_exit_code() -> None:
    runtime = _FakeRuntime(error=RuntimeError("boom"))
    output = StringIO()
    error = StringIO()

    exit_code = mcp_subcommand.main(["list"], runtime=runtime, stdout=output, stderr=error)

    assert exit_code == 1
    assert runtime.commands == ["/mcp list"]
    assert output.getvalue() == ""
    assert error.getvalue() == "mcp error: boom\n"
