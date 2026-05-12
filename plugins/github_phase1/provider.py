from cli.agent_cli.host.plugin_hooks import ProviderHooks


def provider_hooks() -> ProviderHooks:
    return ProviderHooks(
        tool_specs=[
            {"name": "github_issue_create", "description": "Create a GitHub issue through the Phase 1 controlled path."},
            {"name": "github_issue_comment", "description": "Add a GitHub issue comment through the Phase 1 controlled path."},
            {"name": "github_issue_add_labels", "description": "Add labels to a GitHub issue through the Phase 1 controlled path."},
            {"name": "github_issue_close", "description": "Close a GitHub issue through the Phase 1 controlled path."},
            {
                "name": "github_workflow_dispatch",
                "description": "Dispatch a GitHub Actions workflow through the Phase 1 controlled path.",
            },
        ],
        system_prompt_fragments=[
            "Use github_phase1 only for in-scope GitHub webhook, issue, comment, label, close, or workflow dispatch tasks."
        ],
        routing_hints=[
            "Use github_phase1 for GitHub Phase 1 acceptance flows, especially issue and workflow-dispatch actions."
        ],
    )
