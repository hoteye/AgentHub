from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_core import command_dispatch


def _runtime_with_tools(**tool_attrs):
    return SimpleNamespace(tools=SimpleNamespace(**tool_attrs))


def test_run_command_text_result_routes_slash_without_split_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_handle_known_command(runtime, *, name, arg_text, text, slash_invocation=None):
        del runtime
        captured["name"] = name
        captured["arg_text"] = arg_text
        captured["text"] = text
        captured["slash_invocation"] = slash_invocation
        return ("ok", [])

    monkeypatch.setattr(command_dispatch, "handle_known_command", _fake_handle_known_command)
    monkeypatch.setattr(command_dispatch, "split_command", lambda text: (_ for _ in ()).throw(AssertionError(text)))

    runtime = _runtime_with_tools(run_plugin_command=lambda *args: None)
    result = command_dispatch.run_command_text_result(runtime, "/model gpt_54 high user")

    assert result.assistant_text == "ok"
    assert captured["name"] == "model"
    assert captured["arg_text"] == "gpt_54 --reasoning-effort high --write user"
    assert getattr(captured["slash_invocation"], "command_name") == "model"


def test_run_command_text_result_passes_raw_slash_args_to_plugin_fallback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_plugin_command_result(name, arg_text, runtime):
        del runtime
        captured["name"] = name
        captured["arg_text"] = arg_text
        return ("plugin-ok", [])

    monkeypatch.setattr(command_dispatch, "handle_known_command", lambda *args, **kwargs: None)

    runtime = _runtime_with_tools(run_plugin_command_result=_fake_run_plugin_command_result)
    result = command_dispatch.run_command_text_result(runtime, "/provider verbose")

    assert result.assistant_text == "plugin-ok"
    assert captured == {"name": "provider", "arg_text": "verbose"}
