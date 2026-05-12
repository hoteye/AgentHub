from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli.agent_cli.providers.chat_completions_planner as chat_module
import cli.agent_cli.providers.openai_planner as openai_module
from cli.agent_cli.environment_context import (
    build_environment_context_snapshot,
    render_environment_context_update_message,
)
from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.models import (
    ReferenceContextItem,
    ResponseInputItem,
    TurnContextInputItem,
    TurnContextRollout,
)
from cli.agent_cli.provider import request_prelude_contract
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_resolution import (
    InteractionProfileCompatibilityError,
)
from cli.agent_cli.providers.system_prompts import (
    build_chat_completions_system_prompt,
    build_openai_json_system_prompt,
    build_openai_native_system_prompt,
    compose_system_prompt,
    load_agenthub_base_prompt,
    load_reference_base_prompt,
    system_prompt_contract,
)
from cli.agent_cli.providers.tool_specs import responses_minimal_provider_tool_specs
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy, render_permissions_instructions
from cli.agent_cli.workspace_context import (
    build_workspace_reference_context_item,
    build_workspace_reference_snapshot,
    render_workspace_reference_context_item_message,
)

_FIXED_DT = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


def _provider_config(
    *, planner_kind: str = "openai_responses", raw_model: dict | None = None
) -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="test-provider",
        planner_kind=planner_kind,
        raw_model=dict(raw_model or {}),
    )


def _host_platform(system_name: str = "Linux", sys_platform: str = "linux"):
    return detect_host_platform(system_name=system_name, sys_platform=sys_platform)


def _runtime() -> AgentCliRuntime:
    return AgentCliRuntime(
        runtime_policy=RuntimePolicy.normalized(
            approval_policy="never",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
        ),
        current_dt_provider=lambda: _FIXED_DT,
    )


def _workspace_snapshot(tmp_path, *, instructions: str = "workspace secret instructions") -> dict:
    (tmp_path / "AENGTHUB.md").write_text(instructions, encoding="utf-8")
    return build_workspace_reference_snapshot(tmp_path)


def _environment_snapshot(tmp_path) -> dict:
    return build_environment_context_snapshot(
        cwd=str(tmp_path),
        shell="bash",
        network_access=True,
        current_dt=_FIXED_DT,
    )


def _load_reference_capture_request() -> dict:
    base = Path(__file__).resolve().parents[2] / "docs" / "ab_acceptance"
    preferred = (
        base / "reference_logs" / "20260331_101505_reference_503_probe" / "turn1.timeline.jsonl"
    )
    candidates: list[Path] = []
    if preferred.exists():
        candidates.append(preferred)
    for logs_dir in sorted(
        path for path in base.iterdir() if path.is_dir() and path.name.endswith("_logs")
    ):
        candidates.extend(sorted(logs_dir.glob("*503_probe/turn1.timeline.jsonl")))
    for capture_path in candidates:
        for raw_line in capture_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(raw_line)
            if str(record.get("stage") or "").strip() == "stream_responses_api.request.raw":
                payload = record.get("payload")
                if isinstance(payload, dict):
                    return payload
    raise AssertionError("missing reference capture request payload")


def test_load_agenthub_base_prompt() -> None:
    prompt = load_agenthub_base_prompt()
    assert "AgentHub CLI" in prompt
    assert "Respond in concise Chinese" in prompt


def test_compose_system_prompt_skips_empty_sections() -> None:
    prompt = compose_system_prompt("first", "", " second ", None)
    assert prompt == "first\n\nsecond"


def test_system_prompt_contract_has_no_runtime_leakage() -> None:
    contract = system_prompt_contract(load_agenthub_base_prompt())
    assert contract["section_count"] >= 4
    assert contract["contains_environment_context"] is False
    assert contract["contains_permissions_instructions"] is False
    assert contract["contains_runtime_leakage"] is False


def test_platform_variants_share_same_base_prompt_and_keep_runtime_out() -> None:
    base_prompt = load_agenthub_base_prompt()
    platforms = [
        _host_platform("Linux", "linux"),
        _host_platform("Darwin", "darwin"),
        _host_platform("Windows", "win32"),
    ]
    for host_platform in platforms:
        prompts = [
            build_openai_json_system_prompt(host_platform=host_platform),
            build_openai_native_system_prompt(host_platform=host_platform),
            build_chat_completions_system_prompt(host_platform=host_platform),
        ]
        for prompt in prompts:
            assert prompt.startswith(base_prompt)
            contract = system_prompt_contract(prompt)
            assert contract["contains_environment_context"] is False
            assert contract["contains_permissions_instructions"] is False
            assert contract["contains_runtime_leakage"] is False


def test_planners_share_same_base_prompt(monkeypatch) -> None:
    monkeypatch.setattr(openai_module, "build_openai_client", lambda *args, **kwargs: object())
    monkeypatch.setattr(chat_module, "build_openai_client", lambda *args, **kwargs: object())
    host_platform = _host_platform()
    base_prompt = load_agenthub_base_prompt()

    openai_planner = openai_module.OpenAIPlanner(
        _provider_config(),
        host_platform=host_platform,
        plugin_manager_factory=lambda: None,
    )
    chat_planner = chat_module.ChatCompletionsPlanner(
        _provider_config(planner_kind="deepseek_chat"),
        host_platform=host_platform,
        plugin_manager_factory=lambda: None,
    )

    assert openai_planner.system_prompt.startswith(base_prompt)
    assert openai_planner.native_tool_system_prompt.startswith(base_prompt)
    assert chat_planner.system_prompt.startswith(base_prompt)


def test_runtime_prelude_contract_orders_developer_workspace_environment(tmp_path) -> None:
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)

    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )
    contract = request_prelude_contract(prelude_items)

    assert contract["section_order"] == ["developer", "workspace_context", "environment_context"]
    assert contract["items"][0]["role"] == "developer"
    assert contract["items"][1]["item_type"] == "workspace_context"


def test_codex_openai_prelude_injects_existing_skills_as_developer_instructions(tmp_path) -> None:
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    runtime.agent._planner = SimpleNamespace(
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="test-provider",
            planner_kind="openai_responses",
            interaction_profile="codex_openai",
            interaction_profile_source="test",
        )
    )
    skill_dir = tmp_path / ".agents" / "skills" / "linting"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\nname: linting\ndescription: run clippy\n---\n# linting\nUse cargo clippy.\n",
        encoding="utf-8",
    )
    workspace_snapshot = build_workspace_reference_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)

    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    developer = prelude_items[0]
    assert developer["role"] == "developer"
    assert len(developer["content"]) == 2
    skills_text = developer["content"][1]["text"]
    assert skills_text.startswith("<skills_instructions>\n## Skills")
    assert "- linting: run clippy" in skills_text
    assert str(skill_path).replace("\\", "/") in skills_text
    assert skills_text.endswith("</skills_instructions>")


def test_generic_prelude_does_not_inject_skills_developer_block(tmp_path) -> None:
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    runtime.agent._planner = SimpleNamespace(
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="test-provider",
            planner_kind="openai_chat",
            wire_api="openai_chat",
            interaction_profile="generic_chat",
            interaction_profile_source="test",
        )
    )
    skill_dir = tmp_path / ".agents" / "skills" / "linting"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: linting\ndescription: run clippy\n---\n# linting\n",
        encoding="utf-8",
    )
    workspace_snapshot = build_workspace_reference_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)

    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    assert prelude_items[0]["role"] == "developer"
    assert len(prelude_items[0]["content"]) == 1


def test_codex_headless_prelude_uses_effective_never_approval_policy(tmp_path) -> None:
    runtime = _runtime()
    runtime.runtime_policy = RuntimePolicy.normalized(
        approval_policy="on-request",
        sandbox_mode="read-only",
        network_access_enabled=True,
    )
    runtime.set_cwd(tmp_path)
    runtime.agent._planner = SimpleNamespace(
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="test-provider",
            planner_kind="openai_responses",
            interaction_profile="codex_openai",
            interaction_profile_source="test",
        )
    )
    runtime._agenthub_headless_mode = "prompt"
    workspace_snapshot = _workspace_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)

    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    developer_text = str(prelude_items[0]["content"][0]["text"] or "")
    assert "Approval policy is currently never." in developer_text
    assert "How to request escalation" not in developer_text


def test_workspace_context_does_not_leak_into_system_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chat_module, "build_openai_client", lambda *args, **kwargs: object())
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path, instructions="workspace secret instructions")
    environment_snapshot = _environment_snapshot(tmp_path)
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    planner = chat_module.ChatCompletionsPlanner(
        _provider_config(planner_kind="deepseek_chat"),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    messages = planner._chat_messages_from_input_items(
        [
            *prelude_items,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "请检查项目"}],
            },
        ],
        system_prompt=planner.system_prompt,
    )

    assert "workspace secret instructions" not in messages[0]["content"]
    assert any(
        "workspace secret instructions" in str(message.get("content") or "")
        for message in messages[1:]
    )
    assert any(
        "<environment_context>" in str(message.get("content") or "") for message in messages[1:]
    )


def test_openai_json_request_preserves_prompt_layers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(openai_module, "build_openai_client", lambda *args, **kwargs: object())
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path, instructions="workspace secret instructions")
    environment_snapshot = _environment_snapshot(tmp_path)
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    planner = openai_module.OpenAIPlanner(
        _provider_config(),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    captured: dict = {}

    def _fake_collect_stream_text(**kwargs):
        captured.update(kwargs)
        return '{"assistant_text":"已检查","command_text":null,"status_hint":"llm"}'

    planner._collect_stream_text = _fake_collect_stream_text  # type: ignore[method-assign]
    intent = planner._plan_without_native_tools(
        "请检查项目",
        [],
        input_items=prelude_items,
    )

    assert intent.assistant_text == "已检查"
    assert captured["instructions"] == planner.system_prompt
    assert "workspace secret instructions" not in captured["instructions"]
    prelude_contract = request_prelude_contract(list(captured["input"])[: len(prelude_items)])
    assert prelude_contract["section_order"] == [
        "developer",
        "workspace_context",
        "environment_context",
    ]
    assert str(captured["input"][-1].get("role") or "") == "user"


def test_openai_json_request_keeps_flat_role_content_messages(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(openai_module, "build_openai_client", lambda *args, **kwargs: object())
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    planner = openai_module.OpenAIPlanner(
        _provider_config(),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    captured: dict = {}

    def _fake_collect_stream_text(**kwargs):
        captured.update(kwargs)
        return '{"assistant_text":"ok","command_text":null,"status_hint":"llm"}'

    planner._collect_stream_text = _fake_collect_stream_text  # type: ignore[method-assign]
    planner._plan_without_native_tools("继续", [], input_items=prelude_items)

    message_items = [
        item
        for item in list(captured["input"])
        if str(item.get("type") or "").strip() != "reference_context_item"
    ]
    assert message_items
    assert all("type" not in item for item in message_items)
    assert all(isinstance(item.get("content"), str) for item in message_items)
    assert message_items[0]["role"] == "developer"


def test_openai_json_second_turn_request_keeps_503_safe_structure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(openai_module, "build_openai_client", lambda *args, **kwargs: object())
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path)
    environment_snapshot = _environment_snapshot(tmp_path)
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )

    planner = openai_module.OpenAIPlanner(
        _provider_config(),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    captured: dict = {}

    def _fake_collect_stream_text(**kwargs):
        captured.update(kwargs)
        return '{"assistant_text":"北京时间 12:00","command_text":null,"status_hint":"llm"}'

    planner._collect_stream_text = _fake_collect_stream_text  # type: ignore[method-assign]
    planner._plan_without_native_tools(
        "现在北京时间几点",
        [
            {"role": "user", "content": "你帮我看看今天周几"},
            {"role": "assistant", "content": "今天是星期三。"},
        ],
        input_items=prelude_items,
    )

    prelude_contract = request_prelude_contract(list(captured["input"])[: len(prelude_items)])
    assert prelude_contract["section_order"] == [
        "developer",
        "workspace_context",
        "environment_context",
    ]

    message_items = [
        item
        for item in list(captured["input"])
        if str(item.get("type") or "").strip() != "reference_context_item"
    ]
    assert message_items
    assert all("type" not in item for item in message_items)
    assert all(isinstance(item.get("content"), str) for item in message_items)
    assert any(
        item.get("role") == "assistant" and item.get("content") == "今天是星期三。"
        for item in message_items
    )
    assert message_items[-1] == {"role": "user", "content": "现在北京时间几点"}


def test_replay_runtime_preserves_prompt_layers(tmp_path) -> None:
    runtime = _runtime()
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(tmp_path, instructions="workspace secret instructions")
    workspace_item = build_workspace_reference_context_item(None, workspace_snapshot)
    assert workspace_item is not None
    environment_snapshot = _environment_snapshot(tmp_path)
    environment_message = render_environment_context_update_message(None, environment_snapshot)
    assert environment_message is not None

    turn_context = TurnContextRollout(
        approval_policy="never",
        sandbox_mode="workspace-write",
        network_access_enabled=True,
        items=[
            TurnContextInputItem(
                source="environment_context",
                item=ResponseInputItem.from_dict(
                    {"type": "message", "role": "user", "content": environment_message}
                ),
            )
        ],
        reference_context_items=[ReferenceContextItem.from_dict(workspace_item)],
    )
    prelude_items = runtime._planner_turn_context_replay_items(turn_context)
    contract = request_prelude_contract(prelude_items)

    assert contract["section_order"] == ["developer", "workspace_context", "environment_context"]
    rendered_workspace = render_workspace_reference_context_item_message(workspace_item)
    assert rendered_workspace is not None and "workspace secret instructions" in rendered_workspace


def test_render_permissions_instructions_matches_reference_capture_for_danger_full_access_never() -> (
    None
):
    assert render_permissions_instructions(
        sandbox_mode="danger-full-access",
        approval_policy="never",
        network_access_enabled=True,
    ) == (
        "<permissions instructions>\n"
        "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `danger-full-access`: No filesystem sandboxing - all commands are permitted. Network access is enabled.\n"
        "Approval policy is currently never. Do not provide the `sandbox_permissions` for any reason, commands will be rejected.\n"
        "</permissions instructions>"
    )


def test_render_permissions_instructions_unless_trusted_mentions_safe_read_allowlist() -> None:
    rendered = render_permissions_instructions(
        sandbox_mode="workspace-write",
        approval_policy="unless-trusted",
        network_access_enabled=True,
    )

    assert 'limited allowlist of safe "read" commands' in rendered


def test_openai_prompts_use_exact_reference_base_prompt_when_parity_enabled() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        base_url="https://relay.example.com/reference/v1",
        raw_provider={"reference_parity": True},
    )
    host_platform = _host_platform()
    base_prompt = load_reference_base_prompt()

    assert (
        build_openai_json_system_prompt(host_platform=host_platform, config=config) == base_prompt
    )
    assert (
        build_openai_native_system_prompt(host_platform=host_platform, config=config) == base_prompt
    )


def test_openai_prompts_use_exact_reference_base_prompt_when_interaction_profile_codex_openai() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        planner_kind="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )
    host_platform = _host_platform()
    base_prompt = load_reference_base_prompt()

    assert (
        build_openai_json_system_prompt(host_platform=host_platform, config=config) == base_prompt
    )
    assert (
        build_openai_native_system_prompt(host_platform=host_platform, config=config) == base_prompt
    )


def test_openai_prompts_keep_generic_path_when_no_codex_profile() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        planner_kind="openai_responses",
    )
    host_platform = _host_platform()
    base_prompt = load_agenthub_base_prompt()

    assert build_openai_json_system_prompt(host_platform=host_platform, config=config).startswith(
        base_prompt
    )
    assert build_openai_native_system_prompt(host_platform=host_platform, config=config).startswith(
        base_prompt
    )


def test_openai_json_prompt_hides_unexposed_web_commands() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command, write_stdin, grep_files, read_file, list_dir",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses"),
    )

    assert "/web_search" not in prompt
    assert "/web_fetch" not in prompt
    assert "/browser" not in prompt
    assert "/open" not in prompt
    assert "/click" not in prompt
    assert "/find" not in prompt
    assert (
        "Do not promise live web lookup unless web_search is actually exposed in this session."
        in prompt
    )


def test_openai_json_prompt_separates_web_search_web_fetch_and_browser_boundaries() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command, write_stdin, web_search, web_fetch, browser",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses"),
    )

    assert "Use /web_search for general public-web discovery about current external facts" in prompt
    assert "Use /web_fetch only when you already have a concrete URL" in prompt
    assert (
        "Use /browser as the canonical browser-family tool for page navigation, interaction, or managed browser inspection"
        in prompt
    )


def test_openai_json_prompt_prefers_direct_fetch_for_explicit_url_and_search_then_read_flow() -> (
    None
):
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command, write_stdin, web_search, web_fetch, browser, open, click, find",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses"),
    )

    assert (
        "If the user already gives a concrete public URL, skip /web_search and use /web_fetch directly unless the task requires browser navigation or interaction."
        in prompt
    )
    assert (
        "For search-then-read evidence flows, use /web_search first to discover candidate sources, then use /web_fetch on a selected URL when you need page content before answering."
        in prompt
    )
    assert (
        "Use /browser only for navigation, interaction, or managed browser inspection. Do not use it just to read a known URL or to do general public-web discovery."
        in prompt
    )


def test_openai_json_prompt_keeps_open_click_find_as_legacy_browser_aliases_only() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command, write_stdin, web_search, web_fetch, browser, open, click, find",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses"),
    )

    assert (
        "Treat /open, /click, /find as legacy browser-family aliases only; prefer /browser when the canonical browser tool is exposed."
        in prompt
    )
    assert (
        "Do not route plain URL-reading or simple public-web discovery through /open, /click, /find; reserve them for browser-family compatibility flows."
        in prompt
    )


def test_openai_native_prompt_uses_surface_specific_web_search_wording() -> None:
    host_platform = _host_platform()
    native_prompt = build_openai_native_system_prompt(
        host_platform=host_platform,
        available_tool_names="exec_command, write_stdin, web_search",
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            planner_kind="openai_responses",
            wire_api="responses",
            raw_model={"native_web_search_mixed_tools": True},
        ),
    )
    fallback_prompt = build_openai_native_system_prompt(
        host_platform=host_platform,
        available_tool_names="exec_command, write_stdin, web_search",
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
    )
    disabled_prompt = build_openai_native_system_prompt(
        host_platform=host_platform,
        available_tool_names="exec_command, write_stdin",
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            planner_kind="openai_responses",
            wire_api="responses",
            raw_provider={"web_search_mode": "disabled"},
        ),
    )

    assert (
        "Use the provider-native web_search tool for general public-web discovery" in native_prompt
    )
    assert (
        "Use the exposed web_search tool in this loop for general public-web discovery"
        in fallback_prompt
    )
    assert (
        "Do not promise live web lookup unless web_search is actually exposed in this session."
        in disabled_prompt
    )


def test_openai_json_prompt_keeps_exec_command_as_primary_when_exec_surface_is_exposed() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command, write_stdin, grep_files",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses"),
    )

    assert "prefer /exec_command and /write_stdin" in prompt
    assert "Use Bash as the primary command-execution tool" not in prompt


def test_openai_json_prompt_uses_bash_and_powershell_when_claude_style_surface_is_exposed() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="Bash, PowerShell, write_stdin, grep_files",
        config=ProviderConfig(
            model="claude-sonnet-4-6", api_key="test-key", planner_kind="anthropic_messages"
        ),
    )

    assert "For command execution, use Bash as the primary command-execution tool name." in prompt
    assert "Use PowerShell only when it is also exposed" in prompt
    assert "Use write_stdin to continue or poll an existing command session." in prompt
    assert "If you set run_in_background, treat it as an early-return session launch" in prompt
    assert (
        "Use dangerouslyDisableSandbox only when the command genuinely needs escalated execution."
        in prompt
    )
    assert "prefer /exec_command and /write_stdin" not in prompt
    assert "Do not treat shell as the primary tool name." in prompt


def test_openai_json_prompt_mentions_ask_user_question_boundary_when_exposed() -> None:
    prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="Bash, write_stdin, AskUserQuestion, Write, Edit",
        config=ProviderConfig(
            model="claude-sonnet-4-6", api_key="test-key", planner_kind="anthropic_messages"
        ),
    )

    assert "AskUserQuestion(questions=[...])" in prompt
    assert "Use AskUserQuestion only for clarification or concrete user choices" in prompt
    assert "do not use it for plan approval" in prompt


def test_openai_prompts_describe_claude_edit_surface_without_apply_patch_grammar() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )

    json_prompt = build_openai_json_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="Bash, write_stdin, AskUserQuestion, Write, Edit, read_file",
        config=config,
    )
    native_prompt = build_openai_native_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="Bash, write_stdin, AskUserQuestion, Write, Edit, read_file",
        config=config,
    )

    assert (
        "Before modifying an existing file with Write or Edit, use /read_file first" in json_prompt
    )
    assert (
        "Use Write for new files or full rewrites. Prefer Edit for targeted changes to existing files."
        in json_prompt
    )
    assert "match exactly once unless replace_all=true" in json_prompt
    assert (
        "Do not describe or emit raw apply_patch grammar when the surface exposes Write and Edit instead."
        in json_prompt
    )
    assert "/apply_patch <patch>" not in json_prompt

    assert (
        "Before modifying an existing file with Write or Edit, use read_file first" in native_prompt
    )
    assert (
        "Do not describe or emit raw apply_patch grammar when the surface exposes Write and Edit instead."
        in native_prompt
    )
    assert "/apply_patch <patch>" not in native_prompt


def test_chat_completions_prompt_keeps_web_guidance_conditional_and_surface_aware() -> None:
    native_prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        use_native_web_search=True,
    )
    fallback_prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        use_native_web_search=False,
    )

    assert (
        "If web_search is exposed in this session, use it for general public-web discovery"
        in native_prompt
    )
    assert "When the provider exposes native web_search in this session" in native_prompt
    assert "When web_search is exposed only as a fallback tool path" in fallback_prompt


def test_chat_completions_prompt_defines_explicit_url_search_then_read_and_browser_boundaries() -> (
    None
):
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        use_native_web_search=True,
    )

    assert (
        "If the user already gives a concrete public URL, prefer web_fetch directly instead of web_search unless the task requires browser navigation or interaction."
        in prompt
    )
    assert (
        "For search-then-read evidence flows, use web_search first to discover candidate sources, then use web_fetch on a selected URL when you need source content before answering."
        in prompt
    )
    assert (
        "Use browser only for navigation, interaction, or managed browser inspection. Do not use browser, open, click, or find just to read a known URL or to do general public-web discovery."
        in prompt
    )


def test_chat_completions_prompt_uses_config_to_detect_disabled_web_search_surface() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            planner_kind="openai_chat",
            raw_provider={"web_search_mode": "disabled"},
        ),
    )

    assert (
        "Do not promise live web lookup unless web_search is actually exposed in this session."
        in prompt
    )


def test_chat_completions_prompt_describes_profile_specific_command_surfaces_without_promoting_shell() -> (
    None
):
    prompt = build_chat_completions_system_prompt(host_platform=_host_platform())

    assert "Codex-style surfaces use exec_command and write_stdin" in prompt
    assert "Claude-style surfaces use Bash" in prompt
    assert "write_stdin remains the continuation tool" in prompt
    assert "run_in_background means return early from a live session" in prompt
    assert "Do not treat shell as the primary tool name." in prompt


def test_openai_prompt_explicit_incompatible_profile_raises_hard_error() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        planner_kind="openai_chat",
        wire_api="openai_chat",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    with pytest.raises(InteractionProfileCompatibilityError):
        build_openai_json_system_prompt(host_platform=_host_platform(), config=config)


def test_openai_native_reference_parity_request_matches_capture_shape(tmp_path) -> None:
    runtime = AgentCliRuntime(
        runtime_policy=RuntimePolicy.normalized(
            approval_policy="never",
            sandbox_mode="danger-full-access",
            network_access_enabled=True,
        )
    )
    runtime.set_cwd(tmp_path)
    workspace_snapshot = _workspace_snapshot(
        tmp_path, instructions="Follow repo instructions carefully."
    )
    environment_snapshot = build_environment_context_snapshot(
        cwd=str(tmp_path),
        shell="bash",
        network_access=True,
        current_dt=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
    )
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        base_url="https://relay.example.com/reference/v1",
        reasoning_effort="high",
        raw_provider={"reference_parity": True, "web_search_mode": "live"},
    )
    host_platform = _host_platform()
    capture = _load_reference_capture_request()

    class _FakeResponses:
        def __init__(self) -> None:
            self.requests: list[dict] = []

        def create(self, **kwargs):
            self.requests.append(dict(kwargs))
            return type("_Response", (), {"id": "resp_test", "output": [], "output_text": ""})()

    class _FakeClient:
        def __init__(self) -> None:
            self.responses = _FakeResponses()

    client = _FakeClient()
    session = OpenAIResponsesSession(
        client=client,
        model=config.model,
        instructions=build_openai_native_system_prompt(host_platform=host_platform, config=config),
        tool_specs=responses_minimal_provider_tool_specs(
            config, host_platform, plugin_manager_factory=lambda: None
        ),
        reasoning_effort=config.reasoning_effort,
        reference_parity=True,
        prompt_cache_key="019d41ac-53ff-75a3-93aa-7354096116b6",
    )

    session.send(
        input_items=[
            *prelude_items,
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "请列出当前目录下一层文件和目录，不要修改文件。"}
                ],
            },
        ],
        allow_tools=True,
    )

    request = client.responses.requests[0]
    assert request["instructions"].startswith("You are Codex, a coding agent based on GPT-5.")
    assert "# Personality" in request["instructions"]
    assert {item.get("name") or item.get("type") for item in request["tools"]} >= {
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "web_search",
        "view_image",
    }
    assert not {
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "close_agent",
    } & {item.get("name") or item.get("type") for item in request["tools"]}
    assert request["include"] == capture["include"]
    assert request["tool_choice"] == capture["tool_choice"]
    assert request["parallel_tool_calls"] is True
    assert request["input"][0] == capture["input"][0]
    assert request["input"][1]["type"] == "message"
    assert request["input"][1]["role"] == "user"
    assert [block["type"] for block in request["input"][1]["content"]] == [
        "input_text",
        "input_text",
    ]
    assert request["input"][1]["content"][0]["text"].startswith(
        f"# AGENTS.md instructions for {tmp_path}"
    )
    assert request["input"][1]["content"][1]["text"] == (
        "<environment_context>\n"
        f"  <cwd>{tmp_path}</cwd>\n"
        "  <shell>bash</shell>\n"
        "  <current_date>2026-03-31</current_date>\n"
        "  <timezone>UTC</timezone>\n"
        "</environment_context>"
    )
    assert request["input"][2] == {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "请列出当前目录下一层文件和目录，不要修改文件。"}
        ],
    }


def test_runtime_policy_overrides_flow_into_agent_provider_config(tmp_path, monkeypatch) -> None:
    captured: list[ProviderConfig] = []

    monkeypatch.setattr(
        "cli.agent_cli.agent.load_provider_config",
        lambda **kwargs: ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            base_url="https://relay.example.com/reference/v1",
        ),
    )
    monkeypatch.setattr(
        "cli.agent_cli.agent.build_planner",
        lambda config, **kwargs: captured.append(config) or SimpleNamespace(),
    )

    runtime = AgentCliRuntime(
        runtime_policy=RuntimePolicy.normalized(
            approval_policy="never",
            sandbox_mode="workspace-write",
            web_search_mode="cached",
            network_access_enabled=True,
        ),
        current_dt_provider=lambda: _FIXED_DT,
    )
    runtime.set_cwd(tmp_path)

    assert captured
    assert captured[-1].raw_provider["web_search_mode"] == "cached"

    runtime.configure_runtime_policy(web_search_mode="live")

    assert captured[-1].raw_provider["web_search_mode"] == "live"


def test_system_prompts_include_delegation_policy_guidance() -> None:
    host_platform = _host_platform()

    native_prompt = build_openai_native_system_prompt(
        host_platform=host_platform,
        config=ProviderConfig(model="gpt-5.4", api_key="test"),
    )
    json_prompt = build_openai_json_system_prompt(
        host_platform=host_platform,
        config=ProviderConfig(model="gpt-5.4", api_key="test"),
    )
    chat_prompt = build_chat_completions_system_prompt(host_platform=host_platform)

    assert "Use spawn_agent only for bounded side tasks" in native_prompt
    assert "/request_orchestration" not in json_prompt
    assert "Use request_orchestration only for whole-task escalation" not in json_prompt
    assert "Use wait_agent only when the next step explicitly depends" in native_prompt
    assert "Prefer agent_workflow when you only need a non-blocking child status" in native_prompt
    assert (
        "Use recover_agent with retry_step when a delegated workflow exposes a recoverable failed step"
        in chat_prompt
    )
    assert "Do not busy-wait on background agents" in chat_prompt


def test_chat_completions_prompt_maps_implicit_cross_provider_review_requests_to_expert_review() -> (
    None
):
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai-compatible",
            planner_kind="openai_chat",
            interaction_profile="generic_chat",
            interaction_profile_source="test",
        ),
    )

    assert (
        "If expert_review is exposed in this session, use it when the user asks another provider, another model"
        in prompt
    )
    assert "Treat requests to have a different provider or model review" in prompt
    assert "Do not use expert_review when the user explicitly says not to re-check" in prompt


def test_claude_chat_completions_prompt_does_not_mix_agenthub_review_guidance() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
    )

    assert prompt.startswith("You are Claude Code, Anthropic's official CLI for Claude.")
    assert "If expert_review is exposed in this session" not in prompt
    assert "Treat requests to have a different provider or model review" not in prompt


def test_openai_native_prompt_includes_expert_review_trigger_guidance_when_tool_is_exposed() -> (
    None
):
    prompt = build_openai_native_system_prompt(
        host_platform=_host_platform(),
        available_tool_names="exec_command,write_stdin,expert_review",
        config=ProviderConfig(model="gpt-5.4", api_key="test-key"),
    )

    assert "another provider, another model, a second opinion" in prompt
    assert "Treat requests to have a different provider or model review" in prompt


def test_chat_completions_prompt_keeps_policy_guidance_in_english() -> None:
    prompt = build_chat_completions_system_prompt(host_platform=_host_platform())

    assert "For company policy, policy basis, clause, procedure, standard, rule" in prompt


def test_chat_completions_prompt_includes_tool_demo_answer_guidance() -> None:
    prompt = build_chat_completions_system_prompt(host_platform=_host_platform())

    assert "When the user asks how to use a tool or asks for a demo/example" in prompt
    assert "include a concise concrete example using the actual tool call you just used" in prompt


def test_chat_completions_prompt_uses_claude_base_prompt_for_claude_profile() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
    )

    assert prompt.startswith("You are Claude Code, Anthropic's official CLI for Claude.")
    assert "You are a coding agent running in the Codex CLI" not in prompt
    assert "Do not overdo it. Be extra concise." in prompt
    assert "when your task will clearly require more than 3 queries" in prompt
    assert "concise report with an explicit length bound" in prompt
    assert "Write Agent tool description and prompt arguments in English" in prompt


def test_chat_completions_prompt_projects_claude_delegation_boundary() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
    )

    assert "## Agent Tool" in prompt
    assert "Launch a new agent to handle complex, multi-step tasks" in prompt
    assert "When using the Agent tool, specify a subagent_type parameter" in prompt
    assert "Use Agent only for bounded side tasks" not in prompt
    assert "Use SendMessage only to continue an existing delegated child by id" not in prompt
    assert "notification-driven rather than poll-driven" not in prompt
    assert "Use wait_agent only when the next step explicitly depends" not in prompt


def test_chat_completions_prompt_describes_claude_edit_surface_without_patch_grammar() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
    )

    assert "## Edit Tool" in prompt
    assert "Performs exact string replacements in files." in prompt
    assert (
        "You must use your `Read` tool at least once in the conversation before editing." in prompt
    )
    assert "Do not describe or emit raw apply_patch grammar" not in prompt


def test_chat_completions_prompt_keeps_generic_chat_conservative_about_edit_surface_language() -> (
    None
):
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            planner_kind="openai_chat",
            wire_api="openai_chat",
            interaction_profile="generic_chat",
            interaction_profile_source="test",
        ),
    )

    assert "Before modifying an existing file with Write or Edit" not in prompt
    assert (
        "Do not describe or emit raw apply_patch grammar when the surface exposes Write and Edit instead."
        not in prompt
    )
