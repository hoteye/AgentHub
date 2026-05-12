import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cli.replay_integration.drift import build_drift_report
from cli.replay_integration.workspace_snapshot import capture_environment_snapshot, capture_workspace_snapshot

class ReplayDriftTest(unittest.TestCase):
    def test_drift_report_is_clean_for_matching_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "AENGTHUB.md").write_text("repo instructions", encoding="utf-8")
            environment = capture_environment_snapshot(
                cwd=str(workspace),
                shell="bash",
                network_access=False,
                current_dt=datetime(2026, 3, 31, tzinfo=timezone.utc),
            )
            workspace_snapshot = capture_workspace_snapshot(str(workspace))

            report = build_drift_report(
                recorded_environment=environment,
                current_environment=environment,
                recorded_workspace=workspace_snapshot,
                current_workspace=workspace_snapshot,
                policy="strict",
            )

        self.assertFalse(report.issues)
        self.assertFalse(report.blocking)

    def test_drift_report_detects_workspace_digest_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            agents_doc = workspace / "AENGTHUB.md"
            agents_doc.write_text("version one", encoding="utf-8")
            before = capture_workspace_snapshot(str(workspace))
            agents_doc.write_text("version two", encoding="utf-8")
            after = capture_workspace_snapshot(str(workspace))

            report = build_drift_report(
                recorded_environment={"cwd": str(workspace), "shell": "bash"},
                current_environment={"cwd": str(workspace), "shell": "bash"},
                recorded_workspace=before,
                current_workspace=after,
                policy="strict",
            )

        self.assertTrue(report.issues)
        self.assertTrue(report.blocking)
        self.assertEqual(report.issues[0].scope, "workspace")

    def test_drift_report_warns_for_environment_date_change(self) -> None:
        report = build_drift_report(
            recorded_environment={"cwd": "/tmp/demo", "shell": "bash", "current_date": "2026-03-31"},
            current_environment={"cwd": "/tmp/demo", "shell": "bash", "current_date": "2026-04-01"},
            recorded_workspace={"cwd": "/tmp/demo", "instructions_digest": "digest-1"},
            current_workspace={"cwd": "/tmp/demo", "instructions_digest": "digest-1"},
            policy="warn",
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].field, "current_date")
        self.assertFalse(report.blocking)
