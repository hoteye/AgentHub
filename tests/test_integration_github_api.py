import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.integrations import (
    build_github_issue_comment_request,
    build_github_issue_create_request,
    build_github_workflow_dispatch_request,
    github_action_artifact_refs,
    github_delivery_id,
    github_request_target,
    github_repository_full_name,
    github_source_id,
    normalize_github_event_type,
)

class GitHubApiHelpersTest(unittest.TestCase):
    def test_normalize_github_issue_event(self) -> None:
        payload = {
            "action": "opened",
            "repository": {"full_name": "acme/platform"},
            "issue": {"number": 7},
        }
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-123",
        }

        self.assertEqual(normalize_github_event_type(headers=headers, payload=payload), "github.issues.opened")
        self.assertEqual(github_repository_full_name(payload), "acme/platform")
        self.assertEqual(github_source_id(payload), "github:acme/platform")
        self.assertEqual(github_delivery_id(headers), "delivery-123")

    def test_build_issue_and_workflow_requests(self) -> None:
        issue_request = build_github_issue_create_request(
            owner="acme",
            repo="platform",
            title="Phase 1",
            body="body",
            token_env="PM_GITHUB_TOKEN",
        )
        comment_request = build_github_issue_comment_request(
            owner="acme",
            repo="platform",
            issue_number=9,
            body="hello",
            token_env="PM_GITHUB_TOKEN",
        )
        workflow_request = build_github_workflow_dispatch_request(
            owner="acme",
            repo="platform",
            workflow_id="agenthub-validation.yml",
            ref="main",
            inputs={"trace_id": "trace-1"},
            token_env="PM_GITHUB_TOKEN",
        )

        self.assertEqual(issue_request["action"], "http_request")
        self.assertEqual(
            issue_request["parameters"]["url"],
            "https://api.github.com/repos/acme/platform/issues",
        )
        self.assertEqual(comment_request["parameters"]["expected_statuses"], [201])
        self.assertEqual(workflow_request["parameters"]["expected_statuses"], [204])
        self.assertEqual(issue_request["parameters"]["auth"]["token_env"], "PM_GITHUB_TOKEN")
        self.assertNotIn("Authorization", issue_request["parameters"]["headers"])
        self.assertEqual(
            workflow_request["parameters"]["json_body"],
            {"ref": "main", "inputs": {"trace_id": "trace-1"}},
        )

    def test_github_request_target_and_artifact_refs(self) -> None:
        request_payload = {
            "action": "http_request",
            "parameters": {
                "url": "https://api.github.com/repos/acme/platform/issues/9/comments",
            },
        }
        target = github_request_target(request_payload)
        refs = github_action_artifact_refs(
            action_type="github.issue.comment",
            request_payload=request_payload,
            action_output={"json_data": {"html_url": "https://github.com/acme/platform/issues/9#issuecomment-1"}},
        )

        self.assertEqual(target["owner"], "acme")
        self.assertEqual(target["repo"], "platform")
        self.assertEqual(target["issue_number"], 9)
        self.assertEqual(refs["artifact_refs"][0], "https://github.com/acme/platform/issues/9#issuecomment-1")
