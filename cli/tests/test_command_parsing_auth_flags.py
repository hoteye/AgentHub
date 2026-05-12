from __future__ import annotations

from cli.agent_cli.runtime_core.command_parsing import parse_args


def test_parse_args_supports_auth_daemon_and_callback_flags() -> None:
    positionals, options = parse_args(
        "refresh --provider openai --auto --daemon start --managed --interval-seconds 1 "
        "--refresh-window-seconds 300 --force"
    )
    assert positionals == ["refresh"]
    assert options["provider"] == "openai"
    assert options["auto"] is True
    assert options["daemon"] == "start"
    assert options["managed"] is True
    assert options["interval-seconds"] == "1"
    assert options["refresh-window-seconds"] == "300"
    assert options["force"] is True


def test_parse_args_supports_pkce_callback_flags() -> None:
    positionals, options = parse_args(
        "login --provider openai --mode browser_pkce --wait-callback --callback-timeout-seconds 120 --state s1"
    )
    assert positionals == ["login"]
    assert options["provider"] == "openai"
    assert options["mode"] == "browser_pkce"
    assert options["wait-callback"] is True
    assert options["callback-timeout-seconds"] == "120"
    assert options["state"] == "s1"
