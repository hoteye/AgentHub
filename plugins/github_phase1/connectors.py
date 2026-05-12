from __future__ import annotations


def build_connectors(plugin_name: str = "github_phase1") -> list[dict[str, object]]:
    return [
        {
            "connector_key": "github_webhook",
            "plugin_name": plugin_name,
            "display_name": "GitHub Webhook",
            "version": "1",
            "connector_kind": "bidirectional",
            "description": "GitHub Phase 1 webhook ingress and controlled REST actions.",
            "supports_webhook": True,
            "supports_polling": False,
            "supports_actions": True,
            "event_types": [
                "github.ping",
                "github.issues.opened",
                "github.issue_comment.created",
            ],
            "action_types": [
                "github.issue.create",
                "github.issue.comment",
                "github.issue.labels.add",
                "github.issue.close",
                "github.workflow.dispatch",
            ],
            "metadata": {"provider": "github", "phase": "phase1"},
        }
    ]
