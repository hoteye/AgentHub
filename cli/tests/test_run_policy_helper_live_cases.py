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
SCRIPT_PATH = ROOT / "cli" / "scripts" / "run_policy_helper_live_cases.py"
SPEC = importlib.util.spec_from_file_location("run_policy_helper_live_cases", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RunPolicyHelperLiveCasesTest(unittest.TestCase):
    def test_selected_helper_combos_single_manual_override(self) -> None:
        combos = MODULE._selected_helper_combos(
            profile="single",
            helper_combos=[],
            policy_helper_provider="deepseek",
            policy_helper_model="deepseek_chat",
            policy_helper_reasoning_effort="low",
            policy_helper_timeout=30,
        )
        self.assertEqual(len(combos), 1)
        combo = combos[0]
        self.assertEqual(combo.provider, "deepseek")
        self.assertEqual(combo.model, "deepseek_chat")
        self.assertEqual(combo.timeout, 30)
        self.assertEqual(combo.source, "manual_override")
        self.assertIn("manual_", combo.combo_id)

    def test_selected_helper_combos_profile_filter(self) -> None:
        combos = MODULE._selected_helper_combos(
            profile="policy_helper_regression",
            helper_combos=["deepseek_low_latency"],
            policy_helper_provider="",
            policy_helper_model="",
            policy_helper_reasoning_effort="",
            policy_helper_timeout=0,
        )
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0].combo_id, "deepseek_low_latency")
        self.assertEqual(combos[0].provider, "deepseek")

    def test_selected_helper_combos_profile_rejects_manual_provider_override(self) -> None:
        with self.assertRaises(ValueError):
            MODULE._selected_helper_combos(
                profile="policy_helper_regression",
                helper_combos=[],
                policy_helper_provider="deepseek",
                policy_helper_model="deepseek_chat",
                policy_helper_reasoning_effort="low",
                policy_helper_timeout=20,
            )

    def test_aggregate_profile_summary_includes_combo_and_failures(self) -> None:
        summary = MODULE._aggregate_profile_summary(
            [
                {
                    "helper_combo": {"combo_id": "glm_low_latency"},
                    "summary": {"success_count": 1},
                    "cases": [{"success": True, "empty_result": False, "fallback_used": False, "failure_category": "none", "phase": "rewrite"}],
                },
                {
                    "helper_combo": {"combo_id": "deepseek_low_latency"},
                    "summary": {"success_count": 0},
                    "cases": [{"success": False, "empty_result": True, "fallback_used": False, "failure_category": "empty_response", "phase": "rewrite"}],
                },
            ]
        )
        self.assertEqual(summary["combo_count"], 2)
        self.assertEqual(summary["success_count"], 1)
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["failure_categories"]["empty_response"], 1)
        self.assertIn("combo_summary", summary)
        self.assertTrue(summary["human_summary"])

    def test_main_single_profile_keeps_legacy_top_level_fields(self) -> None:
        run_report = {
            "helper_combo": {"combo_id": "manual_deepseek", "provider": "deepseek", "model": "deepseek_chat"},
            "planner_summary": {"planner_kind": "chat_completions"},
            "routes": {"policy_helper": {"provider_name": "deepseek", "model": "deepseek_chat"}},
            "recommended_baseline": {"reason": "live_policy_helper_cases"},
            "cases": [
                {
                    "name": "rewrite_permission_mismatch",
                    "success": True,
                    "empty_result": False,
                    "fallback_used": False,
                    "failure_category": "none",
                    "phase": "rewrite",
                }
            ],
            "summary": {
                "total_cases": 1,
                "success_count": 1,
                "success_rate": 1.0,
                "empty_result_count": 0,
                "empty_result_rate": 0.0,
                "fallback_count": 0,
                "fallback_rate": 0.0,
                "request_count": 1,
                "avg_wall_ms": 10.0,
                "phase_summary": {},
                "failure_categories": {},
                "human_summary": ["ok"],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace(raw_model={})), patch.object(
                MODULE, "_run_combo", return_value=run_report
            ):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--profile",
                            "single",
                            "--case",
                            "rewrite_permission_mismatch",
                            "--policy-helper-provider",
                            "deepseek",
                            "--policy-helper-model",
                            "deepseek_chat",
                            "--log-root",
                            temp_dir,
                        ]
                    )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["profile"], "single")
        self.assertIn("cases", payload)
        self.assertIn("routes", payload)
        self.assertEqual(payload["helper_combo"]["combo_id"], "manual_deepseek")
        self.assertEqual(payload["summary"]["success_count"], 1)

    def test_main_matrix_profile_emits_runs_and_combo_summary(self) -> None:
        def _fake_run_combo(*, combo, **kwargs):
            is_ok = combo.combo_id == "glm_low_latency"
            return {
                "helper_combo": combo.as_dict(),
                "planner_summary": {"planner_kind": "chat_completions"},
                "routes": {"policy_helper": {"provider_name": combo.provider, "model": combo.model}},
                "recommended_baseline": {"reason": "live_policy_helper_cases"},
                "cases": [
                    {
                        "name": "rewrite_permission_mismatch",
                        "success": is_ok,
                        "empty_result": not is_ok,
                        "fallback_used": False,
                        "failure_category": "none" if is_ok else "empty_response",
                        "phase": "rewrite",
                    }
                ],
                "summary": {"success_count": 1 if is_ok else 0},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.object(MODULE, "load_provider_config", return_value=SimpleNamespace(raw_model={})), patch.object(
                MODULE, "_run_combo", side_effect=_fake_run_combo
            ):
                with redirect_stdout(stdout):
                    code = MODULE.main(
                        [
                            "--profile",
                            "policy_helper_regression",
                            "--case",
                            "rewrite_permission_mismatch",
                            "--log-root",
                            temp_dir,
                        ]
                    )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["profile"], "policy_helper_regression")
        self.assertEqual(len(payload["runs"]), 2)
        self.assertEqual(payload["summary"]["combo_count"], 2)
        self.assertEqual(payload["failure_categories"]["empty_response"], 1)
        self.assertEqual(payload["cases"], [])

