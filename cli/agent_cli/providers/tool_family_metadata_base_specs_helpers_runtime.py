from __future__ import annotations

from typing import Any, Dict, Tuple

from cli.agent_cli.slash_surface import surface_usage_text


def navigation_and_policy_tool_specs() -> Tuple[Dict[str, Any], ...]:
    return (
        {
            "name": "open",
            "label": "Open Page",
            "description": "Open one webpage or revisit a stored page reference and inspect its lines and links.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": f"Usage: {surface_usage_text('open')}",
            "provider_description": (
                "Legacy browser-family compatibility alias for opening one webpage or revisiting a stored page reference. "
                "Prefer browser(action=open, ...) for canonical browser-family control."
            ),
        },
        {
            "name": "click",
            "label": "Click Link",
            "description": "Open one link from a previously opened page by link id.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": "Usage: /click <ref-id> <id>",
            "provider_description": (
                "Legacy browser-family compatibility alias for opening one link from a previously opened page by link id. "
                "Prefer browser(action=act, kind=click, ...) or browser(action=open, ...) when possible."
            ),
        },
        {
            "name": "find",
            "label": "Find In Page",
            "description": "Find matching text in a previously opened page.",
            "model_default_exposure": "compatibility_alias",
            "usage_text": "Usage: /find <ref-id> <pattern>",
            "provider_description": (
                "Legacy browser-family compatibility alias for in-page text search. "
                "Prefer browser(action=snapshot, ...) or browser(action=act, ...) for canonical browser-family inspection."
            ),
        },
        {
            "name": "policy_doc_import",
            "label": "Policy Import",
            "description": "Import local company policy documents into the managed Markdown policy library.",
            "model_default_exposure": "internal_only",
            "provider_description": (
                "Import one local company policy or rule document, or a directory of such files, "
                "into the managed Markdown library for later rule lookup."
            ),
        },
        {
            "name": "policy_doc_list",
            "label": "Policy List",
            "description": "List imported company policy documents.",
            "model_default_exposure": "internal_only",
            "provider_description": "List imported company policy and rule documents from the managed Markdown library.",
        },
        {
            "name": "policy_doc_search",
            "label": "Policy Search",
            "description": "Search imported company policy Markdown.",
            "model_default_exposure": "internal_only",
            "provider_description": (
                "Search imported PSBC policy Markdown for policy basis, clause, procedure, standard, rule, and operating procedure questions. "
                "Use short focused queries, and when formal policy documents are found, "
                "follow up with policy_doc_read before giving the final answer."
            ),
        },
        {
            "name": "policy_doc_read",
            "label": "Policy Read",
            "description": "Read one imported policy document by doc_id or path.",
            "model_default_exposure": "internal_only",
            "provider_description": (
                "Read normalized Markdown from one imported formal company policy document by doc_id or path "
                "so the assistant can answer policy, clause, and procedure questions from source text instead of only using search summaries."
            ),
        },
    )
