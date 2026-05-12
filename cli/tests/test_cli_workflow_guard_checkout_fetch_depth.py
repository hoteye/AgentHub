from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardCheckoutFetchDepthTest(unittest.TestCase):
    def test_modularity_guards_checkout_uses_v4_with_fetch_depth_zero(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[2]
            / ".github"
            / "workflows"
            / "cli-cross-platform.yml"
        )
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        jobs = dict(payload.get("jobs") or {})
        self.assertIn("modularity-guards", jobs)
        job = dict(jobs["modularity-guards"] or {})

        steps = [dict(item) for item in list(job.get("steps") or []) if isinstance(item, dict)]
        checkout_step = next(
            (
                step
                for step in steps
                if str(step.get("name") or "").strip() == "Check out repository"
            ),
            None,
        )
        self.assertIsNotNone(checkout_step)
        assert checkout_step is not None

        self.assertEqual(str(checkout_step.get("uses") or "").strip(), "actions/checkout@v4")
        checkout_with = dict(checkout_step.get("with") or {})
        self.assertIn("fetch-depth", checkout_with)
        self.assertEqual(checkout_with["fetch-depth"], 0)

