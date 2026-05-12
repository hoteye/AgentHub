from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.gateway_server import admin_dispatchers_runtime


class _RuntimeStub:
    def __init__(self) -> None:
        self.cwd = ""
        self.model_calls: list[dict[str, object]] = []
        self.delegate_calls: list[tuple[str, dict[str, object]]] = []
        self.policy_calls: list[dict[str, object]] = []
        self._gui_browser_headless = False
        self._gui_plugin_auto_load = True

    def set_cwd(self, cwd: str) -> None:
        self.cwd = cwd

    def configure_model_selection(self, *, model=None, reasoning_effort=None) -> None:
        self.model_calls.append({"model": model, "reasoning_effort": reasoning_effort})

    def configure_delegate_selection(self, role_name: str, **kwargs) -> None:
        self.delegate_calls.append((role_name, dict(kwargs)))

    def configure_runtime_policy(self, **kwargs) -> None:
        self.policy_calls.append(dict(kwargs))


class AdminDispatchersRuntimeTests(unittest.TestCase):
    def test_config_validation_payload_reports_applyable_and_blocked_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            payload = admin_dispatchers_runtime.config_validation_payload(
                current={
                    "model": "gpt-5.4",
                    "reasoningEffort": "medium",
                    "workspaceRoot": str(workspace),
                    "runtimePolicy": {"approval_policy": "on-request"},
                },
                params={
                    "model": "inherit",
                    "reasoningEffort": "high",
                    "workspaceRoot": str(workspace / "missing"),
                },
                known_selectors={"inherit", "gpt-5.4"},
                standard_delegation_names=("subagent", "teammate"),
                requested_policy={},
                requested_reasoning_effort="high",
                requested_delegation_models={},
                normalized_delegation_signature_fn=lambda payload: tuple(sorted(payload.items())),
                current_delegation_signature_fn=lambda payload: tuple(sorted(payload.items())),
                delegation_requested_reasoning_effort_fn=lambda payload: payload.get("reasoningEffort"),
            )

        self.assertEqual(payload["applyableFields"], ["model", "reasoningEffort"])
        self.assertIn("workspaceRoot", payload["blockedFields"])
        self.assertTrue(any(item["field"] == "workspaceRoot" for item in payload["blocked"]))

    def test_config_apply_result_applies_runtime_and_reports_partial(self) -> None:
        runtime = _RuntimeStub()
        validation = {
            "applyableFields": ["model", "reasoningEffort", "delegationModels.teammate", "approval_policy", "browserHeadless"],
            "changedFields": ["model", "reasoningEffort", "delegationModels.teammate", "approval_policy", "browserHeadless", "workspaceRoot"],
            "blocked": [{"field": "workspaceRoot", "reason": "missing"}],
            "restart": {"required": True, "reasons": ["browserHeadless 变更"], "allowed": False, "mode": "manual", "blockedReason": "manual"},
        }

        result = admin_dispatchers_runtime.config_apply_result(
            runtime=runtime,
            params={"model": "inherit", "browserHeadless": True},
            validation=validation,
            standard_delegation_names=("subagent", "teammate"),
            requested_policy={"approval_policy": "never"},
            requested_reasoning_effort="high",
            requested_delegation_models={"teammate": {"model": "inherit", "timeout": 20}},
            delegation_requested_reasoning_effort_fn=lambda payload: payload.get("reasoningEffort"),
            config_settings_snapshot_fn=lambda runtime, runtime_registry_payload_fn=None: {
                "cwd": runtime.cwd,
                "browserHeadless": runtime._gui_browser_headless,
            },
            runtime_registry_payload_fn=lambda runtime: {},
        )

        self.assertTrue(result["applied"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("model", result["appliedFields"])
        self.assertIn("approval_policy", result["appliedFields"])
        self.assertIn("delegationModels.teammate", result["appliedFields"])
        self.assertEqual(runtime.model_calls[0]["model"], "inherit")
        self.assertEqual(runtime.model_calls[0]["reasoning_effort"], "high")
        self.assertEqual(runtime.policy_calls[0]["approval_policy"], "never")
        self.assertTrue(runtime._gui_browser_headless)
        self.assertEqual(runtime.delegate_calls[0][0], "teammate")

