from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "run_multi_llm_live_cases.py"
SPEC = importlib.util.spec_from_file_location("run_multi_llm_live_cases", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

class _DummyPlanner:
    @staticmethod
    def public_summary() -> dict:
        return {}

class _DummyRuntime:
    def __init__(self) -> None:
        self.agent = SimpleNamespace(provider_status=lambda: {"provider_ready": "true"})

    def set_cwd(self, value: str) -> str:
        return value

    def _run_command_text_result(self, text: str):
        raise AssertionError(f"unexpected structured command execution: {text}")

class RunMultiLlmLiveCasesTest(unittest.TestCase):
    def test_selected_cases_supports_orchestration_background_teammate_profile(self) -> None:
        selected = MODULE._selected_cases(None, profile="orchestration_background_teammate")
        names = [case.name for case in selected]
        self.assertEqual(names, ["orchestrate_background_teammate_smoke"])

    def test_selected_cases_supports_focused_delegation_matrix_profile(self) -> None:
        selected = MODULE._selected_cases(None, profile="focused_delegation_matrix")
        names = [case.name for case in selected]
        self.assertIn("followup_pwd", names)
        self.assertIn("followup_git_status", names)
        self.assertIn("synthesis_workspace_state", names)
        self.assertIn("delegate_subagent_git_status", names)
        self.assertIn("delegate_teammate_background_verify", names)

    def test_selected_cases_supports_core_matrix_profile(self) -> None:
        selected = MODULE._selected_cases(None, profile="core_matrix")
        names = [case.name for case in selected]
        self.assertIn("followup_pwd", names)
        self.assertIn("synthesis_workspace_state", names)
        self.assertIn("delegate_subagent_git_status", names)
        self.assertIn("delegate_teammate_background_verify", names)
        self.assertIn("orchestrate_background_teammate_smoke", names)

    def test_failure_category_maps_empty_response(self) -> None:
        category = MODULE._failure_category(["assistant_text_missing"], {"wait_status": ""})
        self.assertEqual(category, "empty_response")

    def test_failure_category_maps_delegation_contract_mismatch(self) -> None:
        category = MODULE._failure_category(["missing_delegated_model", "delegated_role_mismatch"], {"wait_status": ""})
        self.assertEqual(category, "delegation_contract_mismatch")

    def test_failure_category_maps_orchestration_contract_mismatch(self) -> None:
        category = MODULE._failure_category(["missing_orchestration_dispatch_ref"], {"wait_status": ""})
        self.assertEqual(category, "orchestration_contract_mismatch")

    def test_failure_category_maps_stay_local_contract_mismatch(self) -> None:
        category = MODULE._failure_category(["stay_local_reason_mismatch"], {"wait_status": ""})
        self.assertEqual(category, "stay_local_contract_mismatch")

    def test_report_summary_includes_failure_categories_and_human_summary(self) -> None:
        summary = MODULE._report_summary(
            [
                {
                    "passed": True,
                    "assistant_text": "ok",
                    "phase": "tool_followup",
                    "llm_trace": {
                        "requests": [
                            {"provider_name": "openai", "model": "gpt-5.4"},
                        ]
                    },
                    "wait_status": "",
                    "failure_category": "none",
                    "case_wall_ms": 1200,
                },
                {
                    "passed": False,
                    "assistant_text": "模型未返回内容。",
                    "phase": "spawn_agent",
                    "delegation_mode": "background",
                    "llm_trace": {
                        "requests": [
                            {"provider_name": "glm", "model": "glm-5"},
                        ]
                    },
                    "delegated_provider_name": "glm",
                    "delegated_model": "glm-5",
                    "wait_status": "timed_out",
                    "failure_category": "empty_response",
                    "case_wall_ms": 800,
                },
            ]
        )
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["passed_cases"], 1)
        self.assertEqual(summary["failed_cases"], 1)
        self.assertEqual(summary["empty_response_count"], 1)
        self.assertEqual(summary["timeout_count"], 1)
        self.assertEqual(summary["failure_categories"]["empty_response"], 1)
        self.assertEqual(summary["route_phase_counts"]["tool_followup"], 1)
        self.assertEqual(summary["route_phase_counts"]["spawn_agent"], 1)
        self.assertEqual(summary["route_phase_summary"]["tool_followup"]["passed"], 1)
        self.assertEqual(summary["route_phase_summary"]["spawn_agent"]["failed"], 1)
        self.assertEqual(summary["failure_buckets_by_phase"]["spawn_agent"]["empty_response"], 1)
        self.assertEqual(summary["provider_matrix"]["request_trace"]["openai:gpt-5.4"], 1)
        self.assertEqual(summary["provider_matrix"]["request_trace"]["glm:glm-5"], 1)
        self.assertEqual(summary["provider_matrix"]["delegated_targets"]["glm:glm-5"], 1)
        self.assertEqual(summary["provider_matrix"]["request_trace_by_phase"]["tool_followup"]["openai:gpt-5.4"], 1)
        self.assertEqual(summary["provider_matrix"]["request_trace_by_phase"]["spawn_agent"]["glm:glm-5"], 1)
        self.assertEqual(summary["provider_matrix"]["delegated_targets_by_phase"]["spawn_agent"]["glm:glm-5"], 1)
        self.assertEqual(summary["phase_delegation_mode_counts"]["spawn_agent"]["background"], 1)
        self.assertTrue(summary["human_summary"])

    def test_ci_reuse_block_marks_gate_passed_when_strict_and_no_failures(self) -> None:
        block = MODULE._ci_reuse_block(
            profile="core_matrix",
            strict=True,
            selected_case_names=["followup_pwd", "synthesis_workspace_state"],
            summary={"total_cases": 2, "failed_cases": 0},
        )
        self.assertEqual(block["selected_profile"], "core_matrix")
        self.assertEqual(block["selected_case_count"], 2)
        self.assertEqual(block["recommended_profile"], "core_matrix")
        self.assertTrue(block["strict_enabled"])
        self.assertTrue(block["ci_gate_passed"])
        self.assertEqual(block["ci_gate_reason"], "strict_passed")
        self.assertTrue(block["ci_gate"]["all_cases_successful"])
        self.assertEqual(block["ci_gate"]["reason"], "strict_passed")
        self.assertEqual(block["ci_gate"]["cases_run_total"], 2)
        self.assertEqual(block["ci_gate"]["failed_cases_total"], 0)
        self.assertIn("--profile core_matrix --strict", block["recommended_command"])

    def test_ci_reuse_block_marks_gate_not_passed_when_not_strict(self) -> None:
        block = MODULE._ci_reuse_block(
            profile="orchestration_smoke",
            strict=False,
            selected_case_names=["followup_pwd"],
            summary={"total_cases": 1, "failed_cases": 0},
        )
        self.assertFalse(block["ci_gate_passed"])
        self.assertEqual(block["ci_gate_reason"], "strict_missing_or_failures")
        self.assertFalse(block["ci_gate"]["all_cases_successful"])
        self.assertEqual(block["ci_gate"]["reason"], "strict_missing_or_failures")

    def test_ci_reuse_block_dual_contract_fields_remain_consistent(self) -> None:
        block = MODULE._ci_reuse_block(
            profile="core_matrix",
            strict=True,
            selected_case_names=["followup_pwd", "synthesis_workspace_state"],
            summary={"total_cases": 2, "failed_cases": 0},
        )
        self.assertIn("ci_gate", block)
        self.assertIn("ci_gate_passed", block)
        self.assertIn("ci_gate_reason", block)
        self.assertEqual(block["ci_gate_passed"], block["ci_gate"]["all_cases_successful"])
        self.assertEqual(block["ci_gate_reason"], block["ci_gate"]["reason"])

    def test_validation_errors_accepts_valid_spawn_agent_case(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "delegate_subagent_git_status")
        result = {
            "name": case.name,
            "assistant_text": "当前分支为 main。工作区不干净。",
            "tool_event_names": ["spawn_agent"],
            "delegated_provider_name": "glm",
            "delegated_model": "glm-5",
            "delegated_source": "delegation",
            "delegated_role": "subagent",
            "delegation_mode": "sync",
            "delegated_task_shape": "read_only",
            "delegated_wait_required": False,
            "llm_trace": {"requests": []},
        }

        self.assertEqual(MODULE._validation_errors(case, result), [])

    def test_validation_errors_rejects_missing_delegated_provider(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "delegate_subagent_git_status")
        result = {
            "name": case.name,
            "assistant_text": "当前分支为 main。工作区不干净。",
            "tool_event_names": ["spawn_agent"],
            "delegated_provider_name": "",
            "delegated_model": "glm-5",
            "delegated_source": "delegation",
            "delegated_role": "subagent",
            "llm_trace": {"requests": []},
        }

        errors = MODULE._validation_errors(case, result)
        self.assertIn("missing_delegated_provider", errors)

    def test_validation_errors_accepts_teammate_background_defaults_case(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "delegate_teammate_background_verify")
        result = {
            "name": case.name,
            "assistant_text": "两个对象分别需要后续验证。",
            "tool_event_names": ["spawn_agent", "wait_agent"],
            "delegated_agent_id": "agent_1",
            "delegated_async": True,
            "delegated_provider_name": "glm",
            "delegated_model": "glm-5",
            "delegated_source": "delegation",
            "delegated_role": "teammate",
            "delegation_mode": "background",
            "delegated_task_shape": "read_only",
            "delegated_wait_required": False,
            "delegated_background_priority": "low",
            "wait_status": "completed",
            "wait_result_ready": True,
            "wait_adopted": True,
            "llm_trace": {"requests": []},
        }

        self.assertEqual(MODULE._validation_errors(case, result), [])

    def test_validation_errors_accepts_teammate_session_override_case(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "delegate_teammate_workspace_summary")
        result = {
            "name": case.name,
            "assistant_text": "三个对象分别值得先看。",
            "tool_event_names": ["spawn_agent"],
            "delegated_agent_id": "agent_2",
            "delegated_async": True,
            "delegated_provider_name": "glm",
            "delegated_model": "glm-5",
            "delegated_source": "session_override",
            "delegated_role": "teammate",
            "delegation_mode": "background",
            "delegated_task_shape": "read_only",
            "delegated_wait_required": False,
            "delegated_background_priority": "low",
            "llm_trace": {"requests": []},
        }

        self.assertEqual(MODULE._validation_errors(case, result), [])

    def test_validation_errors_rejects_teammate_background_priority_mismatch(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "delegate_teammate_background_briefing")
        result = {
            "name": case.name,
            "assistant_text": "两个入口值得先看。",
            "tool_event_names": ["spawn_agent"],
            "delegated_agent_id": "agent_3",
            "delegated_async": True,
            "delegated_provider_name": "glm",
            "delegated_model": "glm-5",
            "delegated_source": "delegation",
            "delegated_role": "teammate",
            "delegation_mode": "background",
            "delegated_task_shape": "read_only",
            "delegated_wait_required": False,
            "delegated_background_priority": "normal",
            "llm_trace": {"requests": []},
        }

        errors = MODULE._validation_errors(case, result)
        self.assertIn("delegated_background_priority_mismatch", errors)

    def test_validation_errors_accepts_orchestration_background_teammate_case(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "orchestrate_background_teammate_smoke")
        result = {
            "name": case.name,
            "assistant_text": "orchestration progress updated\nrun_id=run_demo",
            "tool_event_names": [],
            "orchestration_run_id": "run_demo",
            "orchestration_created": True,
            "orchestration_dispatched": True,
            "orchestration_progressed": True,
            "orchestration_dispatch_refs": ["CARD-001:background_task:bg_teammate_001"],
            "llm_trace": {"requests": []},
        }

        self.assertEqual(MODULE._validation_errors(case, result), [])

    def test_validation_errors_accepts_followup_stay_local_expectation_case(self) -> None:
        case = MODULE.LiveCase(
            name="followup_stay_local_contract",
            phase="tool_followup",
            prompt="根据工具结果直接回答。",
            expected_spawn_agent=False,
            expected_orchestration_decision="stay_local",
            expected_stay_local_reason="non_delegation_tools_only",
            expected_stay_local_counterexamples=("exec_command",),
        )
        result = {
            "name": case.name,
            "assistant_text": "/tmp/demo",
            "tool_event_names": ["exec_command"],
            "runtime_provider_status": {
                "orchestration_decision": "stay_local",
                "orchestration_stay_local_reason": "non_delegation_tools_only",
                "orchestration_stay_local_counterexamples": ["exec_command"],
            },
            "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}]},
        }
        self.assertEqual(MODULE._validation_errors(case, result), [])

    def test_validation_errors_rejects_followup_when_spawn_agent_unexpected(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "followup_pwd")
        result = {
            "name": case.name,
            "assistant_text": "/tmp/demo",
            "tool_event_names": ["spawn_agent"],
            "runtime_provider_status": {},
            "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}]},
        }
        errors = MODULE._validation_errors(case, result)
        self.assertIn("unexpected_spawn_agent_event", errors)

    def test_validation_errors_rejects_orchestration_dispatch_without_teammate_ref(self) -> None:
        case = next(item for item in MODULE.CASES if item.name == "orchestrate_background_teammate_smoke")
        result = {
            "name": case.name,
            "assistant_text": "orchestration progress updated\nrun_id=run_demo",
            "tool_event_names": [],
            "orchestration_run_id": "run_demo",
            "orchestration_created": True,
            "orchestration_dispatched": True,
            "orchestration_progressed": True,
            "orchestration_dispatch_refs": ["CARD-001:background_task:bg_smoke_001"],
            "llm_trace": {"requests": []},
        }

        errors = MODULE._validation_errors(case, result)
        self.assertIn("orchestration_dispatch_not_teammate_background", errors)

    def test_main_strict_returns_nonzero_when_case_fails_validation(self) -> None:
        failing_case_result = {
            "name": "followup_pwd",
            "phase": "tool_followup",
            "prompt": "prompt",
            "commands": ["pwd"],
            "setup_results": [],
            "assistant_text": "模型未返回内容。",
            "tool_event_summaries": [],
            "tool_event_names": [],
            "delegated_agent_id": "",
            "delegated_role": "",
            "delegation_reason": "",
            "delegation_mode": "",
            "delegated_wait_required": None,
            "delegated_task_shape": "",
            "delegated_parallel_group": "",
            "delegated_provider_name": "",
            "delegated_model": "",
            "delegated_source": "",
            "wait_assistant_text": "",
            "wait_tool_event_names": [],
            "wait_status": "",
            "wait_decision": "",
            "wait_result_ready": None,
            "wait_adopted": None,
            "llm_trace": {"requests": []},
            "log_dir": "/tmp/demo",
            "runtime_provider_status": {"provider_ready": "true"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace()), \
                patch.object(MODULE, "build_planner", return_value=_DummyPlanner()), \
                patch.object(MODULE, "AgentCliRuntime", return_value=_DummyRuntime()), \
                patch.object(MODULE, "_run_case", return_value=failing_case_result):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--strict",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertIn("summary", payload)
        self.assertFalse(payload["passed"])
        self.assertIn("empty_response", payload["summary"]["failure_categories"])

    def test_main_strict_returns_zero_when_case_passes_validation(self) -> None:
        passing_case_result = {
            "name": "followup_pwd",
            "phase": "tool_followup",
            "prompt": "prompt",
            "commands": ["pwd"],
            "setup_results": [],
            "assistant_text": "/tmp/demo",
            "tool_event_summaries": ["pwd ok"],
            "tool_event_names": ["exec_command"],
            "delegated_agent_id": "",
            "delegated_role": "",
            "delegation_reason": "",
            "delegation_mode": "",
            "delegated_wait_required": None,
            "delegated_task_shape": "",
            "delegated_parallel_group": "",
            "delegated_provider_name": "",
            "delegated_model": "",
            "delegated_source": "",
            "wait_assistant_text": "",
            "wait_tool_event_names": [],
            "wait_status": "",
            "wait_decision": "",
            "wait_result_ready": None,
            "wait_adopted": None,
            "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}]},
            "log_dir": "/tmp/demo",
            "runtime_provider_status": {"provider_ready": "true"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace()), \
                patch.object(MODULE, "build_planner", return_value=_DummyPlanner()), \
                patch.object(MODULE, "AgentCliRuntime", return_value=_DummyRuntime()), \
                patch.object(MODULE, "_run_case", return_value=passing_case_result):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--strict",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("summary", payload)
        self.assertTrue(payload["passed"])

    def test_main_ci_gate_returns_nonzero_when_ci_reuse_gate_not_passed(self) -> None:
        passing_case_result = {
            "name": "followup_pwd",
            "phase": "tool_followup",
            "prompt": "prompt",
            "commands": ["pwd"],
            "setup_results": [],
            "assistant_text": "/tmp/demo",
            "tool_event_summaries": ["pwd ok"],
            "tool_event_names": ["exec_command"],
            "delegated_agent_id": "",
            "delegated_role": "",
            "delegation_reason": "",
            "delegation_mode": "",
            "delegated_wait_required": None,
            "delegated_task_shape": "",
            "delegated_parallel_group": "",
            "delegated_provider_name": "",
            "delegated_model": "",
            "delegated_source": "",
            "wait_assistant_text": "",
            "wait_tool_event_names": [],
            "wait_status": "",
            "wait_decision": "",
            "wait_result_ready": None,
            "wait_adopted": None,
            "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}]},
            "log_dir": "/tmp/demo",
            "runtime_provider_status": {"provider_ready": "true"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace()), \
                patch.object(MODULE, "build_planner", return_value=_DummyPlanner()), \
                patch.object(MODULE, "AgentCliRuntime", return_value=_DummyRuntime()), \
                patch.object(MODULE, "_run_case", return_value=passing_case_result):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--ci-gate",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ci_reuse"]["ci_gate_passed"])

    def test_main_ci_gate_returns_zero_when_ci_reuse_gate_passed(self) -> None:
        passing_case_result = {
            "name": "followup_pwd",
            "phase": "tool_followup",
            "prompt": "prompt",
            "commands": ["pwd"],
            "setup_results": [],
            "assistant_text": "/tmp/demo",
            "tool_event_summaries": ["pwd ok"],
            "tool_event_names": ["exec_command"],
            "delegated_agent_id": "",
            "delegated_role": "",
            "delegation_reason": "",
            "delegation_mode": "",
            "delegated_wait_required": None,
            "delegated_task_shape": "",
            "delegated_parallel_group": "",
            "delegated_provider_name": "",
            "delegated_model": "",
            "delegated_source": "",
            "wait_assistant_text": "",
            "wait_tool_event_names": [],
            "wait_status": "",
            "wait_decision": "",
            "wait_result_ready": None,
            "wait_adopted": None,
            "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}]},
            "log_dir": "/tmp/demo",
            "runtime_provider_status": {"provider_ready": "true"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace()), \
                patch.object(MODULE, "build_planner", return_value=_DummyPlanner()), \
                patch.object(MODULE, "AgentCliRuntime", return_value=_DummyRuntime()), \
                patch.object(MODULE, "_run_case", return_value=passing_case_result):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--strict",
                            "--ci-gate",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ci_reuse"]["ci_gate_passed"])

    def test_main_bootstrap_failure_still_outputs_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", side_effect=RuntimeError("provider not ready")):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["summary"]["failure_categories"]["bootstrap_failure"], 1)
        self.assertEqual(payload["cases"][0]["failure_category"], "bootstrap_failure")
        self.assertEqual(payload["cases"][0]["validation_errors"], ["bootstrap_failure"])

    def test_main_case_execution_failure_still_outputs_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace()), \
                patch.object(MODULE, "build_planner", return_value=_DummyPlanner()), \
                patch.object(MODULE, "AgentCliRuntime", return_value=_DummyRuntime()), \
                patch.object(MODULE, "_run_case", side_effect=RuntimeError("tool command produced no events")):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--case",
                            "followup_pwd",
                            "--strict",
                            "--log-root",
                            temp_dir,
                        ]
                    )

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["summary"]["failure_categories"]["case_execution_failure"], 1)
        self.assertEqual(payload["cases"][0]["failure_category"], "case_execution_failure")
        self.assertEqual(payload["cases"][0]["validation_errors"], ["case_execution_failure"])
