from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cli.agent_cli import (
    builtin_agent_profiles_runtime,
    provider_catalog_selection_runtime,
    thread_store_replay,
)
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ResponseInputItem,
    ThreadHistoryTurn,
    ToolEvent,
    default_response_items,
)
from cli.agent_cli.provider import ProviderPathResolution, load_provider_config
from cli.agent_cli.providers.anthropic_claude import (
    DEFAULT_CLAUDE_MODEL,
    AnthropicClaudePlanner,
    AnthropicMessagesSession,
    _command_for_tool_call,
    anthropic_tool_specs,
    build_anthropic_client,
    load_claude_provider_config,
    should_use_claude_provider,
)
from cli.agent_cli.providers.anthropic_claude_session_runtime import normalize_messages
from cli.agent_cli.providers.anthropic_native_web_search_runtime import native_web_search_payload
from cli.agent_cli.providers.config_catalog import ProviderConfig, select_provider_config
from cli.agent_cli.providers.interaction_profile_resolution import (
    InteractionProfileCompatibilityError,
)
from cli.agent_cli.providers.tool_specs import (
    supports_anthropic_native_web_search,
    supports_anthropic_native_web_search_mixed_tools,
)
from cli.agent_cli.runtime_core.tool_commands_helpers import handle_web_search


class _FakeAnthropicMessages:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        if kwargs.get("stream") is True:
            raise TypeError("fake Anthropic stream API is unavailable")
        self.requests.append(kwargs)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(call_id: str, name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=payload)


def _server_tool_use_block(call_id: str, name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="server_tool_use", id=call_id, name=name, input=payload)


def _tool_result_block(tool_use_id: str, content: object) -> SimpleNamespace:
    return SimpleNamespace(type="tool_result", tool_use_id=tool_use_id, content=content)


def _host_platform() -> HostPlatform:
    return HostPlatform(
        family="unix",
        os="linux",
        shell_kind="bash",
        shell_program="/bin/bash",
        list_dir_command="ls -la",
        print_working_dir_command="pwd",
        python_version_command="python -V",
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_build_anthropic_client_sets_default_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))

    build_anthropic_client(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            base_url="https://example.test/anthropic",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )
    )

    assert captured["api_key"] == "sk-claude"
    assert captured["base_url"] == "https://example.test/anthropic"
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60.0


def test_build_anthropic_client_uses_auth_token_when_configured(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))

    build_anthropic_client(
        ProviderConfig(
            model="glm-5.1",
            api_key="bearer-token",
            base_url="https://open.bigmodel.cn/api/anthropic",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            raw_provider={"auth_token_env": "ANTHROPIC_AUTH_TOKEN"},
        )
    )

    assert captured["auth_token"] == "bearer-token"
    assert "api_key" not in captured
    assert captured["base_url"] == "https://open.bigmodel.cn/api/anthropic"
    assert captured["max_retries"] == 0


def test_build_anthropic_client_uses_configured_model_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))

    build_anthropic_client(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            raw_model={"model_timeout": "12.5"},
        )
    )

    assert captured["timeout"] == 12.5


def test_normalize_messages_logs_skipped_tool_use_without_call_id() -> None:
    with (
        patch(
            "cli.agent_cli.providers.anthropic_claude_session_runtime.timeline_debug_enabled",
            return_value=True,
        ),
        patch(
            "cli.agent_cli.providers.anthropic_claude_session_runtime.log_timeline"
        ) as log_timeline_mock,
    ):
        system_parts, messages = normalize_messages(
            [{"type": "function_call", "name": "read_file", "arguments": "{}"}],
            tool_result_block_fn=lambda **kwargs: kwargs,
            message_text_fn=lambda content: str(content or ""),
            workspace_reference_message_fn=lambda payload: str(payload),
        )

    assert system_parts == []
    assert messages == []
    log_timeline_mock.assert_called_once()
    assert log_timeline_mock.call_args.args[0] == "anthropic.replay.tool_use.skipped"
    assert log_timeline_mock.call_args.kwargs["reason"] == "missing_call_id_or_name"


def test_anthropic_tool_result_block_does_not_double_wrap_existing_error_tags() -> None:
    block = AnthropicMessagesSession._tool_result_block(
        call_id="call_shell_1",
        output="stderr line\n<error>Command exited with code 2</error>",
        success=False,
    )

    assert block == {
        "type": "tool_result",
        "tool_use_id": "call_shell_1",
        "content": [
            {
                "type": "text",
                "text": "stderr line\n<error>Command exited with code 2</error>",
            }
        ],
        "is_error": True,
    }


def test_normalize_messages_logs_invalid_function_call_json_and_inserts_missing_result_placeholder() -> (
    None
):
    with (
        patch(
            "cli.agent_cli.providers.anthropic_claude_session_runtime.timeline_debug_enabled",
            return_value=True,
        ),
        patch(
            "cli.agent_cli.providers.anthropic_claude_session_runtime.log_timeline"
        ) as log_timeline_mock,
    ):
        system_parts, messages = normalize_messages(
            [
                {
                    "type": "function_call",
                    "call_id": "call_read_1",
                    "name": "read_file",
                    "arguments": "{bad",
                }
            ],
            tool_result_block_fn=lambda **kwargs: kwargs,
            message_text_fn=lambda content: str(content or ""),
            workspace_reference_message_fn=lambda payload: str(payload),
        )

    assert system_parts == []
    assert messages == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_read_1",
                    "name": "read_file",
                    "input": {},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "call_id": "call_read_1",
                    "output": "[Tool result missing due to internal error]",
                    "success": False,
                }
            ],
        },
    ]
    events = [call.args[0] for call in log_timeline_mock.call_args_list]
    assert events == [
        "anthropic.replay.tool_use.arguments_decode_failed",
        "anthropic.replay.tool_result.placeholder_inserted",
    ]
    assert log_timeline_mock.call_args_list[0].kwargs["call_id"] == "call_read_1"
    assert log_timeline_mock.call_args_list[1].kwargs["missing_call_ids"] == ["call_read_1"]


def test_normalize_messages_inserts_placeholder_for_missing_tool_results_in_tool_use_order() -> (
    None
):
    system_parts, messages = normalize_messages(
        [
            {"type": "message", "role": "user", "content": "Read a.txt and b.txt."},
            {
                "type": "function_call",
                "call_id": "toolu_read_a",
                "name": "read_file",
                "arguments": {"file_path": "/tmp/a.txt"},
            },
            {
                "type": "function_call",
                "call_id": "toolu_read_b",
                "name": "read_file",
                "arguments": {"file_path": "/tmp/b.txt"},
            },
            {
                "type": "function_call_output",
                "call_id": "toolu_read_a",
                "output": "A: alpha",
                "success": True,
            },
            {"type": "message", "role": "assistant", "content": "Only a.txt was available."},
        ],
        tool_result_block_fn=lambda **kwargs: kwargs,
        message_text_fn=lambda content: str(content or ""),
        workspace_reference_message_fn=lambda payload: str(payload),
    )

    assert system_parts == []
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
    assert [block["id"] for block in messages[1]["content"]] == ["toolu_read_a", "toolu_read_b"]
    assert messages[2]["content"] == [
        {"call_id": "toolu_read_a", "output": "A: alpha", "success": True},
        {
            "call_id": "toolu_read_b",
            "output": "[Tool result missing due to internal error]",
            "success": False,
        },
    ]
    assert messages[3]["content"] == [{"type": "text", "text": "Only a.txt was available."}]


def test_normalize_messages_converts_orphan_tool_results_to_plain_text() -> None:
    system_parts, messages = normalize_messages(
        [
            {"type": "message", "role": "user", "content": "Read a.txt, b.txt, and c.txt."},
            {
                "type": "function_call",
                "call_id": "toolu_read_a",
                "name": "read_file",
                "arguments": {"file_path": "/tmp/a.txt"},
            },
            {
                "type": "response_item",
                "item": {
                    "type": "function_call",
                    "call_id": "toolu_read_b",
                    "name": "read_file",
                    "arguments": {"file_path": "/tmp/b.txt"},
                },
            },
            {
                "type": "function_call",
                "call_id": "toolu_read_c",
                "name": "read_file",
                "arguments": {"file_path": "/tmp/c.txt"},
            },
            {
                "type": "response_item",
                "item": {
                    "type": "function_call_output",
                    "call_id": "toolu_read_b",
                    "output": "B: beta",
                    "success": True,
                },
            },
            {
                "type": "function_call_output",
                "call_id": "toolu_read_orphan",
                "output": "orphan output",
                "success": True,
            },
            {
                "type": "response_item",
                "item": {
                    "type": "function_call_output",
                    "call_id": "toolu_read_a",
                    "output": "A: alpha",
                    "success": True,
                },
            },
            {"type": "message", "role": "assistant", "content": "Read results collected."},
        ],
        tool_result_block_fn=lambda **kwargs: kwargs,
        message_text_fn=lambda content: str(content or ""),
        workspace_reference_message_fn=lambda payload: str(payload),
    )

    assert system_parts == []
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "user",
        "assistant",
    ]
    assert [block["id"] for block in messages[1]["content"]] == [
        "toolu_read_a",
        "toolu_read_b",
        "toolu_read_c",
    ]
    assert messages[2]["content"] == [
        {"call_id": "toolu_read_a", "output": "A: alpha", "success": True},
        {"call_id": "toolu_read_b", "output": "B: beta", "success": True},
        {
            "call_id": "toolu_read_c",
            "output": "[Tool result missing due to internal error]",
            "success": False,
        },
    ]
    assert messages[3]["content"][0]["type"] == "text"
    assert (
        "matching tool_use is unavailable: toolu_read_orphan" in messages[3]["content"][0]["text"]
    )
    assert "orphan output" in messages[3]["content"][0]["text"]
    assert messages[4]["content"] == [{"type": "text", "text": "Read results collected."}]


def test_normalize_messages_converts_leading_orphan_tool_outputs_to_plain_text() -> None:
    system_parts, messages = normalize_messages(
        [
            {
                "type": "function_call_output",
                "call_id": "toolu_pruned_1",
                "output": "pruned call output",
                "success": True,
            },
            {"type": "message", "role": "user", "content": "Continue after compaction."},
        ],
        tool_result_block_fn=lambda **kwargs: kwargs,
        message_text_fn=lambda content: str(content or ""),
        workspace_reference_message_fn=lambda payload: str(payload),
    )

    assert system_parts == []
    assert [message["role"] for message in messages] == ["user", "user"]
    assert messages[0]["content"][0]["type"] == "text"
    assert "matching tool_use is unavailable: toolu_pruned_1" in messages[0]["content"][0]["text"]
    assert "pruned call output" in messages[0]["content"][0]["text"]
    assert all(
        block.get("type") != "tool_result" for message in messages for block in message["content"]
    )


def test_normalize_messages_keeps_known_session_tool_output_native() -> None:
    system_parts, messages = AnthropicMessagesSession._normalize_messages(
        [
            {
                "type": "function_call_output",
                "call_id": "toolu_active_1",
                "output": "active output",
                "success": True,
            },
            {
                "type": "function_call_output",
                "call_id": "toolu_orphan_1",
                "output": "orphan output",
                "success": True,
            },
        ],
        known_tool_use_ids={"toolu_active_1"},
    )

    assert system_parts == []
    assert [message["role"] for message in messages] == ["user", "user"]
    assert messages[0]["content"][0]["type"] == "tool_result"
    assert messages[0]["content"][0]["tool_use_id"] == "toolu_active_1"
    assert messages[0]["content"][0]["content"][0]["text"] == "active output"
    assert messages[1]["content"][0]["type"] == "text"
    assert "matching tool_use is unavailable: toolu_orphan_1" in messages[1]["content"][0]["text"]
    assert "orphan output" in messages[1]["content"][0]["text"]


def test_load_claude_provider_config_reads_claude_home_files() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://relay.example/claudecode"}}),
            encoding="utf-8",
        )
        (claude_dir / "config.json").write_text(
            json.dumps({"primaryApiKey": "sk-claude-home"}),
            encoding="utf-8",
        )
        (home / ".claude.json").write_text(
            json.dumps({"hasCompletedOnboarding": True}),
            encoding="utf-8",
        )

        config = load_claude_provider_config(env_mapping={}, home_dir=home)

    assert config is not None
    assert config.model == DEFAULT_CLAUDE_MODEL
    assert config.api_key == "sk-claude-home"
    assert config.base_url == "https://relay.example/claudecode"
    assert config.planner_kind == "anthropic_messages"
    assert config.source == "claude_home"
    assert config.raw_provider["has_completed_onboarding"] is True


def test_load_claude_provider_config_uses_auth_token_and_default_alias_model() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": "bearer-token",
                        "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
                        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.1",
                    },
                    "model": "opus",
                }
            ),
            encoding="utf-8",
        )
        (claude_dir / "config.json").write_text("{}", encoding="utf-8")
        (home / ".claude.json").write_text(
            json.dumps({"hasCompletedOnboarding": True}),
            encoding="utf-8",
        )

        config = load_claude_provider_config(env_mapping={}, home_dir=home)

    assert config is not None
    assert config.model == "glm-5.1"
    assert config.api_key == "bearer-token"
    assert config.base_url == "https://open.bigmodel.cn/api/anthropic"
    assert config.raw_provider["api_key_env"] == "ANTHROPIC_AUTH_TOKEN"
    assert config.raw_provider["auth_token_env"] == "ANTHROPIC_AUTH_TOKEN"


def test_load_claude_provider_config_maps_claude_family_to_default_model() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": "bearer-token",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5-turbo",
                    }
                }
            ),
            encoding="utf-8",
        )
        (claude_dir / "config.json").write_text("{}", encoding="utf-8")
        (home / ".claude.json").write_text("{}", encoding="utf-8")

        config = load_claude_provider_config(
            env_mapping={"AGENT_CLI_MODEL": "claude-sonnet-4-6"},
            home_dir=home,
        )

    assert config is not None
    assert config.model == "glm-5-turbo"
    assert config.raw_provider["auth_token_env"] == "ANTHROPIC_AUTH_TOKEN"


def test_select_provider_config_marks_anthropic_auth_token_for_catalog_provider() -> None:
    resolution = ProviderPathResolution(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
        config_exists=True,
        auth_exists=True,
        used_project_local=True,
    )

    config = select_provider_config(
        env_mapping={"AGENT_CLI_PROVIDER": "anthropic", "AGENT_CLI_MODEL": "glm-5.1"},
        auth_data={"ANTHROPIC_AUTH_TOKEN": "bearer-token"},
        toml_data={
            "model_providers": {
                "anthropic": {
                    "name": "anthropic",
                    "base_url": "https://open.bigmodel.cn/api/anthropic",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
            },
            "models": {
                "glm_51": {
                    "provider": "anthropic",
                    "model_id": "glm-5.1",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                }
            },
        },
        resolution=resolution,
    )

    assert config is not None
    assert config.api_key == "bearer-token"
    assert config.raw_provider["api_key_env"] == "ANTHROPIC_AUTH_TOKEN"
    assert config.raw_provider["auth_token_env"] == "ANTHROPIC_AUTH_TOKEN"


def test_candidate_api_key_names_prefers_anthropic_auth_token() -> None:
    from cli.agent_cli.providers.config_catalog import candidate_api_key_names

    assert candidate_api_key_names(
        "anthropic",
        {"api_key_env": "ANTHROPIC_API_KEY"},
        "glm-5.1",
        "https://open.bigmodel.cn/api/anthropic",
    )[:2] == ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"]


def test_load_provider_config_routes_to_claude_when_explicitly_requested() -> None:
    resolution = ProviderPathResolution(
        config_path=Path("/tmp/missing-config.toml"),
        auth_path=Path("/tmp/missing-auth.json"),
        config_exists=False,
        auth_exists=False,
        used_project_local=False,
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    with patch("cli.agent_cli.provider.resolve_provider_paths", return_value=resolution):
        with patch(
            "cli.agent_cli.provider.load_claude_provider_config", return_value=claude_config
        ) as loader:
            config = load_provider_config(env_overrides={"AGENT_CLI_PROVIDER": "claude"})

    assert config is claude_config
    loader.assert_called_once()


def test_load_provider_config_routes_to_claude_when_selected_from_user_config() -> None:
    resolution = ProviderPathResolution(
        config_path=Path("/tmp/missing-config.toml"),
        auth_path=Path("/tmp/missing-auth.json"),
        config_exists=False,
        auth_exists=False,
        used_project_local=False,
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    with patch("cli.agent_cli.provider.resolve_provider_paths", return_value=resolution):
        with patch(
            "cli.agent_cli.provider._home_provider_paths",
            return_value=(Path("/tmp/home-config.toml"), Path("/tmp/home-auth.json"), False),
        ):
            with patch(
                "cli.agent_cli.provider._read_user_model_selection_toml",
                return_value={"model_provider": "anthropic", "model": "claude-sonnet-4-6"},
            ):
                with patch(
                    "cli.agent_cli.provider.load_claude_provider_config", return_value=claude_config
                ) as loader:
                    config = load_provider_config(env_overrides={})

    assert config is claude_config
    loader.assert_called_once()


def test_load_provider_config_does_not_route_to_claude_without_explicit_selector() -> None:
    resolution = ProviderPathResolution(
        config_path=Path("/tmp/missing-config.toml"),
        auth_path=Path("/tmp/missing-auth.json"),
        config_exists=False,
        auth_exists=False,
        used_project_local=False,
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    with patch("cli.agent_cli.provider.resolve_provider_paths", return_value=resolution):
        with patch("cli.agent_cli.provider._read_user_model_selection_toml", return_value={}):
            with patch(
                "cli.agent_cli.provider.load_claude_provider_config", return_value=claude_config
            ) as loader:
                config = load_provider_config(env_overrides={})

    assert config is None
    loader.assert_not_called()


def test_should_use_claude_provider_ignores_anthropic_env_without_explicit_selector() -> None:
    assert (
        should_use_claude_provider(
            env_mapping={
                "ANTHROPIC_BASE_URL": "https://relay.example/claudecode",
                "ANTHROPIC_API_KEY": "sk-claude",
            }
        )
        is False
    )


def test_runtime_keeps_explicit_custom_anthropic_wire_provider() -> None:
    selected = ProviderConfig(
        model="glm-5",
        api_key="sk-glm-claude-mode",
        provider_name="glm-claude-mode",
        model_key="glm_claude_mode_glm_5",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://open.bigmodel.cn/api/anthropic",
        raw_provider={"base_url": "https://open.bigmodel.cn/api/anthropic"},
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    config = provider_catalog_selection_runtime.load_provider_config(
        cwd=None,
        env_overrides={"AGENT_CLI_PROVIDER": "glm-claude-mode"},
        load_provider_inputs_fn=lambda **_: (
            ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
            {"model_provider": "openai", "model": "gpt-5.4"},
            {},
        ),
        select_provider_config_fn=lambda **_: selected,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        infer_planner_kind_fn=lambda provider_name, model, base_url, provider_block: "anthropic_messages",
        should_use_claude_provider_fn=lambda **_: True,
        project_claude_home_dir_fn=lambda: Path("/tmp/.claude"),
        load_claude_provider_config_fn=lambda **_: claude_config,
    )

    assert config is selected


def test_runtime_keeps_configured_custom_anthropic_wire_provider() -> None:
    selected = ProviderConfig(
        model="glm-5",
        api_key="sk-glm-claude-mode",
        provider_name="glm-claude-mode",
        model_key="glm_claude_mode_glm_5",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://open.bigmodel.cn/api/anthropic",
        raw_provider={"base_url": "https://open.bigmodel.cn/api/anthropic"},
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    config = provider_catalog_selection_runtime.load_provider_config(
        cwd=None,
        env_overrides={},
        load_provider_inputs_fn=lambda **_: (
            ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
            {"model_provider": "glm-claude-mode", "model": "glm_claude_mode_glm_5"},
            {},
        ),
        select_provider_config_fn=lambda **_: selected,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        infer_planner_kind_fn=lambda provider_name, model, base_url, provider_block: "anthropic_messages",
        should_use_claude_provider_fn=lambda **_: True,
        project_claude_home_dir_fn=lambda: Path("/tmp/.claude"),
        load_claude_provider_config_fn=lambda **_: claude_config,
    )

    assert config is selected


def test_runtime_keeps_explicit_anthropic_provider_with_proxy_base_url() -> None:
    selected = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-anthropic-proxy",
        provider_name="anthropic",
        model_key="claude_sonnet_46",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example.com/anthropic",
        source="agent_cli_home",
        raw_provider={"base_url": "https://relay.example.com/anthropic"},
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude-home",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
        source="claude_home",
    )

    config = provider_catalog_selection_runtime.load_provider_config(
        cwd=None,
        env_overrides={},
        load_provider_inputs_fn=lambda **_: (
            ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=False,
            ),
            {"model_provider": "anthropic", "model": "claude_sonnet_46"},
            {},
        ),
        select_provider_config_fn=lambda **_: selected,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        infer_planner_kind_fn=lambda provider_name, model, base_url, provider_block: "anthropic_messages",
        should_use_claude_provider_fn=lambda **_: True,
        project_claude_home_dir_fn=lambda: Path("/tmp/.claude"),
        load_claude_provider_config_fn=lambda **_: claude_config,
    )

    assert config is selected


def test_runtime_keeps_explicit_anthropic_model_selection_without_proxy_base_url() -> None:
    selected = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-anthropic-official",
        provider_name="anthropic",
        model_key="claude_sonnet_46",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        source="project_local",
        raw_model={"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
    )
    claude_config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude-home",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
        source="claude_home",
    )

    config = provider_catalog_selection_runtime.load_provider_config(
        cwd=None,
        env_overrides={},
        load_provider_inputs_fn=lambda **_: (
            ProviderPathResolution(
                config_path=Path("/tmp/config.toml"),
                auth_path=Path("/tmp/auth.json"),
                config_exists=True,
                auth_exists=True,
                used_project_local=True,
            ),
            {"model": "claude_sonnet_46"},
            {},
        ),
        select_provider_config_fn=lambda **_: selected,
        optional_bool_fn=lambda value, default=False: default if value is None else bool(value),
        infer_planner_kind_fn=lambda provider_name, model, base_url, provider_block: "anthropic_messages",
        should_use_claude_provider_fn=lambda **_: True,
        project_claude_home_dir_fn=lambda: Path("/tmp/.claude"),
        load_claude_provider_config_fn=lambda **_: claude_config,
    )

    assert config is selected


def test_anthropic_messages_session_sends_tools_and_normalizes_tool_results() -> None:
    messages_api = _FakeAnthropicMessages(
        [
            SimpleNamespace(
                id="msg_1",
                content=[
                    _text_block("先读取文件"),
                    _tool_use_block("toolu_1", "file_read", {"path": "README.md"}),
                ],
            ),
            SimpleNamespace(
                id="msg_2",
                content=[_text_block("已经完成")],
            ),
        ]
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[
            {"name": "file_read", "description": "Read a file", "input_schema": {"type": "object"}}
        ],
        supports_tools=True,
        max_tokens=2048,
    )

    first = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "read README"}],
            }
        ],
        allow_tools=True,
    )

    tool_items = session.build_tool_result_items(
        call_id="toolu_1",
        command_text="/file_read README.md",
        assistant_text="执行完成",
        events=[],
    )
    second = session.send(input_items=tool_items, allow_tools=True)

    assert first.output_text == "先读取文件"
    assert len(first.tool_calls) == 1
    assert first.tool_calls[0].name == "file_read"
    assert first.tool_calls[0].arguments == {"path": "README.md"}
    assert messages_api.requests[0]["system"] == "You are AgentHub."
    assert messages_api.requests[0]["tool_choice"] == {"type": "auto"}
    assert messages_api.requests[0]["tools"][0]["name"] == "file_read"
    assert messages_api.requests[0]["max_tokens"] == 2048

    tool_result_message = messages_api.requests[1]["messages"][-1]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["type"] == "tool_result"
    assert tool_result_message["content"][0]["tool_use_id"] == "toolu_1"
    assert tool_result_message["content"][0]["content"][0]["text"] == "执行完成"
    assert second.output_text == "已经完成"


def test_anthropic_multiturn_replay_keeps_tool_use_before_tool_result() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_read_1",
        timestamp="2026-04-15T00:00:00+00:00",
        user_text="Read f.txt and tell me the current content.",
        assistant_text="文件内容为：original",
        assistant_history_text="文件内容为：original",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "function_call_output",
                    "call_id": "toolu_read_1",
                    "output": "L1: original",
                    "success": True,
                }
            ),
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "文件内容为：original"}],
                }
            ),
        ],
        tool_events=[
            ToolEvent(
                name="read_file",
                ok=True,
                summary="读取完成",
                payload={
                    "provider_call_id": "toolu_read_1",
                    "arguments": {"file_path": "/tmp/f.txt"},
                },
            )
        ],
    )

    replay_items = thread_store_replay.planner_input_items_from_turns(
        [turn], planner_history_limit=8
    )
    _, messages = AnthropicMessagesSession._normalize_messages(replay_items)

    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[1]["content"][0]["id"] == "toolu_read_1"
    assert messages[2]["content"][0]["type"] == "tool_result"
    assert messages[2]["content"][0]["tool_use_id"] == "toolu_read_1"


def test_anthropic_multiturn_replay_groups_consecutive_tool_uses_into_one_assistant_message() -> (
    None
):
    replay_items = [
        {"type": "message", "role": "user", "content": "Read a.txt and b.txt."},
        {
            "type": "function_call",
            "call_id": "toolu_read_a",
            "name": "read_file",
            "arguments": {"file_path": "/tmp/a.txt"},
        },
        {
            "type": "function_call",
            "call_id": "toolu_read_b",
            "name": "read_file",
            "arguments": {"file_path": "/tmp/b.txt"},
        },
        {
            "type": "function_call_output",
            "call_id": "toolu_read_a",
            "output": "A: alpha",
            "success": True,
        },
        {
            "type": "function_call_output",
            "call_id": "toolu_read_b",
            "output": "B: beta",
            "success": True,
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "a.txt 是 alpha，b.txt 是 beta。"}],
        },
        {"type": "message", "role": "user", "content": "Now summarize both files."},
    ]

    _, messages = AnthropicMessagesSession._normalize_messages(replay_items)

    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert [block["type"] for block in messages[1]["content"]] == ["tool_use", "tool_use"]
    assert [block["id"] for block in messages[1]["content"]] == ["toolu_read_a", "toolu_read_b"]
    assert [block["type"] for block in messages[2]["content"]] == ["tool_result", "tool_result"]
    assert [block["tool_use_id"] for block in messages[2]["content"]] == [
        "toolu_read_a",
        "toolu_read_b",
    ]
    assert messages[3]["content"] == [{"type": "text", "text": "a.txt 是 alpha，b.txt 是 beta。"}]
    assert messages[4]["content"] == [{"type": "text", "text": "Now summarize both files."}]


def test_anthropic_tool_specs_keep_function_web_search_by_default_in_main_loop() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        ),
        _host_platform(),
    )

    web_search_spec = next(spec for spec in specs if spec.get("name") == "web_search")
    assert "input_schema" in web_search_spec
    assert web_search_spec.get("type") != "web_search_20250305"


def test_anthropic_tool_specs_project_claude_delegation_surface_to_agent_and_send_message() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
        _host_platform(),
    )

    names = [spec.get("name") for spec in specs]
    assert "Agent" in names
    assert "SendMessage" in names
    assert "spawn_agent" not in names
    assert "send_input" not in names
    assert "resume_agent" not in names
    assert "wait_agent" not in names
    assert "agent_workflow" not in names
    assert "recover_agent" not in names
    assert "close_agent" not in names

    agent_spec = next(spec for spec in specs if spec.get("name") == "Agent")
    assert agent_spec["input_schema"]["required"] == ["description", "prompt"]
    agent_properties = agent_spec["input_schema"]["properties"]
    assert "run_in_background" in agent_properties
    assert "subagent_type" in agent_properties
    assert agent_properties["subagent_type"]["enum"] == ["Explore"]
    assert "English task label" in agent_properties["description"]["description"]
    assert "Write this prompt in English" in agent_properties["prompt"]["description"]
    assert agent_properties["model"]["enum"] == ["sonnet", "opus", "haiku"]
    assert "provider" not in agent_properties
    assert "reasoning_effort" not in agent_properties
    assert "timeout" not in agent_properties
    assert "Available agent types are listed in <system-reminder>" in agent_spec["description"]
    assert "not visible to the user" in agent_spec["description"]
    assert "concise report with an explicit length bound" in agent_spec["description"]
    assert "description and prompt in English" in agent_spec["description"]
    send_message_spec = next(spec for spec in specs if spec.get("name") == "SendMessage")
    assert send_message_spec["input_schema"]["required"] == ["to", "message"]

    bash_spec = next(spec for spec in specs if spec.get("name") == "Bash")
    assert "File search: Use Glob (NOT find or ls)" in bash_spec["description"]
    assert "multiple Bash tool calls in a single message" in bash_spec["description"]


def test_anthropic_claude_agent_listing_is_available_as_system_reminder_input_item() -> None:
    items = builtin_agent_profiles_runtime.with_agent_listing_input_item(
        [{"type": "message", "role": "user", "content": "seed"}],
        tool_surface_profile="claude_code",
    )

    assert items[0]["role"] == "user"
    reminder = items[0]["content"][0]["text"]
    assert reminder.startswith("<system-reminder>")
    assert "Available agent types for the Agent tool:" in reminder
    assert "- Explore:" in reminder
    assert items[1] == {"type": "message", "role": "user", "content": "seed"}


def test_anthropic_claude_explore_profile_filters_child_tool_specs() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
        _host_platform(),
    )

    filtered = builtin_agent_profiles_runtime.filter_tool_specs_for_profile(
        specs,
        subagent_type="Explore",
    )
    names = {str(spec.get("name") or "") for spec in filtered}

    assert {"Bash", "Glob", "Grep", "Read", "WebSearch", "WebFetch"}.issubset(names)
    assert "Agent" not in names
    assert "SendMessage" not in names
    assert "Write" not in names
    assert "Edit" not in names
    assert "AskUserQuestion" not in names
    assert "update_plan" not in names
    assert "write_stdin" not in names


def test_anthropic_tool_specs_project_claude_file_tool_path_guidance_to_cwd() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
        _host_platform(),
    )

    by_name = {spec.get("name"): spec for spec in specs}
    glob_description = by_name["Glob"]["description"]
    grep_description = by_name["Grep"]["description"]
    read_description = by_name["Read"]["description"]
    glob_path = by_name["Glob"]["input_schema"]["properties"]["path"]["description"]
    grep_path = by_name["Grep"]["input_schema"]["properties"]["path"]["description"]
    read_file_path = by_name["Read"]["input_schema"]["properties"]["file_path"]["description"]

    assert "open-ended searches" in glob_description
    assert "Agent tool" in glob_description
    assert "open-ended searches" in grep_description
    assert "Agent tool" in grep_description
    assert "current working directory" in glob_path
    assert "omit" in glob_path.lower()
    assert "current working directory" in grep_path
    assert "omit" in grep_path.lower()
    assert "active workspace" in read_file_path
    assert "only read files, not directories" in read_description
    assert "ls command via the Bash tool" in read_description


def test_anthropic_command_builder_normalizes_projected_claude_delegation_names() -> None:
    host_platform = _host_platform()

    agent_command = _command_for_tool_call(
        "Agent",
        {
            "prompt": "运行 benchmark 收集 provider 延迟数据",
            "run_in_background": True,
        },
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    send_message_command = _command_for_tool_call(
        "SendMessage",
        {
            "to": "agent_1",
            "message": "继续检查",
        },
        host_platform,
        plugin_manager_factory=lambda: None,
    )

    assert agent_command == (
        '/spawn_agent \'{"task": "\\u8fd0\\u884c benchmark \\u6536\\u96c6 provider \\u5ef6\\u8fdf\\u6570\\u636e", '
        '"async": true, "reason": "long_running_exec", "mode": "background", "wait_required": false, "task_shape": "long_running"}\''
    )
    assert send_message_command == "/send_input agent_1 '继续检查'"


def test_anthropic_command_builder_maps_claude_explore_agent_to_read_only_research() -> None:
    host_platform = _host_platform()

    agent_command = _command_for_tool_call(
        "Agent",
        {
            "description": "Quick codebase overview",
            "subagent_type": "Explore",
            "prompt": "看看项目能力",
        },
        host_platform,
        plugin_manager_factory=lambda: None,
    )

    assert agent_command is not None
    argv = shlex.split(agent_command)
    assert argv[0] == "/spawn_agent"
    payload = json.loads(argv[1])
    assert payload == {
        "task": "看看项目能力",
        "role": "subagent",
        "reason": "research_side_task",
        "mode": "sync",
        "wait_required": False,
        "task_shape": "read_only",
        "subagent_type": "Explore",
    }


def test_anthropic_tool_specs_expose_native_web_search_in_main_loop_when_mixed_tools_supported() -> (
    None
):
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            raw_model={"native_web_search_mixed_tools": True},
        ),
        _host_platform(),
    )

    web_search_spec = next(spec for spec in specs if spec.get("name") == "web_search")
    assert web_search_spec["type"] == "web_search_20250305"
    assert web_search_spec["max_uses"] == 8


def test_anthropic_tool_specs_do_not_expose_native_web_search_for_generic_wire_compat() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="glm-5",
            api_key="sk-glm",
            provider_name="glm-claude-mode",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        ),
        _host_platform(),
    )

    web_search_spec = next(spec for spec in specs if spec.get("name") == "web_search")
    assert "input_schema" in web_search_spec
    assert web_search_spec.get("type") != "web_search_20250305"


def test_anthropic_native_web_search_detection_ignores_generic_anthropic_wire_compat() -> None:
    assert supports_anthropic_native_web_search(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )
    )
    assert not supports_anthropic_native_web_search(
        ProviderConfig(
            model="glm-5",
            api_key="sk-glm",
            provider_name="glm-claude-mode",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )
    )
    assert supports_anthropic_native_web_search(
        ProviderConfig(
            model="glm-5",
            api_key="sk-glm",
            provider_name="glm-claude-mode",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            raw_model={"native_web_search": True},
        )
    )


def test_anthropic_native_web_search_mixed_tools_requires_explicit_opt_in() -> None:
    assert not supports_anthropic_native_web_search_mixed_tools(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )
    )
    assert supports_anthropic_native_web_search_mixed_tools(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            raw_model={"native_web_search_mixed_tools": True},
        )
    )


def test_native_web_search_payload_parses_server_side_blocks() -> None:
    class _FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict] = []
            self.messages = self

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return SimpleNamespace(
                id="msg_native_1",
                content=[
                    _server_tool_use_block("srvtoolu_1", "web_search", {"query": "北京天气"}),
                    SimpleNamespace(
                        type="web_search_tool_result",
                        tool_use_id="srvtoolu_1",
                        content=[
                            {
                                "type": "web_search_result",
                                "title": "北京天气预报",
                                "url": "https://weather.example.com/beijing",
                                "encrypted_content": "今天多云，10-20°C。",
                                "page_age": None,
                            }
                        ],
                    ),
                    _text_block("北京今天多云，10-20°C。"),
                ],
            )

    fake_client = _FakeClient()

    with patch(
        "cli.agent_cli.providers.anthropic_native_web_search_runtime._build_client",
        return_value=fake_client,
    ):
        payload = native_web_search_payload(
            ProviderConfig(
                model="claude-sonnet-4-6",
                api_key="sk-claude",
                provider_name="anthropic",
                planner_kind="anthropic_messages",
                wire_api="anthropic_messages",
            ),
            query="北京天气怎么样",
            limit=5,
            domains=["weather.example.com"],
        )

    assert payload["ok"] is True
    assert payload["engine"] == "anthropic_native_web_search"
    assert payload["text"] == "北京今天多云，10-20°C。"
    assert payload["server_tool_uses"] == ["web_search"]
    assert payload["response_block_types"] == ["server_tool_use", "web_search_tool_result", "text"]
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["results"][0]["title"] == "北京天气预报"
    assert payload["results"][0]["source_domain"] == "weather.example.com"
    assert fake_client.requests[0]["tools"][0]["allowed_domains"] == ["weather.example.com"]
    assert fake_client.requests[0]["tool_choice"] == {"type": "tool", "name": "web_search"}


def test_anthropic_messages_session_ignores_server_tool_use_as_local_tool_call() -> None:
    messages_api = _FakeAnthropicMessages(
        [
            SimpleNamespace(
                id="msg_server_1",
                content=[
                    _text_block("先搜索一下。"),
                    _server_tool_use_block(
                        "srvtoolu_1", "web_search", {"search_query": "北京天气"}
                    ),
                    _tool_result_block(
                        "srvtoolu_1", [{"title": "北京天气", "url": "https://weather.example.com"}]
                    ),
                    _text_block("北京今天多云，10-20°C。"),
                ],
                usage=SimpleNamespace(server_tool_use=SimpleNamespace(web_search_requests=1)),
            ),
        ]
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        supports_tools=True,
    )

    result = session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "北京天气怎么样"}],
            }
        ],
        allow_tools=True,
    )

    assert result.output_text == "先搜索一下。\n北京今天多云，10-20°C。"
    assert result.tool_calls == []
    assert result.trace["server_tool_uses"] == ["web_search"]
    assert result.trace["server_tool_use_count"] == 1
    assert session._messages[-1]["content"][1]["type"] == "server_tool_use"
    assert session._messages[-1]["content"][2]["type"] == "tool_result"


def test_handle_web_search_prefers_anthropic_native_runtime_path() -> None:
    class _Tools:
        def __init__(self) -> None:
            self.last_provider_config = None

        def web_search_result(
            self, query, *, limit=5, domains=None, recency_days=None, market=None
        ):
            del query, limit, domains, recency_days, market
            self.last_provider_config = self._web_search_provider_config_factory()
            return CommandExecutionResult(
                assistant_text="Search the web.",
                tool_events=[
                    ToolEvent(
                        name="web_search",
                        ok=True,
                        summary="web results=2",
                        payload={
                            "ok": True,
                            "count": 2,
                            "engine": "anthropic_native_web_search",
                        },
                    )
                ],
            )

        def web_search(self, *args, **kwargs):
            raise AssertionError("local web_search should not run")

    class _Runtime:
        def __init__(self) -> None:
            self.tools = _Tools()
            self.agent = SimpleNamespace(
                _planner=SimpleNamespace(
                    config=ProviderConfig(
                        model="claude-sonnet-4-6",
                        api_key="sk-claude",
                        provider_name="anthropic",
                        planner_kind="anthropic_messages",
                        wire_api="anthropic_messages",
                    )
                )
            )

        @staticmethod
        def _parse_args(arg_text: str):
            return [arg_text], {}

        @staticmethod
        def web_search_enabled() -> bool:
            return True

        @staticmethod
        def web_access_allowed() -> bool:
            return True

    def _single_event_result(message: str, event: SimpleNamespace | object, *, arguments=None):
        del message, arguments
        return CommandExecutionResult(assistant_text="", tool_events=[event])

    with patch(
        "cli.agent_cli.runtime_core.tool_commands_helpers.native_web_search_payload",
        return_value={
            "ok": True,
            "engine": "anthropic_native_web_search",
            "query": "北京天气",
            "count": 2,
            "results": [
                {
                    "rank": 1,
                    "title": "北京天气预报",
                    "url": "https://weather.example.com",
                    "source_domain": "weather.example.com",
                }
            ],
            "text": "北京今天多云。",
            "assistant_text": "北京今天多云。",
            "server_tool_uses": ["web_search"],
        },
    ):
        result = handle_web_search(
            _Runtime(),
            arg_text="北京天气",
            call_structured=lambda target, method_name, *args, **kwargs: getattr(
                target, method_name
            )(*args, **kwargs),
            single_event_result=_single_event_result,
            text_only_result=lambda text: CommandExecutionResult(assistant_text=text),
            command_usage_text=lambda name: name,
        )

    assert isinstance(result, CommandExecutionResult)
    assert result.tool_events
    assert result.tool_events[0].payload["engine"] == "anthropic_native_web_search"
    assert result.tool_events[0].summary == "web results=2"


def test_handle_web_search_deepseek_falls_back_to_local_runtime_path() -> None:
    class _Tools:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            self.calls.append(
                {
                    "query": query,
                    "limit": limit,
                    "domains": domains,
                    "recency_days": recency_days,
                    "market": market,
                }
            )
            return ToolEvent(
                name="web_search",
                ok=True,
                summary="web results=1",
                payload={"ok": True, "count": 1, "engine": "local_web_search"},
            )

    class _Runtime:
        def __init__(self) -> None:
            self.tools = _Tools()
            self.agent = SimpleNamespace(
                _planner=SimpleNamespace(
                    config=ProviderConfig(
                        model="deepseek-chat",
                        api_key="sk-deepseek",
                        provider_name="deepseek",
                        planner_kind="deepseek_chat",
                        wire_api="openai_chat",
                    )
                )
            )

        @staticmethod
        def _parse_args(arg_text: str):
            return [arg_text], {}

        @staticmethod
        def web_search_enabled() -> bool:
            return True

        @staticmethod
        def web_access_allowed() -> bool:
            return True

    def _single_event_result(message: str, event: SimpleNamespace | object, *, arguments=None):
        del message, arguments
        return CommandExecutionResult(assistant_text="", tool_events=[event])

    runtime = _Runtime()
    with patch(
        "cli.agent_cli.runtime_core.tool_commands_helpers.native_web_search_payload",
        side_effect=AssertionError("anthropic native payload must not run for deepseek"),
    ):
        result = handle_web_search(
            runtime,
            arg_text="北京天气",
            call_structured=lambda *args, **kwargs: None,
            single_event_result=_single_event_result,
            text_only_result=lambda text: CommandExecutionResult(assistant_text=text),
            command_usage_text=lambda name: name,
        )

    assert isinstance(result, CommandExecutionResult)
    assert runtime.tools.calls == [
        {
            "query": "北京天气",
            "limit": 5,
            "domains": None,
            "recency_days": None,
            "market": None,
        }
    ]
    assert result.tool_events[0].payload["engine"] == "local_web_search"


def test_anthropic_messages_session_merges_developer_messages_into_system() -> None:
    messages_api = _FakeAnthropicMessages(
        [SimpleNamespace(id="msg_1", content=[_text_block("你好")])]
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="base system",
        tool_specs=[],
        supports_tools=False,
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "dev rules"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "你好"}],
            },
        ],
        allow_tools=False,
    )

    assert messages_api.requests[0]["system"] == "base system\n\ndev rules"
    assert messages_api.requests[0]["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "你好"}]}
    ]


def test_anthropic_messages_session_logs_request_and_response_raw(
    monkeypatch, tmp_path: Path
) -> None:
    timeline_path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("AGENTHUB_DEBUG_RESPONSES_TIMELINE", str(timeline_path))
    monkeypatch.delenv("AGENTHUB_DEBUG_LOG_DIR", raising=False)

    messages_api = _FakeAnthropicMessages(
        [SimpleNamespace(id="msg_log_1", content=[_text_block("こんにちは")])]
    )
    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=messages_api),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
    )

    session.send(
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "日语回答"}],
            }
        ],
        allow_tools=False,
    )

    llm_rows = _read_jsonl(tmp_path / "llm_io.jsonl")
    stages = [row["stage"] for row in llm_rows]

    assert "anthropic_messages.request_raw" in stages
    assert "anthropic_messages.response_raw" in stages
    request_row = next(row for row in llm_rows if row["stage"] == "anthropic_messages.request_raw")
    response_row = next(
        row for row in llm_rows if row["stage"] == "anthropic_messages.response_raw"
    )
    assert request_row["payload"]["request"]["model"] == "claude-sonnet-4-6"
    assert request_row["payload"]["message_count"] == 1
    assert response_row["payload"]["response_id"] == "msg_log_1"


def test_build_planner_returns_anthropic_planner() -> None:
    from cli.agent_cli.provider import build_planner

    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        base_url="https://relay.example/claudecode",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = build_planner(config)

    assert isinstance(planner, AnthropicClaudePlanner)


def test_anthropic_planner_defaults_to_claude_code_interaction_profile_when_unspecified() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    assert planner.resolved_interaction_contract.profile == "claude_code"
    assert planner.resolved_interaction_contract.source == "planner.anthropic_default"
    assert (
        planner.resolved_interaction_contract.turn_protocol_policy
        == "anthropic_messages_turn_items"
    )
    assert planner.config.interaction_profile == "claude_code"
    assert planner.config.interaction_profile_source == "planner.anthropic_default"


def test_anthropic_planner_accepts_explicit_claude_code_profile() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="model.interaction_profile",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    assert planner.resolved_interaction_contract.profile == "claude_code"
    assert planner.resolved_interaction_contract.source == "model.interaction_profile"


def test_anthropic_planner_prompt_honors_disabled_web_search_surface() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        raw_provider={"web_search_mode": "disabled"},
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    assert (
        "Do not promise live web lookup unless web_search is actually exposed in this session."
        in planner.system_prompt
    )


def test_anthropic_planner_uses_reference_unbounded_turn_engine_rounds() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude_helpers.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    expected_intent = SimpleNamespace(assistant_text="final")
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = expected_intent

    with (
        patch.object(planner, "_build_session", return_value=SimpleNamespace()) as build_session,
        patch(
            "cli.agent_cli.providers.anthropic_claude_helpers.TurnEngine",
            return_value=turn_engine_instance,
        ) as turn_engine_cls,
    ):
        intent = planner.plan("继续整理全链路", [], tool_executor=lambda _command_text: ("ok", []))

    assert intent is expected_intent
    build_session.assert_called_once()
    turn_engine_cls.assert_called_once()
    assert turn_engine_cls.call_args.kwargs["max_rounds"] is None
    assert callable(turn_engine_cls.call_args.kwargs["followup_handler"])
    assert callable(turn_engine_cls.call_args.kwargs["terminal_handler"])
    turn_engine_instance.run.assert_called_once()


def test_anthropic_planner_explore_profile_filters_tools_without_agent_listing() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude_helpers.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    session = SimpleNamespace(
        tool_specs=[
            {"name": "Agent", "description": "delegate", "input_schema": {"type": "object"}},
            {"name": "Write", "description": "write", "input_schema": {"type": "object"}},
            {"name": "Read", "description": "read", "input_schema": {"type": "object"}},
        ]
    )
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = AgentIntent(assistant_text="done")

    with (
        patch.object(planner, "_build_session", return_value=session),
        patch(
            "cli.agent_cli.providers.anthropic_claude_helpers.TurnEngine",
            return_value=turn_engine_instance,
        ),
    ):
        planner.plan(
            "看看项目能力",
            [],
            tool_executor=lambda _command_text: ("ok", []),
            subagent_type="Explore",
        )

    assert [spec["name"] for spec in session.tool_specs] == ["Read"]
    initial_input = turn_engine_instance.run.call_args.kwargs["initial_input"]
    rendered = json.dumps(initial_input, ensure_ascii=False)
    assert "Available agent types for the Agent tool" not in rendered


def test_anthropic_planner_explore_request_matches_child_profile_surface() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )
    messages_api = _FakeAnthropicMessages(
        [SimpleNamespace(id="msg_explore_1", content=[_text_block("ok")])]
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude_helpers.build_anthropic_client",
        return_value=SimpleNamespace(messages=messages_api),
    ):
        planner = AnthropicClaudePlanner(config)

    intent = planner.plan(
        "看看项目能力",
        [],
        tool_executor=lambda _command_text: ("ok", []),
        input_items=builtin_agent_profiles_runtime.profile_instruction_items("Explore"),
        subagent_type="Explore",
    )

    assert intent.assistant_text == "ok"
    request = messages_api.requests[0]
    names = {str(spec.get("name") or "") for spec in request["tools"]}
    assert {"Bash", "Glob", "Grep", "Read"}.issubset(names)
    assert "Agent" not in names
    assert "SendMessage" not in names
    assert "Write" not in names
    assert "Edit" not in names
    assert request["system"].startswith("You are a file search specialist")
    assert "READ-ONLY MODE" in request["system"]
    assert "You are AgentHub" not in request["system"]
    assert "Available agent types for the Agent tool" not in json.dumps(
        request["messages"],
        ensure_ascii=False,
    )


def test_anthropic_planner_terminal_handler_runs_final_synthesis_without_tools() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude_helpers.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    session = MagicMock()
    session.send.return_value = SimpleNamespace(
        output_text="综合结论",
        response_items=[],
    )
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = SimpleNamespace(assistant_text="final")

    with (
        patch.object(planner, "_build_session", return_value=session),
        patch(
            "cli.agent_cli.providers.anthropic_claude_helpers.TurnEngine",
            return_value=turn_engine_instance,
        ) as turn_engine_cls,
    ):
        planner.plan("继续整理全链路", [], tool_executor=lambda _command_text: ("ok", []))

    terminal_handler = turn_engine_cls.call_args.kwargs["terminal_handler"]
    intent = terminal_handler(
        "继续整理全链路",
        [ToolEvent(name="read_file", ok=True, summary="file loaded", payload={"path": "foo.py"})],
        [],
        None,
        [{"type": "function_call_output", "call_id": "call_1", "output": "ok", "success": True}],
    )

    session.send.assert_called_once()
    call = session.send.call_args.kwargs
    assert call["allow_tools"] is False
    assert call["turn_event_callback"] is None
    assert call["input_items"][0] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "ok",
        "success": True,
    }
    assert call["input_items"][-1]["type"] == "message"
    assert call["input_items"][-1]["role"] == "user"
    assert "不要继续搜索，不要调用任何工具" in call["input_items"][-1]["content"]
    assert (
        "请把你刚才实际使用的工具名和关键参数当作简短示例写出来"
        in call["input_items"][-1]["content"]
    )
    assert intent.assistant_text == "综合结论"
    assert intent.status_hint == "tool"
    assert intent.timings["synthesis_rounds"] == 1


def test_anthropic_planner_appends_real_tool_examples_for_demo_requests() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude_helpers.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        planner = AnthropicClaudePlanner(config)

    engine_result = AgentIntent(
        assistant_text="两个工具的结果：先用 Glob 找文件，再用 Grep 看谁引用了它。",
        response_items=default_response_items(
            assistant_text="两个工具的结果：先用 Glob 找文件，再用 Grep 看谁引用了它。"
        ),
        status_hint="tool",
        turn_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_final",
                    "type": "agent_message",
                    "text": "两个工具的结果：先用 Glob 找文件，再用 Grep 看谁引用了它。",
                    "phase": "final_answer",
                },
            }
        ],
        tool_events=[
            ToolEvent(
                name="glob_files",
                ok=True,
                summary="files=1",
                payload={
                    "function_call_name": "Glob",
                    "function_call_arguments": {
                        "pattern": "**/AGENTHUB_NATIVE_INTERACTION_MODE_DESIGN.md",
                        "path": "/home/lyc/project/AgentHub",
                    },
                },
            ),
            ToolEvent(
                name="grep_files",
                ok=True,
                summary="paths=7",
                payload={
                    "function_call_name": "Grep",
                    "function_call_arguments": {
                        "pattern": "AGENTHUB_NATIVE_INTERACTION_MODE_DESIGN",
                        "path": "/home/lyc/project/AgentHub",
                        "output_mode": "files_with_matches",
                    },
                },
            ),
        ],
    )
    turn_engine_instance = MagicMock()
    turn_engine_instance.run.return_value = engine_result

    with (
        patch.object(planner, "_build_session", return_value=SimpleNamespace()),
        patch(
            "cli.agent_cli.providers.anthropic_claude_helpers.TurnEngine",
            return_value=turn_engine_instance,
        ),
    ):
        intent = planner.plan(
            "你示范一下2个工具都怎么用 GREP GLOB",
            [],
            tool_executor=lambda _command_text: ("ok", []),
        )

    assert "本次实际示例：" in intent.assistant_text
    assert (
        'Glob(pattern="**/AGENTHUB_NATIVE_INTERACTION_MODE_DESIGN.md", path="/home/lyc/project/AgentHub")'
        in intent.assistant_text
    )
    assert (
        'Grep(pattern="AGENTHUB_NATIVE_INTERACTION_MODE_DESIGN", path="/home/lyc/project/AgentHub", output_mode="files_with_matches")'
        in intent.assistant_text
    )
    assert "本次实际示例：" in str(intent.response_items[-1].content[0]["text"])
    assert "本次实际示例：" in str(intent.turn_events[-1]["item"]["text"])


def test_anthropic_planner_rejects_explicit_incompatible_profile() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_claude.build_anthropic_client",
        return_value=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: None)),
    ):
        with pytest.raises(InteractionProfileCompatibilityError):
            AnthropicClaudePlanner(config)
