from __future__ import annotations


def build_triggers(plugin_name: str = "github_phase1") -> list[dict[str, object]]:
    return [
        {
            "trigger_key": "github_compliance_issues_opened",
            "plugin_name": plugin_name,
            "trigger_kind": "event",
            "connector_key": "github_webhook",
            "event_types": ["github.issues.opened"],
            "workflow_name": "handle_github_compliance_issue_opened",
            "priority": 10,
            "filters": {
                "payload_contains_any": {
                    "paths": ["issue.title", "issue.body"],
                    "terms": [
                        "compliance",
                        "policy",
                        "audit",
                        "remediation",
                        "control",
                    ],
                }
            },
            "metadata": {"provider": "github", "route": "policy"},
        },
        {
            "trigger_key": "github_issues_opened",
            "plugin_name": plugin_name,
            "trigger_kind": "event",
            "connector_key": "github_webhook",
            "event_types": ["github.issues.opened"],
            "workflow_name": "handle_github_issue_opened",
            "priority": 20,
            "metadata": {"provider": "github"},
        },
        {
            "trigger_key": "github_issue_comment_created",
            "plugin_name": plugin_name,
            "trigger_kind": "event",
            "connector_key": "github_webhook",
            "event_types": ["github.issue_comment.created"],
            "workflow_name": "handle_github_issue_comment_created",
            "priority": 20,
            "metadata": {"provider": "github"},
        },
    ]
