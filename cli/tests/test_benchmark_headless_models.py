from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock
from cli.tests.provider_boundary_test_support import assert_provider_home_absent, assert_provider_home_env

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "benchmark_headless_models.py"
SPEC = importlib.util.spec_from_file_location("benchmark_headless_models", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

class BenchmarkHeadlessModelsTest(unittest.TestCase):
    def test_benchmark_case_env_overrides_omits_provider_home_when_unset(self) -> None:
        env = MODULE.BenchmarkCase(provider="openai", model="gpt-5.4").env_overrides()

        self.assertEqual(
            env,
            {
                "AGENT_CLI_PROVIDER": "openai",
                "AGENT_CLI_MODEL": "gpt-5.4",
            },
        )

    def test_benchmark_case_env_overrides_includes_provider_home_when_explicit(self) -> None:
        env = MODULE.BenchmarkCase(provider="openai", model="gpt-5.4").env_overrides(
            provider_home="/tmp/provider-home"
        )

        assert_provider_home_env(env, "/tmp/provider-home")

    def test_default_cases_include_glm_single_turn_lane(self) -> None:
        cases = MODULE._default_cases()
        labels = {(item.provider, item.model) for item in cases}
        self.assertIn(("glm", "glm-5"), labels)
        self.assertIn(("glm-claude-mode", "glm-5"), labels)

    def test_selected_policy_helper_combos_uses_regression_profile_defaults(self) -> None:
        profile, combos = MODULE._selected_policy_helper_combos(
            Namespace(
                policy_helper_profile="policy_helper_regression",
                policy_helper_combos=[],
                policy_helper_provider="",
                policy_helper_model="",
                policy_helper_reasoning_effort="low",
                policy_helper_timeout=20,
            )
        )
        self.assertEqual(profile, "policy_helper_regression")
        self.assertEqual([item.combo_id for item in combos], ["glm_low_latency", "deepseek_low_latency"])

    def test_selected_policy_helper_combos_manual_override_forces_single(self) -> None:
        profile, combos = MODULE._selected_policy_helper_combos(
            Namespace(
                policy_helper_profile="policy_helper_regression",
                policy_helper_combos=[],
                policy_helper_provider="deepseek",
                policy_helper_model="deepseek_chat",
                policy_helper_reasoning_effort="low",
                policy_helper_timeout=30,
            )
        )
        self.assertEqual(profile, "single")
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0].source, "manual_override")

    def test_aggregate_failure_categories_sums_rows(self) -> None:
        totals = MODULE._aggregate_failure_categories(
            [
                {"failure_categories": {"empty_response": 2, "timeout": 1}},
                {"failure_categories": {"empty_response": 1, "missing_trace_request": 3}},
            ]
        )
        self.assertEqual(totals["empty_response"], 3)
        self.assertEqual(totals["timeout"], 1)
        self.assertEqual(totals["missing_trace_request"], 3)

    def test_summarize_separates_same_model_across_providers(self) -> None:
        cases = [
            MODULE.BenchmarkCase(provider="glm", model="glm-5"),
            MODULE.BenchmarkCase(provider="glm-claude-mode", model="glm-5"),
        ]
        results = [
            {
                "provider": "glm",
                "model": "glm-5",
                "run": 1,
                "exit_code": 0,
                "provider_runtime_state": "ready",
                "assistant_text": "glm ok",
                "initial_model_ms": 9000,
                "total_ms": 9000,
                "wall_ms": 10000,
            },
            {
                "provider": "glm-claude-mode",
                "model": "glm-5",
                "run": 1,
                "exit_code": 0,
                "provider_runtime_state": "ready",
                "assistant_text": "glm claude mode ok",
                "initial_model_ms": 4000,
                "total_ms": 4000,
                "wall_ms": 5000,
            },
        ]

        summary = MODULE._summarize(results, cases)

        self.assertEqual(summary[0]["provider"], "glm")
        self.assertEqual(summary[0]["runs"], 1)
        self.assertEqual(summary[0]["avg_initial_model_ms"], 9000)
        self.assertEqual(summary[1]["provider"], "glm-claude-mode")
        self.assertEqual(summary[1]["runs"], 1)
        self.assertEqual(summary[1]["avg_initial_model_ms"], 4000)

    def test_score_ability_response_rewards_complete_solution_shape(self) -> None:
        ability_test = MODULE._selected_ability_test("normalize_ranges_py")
        response = """
# Implementation
```python
def normalize_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    normalized: list[list[int]] = []
    for start, end in sorted(ranges):
        if start > end:
            raise ValueError("start > end")
        if not normalized or start > normalized[-1][1] + 1:
            normalized.append([start, end])
        else:
            normalized[-1][1] = max(normalized[-1][1], end)
    return [(start, end) for start, end in normalized]
```

# Tests
```python
import pytest

def test_empty():
    assert normalize_ranges([]) == []

def test_single():
    assert normalize_ranges([(1, 1)]) == [(1, 1)]

def test_unsorted_overlap_adjacent():
    assert normalize_ranges([(5, 6), (1, 3), (4, 4)]) == [(1, 6)]

def test_nested_duplicate():
    assert normalize_ranges([(1, 10), (2, 3), (1, 10)]) == [(1, 10)]

def test_invalid():
    with pytest.raises(ValueError):
        normalize_ranges([(3, 1)])
```

# Analysis
先排序，再线性扫描合并，所以总复杂度是 O(n log n)。
相邻区间通过 start <= last_end + 1 合并。
非法区间直接 raise ValueError，避免静默修正输入。
"""
        scored = MODULE._score_ability_response(response, ability_test=ability_test)
        self.assertGreaterEqual(scored["score"], 8)
        self.assertTrue(scored["passed"])
        self.assertEqual(scored["test_id"], "normalize_ranges_py")

    def test_score_ability_response_penalizes_missing_requirements(self) -> None:
        ability_test = MODULE._selected_ability_test("normalize_ranges_py")
        response = """
这里给一个思路：把区间排个序然后合并。

```python
def normalize_ranges(ranges):
    return ranges
```
"""
        scored = MODULE._score_ability_response(response, ability_test=ability_test)
        self.assertLessEqual(scored["score"], 3)
        self.assertFalse(scored["passed"])
        self.assertIn("format_sections", scored["missing"])

    def test_score_ability_response_for_stable_topological_sort(self) -> None:
        ability_test = MODULE._selected_ability_test("stable_topological_sort_py")
        response = """
# Implementation
```python
import heapq

def stable_topological_sort(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    graph = {node: set() for node in nodes}
    in_degree = {node: 0 for node in nodes}
    for src, dst in edges:
        if src not in graph or dst not in graph:
            raise KeyError("unknown node")
        if src == dst:
            raise ValueError("self-loop")
        if dst in graph[src]:
            continue
        graph[src].add(dst)
        in_degree[dst] += 1
    heap = [node for node, degree in in_degree.items() if degree == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for nxt in sorted(graph[node]):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                heapq.heappush(heap, nxt)
    if len(order) != len(nodes):
        raise ValueError("cycle")
    return order
```

# Tests
```python
import pytest

def test_empty_graph():
    assert stable_topological_sort([], []) == []

def test_isolated_nodes():
    assert stable_topological_sort(["b", "a"], []) == ["a", "b"]

def test_stable_lexicographic_choice():
    assert stable_topological_sort(["a", "b", "c"], [("a", "c"), ("b", "c")]) == ["a", "b", "c"]

def test_duplicate_edge():
    assert stable_topological_sort(["a", "b"], [("a", "b"), ("a", "b")]) == ["a", "b"]

def test_self_loop():
    with pytest.raises(ValueError):
        stable_topological_sort(["a"], [("a", "a")])

def test_cycle():
    with pytest.raises(ValueError):
        stable_topological_sort(["a", "b"], [("a", "b"), ("b", "a")])

def test_unknown_node():
    with pytest.raises(KeyError):
        stable_topological_sort(["a"], [("a", "x")])
```

# Analysis
用最小堆维护当前所有入度为 0 的节点，可以保证每次都选字典序最小的候选，因此结果稳定可重复。
重复边先去重，避免重复累计入度。
自环可以立即报错；一般环通过最终 len(order) != len(nodes) 检测。
构图和扫描边是 O(V + E)，堆操作带来 log V，因此总复杂度是 O((V + E) log V)。
"""
        scored = MODULE._score_ability_response(response, ability_test=ability_test)
        self.assertGreaterEqual(scored["score"], 9)
        self.assertTrue(scored["passed"])
        self.assertEqual(scored["test_id"], "stable_topological_sort_py")

    def test_main_single_turn_ability_dry_run_uses_builtin_prompt(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "_run_single_turn_scenario", side_effect=AssertionError("should not run")):
            with mock.patch("sys.stdout", stdout):
                code = MODULE.main(["--ability-test", "normalize_ranges_py", "--dry-run", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload.get("scenario"), "single_turn_headless")
        self.assertEqual((payload.get("ability_test") or {}).get("test_id"), "normalize_ranges_py")
        self.assertIn("normalize_ranges", str(payload.get("prompt") or ""))
        command = list((payload.get("cases") or [])[0].get("command") or [])
        self.assertIn("--prompt", command)

    def test_main_single_turn_dry_run_uses_runtime_provider_home_without_env_override(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            MODULE,
            "_provider_home_report_fields",
            return_value={
                "provider_home": "/tmp/runtime-provider-home",
                "provider_home_override": "",
                "provider_home_source": "runtime_default",
            },
        ):
            with mock.patch("sys.stdout", stdout):
                code = MODULE.main(["--case", "openai:gpt-5.4", "--runs", "1", "--dry-run", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload.get("provider_home"), "/tmp/runtime-provider-home")
        self.assertEqual(payload.get("provider_home_override"), "")
        self.assertEqual(payload.get("provider_home_source"), "runtime_default")
        case_payload = (payload.get("cases") or [])[0]
        assert_provider_home_absent(dict(case_payload.get("env") or {}))

    def test_run_two_turn_dates_scenario_skips_provider_home_forward_when_unset(self) -> None:
        fake_module = types.ModuleType("benchmark_two_turn_multi_provider")
        forwarded_argv: list[str] = []

        def _fake_main(argv: list[str]) -> int:
            forwarded_argv.extend(argv)
            return 0

        fake_module.main = _fake_main  # type: ignore[attr-defined]
        args = Namespace(
            first_prompt="今天几号？",
            second_prompt="明天呢？",
            timezone="Asia/Shanghai",
            timeout=5,
            max_workers=1,
            provider_home="",
            cases=[],
            json=False,
            out="",
            dry_run=False,
        )

        with mock.patch.dict(sys.modules, {"benchmark_two_turn_multi_provider": fake_module}):
            code = MODULE._run_two_turn_dates_scenario(args)

        self.assertEqual(code, 0)
        self.assertNotIn("--provider-home", forwarded_argv)

    def test_main_ability_test_rejects_non_single_turn_scenario(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            MODULE.main(["--scenario", "two_turn_dates", "--ability-test", "normalize_ranges_py"])
        self.assertEqual(exc.exception.code, 2)

    def test_main_single_turn_ability_suite_dry_run_lists_two_tests(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "_run_ability_suite", side_effect=AssertionError("should not run")):
            with mock.patch("sys.stdout", stdout):
                code = MODULE.main(["--ability-suite", "coding_pair", "--dry-run", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual((payload.get("ability_suite") or {}).get("suite_id"), "coding_pair")
        self.assertEqual(len(payload.get("ability_tests") or []), 2)

    def test_summarize_ability_overall_aggregates_two_tests(self) -> None:
        cases = [MODULE.BenchmarkCase(provider="openai", model="gpt-5.4")]
        results = [
            {
                "provider": "openai",
                "model": "gpt-5.4",
                "ability_test_id": "normalize_ranges_py",
                "ability_score": 10,
                "ability_max_score": 11,
                "ability_score_ratio": 10 / 11,
                "ability_passed": True,
                "initial_model_ms": 1000,
                "total_ms": 1000,
                "wall_ms": 1200,
                "provider_runtime_state": "ready",
                "assistant_text": "ok",
            },
            {
                "provider": "openai",
                "model": "gpt-5.4",
                "ability_test_id": "stable_topological_sort_py",
                "ability_score": 8,
                "ability_max_score": 11,
                "ability_score_ratio": 8 / 11,
                "ability_passed": True,
                "initial_model_ms": 1500,
                "total_ms": 1500,
                "wall_ms": 1800,
                "provider_runtime_state": "ready",
                "assistant_text": "ok",
            },
        ]
        summary = MODULE._summarize_ability_overall(results, cases)
        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual(row["completed_test_count"], 2)
        self.assertEqual(row["pass_runs"], 2)
        self.assertEqual(row["total_ability_score"], 18)
        self.assertEqual(row["total_ability_max_score"], 22)

    def test_aggregate_provider_matrix_projects_rows(self) -> None:
        matrix = MODULE._aggregate_provider_matrix(
            [
                {
                    "provider": "openai",
                    "model": "gpt_54",
                    "runs": 2,
                    "successful_runs": 1,
                    "cases_run": 6,
                    "successful_cases": 5,
                    "success_rate": 0.8333,
                    "timeout_count": 1,
                    "fallback_count": 2,
                    "request_count": 9,
                    "failure_categories": {"timeout": 1, "missing_trace_request": 2},
                }
            ]
        )
        key = "openai:gpt_54"
        self.assertIn(key, matrix)
        self.assertEqual(matrix[key]["successful_cases"], 5)
        self.assertEqual(matrix[key]["fallback_count"], 2)
        self.assertEqual(matrix[key]["failure_total"], 5)
        self.assertEqual(matrix[key]["primary_failure_bucket"], "trace_contract")
        self.assertEqual(matrix[key]["failure_taxonomy"]["timeout"], 1)
        self.assertEqual(matrix[key]["failure_taxonomy"]["trace_contract"], 2)
        self.assertEqual(
            matrix[key]["failure_taxonomy_summary"],
            "trace_contract:2,timeout:1,fallback:2",
        )

    def test_aggregate_route_matrix_counts_route_targets(self) -> None:
        matrix = MODULE._aggregate_route_matrix(
            [
                {
                    "routes": {
                        "policy_helper": {"provider_name": "deepseek", "model": "deepseek-chat"},
                        "tool_followup": {"provider_name": "openai", "model": "gpt-5.4-mini"},
                    }
                },
                {
                    "routes": {
                        "policy_helper": {"provider_name": "deepseek", "model": "deepseek-chat"},
                    }
                },
            ]
        )
        self.assertEqual(matrix["policy_helper"]["deepseek:deepseek-chat"], 2)
        self.assertEqual(matrix["tool_followup"]["openai:gpt-5.4-mini"], 1)

    def test_aggregate_failure_categories_by_case_projects_each_provider_model(self) -> None:
        matrix = MODULE._aggregate_failure_categories_by_case(
            [
                {
                    "provider": "openai",
                    "model": "gpt_54",
                    "failure_categories": {"empty_response": 1, "timeout": 2},
                },
                {
                    "provider": "glm",
                    "model": "glm_5",
                    "failure_categories": {"missing_trace_request": 3},
                },
            ]
        )
        self.assertEqual(matrix["openai:gpt_54"]["timeout"], 2)
        self.assertEqual(matrix["glm:glm_5"]["missing_trace_request"], 3)

    def test_failure_taxonomy_from_row_classifies_contract_and_parse_failures(self) -> None:
        taxonomy = MODULE._failure_taxonomy_from_row(
            {
                "failure_categories": {
                    "empty_response": 1,
                    "timeout": 2,
                    "missing_trace_request": 3,
                    "delegation_contract_mismatch": 1,
                    "orchestration_contract_mismatch": 1,
                    "parse_error_runtime_exception": 2,
                },
                "timeout_count": 1,
                "fallback_count": 2,
                "empty_response_count": 1,
            }
        )
        self.assertEqual(taxonomy["empty_response"], 1)
        self.assertEqual(taxonomy["timeout"], 2)
        self.assertEqual(taxonomy["trace_contract"], 3)
        self.assertEqual(taxonomy["delegation_contract"], 1)
        self.assertEqual(taxonomy["orchestration_contract"], 1)
        self.assertEqual(taxonomy["parse_error"], 2)
        self.assertEqual(taxonomy["fallback"], 2)

    def test_aggregate_failure_taxonomy_by_case_and_totals(self) -> None:
        summary = [
            {
                "provider": "openai",
                "model": "gpt_54",
                "failure_categories": {"timeout": 1, "missing_trace_request": 2},
                "timeout_count": 1,
                "fallback_count": 0,
                "empty_response_count": 0,
            },
            {
                "provider": "glm",
                "model": "glm_5",
                "failure_categories": {"empty_response": 1, "delegation_contract_mismatch": 1},
                "timeout_count": 0,
                "fallback_count": 1,
                "empty_response_count": 1,
            },
        ]
        by_case = MODULE._aggregate_failure_taxonomy_by_case(summary)
        totals = MODULE._aggregate_failure_taxonomy_totals(summary)
        self.assertEqual(by_case["openai:gpt_54"]["timeout"], 1)
        self.assertEqual(by_case["openai:gpt_54"]["trace_contract"], 2)
        self.assertEqual(by_case["glm:glm_5"]["empty_response"], 1)
        self.assertEqual(by_case["glm:glm_5"]["delegation_contract"], 1)
        self.assertEqual(by_case["glm:glm_5"]["fallback"], 1)
        self.assertEqual(totals["timeout"], 1)
        self.assertEqual(totals["trace_contract"], 2)
        self.assertEqual(totals["empty_response"], 1)
        self.assertEqual(totals["delegation_contract"], 1)
        self.assertEqual(totals["fallback"], 1)

    def test_ci_gate_from_summary_computes_success_and_totals(self) -> None:
        gate = MODULE._ci_gate_from_summary(
            [
                {
                    "cases_run": 4,
                    "successful_cases": 4,
                    "timeout_count": 0,
                    "fallback_count": 1,
                },
                {
                    "cases_run": 3,
                    "successful_cases": 2,
                    "timeout_count": 1,
                    "fallback_count": 0,
                },
            ]
        )
        self.assertEqual(gate["cases_run_total"], 7)
        self.assertEqual(gate["successful_cases_total"], 6)
        self.assertEqual(gate["timeout_total"], 1)
        self.assertEqual(gate["fallback_total"], 1)
        self.assertFalse(gate["all_cases_successful"])
        self.assertEqual(gate["reason"], "has_failures_or_empty")

    def test_ci_reuse_block_includes_recommended_command_and_gate(self) -> None:
        block = MODULE._ci_reuse_block(
            scenario="multi_llm_live_cases",
            summary=[
                {
                    "cases_run": 5,
                    "successful_cases": 5,
                    "timeout_count": 0,
                    "fallback_count": 0,
                }
            ],
        )
        self.assertEqual(block["scenario"], "multi_llm_live_cases")
        self.assertTrue(block["ci_gate"]["all_cases_successful"])
        self.assertTrue(block["ci_gate_passed"])
        self.assertEqual(block["ci_gate_reason"], "all_cases_successful")
        self.assertIn("--scenario multi_llm_live_cases", block["recommended_command"])

    def test_ci_reuse_block_dual_contract_fields_remain_consistent(self) -> None:
        block = MODULE._ci_reuse_block(
            scenario="policy_helper_live_cases",
            summary=[
                {
                    "cases_run": 2,
                    "successful_cases": 1,
                    "timeout_count": 1,
                    "fallback_count": 0,
                }
            ],
        )
        self.assertIn("ci_gate", block)
        self.assertIn("ci_gate_passed", block)
        self.assertIn("ci_gate_reason", block)
        self.assertEqual(block["ci_gate_passed"], block["ci_gate"]["all_cases_successful"])
        self.assertEqual(block["ci_gate_reason"], block["ci_gate"]["reason"])

    def test_human_summary_from_aggregate_includes_rate_and_timeout(self) -> None:
        lines = MODULE._human_summary_from_aggregate(
            [
                {
                    "provider": "openai",
                    "model": "gpt_54",
                    "successful_cases": 6,
                    "cases_run": 8,
                    "success_rate": 0.75,
                    "timeout_count": 1,
                    "empty_response_count": 1,
                    "avg_wall_ms": 1234.5,
                    "failure_categories": {"missing_trace_request": 2, "timeout": 1},
                }
            ],
            scenario="multi_llm_live_cases",
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("success=6/8", lines[0])
        self.assertIn("rate=0.75", lines[0])
        self.assertIn("timeout=1", lines[0])
        self.assertIn("failure=trace_contract:4", lines[0])
        self.assertIn("failure_taxonomy=trace_contract:2,timeout:1,empty_response:1", lines[0])

    def test_human_summary_from_aggregate_includes_helper_combo_when_present(self) -> None:
        lines = MODULE._human_summary_from_aggregate(
            [
                {
                    "provider": "glm",
                    "model": "glm_5",
                    "helper_combo_id": "deepseek_low_latency",
                    "successful_cases": 3,
                    "cases_run": 6,
                    "success_rate": 0.5,
                    "timeout_count": 0,
                    "empty_response_count": 1,
                    "avg_wall_ms": 999.0,
                    "failure_categories": {"empty_response": 1, "fallback": 1},
                }
            ],
            scenario="policy_helper_live_cases",
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("helper=deepseek_low_latency", lines[0])
        self.assertIn("failure=empty_response:2", lines[0])
        self.assertIn("failure_taxonomy=empty_response:1,fallback:1", lines[0])

    def test_human_summary_from_aggregate_uses_same_priority_for_tie_break(self) -> None:
        lines = MODULE._human_summary_from_aggregate(
            [
                {
                    "provider": "openai",
                    "model": "gpt_54",
                    "successful_cases": 1,
                    "cases_run": 3,
                    "success_rate": 0.3333,
                    "timeout_count": 1,
                    "empty_response_count": 0,
                    "avg_wall_ms": 1000.0,
                    "failure_categories": {
                        "timeout": 1,
                        "missing_trace_request": 1,
                    },
                }
            ],
            scenario="multi_llm_live_cases",
        )
        self.assertIn("failure=trace_contract:2", lines[0])

    def test_multi_llm_case_success_accepts_routed_trace_request(self) -> None:
        self.assertTrue(
            MODULE._multi_llm_case_success(
                {
                    "assistant_text": "当前目录是 /tmp/demo",
                    "llm_trace": {
                        "requests": [
                            {
                                "provider_name": "glm",
                                "model": "glm-5",
                            }
                        ]
                    },
                }
            )
        )

    def test_multi_llm_case_success_accepts_delegated_spawn_agent_result(self) -> None:
        self.assertTrue(
            MODULE._multi_llm_case_success(
                {
                    "assistant_text": "当前分支为 master。工作区干净。",
                    "tool_event_names": ["spawn_agent"],
                    "delegated_provider_name": "glm",
                    "delegated_model": "glm-5",
                    "llm_trace": {
                        "requests": [
                            {
                                "provider_name": "",
                                "model": "glm-5",
                            }
                        ]
                    },
                }
            )
        )

    def test_multi_llm_case_success_rejects_placeholder_assistant_text(self) -> None:
        self.assertFalse(
            MODULE._multi_llm_case_success(
                {
                    "assistant_text": "模型未返回内容。",
                    "tool_event_names": ["spawn_agent"],
                    "delegated_provider_name": "glm",
                    "delegated_model": "glm-5",
                }
            )
        )

    def test_multi_llm_case_success_rejects_spawn_agent_without_delegated_provider(self) -> None:
        self.assertFalse(
            MODULE._multi_llm_case_success(
                {
                    "assistant_text": "当前分支为 master。工作区干净。",
                    "tool_event_names": ["spawn_agent"],
                    "delegated_provider_name": "",
                    "delegated_model": "glm-5",
                    "llm_trace": {
                        "requests": [
                            {
                                "provider_name": "",
                                "model": "glm-5",
                            }
                        ]
                    },
                }
            )
        )

    def test_case_cost_proxy_counts_requests_child_turn_and_fallback_stage(self) -> None:
        proxy = MODULE._case_cost_proxy(
            {
                "delegated_agent_id": "agent_1",
                "wait_status": "completed",
                "llm_trace": {
                    "requests": [
                        {"provider_name": "glm", "model": "glm-5"},
                        {"provider_name": "glm", "model": "glm-5"},
                    ],
                    "stages": ["planner.round_1", "planner.fallback_after_empty"],
                },
            }
        )

        self.assertEqual(proxy["request_count"], 2)
        self.assertEqual(proxy["child_turn_count"], 1)
        self.assertEqual(proxy["fallback_count"], 1)
        self.assertEqual(proxy["timeout_count"], 0)

    def test_case_cost_proxy_prefers_explicit_counts_and_detects_timeout(self) -> None:
        proxy = MODULE._case_cost_proxy(
            {
                "child_turn_count": 3,
                "fallback_count": 2,
                "wait_status": "timed_out",
                "llm_trace": {"requests": [{"provider_name": "openai", "model": "gpt-5.4"}], "stages": []},
            }
        )

        self.assertEqual(proxy["request_count"], 1)
        self.assertEqual(proxy["child_turn_count"], 3)
        self.assertEqual(proxy["fallback_count"], 2)
        self.assertEqual(proxy["timeout_count"], 1)

    def test_summarize_multi_llm_aggregates_cost_proxy_columns(self) -> None:
        results = [
            {
                "provider": "openai",
                "model": "gpt_54",
                "exit_code": 0,
                "cases_run": 2,
                "successful_cases": 2,
                "successful_runs": 1,
                "wall_ms": 1200,
                "cost_proxy": {
                    "request_count": 4,
                    "child_turn_count": 1,
                    "timeout_count": 0,
                    "fallback_count": 1,
                    "delegation_wall_ms": 1200,
                },
            },
            {
                "provider": "openai",
                "model": "gpt_54",
                "timeout": True,
                "wall_ms": 240000,
                "cases_run": 2,
                "successful_cases": 0,
                "cost_proxy": {
                    "request_count": 0,
                    "child_turn_count": 0,
                    "timeout_count": 1,
                    "fallback_count": 0,
                    "delegation_wall_ms": 0,
                },
            },
        ]
        summary = MODULE._summarize_multi_llm(results, [MODULE.BenchmarkCase(provider="openai", model="gpt_54")])
        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual(row["request_count"], 4)
        self.assertEqual(row["child_turn_count"], 1)
        self.assertEqual(row["timeout_count"], 1)
        self.assertEqual(row["fallback_count"], 1)
        self.assertEqual(row["delegation_wall_ms"], 1200)
        self.assertIn("success_rate", row)
        self.assertIn("failure_categories", row)

    def test_cost_proxy_totals_from_summary_sums_all_models(self) -> None:
        totals = MODULE._cost_proxy_totals_from_summary(
            [
                {
                    "request_count": 3,
                    "child_turn_count": 1,
                    "timeout_count": 0,
                    "fallback_count": 2,
                    "delegation_wall_ms": 1000,
                },
                {
                    "request_count": 5,
                    "child_turn_count": 2,
                    "timeout_count": 1,
                    "fallback_count": 0,
                    "delegation_wall_ms": 2000,
                },
            ]
        )
        self.assertEqual(totals["request_count"], 8)
        self.assertEqual(totals["child_turn_count"], 3)
        self.assertEqual(totals["timeout_count"], 1)
        self.assertEqual(totals["fallback_count"], 2)
        self.assertEqual(totals["delegation_wall_ms"], 3000)

    def test_default_fixed_provider_matrix_covers_main_helper_subagent_teammate(self) -> None:
        matrix = list(MODULE.DEFAULT_FIXED_PROVIDER_MATRIX)
        flat_covers = {cover for item in matrix for cover in tuple(item.get("covers") or ())}
        self.assertIn("main", flat_covers)
        self.assertIn("helper", flat_covers)
        self.assertIn("subagent", flat_covers)
        self.assertIn("teammate", flat_covers)

    def test_summarize_policy_helper_splits_rows_by_helper_combo(self) -> None:
        summary = MODULE._summarize_policy_helper(
            [
                {
                    "provider": "glm",
                    "model": "glm_5",
                    "helper_combo_id": "glm_low_latency",
                    "helper_combo": {"combo_id": "glm_low_latency", "provider": "glm", "model": "glm_5", "timeout": 20},
                    "exit_code": 0,
                    "cases_run": 2,
                    "successful_cases": 2,
                    "wall_ms": 1000,
                    "summary": {"empty_response_count": 0},
                    "cost_proxy": {"request_count": 2, "child_turn_count": 0, "timeout_count": 0, "fallback_count": 0, "delegation_wall_ms": 0},
                    "failure_categories": {},
                },
                {
                    "provider": "glm",
                    "model": "glm_5",
                    "helper_combo_id": "deepseek_low_latency",
                    "helper_combo": {
                        "combo_id": "deepseek_low_latency",
                        "provider": "deepseek",
                        "model": "deepseek_chat",
                        "timeout": 20,
                    },
                    "exit_code": 0,
                    "cases_run": 2,
                    "successful_cases": 1,
                    "wall_ms": 1300,
                    "summary": {"empty_response_count": 1},
                    "cost_proxy": {"request_count": 2, "child_turn_count": 0, "timeout_count": 0, "fallback_count": 1, "delegation_wall_ms": 0},
                    "failure_categories": {"empty_response": 1},
                },
            ]
        )
        self.assertEqual(len(summary), 2)
        combo_ids = {row["helper_combo_id"] for row in summary}
        self.assertIn("glm_low_latency", combo_ids)
        self.assertIn("deepseek_low_latency", combo_ids)

    def test_aggregate_failure_categories_adds_parse_error_bucket(self) -> None:
        totals = MODULE._aggregate_failure_categories(
            [
                {
                    "parse_error": "JSONDecodeError: Expecting value",
                    "stdout_preview": "Traceback: worker failed",
                    "stderr": "RuntimeError: boom",
                }
            ]
        )
        self.assertEqual(totals["parse_error"], 1)
        self.assertEqual(totals["parse_error_runtime_exception"], 1)

    def test_main_multi_llm_dry_run_skips_live_subprocess_path(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "_run_multi_llm_scenario", side_effect=AssertionError("should not run")):
            with mock.patch("sys.stdout", stdout):
                code = MODULE.main(["--scenario", "multi_llm_live_cases", "--dry-run", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload.get("dry_run"))
        self.assertEqual(payload.get("scenario"), "multi_llm_live_cases")
        self.assertEqual(payload.get("results"), [])
        self.assertEqual(len(payload.get("cases") or []), 1)
        command = list((payload.get("cases") or [])[0].get("command") or [])
        self.assertIn("run_multi_llm_live_cases.py", " ".join(command))

    def test_main_policy_helper_dry_run_skips_live_subprocess_path(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "_run_policy_helper_scenario", side_effect=AssertionError("should not run")):
            with mock.patch("sys.stdout", stdout):
                code = MODULE.main(["--scenario", "policy_helper_live_cases", "--dry-run", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload.get("dry_run"))
        self.assertEqual(payload.get("scenario"), "policy_helper_live_cases")
        self.assertEqual(payload.get("results"), [])
        self.assertGreaterEqual(len(payload.get("cases") or []), 1)
        command = list((payload.get("cases") or [])[0].get("command") or [])
        self.assertIn("run_policy_helper_live_cases.py", " ".join(command))

    def test_main_multi_llm_ci_gate_returns_nonzero_on_dry_run_empty_summary(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            code = MODULE.main(["--scenario", "multi_llm_live_cases", "--dry-run", "--json", "--ci-gate"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ci_reuse"]["ci_gate"]["all_cases_successful"])

    def test_main_multi_llm_ci_gate_returns_zero_when_summary_all_successful(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            MODULE,
            "_run_multi_llm_scenario",
            return_value=[{"provider": "openai", "model": "gpt_54", "routes": {}}],
        ), mock.patch.object(
            MODULE,
            "_summarize_multi_llm",
            return_value=[
                {
                    "provider": "openai",
                    "model": "gpt_54",
                    "runs": 1,
                    "successful_runs": 1,
                    "cases_run": 3,
                    "successful_cases": 3,
                    "success_rate": 1.0,
                    "timeout_count": 0,
                    "fallback_count": 0,
                    "request_count": 2,
                    "failure_categories": {},
                }
            ],
        ), mock.patch("sys.stdout", stdout):
            code = MODULE.main(["--scenario", "multi_llm_live_cases", "--json", "--ci-gate"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ci_reuse"]["ci_gate"]["all_cases_successful"])

    def test_main_policy_helper_ci_gate_returns_nonzero_on_dry_run_empty_summary(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            code = MODULE.main(["--scenario", "policy_helper_live_cases", "--dry-run", "--json", "--ci-gate"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ci_reuse"]["ci_gate"]["all_cases_successful"])

    def test_main_policy_helper_ci_gate_returns_zero_when_summary_all_successful(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            MODULE,
            "_run_policy_helper_scenario",
            return_value=("policy_helper_regression", [], [{"provider": "glm", "model": "glm_5", "routes": {}}]),
        ), mock.patch.object(
            MODULE,
            "_summarize_policy_helper",
            return_value=[
                {
                    "provider": "glm",
                    "model": "glm_5",
                    "helper_combo_id": "glm_low_latency",
                    "runs": 1,
                    "successful_runs": 1,
                    "cases_run": 2,
                    "successful_cases": 2,
                    "success_rate": 1.0,
                    "timeout_count": 0,
                    "fallback_count": 0,
                    "request_count": 2,
                    "failure_categories": {},
                    "helper_combo": {"combo_id": "glm_low_latency"},
                }
            ],
        ), mock.patch("sys.stdout", stdout):
            code = MODULE.main(["--scenario", "policy_helper_live_cases", "--json", "--ci-gate"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ci_reuse"]["ci_gate"]["all_cases_successful"])
