from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cli.agent_cli.acceptance_support import (
    web_search_wave02_support_projection_evidence_helpers as evidence_helpers_service,
)
from cli.agent_cli.acceptance_support import (
    web_search_wave02_support_projection_report_helpers as report_helpers_service,
)
from cli.agent_cli.acceptance_support.web_search_wave02_support_pure_helpers import (
    CommandResult,
    PromptFamily,
    _answer_quality,
)
from cli.agent_cli.acceptance_support.web_search_wave02_support_runtime_helpers import _write_json


# Wrapper functions kept at this facade surface for import stability and monkeypatchability.
def _agenthub_parity_evidence(detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return evidence_helpers_service.build_agenthub_parity_evidence(detail, args)


def _codex_parity_evidence(detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return evidence_helpers_service.build_codex_parity_evidence(detail, args)


def _claude_parity_evidence(detail: dict[str, Any]) -> dict[str, Any]:
    return evidence_helpers_service.build_claude_parity_evidence(detail)


def _parity_evidence(system: str, detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return evidence_helpers_service.build_parity_evidence(system, detail, args)


def _observable_execution_path(system: str, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    return evidence_helpers_service.build_observable_execution_path(system, parity_evidence)


def _request_contract(system: str, args: argparse.Namespace, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    return evidence_helpers_service.build_request_contract(system, args, parity_evidence)


def _outcome_classification(
    system: str,
    *,
    run: dict[str, Any],
    answer_quality: dict[str, Any],
    parity_evidence: dict[str, Any],
) -> dict[str, Any]:
    return evidence_helpers_service.classify_outcome(
        system,
        run=run,
        answer_quality=answer_quality,
        parity_evidence=parity_evidence,
    )


def _supported_conclusions(case: PromptFamily, systems: list[dict[str, Any]]) -> list[str]:
    return report_helpers_service.build_supported_conclusions(case, systems)


def _unsupported_conclusions(case: PromptFamily, systems: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    return report_helpers_service.build_unsupported_conclusions(case, systems, args)


def _provider_instability_notes(systems: list[dict[str, Any]]) -> list[str]:
    return report_helpers_service.build_provider_instability_notes(systems)


def _case_report(case: PromptFamily, systems: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    return report_helpers_service.build_case_report(
        case,
        systems,
        args,
        provider_instability_notes_fn=_provider_instability_notes,
        supported_conclusions_fn=_supported_conclusions,
        unsupported_conclusions_fn=_unsupported_conclusions,
    )


def _markdown_report(report: dict[str, Any]) -> str:
    return report_helpers_service.render_markdown_report(report)


def build_case_system_summary(
    *,
    system: str,
    case: PromptFamily,
    detail: dict[str, Any],
    result: CommandResult,
    args: argparse.Namespace,
    detail_path: Path,
) -> dict[str, Any]:
    return report_helpers_service.build_case_system_summary(
        system=system,
        case=case,
        detail=detail,
        result=result,
        args=args,
        detail_path=detail_path,
        parity_evidence_fn=_parity_evidence,
        answer_quality_fn=_answer_quality,
        request_contract_fn=_request_contract,
        observable_execution_path_fn=_observable_execution_path,
        outcome_classification_fn=_outcome_classification,
        write_json_fn=_write_json,
    )


__all__ = [
    "_agenthub_parity_evidence",
    "_case_report",
    "_claude_parity_evidence",
    "_codex_parity_evidence",
    "_markdown_report",
    "_observable_execution_path",
    "_outcome_classification",
    "_parity_evidence",
    "_provider_instability_notes",
    "_request_contract",
    "_supported_conclusions",
    "_unsupported_conclusions",
    "build_case_system_summary",
]
