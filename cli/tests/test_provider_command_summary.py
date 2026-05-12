from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_core.provider_commands import handle_provider_command


def _switch_disabled_result(exc: Exception) -> tuple[str, list[object]]:
    return (str(exc), [])


class _FakeAgent:
    def __init__(self) -> None:
        self.switched_to: str | None = None

    def switch_provider(self, provider_name: str, persist: bool = True) -> dict[str, object]:
        del persist
        self.switched_to = provider_name
        return {
            "provider_display_label": f"{provider_name} | gpt-5.4 | tool-calls",
            "provider_public_name": provider_name,
            "provider_route_name": "openai",
            "provider_planner": "openai_responses",
            "provider_source": "project_local",
            "provider_ready": "true",
        }

    @staticmethod
    def provider_status() -> dict[str, object]:
        return {
            "provider_display_label": "openai | gpt-5.4 | tool-calls",
            "provider_public_name": "openai",
            "provider_route_name": "openai",
            "provider_ready": "true",
            "provider_planner": "openai_responses",
            "provider_model": "gpt-5.4",
            "provider_reasoning_effort": "high",
            "provider_tools": "tool-calls",
            "session_line": "openai-tools",
            "provider_source": "project_local",
            "provider_config_scope": "project_local",
            "provider_selection_scope": "none",
            "provider_selection_active": False,
            "provider_runtime_home_active": False,
            "provider_runtime_home_path": "",
            "provider_runtime_state": "ready",
            "route_tool_followup": "openai | gpt-5.4 | reasoning=high | source=main",
            "route_final_synthesis": "openai | gpt-5.4 | reasoning=high | source=main",
            "delegate_subagent": "openai | gpt-5.4 | reasoning=high | source=inherit_main",
            "delegate_teammate": "openai | gpt-5.4 | reasoning=high | source=inherit_main",
            "provider_config_path": "/tmp/config.toml",
            "provider_auth_path": "/tmp/auth.json",
            "provider_selection_path": "/home/test/.agent_cli/config.toml",
            "auth_mode": "none",
            "no_auth_guardrail_reason": "explicit_allow_no_auth",
            "no_auth_guardrail_pass": True,
            "platform_family": "unix",
            "platform_os": "linux",
            "shell_kind": "posix",
            "shell_program": "/bin/bash",
            "availability_status": "unknown",
            "availability_known": False,
            "availability_health_bucket": "unknown",
            "availability": {
                "status": "unknown",
                "known": False,
            },
        }


def test_provider_default_summary_is_compact() -> None:
    runtime = SimpleNamespace(agent=_FakeAgent())

    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert "provider status" in text
    assert "provider_name=openai" in text
    assert "provider_model=gpt-5.4" in text
    assert "provider_reasoning_effort=high" in text
    assert "provider_ready=true" in text
    assert "provider_source=project_local" in text
    assert "provider_selection_scope=" not in text
    assert "provider_config_path=/tmp/config.toml" not in text
    assert "auth_mode=none" not in text
    assert "route_health_summary=" not in text
    assert "provider_verbose=true" not in text
    assert "availability={'status': 'unknown', 'known': False}" not in text


def test_provider_verbose_surfaces_raw_extra_fields() -> None:
    runtime = SimpleNamespace(agent=_FakeAgent())

    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="--verbose",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert "provider_verbose=true" in text
    assert "auth_mode=none" in text
    assert "no_auth_guardrail_reason=explicit_allow_no_auth" in text
    assert "no_auth_guardrail_pass=True" in text
    assert "provider_selection_path=/home/test/.agent_cli/config.toml" in text
    assert "provider_config_scope=project_local" in text
    assert "provider_selection_scope=none" in text
    assert "provider_runtime_home_active=False" in text
    assert "availability={'status': 'unknown', 'known': False}" in text


def test_provider_default_summary_surfaces_active_user_selection_scope() -> None:
    class _SelectionActiveAgent(_FakeAgent):
        @staticmethod
        def provider_status() -> dict[str, object]:
            payload = dict(_FakeAgent.provider_status())
            payload["provider_selection_scope"] = "user_home"
            payload["provider_selection_active"] = True
            return payload

    runtime = SimpleNamespace(agent=_SelectionActiveAgent())

    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert "provider_source=project_local" in text
    assert "provider_selection_scope=user_home" in text


def test_provider_usage_rejects_multiple_positionals() -> None:
    runtime = SimpleNamespace(agent=_FakeAgent())

    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="openai anthropic",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert text == (
        "Usage: /provider [name]\n"
        "Advanced: /provider [name] --write <session|user|project> [--verbose] [--probe]"
    )


def test_provider_switch_allows_verbose_flag_with_provider_name() -> None:
    agent = _FakeAgent()
    runtime = SimpleNamespace(agent=agent)

    text, events = handle_provider_command(
        runtime,
        name="provider",
        arg_text="anthropic --verbose",
        switch_disabled_result=_switch_disabled_result,
    ) or ("", [])

    assert events == []
    assert "switched provider to anthropic" in text
    assert agent.switched_to == "anthropic"
