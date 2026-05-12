from __future__ import annotations

from cli.agent_cli.providers.policy_activity_reporting import PolicyActivityReportingMixin
from cli.agent_cli.providers.policy_answer_rendering import PolicyAnswerRenderingMixin
from cli.agent_cli.providers.policy_answer_snippets import PolicyAnswerSnippetsMixin
from cli.agent_cli.providers.policy_document_summary import PolicyDocumentSummaryMixin
from cli.agent_cli.providers.policy_evidence import PolicyEvidenceMixin
from cli.agent_cli.providers.policy_evidence_profile import PolicyEvidenceProfileMixin
from cli.agent_cli.providers.policy_evidence_ranking import PolicyEvidenceRankingMixin
from cli.agent_cli.providers.policy_evidence_selection import PolicyEvidenceSelectionMixin
from cli.agent_cli.providers.policy_llm_assist import PolicyLlmAssistMixin
from cli.agent_cli.providers.policy_preflight import PolicyPreflightMixin
from cli.agent_cli.providers.policy_response import PolicyResponseMixin


class PolicyGroundingMixin(
    PolicyLlmAssistMixin,
    PolicyPreflightMixin,
    PolicyActivityReportingMixin,
    PolicyDocumentSummaryMixin,
    PolicyAnswerSnippetsMixin,
    PolicyAnswerRenderingMixin,
    PolicyEvidenceProfileMixin,
    PolicyEvidenceRankingMixin,
    PolicyEvidenceSelectionMixin,
    PolicyEvidenceMixin,
    PolicyResponseMixin,
):
    """Compatibility facade that preserves the existing planner mixin surface."""

    pass
