import json
import shlex
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import agent_fallback_runtime  # noqa: E402
from cli.agent_cli.agent import RuleBasedAgent  # noqa: E402
from cli.agent_cli.background_tasks import (  # noqa: E402
    BackgroundTasksConfig,
    HueyConfig,
    build_background_task_adapter,
)
from cli.agent_cli.host_platform import current_host_platform  # noqa: E402
from cli.agent_cli.models import ActivityEvent, AgentIntent, ToolEvent  # noqa: E402
from cli.agent_cli.providers.availability_models import (  # noqa: E402
    AvailabilityRecord,
    ProbeStatus,
)
from cli.agent_cli.providers.config_catalog import (  # noqa: E402
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderCatalogEntry,
    ProviderConfig,
    build_provider_catalog,
)
from cli.agent_cli.providers.planners_common import BasePlanner  # noqa: E402
from cli.agent_cli.runtime import AgentCliRuntime  # noqa: E402
from cli.agent_cli.runtime_core import background_task_commands_text_runtime  # noqa: E402
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command  # noqa: E402
from cli.agent_cli.runtime_policy import RuntimePolicy  # noqa: E402
from cli.agent_cli.slash_parser import parse_slash_invocation  # noqa: E402


class ProviderStatusTest(unittest.TestCase):
    def test_agent_fallback_runtime_keeps_provider_failure_text_concise(self):
        text = agent_fallback_runtime.planner_fallback_text(
            planner_runtime_error="RuntimeError: proxy_unavailable",
            planner_error=None,
            provider_status={"provider_display_label": "deepseek | deepseek-reasoner | tool-calls"},
            planner_runtime_error_diagnostics={
                "issues": [
                    {
                        "index": 1,
                        "element": "previous_turn_function_call",
                        "detail": "arguments 只有 cmd，缺少 workdir/yield_time_ms/max_output_tokens 等执行上下文。",
                    }
                ]
            },
            planner_runtime_fallback_text=RuleBasedAgent._PLANNER_RUNTIME_FALLBACK_TEXT,
            planner_unavailable_fallback_text=RuleBasedAgent._PLANNER_UNAVAILABLE_FALLBACK_TEXT,
        )

        self.assertEqual(text, "无法继续：proxy_unavailable")
        self.assertNotIn("当前 provider", text)
        self.assertNotIn("provider 失败类型", text)
        self.assertNotIn("最近一次 provider 异常", text)

    def test_agent_fallback_runtime_extracts_upstream_error_message(self):
        text = agent_fallback_runtime.planner_fallback_text(
            planner_runtime_error=(
                "PermissionDeniedError: Error code: 403 - "
                "{'error': {'message': '用户额度不足, 剩余额度: ¤-2.524978 "
                "(request id: 20260511110445263289739cy932qm)', "
                "'type': 'rix_api_error', 'param': '', 'code': 'insufficient_user_quota'}}"
            ),
            planner_error=None,
            provider_status={"provider_display_label": "openai | gpt-5.5 | tool-calls"},
            planner_runtime_error_diagnostics=None,
            planner_runtime_fallback_text=RuleBasedAgent._PLANNER_RUNTIME_FALLBACK_TEXT,
            planner_unavailable_fallback_text=RuleBasedAgent._PLANNER_UNAVAILABLE_FALLBACK_TEXT,
        )

        self.assertEqual(text, "无法继续：用户额度不足, 剩余额度: ¤-2.524978")
        self.assertNotIn("request id", text)
        self.assertNotIn("当前 provider", text)

    def test_agent_fallback_runtime_extracts_plain_error_payload(self):
        text = agent_fallback_runtime.planner_fallback_text(
            planner_runtime_error=(
                "APIStatusError: Error code: 402 - "
                "{'error': 'Access denied: No active subscription'}"
            ),
            planner_error=None,
            provider_status={
                "provider_display_label": "anthropic | claude-sonnet-4-6 | tool-calls"
            },
            planner_runtime_error_diagnostics=None,
            planner_runtime_fallback_text=RuleBasedAgent._PLANNER_RUNTIME_FALLBACK_TEXT,
            planner_unavailable_fallback_text=RuleBasedAgent._PLANNER_UNAVAILABLE_FALLBACK_TEXT,
        )

        self.assertEqual(text, "无法继续：Access denied: No active subscription")

    def test_rule_based_agent_routes_simple_dialog_to_planner(self):
        class _RecordingPlanner:
            def __init__(self) -> None:
                self.calls: list[str] = []

            @staticmethod
            def public_summary():
                return {
                    "provider_name": "openai",
                    "model_key": "gpt-5.4-reference",
                    "planner_kind": "openai_responses",
                    "model": "gpt-5.4-reference",
                    "base_url": "https://example.invalid/v1",
                    "source": "project_local",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                }

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                self.calls.append(text)
                return AgentIntent(assistant_text=f"provider: {text}")

        planner = _RecordingPlanner()
        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=planner):
                    agent = RuleBasedAgent()
                    prompts = ["你好", "你帮我看看今天周几", "现在北京时间几点"]
                    outputs = [agent.plan(prompt, history=[]) for prompt in prompts]

        self.assertEqual(planner.calls, prompts)
        self.assertEqual(
            [intent.assistant_text for intent in outputs],
            [f"provider: {prompt}" for prompt in prompts],
        )
        for intent in outputs:
            self.assertEqual(intent.protocol_diagnostics["protocol_path"]["kind"], "provider_loop")
            self.assertTrue(intent.protocol_diagnostics["protocol_path"]["provider_used"])

    def test_rule_based_directory_fallback_uses_reference_aligned_exec_command(self):
        class _FailingPlanner:
            @staticmethod
            def public_summary():
                return {
                    "provider_name": "openai",
                    "model_key": "gpt-5.4-reference",
                    "planner_kind": "openai_responses",
                    "model": "gpt-5.4-reference",
                    "base_url": "https://example.invalid/v1",
                    "source": "project_local",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                }

            def plan(self, text, history, *, tool_executor=None, attachments=None):
                raise RuntimeError("InternalServerError: Error code: 503 - proxy_unavailable")

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=_FailingPlanner()):
                    agent = RuleBasedAgent()
                    intent = agent.plan("请列出当前目录下的文件", history=[])

        host = current_host_platform()
        if host.family == "windows":
            self.assertEqual(intent.command_text, "/list_dir . --limit 50 --depth 1")
        else:
            self.assertTrue(intent.command_text.startswith("/exec_command "))
            self.assertIn("find . -mindepth 1 -maxdepth 1 -printf", intent.command_text)
        self.assertIn("识别为列出当前工作区文件", intent.assistant_text)

    def test_provider_command_includes_resolved_paths(self):
        runtime = AgentCliRuntime()

        response = runtime.handle_prompt("/provider --verbose")

        self.assertIn("provider_label=", response.assistant_text)
        self.assertIn("provider_tools=", response.assistant_text)
        self.assertIn("provider_config_path=", response.assistant_text)
        self.assertIn("provider_auth_path=", response.assistant_text)
        self.assertIn("session_line=", response.assistant_text)
        self.assertIn("platform_family=", response.assistant_text)
        self.assertIn("platform_os=", response.assistant_text)
        self.assertIn("shell_kind=", response.assistant_text)
        self.assertTrue(
            any(
                token in response.assistant_text
                for token in (".config", ".agent_cli", ".agent_cli_legacy", ".claude")
            ),
            "provider status should reference .config, .agent_cli, .agent_cli_legacy, or .claude paths",
        )
        self.assertIn("provider_config_path", response.status)
        self.assertIn("provider_auth_path", response.status)
        self.assertIn("provider_tools", response.status)
        self.assertIn("session_line", response.status)
        self.assertIn("platform_family", response.status)
        self.assertIn("platform_os", response.status)
        self.assertIn("shell_kind", response.status)

    def test_provider_command_surfaces_multi_llm_route_summary(self):
        class _Planner:
            @staticmethod
            def public_summary():
                return {
                    "provider_name": "openai",
                    "model_key": "gpt_54",
                    "planner_kind": "openai_responses",
                    "model": "gpt-5.4",
                    "base_url": "https://relay.example/v1",
                    "source": "project_local",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                    "routes": {
                        "policy_helper": {
                            "provider_name": "deepseek",
                            "model": "deepseek-chat",
                            "reasoning_effort": "low",
                            "timeout": 20,
                            "source": "route",
                        },
                        "tool_followup": {
                            "provider_name": "openai",
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "source": "route",
                        },
                        "final_synthesis": {
                            "provider_name": "openai",
                            "model": "gpt-5.4",
                            "reasoning_effort": "high",
                            "source": "main",
                        },
                    },
                    "delegation": {
                        "subagent": {
                            "provider_name": "openai",
                            "model": "gpt-5.4",
                            "reasoning_effort": "high",
                            "source": "inherit_main",
                        },
                        "teammate": {
                            "provider_name": "glm",
                            "model": "glm-5",
                            "reasoning_effort": "medium",
                            "timeout": 30,
                            "source": "delegation",
                        },
                    },
                }

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                return AgentIntent(assistant_text="ok")

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=_Planner()):
                    agent = RuleBasedAgent()
                    runtime = AgentCliRuntime(agent=agent)
                    response = runtime.handle_prompt("/provider --verbose")
                    status = agent.provider_status()

        self.assertIn("route_policy_helper=", response.assistant_text)
        self.assertIn("route_tool_followup=", response.assistant_text)
        self.assertIn("route_final_synthesis=", response.assistant_text)
        self.assertIn("orchestration_route_summary=", response.assistant_text)
        self.assertIn("orchestration_delegate_summary=", response.assistant_text)
        self.assertIn("provider_readiness_summary=", response.assistant_text)
        self.assertIn("route_health_summary=", response.assistant_text)
        self.assertEqual(
            status["route_policy_helper"],
            "deepseek | deepseek-chat | reasoning=low | timeout=20 | source=route",
        )
        self.assertEqual(
            status["route_tool_followup"],
            "openai | gpt-5.4-mini | reasoning=medium | source=route",
        )
        self.assertEqual(
            status["route_final_synthesis"],
            "openai | gpt-5.4 | reasoning=high | source=main",
        )
        self.assertIn("policy_helper:deepseek | deepseek-chat", response.assistant_text)
        self.assertIn("tool_followup:openai | gpt-5.4-mini", response.assistant_text)
        self.assertIn(
            "subagent:openai | gpt-5.4 | reasoning=high | source=inherit_main",
            response.assistant_text,
        )
        self.assertIn(
            "teammate:glm | glm-5 | reasoning=medium | timeout=30 | source=delegation",
            response.assistant_text,
        )
        self.assertIn("provider_ready=true", response.assistant_text)
        self.assertIn("route_health_summary=policy_helper=ready", response.assistant_text)

    def test_provider_command_surfaces_availability_and_route_health_aggregate(self):
        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_display_label": "openai | gpt-5.4 | tool-calls",
                    "provider_public_name": "openai",
                    "provider_route_name": "openai",
                    "provider_ready": "true",
                    "availability_status": "unavailable",
                    "availability_known": True,
                    "availability_health_bucket": "degraded",
                    "availability_avg_latency_ms": 2200,
                    "availability_last_latency_ms": 3100,
                    "availability_failure_count": 2,
                    "availability_consecutive_failures": 2,
                    "route_policy_helper": "openai | gpt-5.4 | reasoning=low | source=main_availability_fallback_main | availability_fallback=true",
                    "route_tool_followup": "openai | gpt-5.4-mini | reasoning=medium | source=route",
                    "route_final_synthesis": "openai | gpt-5.4 | reasoning=high | source=main",
                }

        runtime = SimpleNamespace(agent=_Agent())
        text, events = handle_provider_command(
            runtime,
            name="provider",
            arg_text="--verbose",
            switch_disabled_result=lambda exc: (str(exc), []),
        )

        self.assertEqual(events, [])
        self.assertIn(
            "provider_readiness_summary=provider_ready=true; availability=unavailable; known=true; health=degraded",
            text,
        )
        self.assertIn("avg_latency_ms=2200", text)
        self.assertIn(
            "route_health_summary=policy_helper=degraded:fallback_main; tool_followup=ready; final_synthesis=ready; counts=ready:2,degraded:1,missing:0",
            text,
        )

    def test_provider_command_surfaces_orchestration_reason_and_budget_summaries(self):
        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_display_label": "openai | gpt-5.4 | tool-calls",
                    "provider_public_name": "openai",
                    "provider_route_name": "openai",
                    "orchestration_decision": "delegate_async",
                    "orchestration_policy_reason": "spawn_agent",
                    "orchestration_execution_mode": "parallel",
                    "orchestration_execution_reason": "task_shape:long_running",
                    "delegation_reason": "long_running_exec",
                    "delegation_mode": "background",
                    "task_shape": "long_running",
                    "wait_required": False,
                    "orchestration_strategy": "stop_and_return",
                    "orchestration_strategy_reason": "wait_timeout_budget_hit",
                    "orchestration_strategy_source": "budget_timeout_policy",
                    "orchestration_budget_source": "planner_arguments",
                    "orchestration_observation_source": "tool_execution",
                    "orchestration_timeout_reason": "wait_timeout",
                    "orchestration_continue_delegation": False,
                    "orchestration_budget_hit": True,
                    "wait_timeout_ms": 200,
                    "orchestration_budget_snapshot": {
                        "wait_timeout_ms": 200,
                        "wait_observed_ms": 250,
                    },
                }

        runtime = SimpleNamespace(agent=_Agent())
        text, events = handle_provider_command(
            runtime,
            name="provider",
            arg_text="--verbose",
            switch_disabled_result=lambda exc: (str(exc), []),
        ) or ("", [])

        self.assertEqual(events, [])
        self.assertIn("orchestration_reason_surface=decision=delegate_async", text)
        self.assertIn("execution=parallel", text)
        self.assertIn("policy_reason=spawn_agent", text)
        self.assertIn("delegation_reason=long_running_exec", text)
        self.assertIn("task_shape=long_running", text)
        self.assertIn("wait_required=false", text)
        self.assertIn("orchestration_budget_surface=strategy=stop_and_return", text)
        self.assertIn("reason=wait_timeout_budget_hit", text)
        self.assertIn("strategy_source=budget_timeout_policy", text)
        self.assertIn("budget_source=planner_arguments", text)
        self.assertIn("observation_source=tool_execution", text)
        self.assertIn("timeout_reason=wait_timeout", text)
        self.assertIn("wait_timeout_ms=200", text)
        self.assertIn("wait_observed_ms=250", text)
        self.assertIn("continue_delegation=false", text)
        self.assertIn("budget_hit=true", text)

    def test_provider_command_surfaces_stay_local_counterexample_matrix(self):
        class _Agent:
            @staticmethod
            def provider_status():
                return {
                    "provider_display_label": "openai | gpt-5.4 | tool-calls",
                    "provider_public_name": "openai",
                    "provider_route_name": "openai",
                    "orchestration_decision": "stay_local",
                    "orchestration_policy_reason": "no_delegation_tools_observed",
                    "orchestration_stay_local_source": "planner_tool_calls",
                    "orchestration_stay_local_reason": "non_delegation_tools_only",
                    "orchestration_stay_local_counterexamples": "exec_command,read_file,exec_command",
                    "observed_tool_count": 3,
                    "observed_delegation_tool_count": 0,
                    "observed_non_delegation_tool_count": 3,
                }

        runtime = SimpleNamespace(agent=_Agent())
        text, events = handle_provider_command(
            runtime,
            name="provider",
            arg_text="--verbose",
            switch_disabled_result=lambda exc: (str(exc), []),
        ) or ("", [])

        self.assertEqual(events, [])
        self.assertIn("orchestration_reason_surface=decision=stay_local", text)
        self.assertIn("policy_reason=no_delegation_tools_observed", text)
        self.assertIn("orchestration_stay_local_source=planner_tool_calls", text)
        self.assertIn("orchestration_stay_local_reason=non_delegation_tools_only", text)
        self.assertIn(
            "orchestration_stay_local_counterexamples=exec_command,read_file,exec_command", text
        )
        self.assertIn("observed_non_delegation_tool_count=3", text)

    def test_background_task_status_text_surfaces_orchestration_reason_and_budget_from_route_trace(
        self,
    ):
        text = background_task_commands_text_runtime.background_task_status_text(
            {
                "status": "running",
                "artifact": {
                    "route_report": {
                        "planning_trace": [
                            {
                                "orchestration_decision": "wait_now",
                                "orchestration_policy_reason": "wait_agent_blocking_join",
                                "wait_reason": "wait_for_child_result",
                                "wait_required": True,
                                "orchestration_strategy": "stop_and_return",
                                "orchestration_strategy_reason": "wait_timeout_budget_hit",
                                "orchestration_strategy_source": "budget_timeout_policy",
                                "orchestration_budget_source": "planner_arguments",
                                "orchestration_observation_source": "tool_execution",
                                "orchestration_budget_hit": True,
                                "orchestration_continue_delegation": False,
                                "wait_timeout_ms": 200,
                                "orchestration_budget_snapshot": {
                                    "wait_timeout_ms": 200,
                                    "wait_observed_ms": 250,
                                },
                            }
                        ]
                    },
                    "scheduler_reason": "workspace_write_budget_exhausted",
                    "parallel_group": "serial",
                    "parallel_limit": 1,
                },
            },
            task_id="bg_reason_budget",
        )

        self.assertIn("orchestration_decision=wait_now", text)
        self.assertIn("orchestration_policy_reason=wait_agent_blocking_join", text)
        self.assertIn("wait_reason=wait_for_child_result", text)
        self.assertIn("wait_required=true", text)
        self.assertIn("scheduler_reason=workspace_write_budget_exhausted", text)
        self.assertIn("parallel_group=serial", text)
        self.assertIn("parallel_limit=1", text)
        self.assertIn("orchestration_strategy=stop_and_return", text)
        self.assertIn("orchestration_strategy_reason=wait_timeout_budget_hit", text)
        self.assertIn("orchestration_budget_hit=true", text)
        self.assertIn("orchestration_continue_delegation=false", text)
        self.assertIn("orchestration_reason_surface=decision=wait_now", text)
        self.assertIn("execution=serial", text)
        self.assertIn("orchestration_budget_surface=strategy=stop_and_return", text)
        self.assertIn("wait_observed_ms=250", text)

    def test_rule_based_agent_route_override_reloads_route_summary_and_clear_restores_config(self):
        class _RoutePlanner(BasePlanner):
            def _route_status_specs(self):
                return {
                    "policy_helper": {},
                    "tool_followup": {},
                    "final_synthesis": {},
                }

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                return AgentIntent(assistant_text="ok")

        def _main_config():
            return ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                model_key="gpt_54",
                planner_kind="openai_responses",
                wire_api="responses",
                base_url="https://relay.example/v1",
                reasoning_effort="high",
                source="test",
                config_path="/tmp/config.toml",
                auth_path="/tmp/auth.json",
                raw_model={
                    "routes": {
                        "tool_followup": {
                            "provider": "glm",
                            "model": "glm_5",
                            "reasoning_effort": "high",
                            "timeout": 30,
                        }
                    }
                },
            )

        def _route_config(*, cwd=None, env_overrides=None):
            del cwd
            selector = str((env_overrides or {}).get("AGENT_CLI_MODEL") or "").strip()
            if selector == "glm_5":
                return ProviderConfig(
                    model="glm-5",
                    api_key="sk-test",
                    provider_name="glm",
                    model_key="glm_5",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    base_url="https://glm.example/v1",
                    reasoning_effort=str(
                        (env_overrides or {}).get("AGENT_CLI_REASONING_EFFORT") or "high"
                    ),
                    source="test",
                    config_path="/tmp/config.toml",
                    auth_path="/tmp/auth.json",
                )
            if selector == "gpt_54":
                return ProviderConfig(
                    model="gpt-5.4",
                    api_key="sk-test",
                    provider_name="openai",
                    model_key="gpt_54",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    base_url="https://relay.example/v1",
                    reasoning_effort=str(
                        (env_overrides or {}).get("AGENT_CLI_REASONING_EFFORT") or "high"
                    ),
                    source="test",
                    config_path="/tmp/config.toml",
                    auth_path="/tmp/auth.json",
                )
            return None

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch(
                "cli.agent_cli.agent.load_provider_config",
                side_effect=lambda **kwargs: _main_config(),
            ):
                with patch(
                    "cli.agent_cli.providers.model_routing._load_provider_config_for_route",
                    side_effect=_route_config,
                ):
                    with patch(
                        "cli.agent_cli.agent.build_planner",
                        side_effect=lambda config, **kwargs: _RoutePlanner(
                            config,
                            host_platform=kwargs.get("host_platform"),
                            cwd=kwargs.get("cwd"),
                            plugin_manager_factory=kwargs.get("plugin_manager_factory"),
                        ),
                    ):
                        agent = RuleBasedAgent()
                        initial = agent.provider_status()
                        updated = agent.configure_route_selection(
                            "tool_followup",
                            model="gpt_54",
                            reasoning_effort="xhigh",
                            timeout="45",
                        )
                        cleared = agent.configure_route_selection("tool_followup", clear=True)

        self.assertEqual(
            initial["route_tool_followup"],
            "glm | glm-5 | reasoning=high | timeout=30 | source=route",
        )
        self.assertEqual(
            updated["route_tool_followup"],
            "openai | gpt-5.4 | reasoning=xhigh | timeout=45 | source=session_override",
        )
        self.assertEqual(updated["route_override_count"], "1")
        self.assertEqual(
            cleared["route_tool_followup"],
            "glm | glm-5 | reasoning=high | timeout=30 | source=route",
        )

    def test_rule_based_agent_delegate_override_reloads_delegate_summary_and_clear_restores_config(
        self,
    ):
        class _RoutingPlanner(BasePlanner):
            def _route_status_specs(self):
                return {
                    "policy_helper": {},
                    "tool_followup": {},
                    "final_synthesis": {},
                }

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                return AgentIntent(assistant_text="ok")

        def _main_config():
            return ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                model_key="gpt_54",
                planner_kind="openai_responses",
                wire_api="responses",
                base_url="https://relay.example/v1",
                reasoning_effort="high",
                source="test",
                config_path="/tmp/config.toml",
                auth_path="/tmp/auth.json",
                raw_model={
                    "delegation": {
                        "teammate": {
                            "provider": "glm",
                            "model": "glm_5",
                            "reasoning_effort": "medium",
                            "timeout": 40,
                        }
                    }
                },
            )

        def _delegate_config(*, cwd=None, env_overrides=None):
            del cwd
            selector = str((env_overrides or {}).get("AGENT_CLI_MODEL") or "").strip()
            if selector == "glm_5":
                return ProviderConfig(
                    model="glm-5",
                    api_key="sk-test",
                    provider_name="glm",
                    model_key="glm_5",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    base_url="https://glm.example/v1",
                    reasoning_effort=str(
                        (env_overrides or {}).get("AGENT_CLI_REASONING_EFFORT") or "medium"
                    ),
                    source="test",
                    config_path="/tmp/config.toml",
                    auth_path="/tmp/auth.json",
                )
            if selector == "gpt_54":
                return ProviderConfig(
                    model="gpt-5.4",
                    api_key="sk-test",
                    provider_name="openai",
                    model_key="gpt_54",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    base_url="https://relay.example/v1",
                    reasoning_effort=str(
                        (env_overrides or {}).get("AGENT_CLI_REASONING_EFFORT") or "high"
                    ),
                    source="test",
                    config_path="/tmp/config.toml",
                    auth_path="/tmp/auth.json",
                )
            return None

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch(
                "cli.agent_cli.agent.load_provider_config",
                side_effect=lambda **kwargs: _main_config(),
            ):
                with patch(
                    "cli.agent_cli.providers.model_routing._load_provider_config_for_route",
                    side_effect=_delegate_config,
                ):
                    with patch(
                        "cli.agent_cli.agent.build_planner",
                        side_effect=lambda config, **kwargs: _RoutingPlanner(
                            config,
                            host_platform=kwargs.get("host_platform"),
                            cwd=kwargs.get("cwd"),
                            plugin_manager_factory=kwargs.get("plugin_manager_factory"),
                        ),
                    ):
                        agent = RuleBasedAgent()
                        initial = agent.provider_status()
                        updated = agent.configure_delegate_selection(
                            "teammate",
                            model="inherit",
                            timeout="25",
                        )
                        cleared = agent.configure_delegate_selection("teammate", clear=True)

        self.assertEqual(
            initial["delegate_subagent"],
            "openai | gpt-5.4 | reasoning=high | source=inherit_main",
        )
        self.assertEqual(
            initial["delegate_teammate"],
            "glm | glm-5 | reasoning=medium | timeout=40 | source=delegation",
        )
        self.assertEqual(
            updated["delegate_teammate"],
            "openai | gpt-5.4 | reasoning=high | timeout=25 | source=session_override_inherit_main",
        )
        self.assertEqual(updated["delegate_override_count"], "1")
        self.assertEqual(
            cleared["delegate_teammate"],
            "glm | glm-5 | reasoning=medium | timeout=40 | source=delegation",
        )

    def test_provider_command_surfaces_last_runtime_error_without_dropping_ready_status(self):
        class _Planner:
            def __init__(self) -> None:
                self.fail = True

            @staticmethod
            def public_summary():
                return {
                    "provider_name": "deepseek",
                    "model_key": "deepseek_reasoner",
                    "planner_kind": "deepseek_reasoner",
                    "model": "deepseek-reasoner",
                    "base_url": "https://api.deepseek.com",
                    "source": "project_local",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                }

            def plan(self, text, history, *, tool_executor=None, attachments=None):
                if self.fail:
                    raise RuntimeError("AuthenticationError: 401 Unauthorized")
                return AgentIntent(assistant_text=f"ok: {text}")

        planner = _Planner()
        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=planner):
                    agent = RuleBasedAgent()
                    runtime = AgentCliRuntime(agent=agent)

                    failed = runtime.handle_prompt("hello")
                    status_after_failure = agent.provider_status()
                    provider_response = runtime.handle_prompt("/provider --verbose")

                    self.assertEqual(
                        failed.assistant_text, "无法继续：AuthenticationError: 401 Unauthorized"
                    )
                    self.assertNotIn("当前 provider", failed.assistant_text)
                    self.assertNotIn("已回退到本地规则模式", failed.assistant_text)
                    self.assertEqual(status_after_failure["provider_ready"], "true")
                    self.assertEqual(status_after_failure["provider_runtime_state"], "degraded")
                    self.assertIn(
                        "AuthenticationError: 401 Unauthorized",
                        status_after_failure["provider_last_error"],
                    )
                    self.assertIn(
                        "provider_runtime_state=degraded", provider_response.assistant_text
                    )
                    self.assertIn(
                        "provider_last_error=RuntimeError: AuthenticationError: 401 Unauthorized",
                        provider_response.assistant_text,
                    )

                    planner.fail = False
                    recovered = runtime.handle_prompt("hello again")
                    status_after_recovery = agent.provider_status()

                    self.assertEqual(recovered.assistant_text, "ok: hello again")
                    self.assertEqual(status_after_recovery["provider_runtime_state"], "ready")
                    self.assertNotIn("provider_last_error", status_after_recovery)

    def test_provider_runtime_400_reports_protocol_error_with_current_provider(self):
        class _Planner:
            @staticmethod
            def public_summary():
                return {
                    "provider_name": "anthropic",
                    "model_key": "claude_sonnet_4",
                    "planner_kind": "anthropic_messages",
                    "model": "claude-sonnet-4-6",
                    "base_url": "https://anthropic.example/messages",
                    "source": "project_local",
                    "config_path": "/tmp/config.toml",
                    "auth_path": "/tmp/auth.json",
                }

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                raise RuntimeError(
                    "BadRequestError: Error code: 400 - {'message': 'Improperly formed request.', 'reason': None}"
                )

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_config", return_value=object()):
                with patch("cli.agent_cli.agent.build_planner", return_value=_Planner()):
                    agent = RuleBasedAgent()
                    failed = agent.plan("日语回答", history=[])

        self.assertEqual(failed.assistant_text, "无法继续：Improperly formed request.")
        self.assertNotIn("当前 provider", failed.assistant_text)
        self.assertNotIn("provider 失败类型", failed.assistant_text)
        self.assertNotIn("当前没有可用的 LLM provider", failed.assistant_text)

    def test_rule_based_agent_applies_session_model_and_reasoning_selection(self):
        catalog = ProviderCatalog(
            providers={
                "openai": ProviderCatalogEntry(
                    provider_name="openai",
                    display_name="OpenAI",
                    base_url="https://relay.example/v1",
                    default_model="gpt_54",
                ),
                "glm": ProviderCatalogEntry(
                    provider_name="glm",
                    display_name="GLM",
                    base_url="https://glm.example/v1",
                    default_model="glm_5",
                ),
            },
            models={
                "gpt_54": ModelCatalogEntry(
                    key="gpt_54",
                    provider_name="openai",
                    model_id="gpt-5.4",
                    supports_reasoning=True,
                ),
                "glm_5": ModelCatalogEntry(
                    key="glm_5",
                    provider_name="glm",
                    model_id="glm-5",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    supports_reasoning=True,
                ),
            },
        )

        class _PlannerFromConfig:
            def __init__(self, config):
                self._config = config

            def public_summary(self):
                return self._config.public_summary()

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del history, tool_executor, attachments, input_items
                return AgentIntent(
                    assistant_text=f"{self._config.model}:{self._config.reasoning_effort}:{text}"
                )

        def _fake_load_provider_config(*, env_overrides=None, **kwargs):
            del kwargs
            overrides = dict(env_overrides or {})
            selector = str(overrides.get("AGENT_CLI_MODEL") or "gpt_54").strip() or "gpt_54"
            provider_name = str(
                overrides.get("AGENT_CLI_PROVIDER") or ("glm" if selector == "glm_5" else "openai")
            ).strip()
            reasoning_effort = str(overrides.get("AGENT_CLI_REASONING_EFFORT") or "high").strip()
            mapping = {
                "gpt_54": (
                    "gpt_54",
                    "gpt-5.4",
                    "openai_responses",
                    "responses",
                    "https://relay.example/v1",
                    "openai",
                ),
                "glm_5": (
                    "glm_5",
                    "glm-5",
                    "openai_chat",
                    "openai_chat",
                    "https://glm.example/v1",
                    "glm",
                ),
            }
            model_key, model_id, planner_kind, wire_api, base_url, provider_name = mapping[selector]
            return ProviderConfig(
                model=model_id,
                api_key="sk-test",
                provider_name=provider_name,
                model_key=model_key,
                planner_kind=planner_kind,
                wire_api=wire_api,
                base_url=base_url,
                reasoning_effort=reasoning_effort,
                source="test",
                config_path="/tmp/config.toml",
                auth_path="/tmp/auth.json",
            )

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_catalog", return_value=catalog):
                with patch(
                    "cli.agent_cli.agent.load_provider_config",
                    side_effect=_fake_load_provider_config,
                ):
                    with patch(
                        "cli.agent_cli.agent.build_planner",
                        side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                    ):
                        agent = RuleBasedAgent()

                        self.assertEqual(agent.provider_status()["provider_model"], "gpt-5.4")
                        self.assertEqual(
                            agent.provider_status()["provider_reasoning_effort"], "high"
                        )

                        switched = agent.configure_model_selection(
                            model="glm_5", reasoning_effort="xhigh"
                        )
                        self.assertEqual(switched["provider_name"], "glm")
                        self.assertEqual(switched["provider_model"], "glm-5")
                        self.assertEqual(switched["provider_reasoning_effort"], "xhigh")

                        reset = agent.configure_model_selection(
                            model="default", reasoning_effort="default"
                        )
                        self.assertEqual(reset["provider_name"], "openai")
                        self.assertEqual(reset["provider_model"], "gpt-5.4")
                        self.assertEqual(reset["provider_reasoning_effort"], "high")

    def test_build_provider_catalog_infers_default_model_from_top_level_selection(self):
        catalog = build_provider_catalog(
            {
                "model_provider": "openai",
                "model": "gpt-5.4",
                "model_providers": {
                    "openai": {
                        "base_url": "https://relay.example/v1",
                        "wire_api": "responses",
                    }
                },
            }
        )

        self.assertIn("openai", catalog.providers)
        self.assertEqual(catalog.providers["openai"].default_model, "gpt-5.4")
        self.assertIn("gpt_5_4", catalog.models)
        self.assertEqual(catalog.models["gpt_5_4"].provider_name, "openai")
        self.assertEqual(catalog.models["gpt_5_4"].model_id, "gpt-5.4")

    def test_rule_based_agent_exposes_public_provider_names_and_switches_by_vendor_alias(self):
        catalog = ProviderCatalog(
            providers={
                "openai": ProviderCatalogEntry(
                    provider_name="openai",
                    display_name="OpenAI",
                    base_url="https://relay.example/v1",
                    wire_api="responses",
                    default_model="gpt_54",
                ),
                "glm": ProviderCatalogEntry(
                    provider_name="glm",
                    display_name="GLM",
                    base_url="https://glm.example/v1",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    default_model="glm_5",
                ),
            },
            models={
                "gpt_54": ModelCatalogEntry(
                    key="gpt_54",
                    provider_name="openai",
                    model_id="gpt-5.4",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    supports_reasoning=True,
                ),
                "glm_5": ModelCatalogEntry(
                    key="glm_5",
                    provider_name="glm",
                    model_id="glm-5",
                    planner_kind="openai_chat",
                    wire_api="openai_chat",
                    supports_reasoning=True,
                ),
            },
        )

        class _PlannerFromConfig:
            def __init__(self, config):
                self._config = config

            def public_summary(self):
                return self._config.public_summary()

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                return AgentIntent(assistant_text="ok")

        def _fake_load_provider_config(*, env_overrides=None, **kwargs):
            del kwargs
            overrides = dict(env_overrides or {})
            selector = str(overrides.get("AGENT_CLI_MODEL") or "gpt_54").strip() or "gpt_54"
            mapping = {
                "gpt_54": (
                    "openai",
                    "gpt_54",
                    "gpt-5.4",
                    "openai_responses",
                    "responses",
                    "https://relay.example/v1",
                ),
                "glm_5": (
                    "glm",
                    "glm_5",
                    "glm-5",
                    "openai_chat",
                    "openai_chat",
                    "https://glm.example/v1",
                ),
            }
            provider_name, model_key, model_id, planner_kind, wire_api, base_url = mapping[selector]
            return ProviderConfig(
                model=model_id,
                api_key="sk-test",
                provider_name=provider_name,
                model_key=model_key,
                planner_kind=planner_kind,
                wire_api=wire_api,
                base_url=base_url,
                reasoning_effort="high",
                source="test",
                config_path="/tmp/config.toml",
                auth_path="/tmp/auth.json",
            )

        class _AvailabilityRegistry:
            def __init__(self, records):
                self._records = records

            def get(self, provider_name, model):
                return self._records.get((provider_name, model))

            def status(self, provider_name, model):
                record = self.get(provider_name, model)
                return record.status if record is not None else ProbeStatus.UNKNOWN

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )

        with patch.dict("os.environ", {}, clear=True):
            with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
                with patch("cli.agent_cli.agent.load_provider_catalog", return_value=catalog):
                    with patch(
                        "cli.agent_cli.agent.load_provider_inputs",
                        return_value=(fake_paths, {}, {"OPENAI_API_KEY": "sk-test"}),
                    ):
                        with patch(
                            "cli.agent_cli.agent._project_claude_home_dir", return_value=None
                        ):
                            with patch(
                                "cli.agent_cli.agent.load_provider_config",
                                side_effect=_fake_load_provider_config,
                            ):
                                with patch(
                                    "cli.agent_cli.agent.build_planner",
                                    side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                                ):
                                    agent = RuleBasedAgent()
                                    agent.set_availability_registry(
                                        _AvailabilityRegistry(
                                            {
                                                ("openai", "gpt-5.4"): AvailabilityRecord(
                                                    provider_name="openai",
                                                    model="gpt-5.4",
                                                    status=ProbeStatus.AVAILABLE,
                                                )
                                            }
                                        )
                                    )
                                    providers = agent.available_providers()
                                    review_gate = agent.provider_review_gate()
                                    models = agent.available_models()
                                    switched = agent.switch_provider("openai")
                                    runtime = AgentCliRuntime(agent=agent)
                                    provider_response = runtime.handle_prompt("/provider --verbose")

        self.assertEqual([item["provider_name"] for item in providers], ["glm", "openai"])
        self.assertIn("provider_status_state", providers[0])
        self.assertEqual(providers[1]["provider_status_state"], "ready")
        self.assertTrue(providers[1]["provider_auth_ready"])
        self.assertTrue(review_gate["expert_review_available"])
        self.assertEqual(review_gate["eligible_provider_count"], 2)
        self.assertEqual(review_gate["preferred_reviewer_candidate_names"], ["glm"])
        self.assertEqual(providers[1]["config_provider_name"], "openai")
        self.assertEqual(providers[1]["planner_kind"], "openai_responses")
        self.assertEqual(models[0]["provider_name"], "glm")
        self.assertEqual(models[1]["provider_name"], "openai")
        self.assertEqual(switched["provider_name"], "openai")
        self.assertEqual(switched["provider_public_name"], "openai")
        self.assertEqual(switched["provider_display_label"], "openai | gpt-5.4 | tool-calls")
        self.assertIn("provider_name=openai", provider_response.assistant_text)
        self.assertIn("provider_route_name=openai", provider_response.assistant_text)
        self.assertIn("expert_review_available=True", provider_response.assistant_text)
        self.assertIn("eligible_provider_count=2", provider_response.assistant_text)

    def test_rule_based_agent_lists_project_local_anthropic_provider_copy(self):
        catalog = ProviderCatalog(
            providers={
                "openai": ProviderCatalogEntry(
                    provider_name="openai",
                    display_name="OpenAI",
                    base_url="https://relay.example/v1",
                    wire_api="responses",
                    default_model="gpt_54",
                ),
            },
            models={
                "gpt_54": ModelCatalogEntry(
                    key="gpt_54",
                    provider_name="openai",
                    model_id="gpt-5.4",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    supports_reasoning=True,
                ),
            },
        )

        class _PlannerFromConfig:
            def __init__(self, config):
                self._config = config

            def public_summary(self):
                return self._config.public_summary()

            def plan(
                self, text, history, *, tool_executor=None, attachments=None, input_items=None
            ):
                del text, history, tool_executor, attachments, input_items
                return AgentIntent(assistant_text="ok")

        def _fake_load_provider_config(*, env_overrides=None, **kwargs):
            del kwargs
            overrides = dict(env_overrides or {})
            selector = str(overrides.get("AGENT_CLI_MODEL") or "gpt_54").strip() or "gpt_54"
            mapping = {
                "gpt_54": (
                    "openai",
                    "gpt_54",
                    "gpt-5.4",
                    "openai_responses",
                    "responses",
                    "https://relay.example/v1",
                ),
                "claude-sonnet-4-6": (
                    "anthropic",
                    "",
                    "claude-sonnet-4-6",
                    "anthropic_messages",
                    "anthropic_messages",
                    "https://claude.example/api",
                ),
            }
            provider_name, model_key, model_id, planner_kind, wire_api, base_url = mapping[selector]
            return ProviderConfig(
                model=model_id,
                api_key="sk-test",
                provider_name=provider_name,
                model_key=model_key,
                planner_kind=planner_kind,
                wire_api=wire_api,
                base_url=base_url,
                reasoning_effort=None,
                source="test",
                config_path="/tmp/config.toml",
                auth_path="/tmp/auth.json",
            )

        fake_paths = SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        )
        anthropic_copy = ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-anthropic",
            provider_name="anthropic",
            model_key="",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
            base_url="https://claude.example/api",
            reasoning_effort=None,
            source="claude_home",
            config_path="/tmp/.config/.claude/settings.json",
            auth_path="/tmp/.config/.claude/config.json",
            raw_provider={"api_key_env": "ANTHROPIC_API_KEY"},
            raw_model={"supports_tools": True},
        )

        with patch("cli.agent_cli.agent.resolve_provider_paths", return_value=fake_paths):
            with patch("cli.agent_cli.agent.load_provider_catalog", return_value=catalog):
                with patch(
                    "cli.agent_cli.agent._project_claude_home_dir",
                    return_value=Path("/tmp/.config"),
                ):
                    with patch(
                        "cli.agent_cli.agent.load_claude_provider_config",
                        return_value=anthropic_copy,
                    ):
                        with patch(
                            "cli.agent_cli.agent.load_provider_config",
                            side_effect=_fake_load_provider_config,
                        ):
                            with patch(
                                "cli.agent_cli.agent.build_planner",
                                side_effect=lambda config, **kwargs: _PlannerFromConfig(config),
                            ):
                                agent = RuleBasedAgent()
                                providers = agent.available_providers()
                                models = agent.available_models()
                                switched = agent.switch_provider("anthropic")
                                runtime = AgentCliRuntime(agent=agent)
                                provider_response = runtime.handle_prompt("/provider anthropic")

        self.assertEqual([item["provider_name"] for item in providers], ["anthropic", "openai"])
        self.assertEqual(providers[0]["default_model"], "claude-sonnet-4-6")
        self.assertEqual(models[0]["provider_name"], "anthropic")
        self.assertEqual(models[0]["model_key"], "claude-sonnet-4-6")
        self.assertEqual(switched["provider_name"], "anthropic")
        self.assertEqual(switched["provider_public_name"], "anthropic")
        self.assertEqual(switched["provider_model"], "claude-sonnet-4-6")
        self.assertIn("switched provider to anthropic", provider_response.assistant_text)

    def test_model_command_updates_current_session_reasoning_effort(self):
        class _SessionAgent:
            def __init__(self) -> None:
                self.status = {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            def provider_status(self):
                return dict(self.status)

            def configure_model_selection(self, *, model=None, reasoning_effort=None):
                if model is not None:
                    self.status["model_key"] = str(model)
                if reasoning_effort is not None:
                    self.status["provider_reasoning_effort"] = str(reasoning_effort)
                return dict(self.status)

            def plan(self, text, history=None, *, tool_executor=None, attachments=None):
                del history, tool_executor, attachments
                return AgentIntent(assistant_text=text)

        runtime = AgentCliRuntime(agent=_SessionAgent())

        updated = runtime.handle_prompt("/model --reasoning-effort xhigh")
        self.assertIn("updated user default reasoning_effort=xhigh", updated.assistant_text)
        self.assertIn("current_reasoning_effort=xhigh", updated.assistant_text)

        current = runtime.handle_prompt("/model")
        self.assertIn("current_reasoning_effort=xhigh", current.assistant_text)

    def test_model_route_command_updates_and_clears_session_override(self):
        class _SessionRouteAgent:
            def __init__(self) -> None:
                self.route_overrides: dict[str, dict[str, str]] = {}

            def provider_status(self):
                route_status = "openai | gpt-5.4 | reasoning=high | source=main"
                override = self.route_overrides.get("tool_followup")
                if override:
                    route_status = (
                        f"{override.get('provider') or 'openai'} | "
                        f"{override.get('model') or 'gpt_54'} | "
                        f"reasoning={override.get('reasoning_effort') or 'high'} | "
                        f"timeout={override.get('timeout') or 30} | "
                        "source=session_override"
                    )
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "route_policy_helper": "openai | gpt-5.4 | source=main",
                    "route_tool_followup": route_status,
                    "route_final_synthesis": "openai | gpt-5.4 | source=main",
                }

            def session_route_overrides(self):
                return {
                    route_name: dict(payload)
                    for route_name, payload in self.route_overrides.items()
                }

            def configure_route_selection(
                self,
                route_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    self.route_overrides.pop(route_name, None)
                    return self.provider_status()
                payload: dict[str, str] = {}
                if model is not None:
                    payload["model"] = str(model)
                if provider is not None:
                    payload["provider"] = str(provider)
                if reasoning_effort is not None:
                    payload["reasoning_effort"] = str(reasoning_effort)
                if timeout is not None:
                    payload["timeout"] = str(timeout)
                self.route_overrides[route_name] = payload
                return self.provider_status()

            def plan(self, text, history=None, *, tool_executor=None, attachments=None):
                del history, tool_executor, attachments
                return AgentIntent(assistant_text=text)

        runtime = AgentCliRuntime(agent=_SessionRouteAgent())

        updated = runtime.handle_prompt(
            "/model-route tool_followup glm_5 provider glm reasoning-effort high timeout 30"
        )
        current = runtime.handle_prompt("/model-route tool_followup")
        cleared = runtime.handle_prompt("/model-route tool_followup clear")

        self.assertIn("updated session route override route=tool_followup", updated.assistant_text)
        self.assertIn("source=session_override", updated.assistant_text)
        self.assertIn("override_active=true", current.assistant_text)
        self.assertIn("cleared session route override route=tool_followup", cleared.assistant_text)
        self.assertIn("override_active=false", cleared.assistant_text)

    def test_delegate_model_command_supports_session_override_and_clear(self):
        class _SessionDelegateAgent:
            def __init__(self) -> None:
                self.delegate_overrides: dict[str, dict[str, str]] = {}

            def provider_status(self):
                delegate_subagent = "openai | gpt-5.4 | reasoning=high | source=inherit_main"
                delegate_teammate = "openai | gpt-5.4 | reasoning=high | source=inherit_main"
                teammate_override = self.delegate_overrides.get("teammate")
                if teammate_override is not None:
                    provider_name = str(teammate_override.get("provider") or "openai")
                    model = (
                        "gpt-5.4"
                        if str(teammate_override.get("model") or "").strip().lower() == "inherit"
                        else "glm-5"
                    )
                    delegate_teammate = (
                        f"{provider_name} | {model} | "
                        f"reasoning={teammate_override.get('reasoning_effort') or 'high'} | "
                        f"timeout={teammate_override.get('timeout') or '30'} | "
                        "source=session_override"
                    )
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "delegate_subagent": delegate_subagent,
                    "delegate_teammate": delegate_teammate,
                }

            def session_delegate_overrides(self):
                return {
                    role_name: dict(payload)
                    for role_name, payload in self.delegate_overrides.items()
                }

            def configure_delegate_selection(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    self.delegate_overrides.pop(role_name, None)
                    return self.provider_status()
                payload: dict[str, str] = {}
                if model is not None:
                    payload["model"] = str(model)
                if provider is not None:
                    payload["provider"] = str(provider)
                if reasoning_effort is not None:
                    payload["reasoning_effort"] = str(reasoning_effort)
                if timeout is not None:
                    payload["timeout"] = str(timeout)
                self.delegate_overrides[role_name] = payload
                return self.provider_status()

            def plan(self, text, history=None, *, tool_executor=None, attachments=None):
                del history, tool_executor, attachments
                return AgentIntent(assistant_text=text)

        runtime = AgentCliRuntime(agent=_SessionDelegateAgent())

        updated = runtime.handle_prompt(
            "/delegate-model teammate glm_5 provider glm reasoning-effort medium timeout 30"
        )
        current = runtime.handle_prompt("/delegate-model teammate")
        cleared = runtime.handle_prompt("/delegate-model teammate clear")

        self.assertIn("updated session delegation override role=teammate", updated.assistant_text)
        self.assertIn("source=session_override", updated.assistant_text)
        self.assertIn("override_active=true", current.assistant_text)
        self.assertIn("cleared session delegation override role=teammate", cleared.assistant_text)
        self.assertIn("override_active=false", cleared.assistant_text)

    def test_model_route_slash_invocation_native_path_does_not_require_parse_args(self):
        class _RouteRuntime:
            class _Agent:
                @staticmethod
                def provider_status():
                    return {
                        "route_tool_followup": "glm | glm-5 | reasoning=high | timeout=30 | source=session_override",
                    }

                @staticmethod
                def session_route_overrides():
                    return {"tool_followup": {"provider": "glm"}}

            def __init__(self) -> None:
                self.agent = self._Agent()

            @staticmethod
            def configure_route_selection(
                route_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    return {"route_tool_followup": "glm | glm-5 | source=main"}
                return {
                    f"route_{route_name}": (
                        f"{provider or 'glm'} | {model or 'glm-5'} | reasoning={reasoning_effort or 'high'} | "
                        f"timeout={timeout or '30'} | source=session_override"
                    )
                }

        runtime = _RouteRuntime()
        text, events = handle_provider_command(
            runtime,
            name="model-route",
            arg_text="",
            slash_invocation=parse_slash_invocation(
                "/model-route tool_followup glm_5 provider glm reasoning-effort high timeout 30"
            ),
            switch_disabled_result=lambda exc: (str(exc), []),
        ) or ("", [])

        self.assertEqual(events, [])
        self.assertIn("updated session route override route=tool_followup", text)
        self.assertIn("source=session_override", text)

    def test_delegate_model_slash_invocation_native_path_does_not_require_parse_args(self):
        class _DelegateRuntime:
            class _Agent:
                @staticmethod
                def provider_status():
                    return {
                        "delegate_teammate": "glm | glm-5 | reasoning=medium | timeout=30 | source=session_override",
                    }

                @staticmethod
                def session_delegate_overrides():
                    return {"teammate": {"provider": "glm"}}

            def __init__(self) -> None:
                self.agent = self._Agent()

            @staticmethod
            def configure_delegate_selection(
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    return {"delegate_teammate": "openai | gpt-5.4 | source=inherit_main"}
                return {
                    f"delegate_{role_name}": (
                        f"{provider or 'glm'} | {model or 'glm-5'} | reasoning={reasoning_effort or 'medium'} | "
                        f"timeout={timeout or '30'} | source=session_override"
                    )
                }

        runtime = _DelegateRuntime()
        text, events = handle_provider_command(
            runtime,
            name="delegate-model",
            arg_text="",
            slash_invocation=parse_slash_invocation(
                "/delegate-model teammate glm_5 provider glm reasoning-effort medium timeout 30"
            ),
            switch_disabled_result=lambda exc: (str(exc), []),
        ) or ("", [])

        self.assertEqual(events, [])
        self.assertIn("updated session delegation override role=teammate", text)
        self.assertIn("source=session_override", text)

    def test_runtime_spawn_agent_result_uses_resolved_delegation_config(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                assert role_name == "subagent"
                assert model is None
                assert provider is None
                assert reasoning_effort is None
                assert timeout is None
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=28,
                    source="delegation",
                )

        class _DelegatedPlanner:
            @staticmethod
            def plan(
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                assert user_text == "检查多模型差异"
                assert history == []
                assert tool_executor is not None
                assert isinstance(input_items, list)
                assert input_items
                assert isinstance(prompt_cache_key, str)
                return AgentIntent(assistant_text="delegated answer")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner", return_value=_DelegatedPlanner()
        ) as build_planner:
            result = runtime.spawn_agent_result(task="检查多模型差异", role="subagent")

        build_planner.assert_called_once()
        delegated_config = build_planner.call_args.args[0]
        self.assertEqual(delegated_config.model, "glm-5")
        self.assertEqual(delegated_config.provider_name, "glm")
        self.assertEqual(delegated_config.raw_model.get("model_timeout"), 28)
        self.assertEqual(result.assistant_text, "delegated answer")
        self.assertEqual(result.tool_events[0].name, "spawn_agent")
        self.assertEqual(result.tool_events[0].payload["model"], "glm-5")
        self.assertEqual(result.tool_events[0].payload["timeout"], 28)
        self.assertEqual(result.tool_events[0].payload["source"], "delegation")
        self.assertTrue(result.tool_events[0].payload["result_ready"])
        self.assertTrue(result.tool_events[0].payload["adopted"])
        self.assertEqual(result.tool_events[0].payload["parallel_group"], "sync_inline")
        self.assertEqual(result.tool_events[0].payload["parallel_limit"], 1)
        self.assertEqual(result.tool_events[0].payload["result_contract"]["goal"], "检查多模型差异")
        self.assertEqual(result.tool_events[0].payload["result_contract"]["status"], "completed")
        self.assertEqual(
            result.tool_events[0].payload["result_contract"]["next_action"], "already_adopted"
        )

    def test_runtime_spawn_agent_result_contract_supports_structured_artifact_and_relative_paths(
        self,
    ):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            @staticmethod
            def plan(
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(
                    assistant_text=json.dumps(
                        {"summary": "ok", "files": ["pkg/example.py"]},
                        ensure_ascii=False,
                    ),
                    tool_events=[
                        ToolEvent(
                            name="file_read",
                            ok=True,
                            summary="file loaded",
                            payload={"path": "pkg/example.py"},
                        )
                    ],
                )

        with TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "pkg" / "example.py"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text("print('ok')\n", encoding="utf-8")
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            with patch("cli.agent_cli.runtime.build_planner", return_value=_DelegatedPlanner()):
                result = runtime.spawn_agent_result(task="结构化检查", role="subagent")

        contract = result.tool_events[0].payload["result_contract"]
        self.assertEqual(contract["artifact"]["kind"], "structured")
        self.assertEqual(contract["artifact"]["format"], "json")
        self.assertEqual(contract["artifact"]["structured"]["summary"], "ok")
        self.assertEqual(contract["confidence"], "high")
        self.assertEqual(contract["touched_scope"], [str(target_path.resolve())])

    def test_runtime_spawn_agent_result_contract_marks_empty_completion_low_confidence(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _EmptyPlanner:
            @staticmethod
            def plan(
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent()

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch("cli.agent_cli.runtime.build_planner", return_value=_EmptyPlanner()):
            result = runtime.spawn_agent_result(task="空结果检查", role="subagent")

        contract = result.tool_events[0].payload["result_contract"]
        self.assertEqual(contract["artifact"]["kind"], "empty")
        self.assertEqual(contract["confidence"], "low")
        self.assertEqual(contract["next_action"], "already_adopted")
        self.assertEqual(contract["summary"], "delegated task completed")

    def test_runtime_teammate_session_override_affects_spawn_execution(self):
        class _SessionDelegateAgent:
            host_platform = current_host_platform()

            def __init__(self) -> None:
                self.delegate_overrides: dict[str, dict[str, str]] = {}

            def provider_status(self):
                delegate_teammate = "openai | gpt-5.4 | reasoning=high | source=inherit_main"
                teammate_override = self.delegate_overrides.get("teammate")
                if teammate_override is not None:
                    delegate_teammate = (
                        f"{teammate_override.get('provider') or 'glm'} | glm-5 | "
                        f"reasoning={teammate_override.get('reasoning_effort') or 'medium'} | "
                        f"timeout={teammate_override.get('timeout') or '30'} | "
                        "source=session_override"
                    )
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "delegate_teammate": delegate_teammate,
                }

            def configure_delegate_selection(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    self.delegate_overrides.pop(role_name, None)
                    return self.provider_status()
                payload: dict[str, str] = {}
                if model is not None:
                    payload["model"] = str(model)
                if provider is not None:
                    payload["provider"] = str(provider)
                if reasoning_effort is not None:
                    payload["reasoning_effort"] = str(reasoning_effort)
                if timeout is not None:
                    payload["timeout"] = str(timeout)
                self.delegate_overrides[role_name] = payload
                return self.provider_status()

            def resolve_delegate_execution(
                self, role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                assert role_name == "teammate"
                assert model is None
                assert provider is None
                assert reasoning_effort is None
                assert timeout is None
                override = self.delegate_overrides.get("teammate") or {}
                assert override.get("provider") == "glm"
                assert override.get("model") == "glm_5"
                assert override.get("reasoning_effort") == "medium"
                assert override.get("timeout") == "30"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=30,
                    source="session_override",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_SessionDelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        updated = runtime.handle_prompt(
            "/delegate-model teammate glm_5 --provider glm --reasoning-effort medium --timeout 30"
        )
        self.assertIn("updated session delegation override role=teammate", updated.assistant_text)

        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(task="总结仓库入口", role="teammate")
            self.assertEqual(spawned.tool_events[0].payload["provider_name"], "glm")
            self.assertEqual(spawned.tool_events[0].payload["model"], "glm-5")
            self.assertEqual(spawned.tool_events[0].payload["source"], "session_override")

            waited = runtime.wait_agent_result(
                spawned.tool_events[0].payload["agent_id"],
                timeout_ms=1000,
            )

        self.assertEqual(waited.assistant_text, "answer:总结仓库入口")

    def test_runtime_spawn_and_wait_agent_results_preserve_delegation_metadata(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="验证 smoke",
                role="subagent",
                async_mode=True,
                reason="verify_side_task",
                mode="background",
                wait_required=False,
                task_shape="read_only",
            )
            self.assertEqual(
                spawned.tool_events[0].payload["delegation_reason"], "verify_side_task"
            )
            self.assertEqual(spawned.tool_events[0].payload["delegation_mode"], "background")
            self.assertEqual(spawned.tool_events[0].payload["task_shape"], "read_only")
            self.assertFalse(spawned.tool_events[0].payload["wait_required"])
            self.assertEqual(spawned.tool_events[0].payload["completion_policy"], "silent")
            self.assertEqual(spawned.tool_events[0].payload["completion_state"], "pending")
            self.assertEqual(spawned.tool_events[0].payload["parallel_group"], "read_only")
            self.assertEqual(spawned.tool_events[0].payload["parallel_limit"], 3)
            self.assertFalse(spawned.tool_events[0].payload["adopted"])
            agent_id = spawned.tool_events[0].payload["agent_id"]

            waited = runtime.wait_agent_result(
                agent_id, timeout_ms=1000, reason="wait_for_child_result"
            )
            self.assertEqual(waited.tool_events[0].payload["delegation_reason"], "verify_side_task")
            self.assertEqual(waited.tool_events[0].payload["wait_reason"], "wait_for_child_result")
            self.assertTrue(waited.tool_events[0].payload["wait_required"])
            self.assertEqual(waited.tool_events[0].payload["wait_decision"], "blocking_join")
            self.assertGreaterEqual(waited.tool_events[0].payload["wait_blocked_ms"], 0)
            self.assertFalse(waited.tool_events[0].payload["wait_timed_out"])
            self.assertTrue(waited.tool_events[0].payload["result_ready"])
            self.assertTrue(waited.tool_events[0].payload["adopted"])
            self.assertEqual(waited.tool_events[0].payload["terminal_state"], "completed")
            self.assertEqual(waited.tool_events[0].payload["terminal_reason"], "completed")
            self.assertIn("adopted_at", waited.tool_events[0].payload)
            self.assertEqual(
                waited.tool_events[0].payload["result_contract"]["status"], "completed"
            )
            self.assertEqual(waited.tool_events[0].payload["completion_policy"], "silent")
            self.assertEqual(waited.tool_events[0].payload["completion_state"], "adopted")
            self.assertEqual(
                waited.tool_events[0].payload["result_contract"]["next_action"], "already_adopted"
            )

    def test_runtime_wait_agent_status_snapshot_does_not_block_when_wait_not_required(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _ControlledPlanner:
            started = threading.Event()
            release = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                self.__class__.started.set()
                self.__class__.release.wait(timeout=5)
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _ControlledPlanner.started = threading.Event()
        _ControlledPlanner.release = threading.Event()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _ControlledPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="slow background verify",
                role="subagent",
                async_mode=True,
                reason="background_side_task",
                mode="background",
                wait_required=False,
                task_shape="long_running",
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_ControlledPlanner.started.wait(timeout=3))
            snapshot = runtime.wait_agent_result(agent_id, timeout_ms=3000, wait_required=False)
            self.assertTrue(snapshot.tool_events[0].ok)
            self.assertEqual(snapshot.tool_events[0].summary, "wait_agent status snapshot")
            self.assertEqual(snapshot.tool_events[0].payload["wait_decision"], "status_snapshot")
            self.assertFalse(snapshot.tool_events[0].payload["wait_required"])
            self.assertFalse(snapshot.tool_events[0].payload["wait_timed_out"])
            self.assertEqual(snapshot.tool_events[0].payload["status"], "running")
            self.assertFalse(snapshot.tool_events[0].payload["adopted"])
            self.assertEqual(
                snapshot.tool_events[0].payload["result_contract"]["status"], "running"
            )
            self.assertLess(snapshot.tool_events[0].payload["wait_blocked_ms"], 500)

            _ControlledPlanner.release.set()
            completed = runtime.wait_agent_result(
                agent_id, timeout_ms=3000, reason="wait_for_child_result"
            )
            self.assertEqual(completed.tool_events[0].payload["wait_decision"], "blocking_join")
            self.assertEqual(completed.tool_events[0].payload["status"], "completed")
            self.assertTrue(completed.tool_events[0].payload["adopted"])
            self.assertEqual(
                completed.tool_events[0].payload["result_contract"]["next_action"],
                "already_adopted",
            )
            self.assertEqual(completed.assistant_text, "answer:slow background verify")

    def test_runtime_wait_agent_timeout_preserves_pending_result_contract(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _SlowPlanner:
            started = threading.Event()
            release = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, tool_executor, attachments, input_items, prompt_cache_key
                self.__class__.started.set()
                self.__class__.release.wait(timeout=5)
                return AgentIntent(assistant_text="done")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _SlowPlanner.started = threading.Event()
        _SlowPlanner.release = threading.Event()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _SlowPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="timeout verify", role="subagent", async_mode=True
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_SlowPlanner.started.wait(timeout=3))
            timed_out = runtime.wait_agent_result(
                agent_id, timeout_ms=50, reason="wait_for_child_result"
            )
            payload = timed_out.tool_events[0].payload
            self.assertEqual(payload["status"], "running")
            self.assertTrue(payload["wait_timed_out"])
            self.assertEqual(payload["result_contract"]["status"], "running")
            self.assertEqual(payload["result_contract"]["artifact"]["kind"], "pending")
            self.assertEqual(payload["result_contract"]["confidence"], "pending")
            self.assertEqual(
                payload["result_contract"]["next_action"], "continue_main_thread_or_wait"
            )
            workflow = runtime.agent_workflow_result(agent_id)
            workflow_payload = workflow.tool_events[0].payload
            self.assertEqual(workflow_payload["last_wait_decision"], "blocking_join")
            self.assertEqual(workflow_payload["last_wait_reason"], "wait_for_child_result")
            self.assertTrue(workflow_payload["last_wait_timed_out"])
            self.assertGreaterEqual(workflow_payload["last_wait_blocked_ms"], 50)
            self.assertIn("last_wait_decision=blocking_join", workflow.assistant_text)
            self.assertIn("last_wait_timed_out=true", workflow.assistant_text)

            _SlowPlanner.release.set()
            completed = runtime.wait_agent_result(agent_id, timeout_ms=1000)

        self.assertEqual(completed.tool_events[0].payload["status"], "completed")

    def test_runtime_failed_delegated_agent_exposes_timeout_telemetry(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _TimeoutPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del user_text, history, tool_executor, attachments, input_items, prompt_cache_key
                time.sleep(0.02)
                raise TimeoutError("planner request timed out")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _TimeoutPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="timeout telemetry", role="subagent", async_mode=True
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            waited = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            payload = waited.tool_events[0].payload
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["terminal_state"], "failed")
            self.assertTrue(payload["timeout_hit"])
            self.assertEqual(payload["timeout_reason"], "model_timeout")
            self.assertEqual(payload["timeout_source"], "planner")
            self.assertEqual(payload["timeout_budget_seconds"], 18)
            self.assertGreaterEqual(payload["wall_time_ms"], 20)
            self.assertGreaterEqual(payload["current_step_wall_time_ms"], 20)

            workflow = runtime.agent_workflow_result(agent_id)
            workflow_payload = workflow.tool_events[0].payload
            self.assertTrue(workflow_payload["timeout_hit"])
            self.assertEqual(workflow_payload["timeout_reason"], "model_timeout")
            self.assertEqual(workflow_payload["timeout_source"], "planner")
            self.assertEqual(workflow_payload["timeout_budget_seconds"], 18)
            self.assertGreaterEqual(workflow_payload["wall_time_ms"], 20)

    def test_runtime_callback_suppression_scope_restores_activity_and_turn_callbacks(self):
        activity_events: list[ActivityEvent] = []
        turn_events: list[dict[str, object]] = []
        runtime = AgentCliRuntime(
            activity_callback=activity_events.append,
            turn_event_callback=lambda event: turn_events.append(dict(event)),
        )

        runtime._emit_activity(ActivityEvent(title="visible-1", code="visible.1"))
        runtime._emit_turn_event({"type": "visible.1"})

        with runtime._bound_callback_suppression(
            suppress_activity=True,
            suppress_turn_events=True,
        ):
            self.assertTrue(runtime._activity_callbacks_suppressed())
            self.assertTrue(runtime._turn_event_callbacks_suppressed())
            runtime._emit_activity(ActivityEvent(title="hidden", code="hidden"))
            runtime._emit_turn_event({"type": "hidden"})

        self.assertFalse(runtime._activity_callbacks_suppressed())
        self.assertFalse(runtime._turn_event_callbacks_suppressed())

        runtime._emit_activity(ActivityEvent(title="visible-2", code="visible.2"))
        runtime._emit_turn_event({"type": "visible.2"})

        self.assertEqual([event.title for event in activity_events], ["visible-1", "visible-2"])
        self.assertEqual([event["type"] for event in turn_events], ["visible.1", "visible.2"])

    def test_runtime_background_delegated_shell_activity_isolated_from_foreground_callback(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _ShellDelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, attachments, input_items, prompt_cache_key
                command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                    "print('delegated-background-output')"
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 250"
                )
                return AgentIntent(
                    assistant_text=f"answer:{user_text}",
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        activity_events: list[ActivityEvent] = []
        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                activity_callback=activity_events.append,
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            foreground_command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                "print('foreground-visible-output')"
            )
            runtime._run_command_text_result(
                f"/exec_command --cmd {shlex.quote(foreground_command)} --yield-time-ms 250"
            )
            self.assertTrue(any(event.code == "command.output" for event in activity_events))

            with patch(
                "cli.agent_cli.runtime.build_planner",
                side_effect=lambda *args, **kwargs: _ShellDelegatedPlanner(),
            ):
                spawned = runtime.spawn_agent_result(
                    task="background shell task",
                    role="subagent",
                    async_mode=True,
                    mode="background",
                    wait_required=False,
                    task_shape="long_running",
                )
                after_spawn_activity_count = len(activity_events)
                agent_id = spawned.tool_events[0].payload["agent_id"]

                snapshot = None
                for _ in range(20):
                    snapshot = runtime.wait_agent_result(
                        agent_id, timeout_ms=250, wait_required=False
                    )
                    if snapshot.tool_events[0].payload["status"] == "completed":
                        break
                    time.sleep(0.05)
                assert snapshot is not None
                self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
                self.assertFalse(snapshot.tool_events[0].payload["adopted"])
                self.assertEqual(len(activity_events), after_spawn_activity_count)

                completed = runtime.wait_agent_result(agent_id, timeout_ms=4000)
                self.assertEqual(completed.tool_events[0].payload["status"], "completed")
                self.assertIn("delegated-background-output", completed.assistant_text)
                self.assertTrue(completed.tool_events[0].payload["adopted"])

            followup_command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                "print('foreground-visible-output-2')"
            )
            runtime._run_command_text_result(
                f"/exec_command --cmd {shlex.quote(followup_command)} --yield-time-ms 250"
            )
            self.assertGreater(len(activity_events), after_spawn_activity_count)

    def test_runtime_async_workspace_mutating_delegated_agents_are_serialized(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _SerialPlanner:
            started: list[str] = []
            first_started = threading.Event()
            second_started = threading.Event()
            release_first = threading.Event()
            lock = threading.Lock()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                with self.__class__.lock:
                    self.__class__.started.append(user_text)
                if user_text == "write first":
                    self.__class__.first_started.set()
                    self.__class__.release_first.wait(timeout=5)
                else:
                    self.__class__.second_started.set()
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _SerialPlanner.started = []
        _SerialPlanner.first_started = threading.Event()
        _SerialPlanner.second_started = threading.Event()
        _SerialPlanner.release_first = threading.Event()
        _SerialPlanner.lock = threading.Lock()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _SerialPlanner(),
        ):
            first = runtime.spawn_agent_result(
                task="write first",
                role="subagent",
                async_mode=True,
                task_shape="workspace_mutating",
            )
            first_id = first.tool_events[0].payload["agent_id"]
            self.assertTrue(_SerialPlanner.first_started.wait(timeout=3))

            second = runtime.spawn_agent_result(
                task="write second",
                role="subagent",
                async_mode=True,
                task_shape="workspace_mutating",
            )
            second_id = second.tool_events[0].payload["agent_id"]

            queued_snapshot = None
            for _ in range(20):
                queued_snapshot = runtime.wait_agent_result(
                    second_id, timeout_ms=250, wait_required=False
                )
                if queued_snapshot.tool_events[0].payload.get("scheduler_reason"):
                    break
                time.sleep(0.05)
            assert queued_snapshot is not None
            self.assertEqual(queued_snapshot.tool_events[0].payload["status"], "queued")
            self.assertEqual(queued_snapshot.tool_events[0].payload["parallel_group"], "serial")
            self.assertEqual(queued_snapshot.tool_events[0].payload["parallel_limit"], 1)
            self.assertEqual(
                queued_snapshot.tool_events[0].payload["scheduler_reason"],
                "serialized_by_active_child",
            )
            self.assertFalse(_SerialPlanner.second_started.is_set())

            _SerialPlanner.release_first.set()
            first_wait = runtime.wait_agent_result(first_id, timeout_ms=3000)
            second_wait = runtime.wait_agent_result(second_id, timeout_ms=3000)

        self.assertEqual(first_wait.tool_events[0].payload["status"], "completed")
        self.assertEqual(second_wait.tool_events[0].payload["status"], "completed")
        self.assertTrue(_SerialPlanner.second_started.is_set())
        self.assertEqual(_SerialPlanner.started, ["write first", "write second"])

    def test_runtime_async_read_only_delegated_agents_can_run_in_parallel(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _ParallelPlanner:
            started: list[str] = []
            two_started = threading.Event()
            release = threading.Event()
            lock = threading.Lock()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                with self.__class__.lock:
                    self.__class__.started.append(user_text)
                    if len(self.__class__.started) >= 2:
                        self.__class__.two_started.set()
                self.__class__.release.wait(timeout=5)
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _ParallelPlanner.started = []
        _ParallelPlanner.two_started = threading.Event()
        _ParallelPlanner.release = threading.Event()
        _ParallelPlanner.lock = threading.Lock()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _ParallelPlanner(),
        ):
            first = runtime.spawn_agent_result(
                task="read first",
                role="subagent",
                async_mode=True,
                task_shape="read_only",
            )
            second = runtime.spawn_agent_result(
                task="read second",
                role="subagent",
                async_mode=True,
                task_shape="read_only",
            )
            first_id = first.tool_events[0].payload["agent_id"]
            second_id = second.tool_events[0].payload["agent_id"]

            self.assertTrue(_ParallelPlanner.two_started.wait(timeout=3))
            first_snapshot = runtime.wait_agent_result(
                first_id, timeout_ms=250, wait_required=False
            )
            second_snapshot = runtime.wait_agent_result(
                second_id, timeout_ms=250, wait_required=False
            )
            self.assertEqual(first_snapshot.tool_events[0].payload["status"], "running")
            self.assertEqual(second_snapshot.tool_events[0].payload["status"], "running")
            self.assertEqual(first_snapshot.tool_events[0].payload["parallel_group"], "read_only")
            self.assertEqual(second_snapshot.tool_events[0].payload["parallel_group"], "read_only")
            self.assertEqual(first_snapshot.tool_events[0].payload["parallel_limit"], 3)
            self.assertEqual(second_snapshot.tool_events[0].payload["parallel_limit"], 3)

            _ParallelPlanner.release.set()
            first_wait = runtime.wait_agent_result(first_id, timeout_ms=3000)
            second_wait = runtime.wait_agent_result(second_id, timeout_ms=3000)

        self.assertEqual(first_wait.tool_events[0].payload["status"], "completed")
        self.assertEqual(second_wait.tool_events[0].payload["status"], "completed")
        self.assertCountEqual(_ParallelPlanner.started, ["read first", "read second"])

    def test_runtime_async_delegated_agent_lifecycle_supports_wait_send_resume_and_close(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            calls: list[dict] = []

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                self.__class__.calls.append(
                    {
                        "user_text": user_text,
                        "history": list(history or []),
                        "input_items": list(input_items or []),
                        "prompt_cache_key": prompt_cache_key,
                    }
                )
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="first turn", role="subagent", async_mode=True
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(first_wait.tool_events[0].payload["status"], "completed")
            self.assertEqual(first_wait.assistant_text, "answer:first turn")

            queued = runtime.send_input_result(agent_id, message="second turn")
            self.assertEqual(queued.tool_events[0].name, "send_input")

            second_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(second_wait.assistant_text, "answer:second turn")

            closed = runtime.close_agent_result(agent_id)
            self.assertEqual(closed.tool_events[0].payload["status"], "closed")
            with self.assertRaises(RuntimeError):
                runtime.send_input_result(agent_id, message="blocked turn")

            resumed = runtime.resume_agent_result(agent_id)
            self.assertEqual(resumed.tool_events[0].payload["status"], "completed")

            runtime.send_input_result(agent_id, message="third turn", interrupt=True)
            third_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(third_wait.assistant_text, "answer:third turn")
            self.assertEqual(third_wait.tool_events[0].payload["step_count"], 3)
            self.assertEqual(third_wait.tool_events[0].payload["current_step_id"], "step_3")
            self.assertEqual(third_wait.tool_events[0].payload["current_step_status"], "completed")
            self.assertGreaterEqual(third_wait.tool_events[0].payload["checkpoint_count"], 10)

        self.assertEqual(
            [item["user_text"] for item in _DelegatedPlanner.calls],
            ["first turn", "second turn", "third turn"],
        )
        second_items = _DelegatedPlanner.calls[1]["input_items"]
        third_items = _DelegatedPlanner.calls[2]["input_items"]
        self.assertTrue(
            any(
                "answer:first turn" in json.dumps(item, ensure_ascii=False) for item in second_items
            )
        )
        self.assertTrue(
            any(
                "answer:second turn" in json.dumps(item, ensure_ascii=False) for item in third_items
            )
        )

    def test_runtime_delegated_agent_workflow_state_supports_retry_recovery(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _FlakyDelegatedPlanner:
            attempts: dict[str, int] = {}

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                attempt = self.__class__.attempts.get(user_text, 0) + 1
                self.__class__.attempts[user_text] = attempt
                if user_text == "second turn" and attempt == 1:
                    raise RuntimeError("temporary failure")
                return AgentIntent(assistant_text=f"answer:{user_text}:attempt{attempt}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _FlakyDelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="first turn", role="subagent", async_mode=True
            )
            agent_id = spawned.tool_events[0].payload["agent_id"]

            first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(first_wait.assistant_text, "answer:first turn:attempt1")

            runtime.send_input_result(agent_id, message="second turn")
            failed_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(failed_wait.tool_events[0].payload["status"], "failed")
            self.assertEqual(failed_wait.tool_events[0].payload["terminal_state"], "failed")
            self.assertEqual(failed_wait.tool_events[0].payload["terminal_reason"], "failed")
            self.assertEqual(
                failed_wait.tool_events[0].payload["result_contract"]["artifact"]["kind"],
                "failure",
            )
            self.assertEqual(
                failed_wait.tool_events[0].payload["result_contract"]["confidence"], "low"
            )
            self.assertIn(
                "temporary failure",
                failed_wait.tool_events[0].payload["result_contract"]["artifact"]["error"],
            )
            self.assertEqual(failed_wait.tool_events[0].payload["workflow_state"], "recoverable")
            self.assertGreaterEqual(failed_wait.tool_events[0].payload["recovery_action_count"], 1)
            self.assertEqual(
                failed_wait.tool_events[0].payload["recovery_actions"][0]["action"], "retry_step"
            )
            self.assertEqual(failed_wait.tool_events[0].payload["current_step_id"], "step_2")
            self.assertEqual(failed_wait.tool_events[0].payload["current_step_status"], "failed")

            workflow = runtime.agent_workflow_result(agent_id)
            self.assertEqual(workflow.tool_events[0].payload["workflow_state"], "recoverable")
            self.assertEqual(workflow.tool_events[0].payload["step_count"], 2)
            self.assertEqual(workflow.tool_events[0].payload["steps"][-1]["step_id"], "step_2")
            self.assertEqual(workflow.tool_events[0].payload["steps"][-1]["status"], "failed")

            recovered = runtime.recover_agent_result(agent_id, action="retry_step")
            self.assertEqual(recovered.tool_events[0].payload["recovery_action"], "retry_step")
            self.assertEqual(recovered.tool_events[0].payload["recovered_step_id"], "step_2")
            self.assertEqual(recovered.tool_events[0].payload["retry_step_id"], "step_3")
            self.assertEqual(recovered.tool_events[0].payload["workflow_state"], "active")
            self.assertEqual(recovered.tool_events[0].payload["current_step_id"], "step_3")

            retried_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
            self.assertEqual(retried_wait.assistant_text, "answer:second turn:attempt2")
            self.assertEqual(retried_wait.tool_events[0].payload["status"], "completed")
            self.assertEqual(retried_wait.tool_events[0].payload["workflow_state"], "completed")
            self.assertEqual(retried_wait.tool_events[0].payload["step_count"], 3)

            final_workflow = runtime.agent_workflow_result(agent_id)
            final_steps = final_workflow.tool_events[0].payload["steps"]
            self.assertEqual(final_steps[-2]["step_id"], "step_2")
            self.assertEqual(final_steps[-2]["status"], "failed")
            self.assertEqual(final_steps[-1]["step_id"], "step_3")
            self.assertEqual(final_steps[-1]["status"], "completed")
            self.assertEqual(final_steps[-1]["retry_of_step_id"], "step_2")
            self.assertEqual(final_steps[-1]["retry_root_step_id"], "step_2")
            self.assertEqual(final_steps[-1]["retry_attempt"], 1)

    def test_runtime_async_teammate_background_sessions_sync_to_background_task_store(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            calls: list[str] = []

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                self.__class__.calls.append(user_text)
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=Path(temp_dir) / "background_tasks.sqlite3",
                        results_dir=Path(temp_dir) / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )
            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="first turn",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                    self.assertEqual(first_wait.assistant_text, "answer:first turn")

                    runtime.send_input_result(agent_id, message="second turn")
                    followup_worker = runtime._delegated_agents[agent_id].worker
                    second_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                    self.assertEqual(second_wait.assistant_text, "answer:second turn")
                    if followup_worker is not None:
                        followup_worker.join(timeout=1)

            stored = None
            for _ in range(20):
                stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                if (
                    stored is not None
                    and int((stored.artifact or {}).get("checkpoint_count") or 0) >= 7
                ):
                    break
                time.sleep(0.05)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.status.value, "completed")
            self.assertIn("answer:second turn", stored.summary)
            self.assertEqual(stored.artifact["step_count"], 2)
            self.assertGreaterEqual(stored.artifact["checkpoint_count"], 7)
            self.assertEqual(stored.artifact["terminal_state"], "completed")
            self.assertEqual(stored.artifact["terminal_reason"], "completed")
            self.assertEqual(stored.artifact["current_step_id"], "step_2")
            self.assertEqual(stored.artifact["current_step_status"], "completed")
            self.assertEqual(second_wait.assistant_text, "answer:second turn")

            snapshot_path = Path(stored.artifact["snapshot_path"])
            self.assertTrue(snapshot_path.exists())
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["task_type"], "teammate")
            self.assertEqual(snapshot["delegated_agent"]["role"], "teammate")
            self.assertEqual(snapshot["delegated_agent"]["status"], "completed")
            self.assertEqual(snapshot["delegated_agent"]["turn_count"], 2)
            self.assertEqual(snapshot["delegated_agent"]["step_count"], 2)
            self.assertEqual(snapshot["step_count"], 2)
            self.assertGreaterEqual(snapshot["checkpoint_count"], 7)
            self.assertEqual(snapshot["current_step_id"], "step_2")
            self.assertEqual(snapshot["steps"][0]["status"], "completed")
            self.assertEqual(snapshot["steps"][1]["status"], "completed")
            self.assertEqual(snapshot["latest_checkpoint"]["kind"], "result_adopted")
            self.assertEqual(snapshot["delegated_agent"]["completion_policy"], "suggest_adopt")
            self.assertEqual(snapshot["delegated_agent"]["completion_state"], "adopted")
            self.assertEqual(snapshot["result_contract"]["status"], "completed")
            self.assertEqual(_DelegatedPlanner.calls, ["first turn", "second turn"])

    def test_runtime_background_teammate_notification_state_transitions_after_foreground_adoption(
        self,
    ):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=Path(temp_dir) / "background_tasks.sqlite3",
                        results_dir=Path(temp_dir) / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )
            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="后台总结仓库",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    snapshot = None
                    for _ in range(20):
                        snapshot = runtime.wait_agent_result(
                            agent_id, timeout_ms=250, wait_required=False
                        )
                        if snapshot.tool_events[0].payload["status"] == "completed":
                            break
                        time.sleep(0.05)
                    assert snapshot is not None
                    self.assertEqual(
                        snapshot.tool_events[0].payload["completion_state"], "ready_to_adopt"
                    )

                    stored_ready = None
                    for _ in range(20):
                        stored_ready = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                        if (
                            stored_ready is not None
                            and (stored_ready.artifact or {}).get("notification_state") == "ready"
                        ):
                            break
                        time.sleep(0.05)
                    self.assertIsNotNone(stored_ready)
                    assert stored_ready is not None
                    self.assertEqual(stored_ready.artifact["notification_state"], "ready")
                    self.assertEqual(stored_ready.artifact["terminal_state"], "completed")

                    adopted = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                    self.assertTrue(adopted.tool_events[0].payload["adopted"])

            stored_adopted = None
            for _ in range(20):
                stored_adopted = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                if (
                    stored_adopted is not None
                    and (stored_adopted.artifact or {}).get("notification_state")
                    == "foreground_adopted"
                ):
                    break
                time.sleep(0.05)
            self.assertIsNotNone(stored_adopted)
            assert stored_adopted is not None
            self.assertEqual(stored_adopted.artifact["notification_state"], "foreground_adopted")
            self.assertEqual(stored_adopted.artifact["terminal_state"], "completed")
            self.assertEqual(
                stored_adopted.artifact["foreground_taken_over_at"],
                adopted.tool_events[0].payload["adopted_at"],
            )

    def test_runtime_background_teammate_repeated_wait_does_not_duplicate_foreground_adoption(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=Path(temp_dir) / "background_tasks.sqlite3",
                        results_dir=Path(temp_dir) / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )
            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="后台总结仓库",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    first_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                    first_adopted_at = str(first_wait.tool_events[0].payload["adopted_at"] or "")
                    self.assertTrue(first_adopted_at)

                    stored = None
                    for _ in range(20):
                        stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                        if (
                            stored is not None
                            and (stored.artifact or {}).get("notification_state")
                            == "foreground_adopted"
                        ):
                            break
                        time.sleep(0.05)
                    self.assertIsNotNone(stored)
                    assert stored is not None
                    first_checkpoint_count = int(
                        (stored.artifact or {}).get("checkpoint_count") or 0
                    )
                    self.assertEqual(stored.artifact["foreground_taken_over_at"], first_adopted_at)

                    second_wait = runtime.wait_agent_result(agent_id, timeout_ms=1000)
                    self.assertEqual(
                        second_wait.tool_events[0].payload["adopted_at"], first_adopted_at
                    )
                    self.assertEqual(
                        second_wait.tool_events[0].payload["terminal_state"], "completed"
                    )

                    stored_again = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                    self.assertIsNotNone(stored_again)
                    assert stored_again is not None
                    self.assertEqual(
                        stored_again.artifact["notification_state"], "foreground_adopted"
                    )
                    self.assertEqual(stored_again.artifact["terminal_state"], "completed")
                    self.assertEqual(
                        stored_again.artifact["foreground_taken_over_at"], first_adopted_at
                    )
                    self.assertEqual(
                        int((stored_again.artifact or {}).get("checkpoint_count") or 0),
                        first_checkpoint_count,
                    )

    def test_runtime_delegate_override_change_orphan_cleans_active_teammate_background_session(
        self,
    ):
        class _DelegateAgent:
            host_platform = current_host_platform()

            def __init__(self) -> None:
                self.delegate_overrides: dict[str, dict[str, str]] = {}

            def provider_status(self):
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            def configure_delegate_selection(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    self.delegate_overrides.pop(str(role_name), None)
                else:
                    self.delegate_overrides[str(role_name)] = {
                        "model": str(model or ""),
                        "provider": str(provider or ""),
                        "reasoning_effort": str(reasoning_effort or ""),
                        "timeout": str(timeout or ""),
                    }
                return self.provider_status()

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _SlowInterruptiblePlanner:
            started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, attachments, input_items, prompt_cache_key
                self.__class__.started.set()
                command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                    "import sys,time; print('delegate-override'); sys.stdout.flush(); time.sleep(30)"
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                )
                if tool_executor.interrupt_requested():
                    interrupt_text, interrupt_events = tool_executor.interrupt_result()
                    return AgentIntent(
                        assistant_text=str(interrupt_text or result.assistant_text or ""),
                        tool_events=[
                            *list(result.tool_events or []),
                            *list(interrupt_events or []),
                        ],
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(
                    assistant_text=str(result.assistant_text or ""),
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=Path(temp_dir) / "background_tasks.sqlite3",
                        results_dir=Path(temp_dir) / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )
            _SlowInterruptiblePlanner.started = threading.Event()
            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _SlowInterruptiblePlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="后台验证 provider",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]
                    self.assertTrue(_SlowInterruptiblePlanner.started.wait(timeout=3))

                    runtime.configure_delegate_selection(
                        "teammate",
                        model="glm_5",
                        provider="glm",
                        reasoning_effort="medium",
                        timeout=30,
                    )
                    waited = runtime.wait_agent_result(agent_id, timeout_ms=6000)
                    worker = runtime._delegated_agents[agent_id].worker
                    if worker is not None:
                        worker.join(timeout=1)

            self.assertEqual(waited.tool_events[0].payload["status"], "closed")
            self.assertEqual(waited.tool_events[0].payload["terminal_state"], "orphaned")
            self.assertEqual(
                waited.tool_events[0].payload["terminal_reason"], "role_override_changed"
            )
            stored = None
            for _ in range(20):
                stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                if (
                    stored is not None
                    and (stored.artifact or {}).get("terminal_reason") == "role_override_changed"
                ):
                    break
                time.sleep(0.05)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.status.value, "cancelled")
            self.assertEqual(stored.artifact["terminal_state"], "orphaned")
            self.assertEqual(stored.artifact["terminal_reason"], "role_override_changed")
            self.assertEqual(stored.artifact["notification_state"], "orphaned")

    def test_runtime_delegate_override_change_does_not_orphan_completed_teammate_background_session(
        self,
    ):
        class _DelegateAgent:
            host_platform = current_host_platform()

            def __init__(self) -> None:
                self.delegate_overrides: dict[str, dict[str, str]] = {}

            def provider_status(self):
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            def configure_delegate_selection(
                self,
                role_name,
                *,
                model=None,
                provider=None,
                reasoning_effort=None,
                timeout=None,
                clear=False,
            ):
                if clear:
                    self.delegate_overrides.pop(str(role_name), None)
                else:
                    self.delegate_overrides[str(role_name)] = {
                        "model": str(model or ""),
                        "provider": str(provider or ""),
                        "reasoning_effort": str(reasoning_effort or ""),
                        "timeout": str(timeout or ""),
                    }
                return self.provider_status()

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        with TemporaryDirectory() as temp_dir:
            runtime = AgentCliRuntime(
                agent=_DelegateAgent(),
                runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
            )
            runtime.set_cwd(temp_dir)
            adapter = build_background_task_adapter(
                config=BackgroundTasksConfig(
                    enabled=True,
                    provider="huey",
                    huey=HueyConfig(
                        backend="sqlite",
                        path=Path(temp_dir) / "background_tasks.sqlite3",
                        results_dir=Path(temp_dir) / "results",
                        worker_count=1,
                        immediate=True,
                    ),
                )
            )
            with patch("cli.agent_cli.runtime.build_background_task_adapter", return_value=adapter):
                with patch(
                    "cli.agent_cli.runtime.build_planner",
                    side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
                ):
                    spawned = runtime.spawn_agent_result(
                        task="后台总结仓库",
                        role="teammate",
                        async_mode=True,
                        mode="background",
                        wait_required=False,
                    )
                    agent_id = spawned.tool_events[0].payload["agent_id"]

                    snapshot = None
                    for _ in range(20):
                        snapshot = runtime.wait_agent_result(
                            agent_id, timeout_ms=250, wait_required=False
                        )
                        if snapshot.tool_events[0].payload["status"] == "completed":
                            break
                        time.sleep(0.05)
                    assert snapshot is not None
                    self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
                    self.assertFalse(snapshot.tool_events[0].payload["adopted"])
                    self.assertEqual(snapshot.tool_events[0].payload["terminal_state"], "completed")

                    runtime.configure_delegate_selection(
                        "teammate",
                        model="glm_5",
                        provider="glm",
                        reasoning_effort="medium",
                        timeout=30,
                    )

                    stored = adapter.storage.get_result(f"bg_delegate_{agent_id}")
                    self.assertIsNotNone(stored)
                    assert stored is not None
                    self.assertEqual(stored.status.value, "completed")
                    self.assertEqual(stored.artifact["notification_state"], "ready")
                    self.assertEqual(stored.artifact["terminal_state"], "completed")
                    self.assertEqual(stored.artifact["terminal_reason"], "completed")

                    still_completed = runtime.wait_agent_result(
                        agent_id, timeout_ms=250, wait_required=False
                    )
                    self.assertEqual(still_completed.tool_events[0].payload["status"], "completed")
                    self.assertEqual(
                        still_completed.tool_events[0].payload["terminal_state"], "completed"
                    )
                    self.assertEqual(
                        still_completed.tool_events[0].payload["terminal_reason"], "completed"
                    )

    def test_runtime_teammate_defaults_to_background_async_session(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(task="收集 provider 差异", role="teammate")
            self.assertIn("delegated agent", spawned.assistant_text)
            self.assertEqual(spawned.tool_events[0].summary, "spawn_agent started")
            self.assertTrue(spawned.tool_events[0].payload["async"])
            self.assertEqual(
                spawned.tool_events[0].payload["delegation_reason"], "research_side_task"
            )
            self.assertEqual(spawned.tool_events[0].payload["delegation_mode"], "background")
            self.assertFalse(spawned.tool_events[0].payload["wait_required"])
            self.assertEqual(spawned.tool_events[0].payload["task_shape"], "read_only")
            self.assertEqual(spawned.tool_events[0].payload["background_priority"], "low")
            self.assertEqual(spawned.tool_events[0].payload["completion_policy"], "suggest_adopt")
            self.assertIn(
                spawned.tool_events[0].payload["adoption_expectation"],
                {"continue_main_thread_or_wait", "review_or_adopt_teammate_result"},
            )
            self.assertIn(
                spawned.tool_events[0].payload["completion_state"],
                {"pending", "ready_to_adopt"},
            )

            waited = runtime.wait_agent_result(
                spawned.tool_events[0].payload["agent_id"],
                timeout_ms=1000,
            )

        self.assertEqual(waited.assistant_text, "answer:收集 provider 差异")
        self.assertEqual(waited.tool_events[0].payload["status"], "completed")
        self.assertEqual(waited.tool_events[0].payload["background_priority"], "low")
        self.assertEqual(waited.tool_events[0].payload["completion_policy"], "suggest_adopt")
        self.assertEqual(waited.tool_events[0].payload["completion_state"], "adopted")
        self.assertEqual(waited.tool_events[0].payload["adoption_expectation"], "already_adopted")

    def test_runtime_low_priority_background_teammate_yields_to_active_background_child(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name in {"subagent", "teammate"}
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _ControlledPlanner:
            high_started = threading.Event()
            low_started = threading.Event()
            release_high = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                if user_text == "high priority background verify":
                    self.__class__.high_started.set()
                    self.__class__.release_high.wait(timeout=5)
                elif user_text == "low priority teammate summary":
                    self.__class__.low_started.set()
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _ControlledPlanner.high_started = threading.Event()
        _ControlledPlanner.low_started = threading.Event()
        _ControlledPlanner.release_high = threading.Event()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _ControlledPlanner(),
        ):
            high = runtime.spawn_agent_result(
                task="high priority background verify",
                role="subagent",
                async_mode=True,
                mode="background",
                task_shape="read_only",
                reason="verify_side_task",
                wait_required=False,
            )
            high_id = high.tool_events[0].payload["agent_id"]
            self.assertTrue(_ControlledPlanner.high_started.wait(timeout=3))

            low = runtime.spawn_agent_result(
                task="low priority teammate summary",
                role="teammate",
            )
            low_id = low.tool_events[0].payload["agent_id"]
            self.assertEqual(low.tool_events[0].payload["background_priority"], "low")

            queued_snapshot = None
            for _ in range(20):
                queued_snapshot = runtime.wait_agent_result(
                    low_id, timeout_ms=250, wait_required=False
                )
                if queued_snapshot.tool_events[0].payload.get("scheduler_reason"):
                    break
                time.sleep(0.05)
            assert queued_snapshot is not None
            self.assertEqual(queued_snapshot.tool_events[0].payload["status"], "queued")
            self.assertEqual(queued_snapshot.tool_events[0].payload["background_priority"], "low")
            self.assertEqual(
                queued_snapshot.tool_events[0].payload["scheduler_reason"],
                "deferred_by_higher_priority_background_child",
            )
            self.assertFalse(_ControlledPlanner.low_started.is_set())

            _ControlledPlanner.release_high.set()
            high_wait = runtime.wait_agent_result(high_id, timeout_ms=3000)
            low_wait = runtime.wait_agent_result(low_id, timeout_ms=3000)

        self.assertEqual(high_wait.tool_events[0].payload["status"], "completed")
        self.assertEqual(low_wait.tool_events[0].payload["status"], "completed")
        self.assertTrue(_ControlledPlanner.low_started.is_set())

    def test_runtime_teammate_context_sensitive_task_defaults_to_sync(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="Continue current task using current context and above conversation",
                role="teammate",
            )

        self.assertEqual(
            spawned.assistant_text,
            "answer:Continue current task using current context and above conversation",
        )
        self.assertEqual(spawned.tool_events[0].summary, "spawn_agent completed")
        self.assertEqual(
            spawned.tool_events[0].payload["delegation_reason"], "background_side_task"
        )
        self.assertEqual(spawned.tool_events[0].payload["delegation_mode"], "sync")
        self.assertFalse(spawned.tool_events[0].payload["wait_required"])
        self.assertEqual(spawned.tool_events[0].payload["task_shape"], "context_sensitive")
        self.assertEqual(spawned.tool_events[0].payload["adoption_expectation"], "already_adopted")
        self.assertNotIn("agent_id", spawned.tool_events[0].payload)
        self.assertNotIn("async", spawned.tool_events[0].payload)

    def test_runtime_subagent_long_running_task_defaults_to_background(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="运行 benchmark 收集 provider 延迟数据",
                role="subagent",
            )
            self.assertIn("delegated agent", spawned.assistant_text)
            self.assertEqual(spawned.tool_events[0].summary, "spawn_agent started")
            self.assertTrue(spawned.tool_events[0].payload["async"])
            self.assertEqual(
                spawned.tool_events[0].payload["delegation_reason"], "long_running_exec"
            )
            self.assertEqual(spawned.tool_events[0].payload["delegation_mode"], "background")
            self.assertFalse(spawned.tool_events[0].payload["wait_required"])
            self.assertEqual(spawned.tool_events[0].payload["task_shape"], "long_running")
            self.assertEqual(
                spawned.tool_events[0].payload["adoption_expectation"],
                "continue_main_thread_or_wait",
            )

    def test_runtime_teammate_completed_background_snapshot_surfaces_ready_to_adopt_state(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(task="后台总结仓库", role="teammate")
            agent_id = spawned.tool_events[0].payload["agent_id"]

            snapshot = None
            for _ in range(20):
                snapshot = runtime.wait_agent_result(agent_id, timeout_ms=250, wait_required=False)
                if snapshot.tool_events[0].payload["status"] == "completed":
                    break
                time.sleep(0.05)
            assert snapshot is not None
            self.assertEqual(snapshot.tool_events[0].payload["status"], "completed")
            self.assertFalse(snapshot.tool_events[0].payload["adopted"])
            self.assertEqual(snapshot.tool_events[0].payload["completion_policy"], "suggest_adopt")
            self.assertEqual(snapshot.tool_events[0].payload["completion_state"], "ready_to_adopt")
            self.assertEqual(snapshot.tool_events[0].payload["result_state"], "pending_review")
            self.assertEqual(snapshot.tool_events[0].payload["delegated_result_returned"], 0)
            self.assertEqual(snapshot.tool_events[0].payload["delegated_result_adopted"], 0)
            self.assertEqual(snapshot.tool_events[0].payload["delegated_result_pending_review"], 1)
            self.assertEqual(snapshot.tool_events[0].payload["background_result_returned"], 0)
            self.assertEqual(snapshot.tool_events[0].payload["background_result_adopted"], 0)
            self.assertEqual(snapshot.tool_events[0].payload["background_result_pending_review"], 1)
            self.assertEqual(snapshot.tool_events[0].payload["background_priority"], "low")
            self.assertEqual(
                snapshot.tool_events[0].payload["adoption_expectation"],
                "review_or_adopt_teammate_result",
            )
            self.assertEqual(
                snapshot.tool_events[0].payload["result_contract"]["next_action"],
                "review_or_adopt_teammate_result",
            )
            session_snapshot = runtime._snapshot_delegated_agent_session(
                runtime._delegated_agents[agent_id]
            )
            self.assertEqual(session_snapshot["live_snapshot_version"], 1)
            self.assertIn("live_snapshot_exported_at", session_snapshot)
            self.assertIsInstance(session_snapshot["live_snapshot_exported_at"], str)
            self.assertIn("live_current_step_status", session_snapshot)
            self.assertIsInstance(session_snapshot["live_current_step_status"], str)
            self.assertIn("live_current_step_title", session_snapshot)
            self.assertIsInstance(session_snapshot["live_current_step_title"], str)
            self.assertIn("live_last_checkpoint_kind", session_snapshot)
            self.assertIsInstance(session_snapshot["live_last_checkpoint_kind"], str)
            self.assertIn("live_last_checkpoint_at", session_snapshot)
            self.assertIsInstance(session_snapshot["live_last_checkpoint_at"], str)
            self.assertFalse(session_snapshot["live_has_active_input"])
            self.assertEqual(session_snapshot["live_queued_input_count"], 0)
            self.assertEqual(
                session_snapshot["live_last_tool_event_count"],
                len(session_snapshot.get("last_tool_events") or []),
            )
            self.assertEqual(
                session_snapshot["live_last_item_event_count"],
                len(session_snapshot.get("last_item_events") or []),
            )
            self.assertEqual(
                session_snapshot["live_last_turn_event_count"],
                len(session_snapshot.get("last_turn_events") or []),
            )

            workflow = runtime.agent_workflow_result(agent_id)
            self.assertEqual(workflow.tool_events[0].payload["completion_policy"], "suggest_adopt")
            self.assertEqual(workflow.tool_events[0].payload["completion_state"], "ready_to_adopt")
            self.assertEqual(workflow.tool_events[0].payload["result_state"], "pending_review")
            self.assertEqual(workflow.tool_events[0].payload["delegated_result_pending_review"], 1)
            self.assertEqual(workflow.tool_events[0].payload["background_result_pending_review"], 1)
            self.assertEqual(workflow.tool_events[0].payload["background_priority"], "low")
            self.assertEqual(
                workflow.tool_events[0].payload["adoption_expectation"],
                "review_or_adopt_teammate_result",
            )
            self.assertIn("completion_policy=suggest_adopt", workflow.assistant_text)
            self.assertIn("completion_state=ready_to_adopt", workflow.assistant_text)
            self.assertIn("result_state=pending_review", workflow.assistant_text)
            self.assertIn("delegated_result_pending_review=1", workflow.assistant_text)
            self.assertIn("background_result_pending_review=1", workflow.assistant_text)
            self.assertIn("background_priority=low", workflow.assistant_text)
            self.assertIn(
                "adoption_expectation=review_or_adopt_teammate_result", workflow.assistant_text
            )

            adopted = runtime.wait_agent_result(
                agent_id, timeout_ms=1000, reason="wait_for_child_result"
            )
            self.assertTrue(adopted.tool_events[0].payload["adopted"])
            self.assertEqual(adopted.tool_events[0].payload["completion_state"], "adopted")
            self.assertEqual(adopted.tool_events[0].payload["result_state"], "adopted")
            self.assertEqual(adopted.tool_events[0].payload["delegated_result_returned"], 0)
            self.assertEqual(adopted.tool_events[0].payload["delegated_result_adopted"], 1)
            self.assertEqual(adopted.tool_events[0].payload["delegated_result_pending_review"], 0)
            self.assertEqual(adopted.tool_events[0].payload["background_result_returned"], 0)
            self.assertEqual(adopted.tool_events[0].payload["background_result_adopted"], 1)
            self.assertEqual(adopted.tool_events[0].payload["background_result_pending_review"], 0)
            self.assertEqual(
                adopted.tool_events[0].payload["adoption_expectation"], "already_adopted"
            )
            self.assertEqual(
                adopted.tool_events[0].payload["result_contract"]["next_action"], "already_adopted"
            )

    def test_runtime_teammate_wait_required_true_uses_must_join_completion_policy(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(
                task="必须 join 的后台验证",
                role="teammate",
                async_mode=True,
                mode="background",
                wait_required=True,
            )
            self.assertEqual(spawned.tool_events[0].payload["completion_policy"], "must_join")
            self.assertEqual(spawned.tool_events[0].payload["background_priority"], "normal")
            agent_id = spawned.tool_events[0].payload["agent_id"]

            snapshot = None
            for _ in range(20):
                snapshot = runtime.wait_agent_result(agent_id, timeout_ms=250, wait_required=False)
                if snapshot.tool_events[0].payload["status"] == "completed":
                    break
                time.sleep(0.05)
            assert snapshot is not None
            self.assertEqual(snapshot.tool_events[0].payload["completion_policy"], "must_join")
            self.assertEqual(snapshot.tool_events[0].payload["completion_state"], "awaiting_join")
            self.assertEqual(snapshot.tool_events[0].payload["background_priority"], "normal")
            self.assertEqual(
                snapshot.tool_events[0].payload["adoption_expectation"], "wait_agent_to_adopt"
            )
            self.assertEqual(
                snapshot.tool_events[0].payload["result_contract"]["next_action"],
                "wait_agent_to_adopt",
            )

    def test_runtime_teammate_conflicting_async_and_mode_prefers_explicit_async_flag(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "teammate"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _DelegatedPlanner:
            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, tool_executor, attachments, input_items, prompt_cache_key
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _DelegatedPlanner(),
        ):
            forced_sync = runtime.spawn_agent_result(
                task="复核当前结论",
                role="teammate",
                async_mode=False,
                mode="background",
            )
            self.assertEqual(forced_sync.tool_events[0].summary, "spawn_agent completed")
            self.assertEqual(forced_sync.tool_events[0].payload["delegation_mode"], "sync")
            self.assertFalse(forced_sync.tool_events[0].payload["wait_required"])
            self.assertEqual(forced_sync.tool_events[0].payload["completion_state"], "adopted")
            self.assertEqual(
                forced_sync.tool_events[0].payload["adoption_expectation"], "already_adopted"
            )
            self.assertNotIn("agent_id", forced_sync.tool_events[0].payload)
            self.assertNotIn("async", forced_sync.tool_events[0].payload)

            forced_async = runtime.spawn_agent_result(
                task="并行整理证据",
                role="teammate",
                async_mode=True,
                mode="sync",
            )
            self.assertEqual(forced_async.tool_events[0].summary, "spawn_agent started")
            self.assertTrue(forced_async.tool_events[0].payload["async"])
            self.assertEqual(forced_async.tool_events[0].payload["delegation_mode"], "background")
            self.assertFalse(forced_async.tool_events[0].payload["wait_required"])
            self.assertEqual(
                forced_async.tool_events[0].payload["completion_policy"], "suggest_adopt"
            )
            self.assertEqual(
                forced_async.tool_events[0].payload["adoption_expectation"],
                "continue_main_thread_or_wait",
            )

    def test_runtime_async_delegated_agent_interrupt_preempts_active_turn_without_replaying_partial_history(
        self,
    ):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _InterruptibleDelegatedPlanner:
            calls: list[dict] = []
            slow_turn_started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del attachments
                self.__class__.calls.append(
                    {
                        "user_text": user_text,
                        "history": list(history or []),
                        "input_items": list(input_items or []),
                        "prompt_cache_key": prompt_cache_key,
                    }
                )
                if user_text == "slow turn":
                    self.__class__.slow_turn_started.set()
                    command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                        "import sys,time; print('delegated-ready'); sys.stdout.flush(); time.sleep(30)"
                    )
                    result = tool_executor.run_structured(
                        f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                    )
                    if tool_executor.interrupt_requested():
                        interrupt_text, interrupt_events = tool_executor.interrupt_result()
                        return AgentIntent(
                            assistant_text=str(interrupt_text or result.assistant_text or ""),
                            tool_events=[
                                *list(result.tool_events or []),
                                *list(interrupt_events or []),
                            ],
                            turn_events=list(result.turn_events or []),
                        )
                    return AgentIntent(
                        assistant_text=str(result.assistant_text or ""),
                        tool_events=list(result.tool_events or []),
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(assistant_text=f"answer:{user_text}")

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _InterruptibleDelegatedPlanner.calls = []
        _InterruptibleDelegatedPlanner.slow_turn_started = threading.Event()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _InterruptibleDelegatedPlanner(),
        ):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_InterruptibleDelegatedPlanner.slow_turn_started.wait(timeout=3))
            queued = runtime.send_input_result(agent_id, message="fast turn", interrupt=True)
            self.assertTrue(queued.tool_events[0].payload["interrupt_requested"])

            completed = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            self.assertEqual(completed.tool_events[0].payload["status"], "completed")
            self.assertEqual(completed.assistant_text, "answer:fast turn")

            session = runtime._delegated_agents[agent_id]
            self.assertEqual(session.turn_count, 1)
            self.assertEqual(
                [item["user_text"] for item in _InterruptibleDelegatedPlanner.calls],
                ["slow turn", "fast turn"],
            )
            second_call = _InterruptibleDelegatedPlanner.calls[1]
            self.assertEqual(second_call["history"], [])
            self.assertFalse(
                any(
                    "slow turn" in json.dumps(item, ensure_ascii=False)
                    for item in second_call["input_items"]
                )
            )
            self.assertFalse(
                any(
                    "Conversation interrupted" in json.dumps(item, ensure_ascii=False)
                    for item in second_call["input_items"]
                )
            )

    def test_runtime_async_delegated_agent_close_interrupts_active_turn(self):
        class _DelegateAgent:
            host_platform = current_host_platform()

            @staticmethod
            def provider_status():
                return {
                    "provider_ready": "true",
                    "provider_name": "openai",
                    "provider_model": "gpt-5.4",
                    "provider_reasoning_effort": "high",
                    "provider_planner": "openai_responses",
                    "provider_source": "test",
                    "provider_label": "openai | gpt-5.4 | tool-calls",
                    "model_key": "gpt_54",
                    "session_line": "openai-tools",
                    "shell_kind": "bash",
                }

            @staticmethod
            def resolve_delegate_execution(
                role_name, *, model=None, provider=None, reasoning_effort=None, timeout=None
            ):
                del model, provider, reasoning_effort, timeout
                assert role_name == "subagent"
                return SimpleNamespace(
                    config=ProviderConfig(
                        model="glm-5",
                        api_key="sk-glm",
                        provider_name="glm",
                        model_key="glm_5",
                        planner_kind="openai_chat",
                        wire_api="openai_chat",
                        base_url="https://glm.example/v1",
                        reasoning_effort="medium",
                        raw_model={},
                    ),
                    timeout=18,
                    source="delegation",
                )

        class _CloseInterruptPlanner:
            slow_turn_started = threading.Event()

            def plan(
                self,
                user_text,
                history,
                *,
                tool_executor=None,
                attachments=None,
                input_items=None,
                prompt_cache_key=None,
            ):
                del history, attachments, input_items, prompt_cache_key
                self.__class__.slow_turn_started.set()
                command = f"{shlex.quote(sys.executable)} -u -c " + shlex.quote(
                    "import sys,time; print('delegated-close'); sys.stdout.flush(); time.sleep(30)"
                )
                result = tool_executor.run_structured(
                    f"/exec_command --cmd {shlex.quote(command)} --yield-time-ms 5000"
                )
                if tool_executor.interrupt_requested():
                    interrupt_text, interrupt_events = tool_executor.interrupt_result()
                    return AgentIntent(
                        assistant_text=str(interrupt_text or result.assistant_text or ""),
                        tool_events=[
                            *list(result.tool_events or []),
                            *list(interrupt_events or []),
                        ],
                        turn_events=list(result.turn_events or []),
                    )
                return AgentIntent(
                    assistant_text=str(result.assistant_text or ""),
                    tool_events=list(result.tool_events or []),
                    turn_events=list(result.turn_events or []),
                )

        runtime = AgentCliRuntime(
            agent=_DelegateAgent(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        _CloseInterruptPlanner.slow_turn_started = threading.Event()
        with patch(
            "cli.agent_cli.runtime.build_planner",
            side_effect=lambda *args, **kwargs: _CloseInterruptPlanner(),
        ):
            spawned = runtime.spawn_agent_result(task="slow turn", role="subagent", async_mode=True)
            agent_id = spawned.tool_events[0].payload["agent_id"]

            self.assertTrue(_CloseInterruptPlanner.slow_turn_started.wait(timeout=3))
            close_result = runtime.close_agent_result(agent_id)
            self.assertIn(close_result.tool_events[0].payload["status"], {"closing", "closed"})
            self.assertEqual(
                close_result.tool_events[0].payload["terminal_state"], "closed_by_request"
            )
            self.assertEqual(
                close_result.tool_events[0].payload["terminal_reason"], "close_requested"
            )

            waited = runtime.wait_agent_result(agent_id, timeout_ms=6000)
            self.assertEqual(waited.tool_events[0].payload["status"], "closed")
            self.assertEqual(waited.tool_events[0].payload["pending_input_count"], 0)
            self.assertEqual(waited.tool_events[0].payload["terminal_state"], "closed_by_request")
            self.assertEqual(waited.tool_events[0].payload["terminal_reason"], "close_requested")
            self.assertEqual(waited.tool_events[0].payload["result_contract"]["status"], "closed")
            self.assertEqual(
                waited.tool_events[0].payload["result_contract"]["artifact"]["kind"], "empty"
            )
            self.assertEqual(waited.tool_events[0].payload["result_contract"]["confidence"], "low")

            session = runtime._delegated_agents[agent_id]
            self.assertTrue(session.closed)
            self.assertEqual(session.turn_count, 0)
            self.assertTrue(
                any(event.payload.get("interrupted") for event in session.last_tool_events)
            )
