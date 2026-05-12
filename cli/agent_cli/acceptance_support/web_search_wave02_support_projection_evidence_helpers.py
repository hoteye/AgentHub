from __future__ import annotations

import argparse
from typing import Any

from cli.agent_cli.acceptance_support.web_search_wave02_support_pure_helpers import (
    AGENTHUB_ANTHROPIC_NATIVE_BACKEND,
    AGENTHUB_LOCAL_BACKEND,
    AGENTHUB_OPENAI_NATIVE_BACKEND,
    _clean_strings,
    _effective_web_search_mode_for_turn,
    _external_web_access_for_turn,
    _response_completed_truth,
    _to_int,
    _tool_surface_contract,
)


def _action_families(detail: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(item.get("action_type") or "").strip()
            for item in list(detail.get("web_search_actions") or [])
            if str(item.get("action_type") or "").strip()
        }
    )


def build_agenthub_parity_evidence(detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    turn_types = list(detail.get("turn_item_types") or [])
    response_item_types = list(detail.get("response_item_types") or [])
    routes = [dict(item) for item in list(detail.get("web_search_routes") or []) if isinstance(item, dict)]
    first_route = routes[0] if routes else {}
    web_search_call_seen = "web_search_call" in turn_types or "web_search_call" in response_item_types
    planner = str(detail.get("provider_planner") or "").strip()
    protocol_path = dict(detail.get("protocol_path") or {})
    selected_backend_id = str(first_route.get("selected_backend_id") or "").strip()
    effective_backend_id = str(first_route.get("effective_backend_id") or "").strip()
    selected_backend_kind = str(first_route.get("selected_backend_kind") or "").strip()
    effective_backend_kind = str(first_route.get("effective_backend_kind") or "").strip()
    execution_path = str(first_route.get("execution_path") or "").strip()
    fallback_reason = str(first_route.get("fallback_reason") or "").strip()
    backend_observation = "observed_tool_event" if first_route else "unobserved"
    if not effective_backend_id and web_search_call_seen and planner == "openai_responses":
        selected_backend_id = AGENTHUB_OPENAI_NATIVE_BACKEND
        effective_backend_id = AGENTHUB_OPENAI_NATIVE_BACKEND
        selected_backend_kind = "provider_native"
        effective_backend_kind = "provider_native"
        execution_path = "openai_responses_native"
        backend_observation = "inferred_from_provider_native_item"
    elif not effective_backend_id and web_search_call_seen and planner == "anthropic_messages":
        selected_backend_id = AGENTHUB_ANTHROPIC_NATIVE_BACKEND
        effective_backend_id = AGENTHUB_ANTHROPIC_NATIVE_BACKEND
        selected_backend_kind = "provider_native"
        effective_backend_kind = "provider_native"
        execution_path = "anthropic_native"
        backend_observation = "inferred_from_provider_native_item"
    elif not effective_backend_id and str(protocol_path.get("kind") or "").strip() == "provider_degraded_fallback":
        selected_backend_id = AGENTHUB_LOCAL_BACKEND
        effective_backend_id = AGENTHUB_LOCAL_BACKEND
        selected_backend_kind = "local_fallback"
        effective_backend_kind = "local_fallback"
        execution_path = "local_fallback"
        fallback_reason = fallback_reason or str(protocol_path.get("reason") or "").strip()
        backend_observation = "inferred_from_protocol_path"
    has_final_message = bool(detail.get("has_final_message"))
    continuation_pending = bool(web_search_call_seen and not has_final_message)
    turn_search_phase = ""
    if web_search_call_seen:
        turn_search_phase = "search_results_received" if has_final_message else "search_dispatched"
    effective_mode = _effective_web_search_mode_for_turn(args.web_search_mode, args.sandbox_mode)
    return {
        "codex_comparable": {
            "web_search_call_seen": web_search_call_seen,
            "external_web_access": _external_web_access_for_turn(args.web_search_mode, args.sandbox_mode),
            "effective_web_search_mode": effective_mode,
            "external_web_access_observation": "derived_from_effective_turn_web_search_mode(requested_mode+sandbox_mode)",
            "action_families": _action_families(detail),
            "actions": list(detail.get("web_search_actions") or []),
        },
        "claude_comparable": {
            "server_tool_use_seen": False,
            "web_search_tool_result_seen": False,
            "web_search_requests": 0,
            "observation_mode": "not_applicable_for_openai_native_item_path",
        },
        "agenthub": {
            "selected_backend_id": selected_backend_id,
            "selected_backend_kind": selected_backend_kind,
            "effective_backend_id": effective_backend_id,
            "effective_backend_kind": effective_backend_kind,
            "execution_path": execution_path,
            "backend_observation": backend_observation,
            "fallback_reason": fallback_reason,
            "protocol_path_kind": str(protocol_path.get("kind") or "").strip(),
            "protocol_path_reason": str(protocol_path.get("reason") or "").strip(),
            "provider_used": bool(protocol_path.get("provider_used")),
            "turn_search_phase": turn_search_phase,
            "continuation_pending": continuation_pending,
            "final_answer_present": has_final_message,
            "stream_complete_truth": _response_completed_truth(
                observed=None,
                inferred="final_answer_present"
                if has_final_message
                else "provider_native_item_without_final_answer"
                if web_search_call_seen
                else "unobserved",
                source="AgentHub headless JSON does not expose raw provider SSE response.completed directly",
            ),
            "provider_runtime_state": str(detail.get("provider_runtime_state") or "").strip(),
            "availability_status": str(detail.get("availability_status") or "").strip(),
        },
    }


def build_codex_parity_evidence(detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    item_counts = dict(detail.get("item_counts") or {})
    web_search_call_seen = bool(item_counts.get("web_search") or item_counts.get("web_search_call"))
    has_answer = bool(str(detail.get("assistant_text") or "").strip())
    effective_mode = _effective_web_search_mode_for_turn(args.web_search_mode, args.sandbox_mode)
    return {
        "codex_comparable": {
            "web_search_call_seen": web_search_call_seen,
            "external_web_access": _external_web_access_for_turn(args.web_search_mode, args.sandbox_mode),
            "effective_web_search_mode": effective_mode,
            "external_web_access_observation": "derived_from_effective_turn_web_search_mode_via_codex_ref_spec(requested_mode+sandbox_mode)",
            "action_families": _action_families(detail),
            "actions": list(detail.get("web_search_actions") or []),
            "stream_complete_truth": _response_completed_truth(
                observed=None,
                inferred="assistant_message_present"
                if has_answer
                else "native_marker_without_final_answer"
                if web_search_call_seen
                else "unobserved",
                source="codex exec JSONL preserves items but not raw response.completed events",
            ),
        },
        "claude_comparable": {
            "server_tool_use_seen": False,
            "web_search_tool_result_seen": False,
            "web_search_requests": 0,
            "observation_mode": "not_applicable_for_codex_native_items",
        },
        "agenthub": {"applicable": False},
    }


def build_claude_parity_evidence(detail: dict[str, Any]) -> dict[str, Any]:
    response_block_types = _clean_strings(detail.get("response_block_types"))
    server_tool_uses = _clean_strings(detail.get("server_tool_uses"))
    web_search_requests = _to_int(detail.get("web_search_requests"))
    has_answer = bool(str(detail.get("assistant_text") or "").strip())
    raw_blocks_available = bool(response_block_types or server_tool_uses)
    server_tool_use_seen = bool(server_tool_uses) or web_search_requests > 0
    web_search_tool_result_seen = "web_search_tool_result" in response_block_types
    return {
        "codex_comparable": {
            "web_search_call_seen": False,
            "external_web_access": None,
            "external_web_access_observation": "Claude wrapper does not expose Codex native external_web_access markers",
            "action_families": [],
            "actions": [],
        },
        "claude_comparable": {
            "server_tool_use_seen": server_tool_use_seen,
            "web_search_tool_result_seen": web_search_tool_result_seen,
            "web_search_requests": web_search_requests,
            "response_block_types": response_block_types,
            "server_tool_uses": server_tool_uses,
            "raw_block_markers_available": raw_blocks_available,
            "observation_mode": "raw_blocks_observed" if raw_blocks_available else "usage_counter_only",
            "stream_complete_truth": _response_completed_truth(
                observed=None,
                inferred="assistant_result_present" if has_answer else "unobserved",
                source="claude CLI JSON does not expose raw provider response.completed events",
            ),
        },
        "agenthub": {"applicable": False},
    }


def build_parity_evidence(system: str, detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if system == "agenthub":
        return build_agenthub_parity_evidence(detail, args)
    if system == "codex":
        return build_codex_parity_evidence(detail, args)
    return build_claude_parity_evidence(detail)


def build_observable_execution_path(system: str, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    if system == "agenthub":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        agenthub = dict(parity_evidence.get("agenthub") or {})
        return {
            "web_search_call_seen": bool(codex.get("web_search_call_seen")),
            "effective_backend_id": str(agenthub.get("effective_backend_id") or "").strip(),
            "execution_path": str(agenthub.get("execution_path") or "").strip(),
            "turn_search_phase": str(agenthub.get("turn_search_phase") or "").strip(),
            "fallback_reason": str(agenthub.get("fallback_reason") or "").strip(),
        }
    if system == "codex":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        return {
            "web_search_call_seen": bool(codex.get("web_search_call_seen")),
            "action_families": list(codex.get("action_families") or []),
            "external_web_access": codex.get("external_web_access"),
        }
    claude = dict(parity_evidence.get("claude_comparable") or {})
    return {
        "server_tool_use_seen": bool(claude.get("server_tool_use_seen")),
        "web_search_tool_result_seen": bool(claude.get("web_search_tool_result_seen")),
        "web_search_requests": _to_int(claude.get("web_search_requests")),
        "observation_mode": str(claude.get("observation_mode") or "").strip(),
    }


def _stream_complete_truth(system: str, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    if system == "agenthub":
        return dict((parity_evidence.get("agenthub") or {}).get("stream_complete_truth") or {})
    if system == "codex":
        return dict((parity_evidence.get("codex_comparable") or {}).get("stream_complete_truth") or {})
    return dict((parity_evidence.get("claude_comparable") or {}).get("stream_complete_truth") or {})


def build_request_contract(system: str, args: argparse.Namespace, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    effective_mode = _effective_web_search_mode_for_turn(args.web_search_mode, args.sandbox_mode)
    return {
        "reasoning_effort": str(args.reasoning_effort),
        "web_search_mode": str(args.web_search_mode),
        "sandbox_mode": str(args.sandbox_mode),
        "effective_web_search_mode": effective_mode,
        "external_web_access": _external_web_access_for_turn(args.web_search_mode, args.sandbox_mode),
        "tool_surface": _tool_surface_contract(system),
        "stream_complete_truth": _stream_complete_truth(system, parity_evidence),
    }


def classify_outcome(
    system: str,
    *,
    run: dict[str, Any],
    answer_quality: dict[str, Any],
    parity_evidence: dict[str, Any],
) -> dict[str, Any]:
    if bool(run.get("skipped")):
        return {
            "classification": "not_run",
            "reason": str(run.get("skip_reason") or "").strip() or "skipped",
            "inferred": False,
        }
    if system == "agenthub":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        agenthub = dict(parity_evidence.get("agenthub") or {})
        effective_kind = str(agenthub.get("effective_backend_kind") or "").strip()
        execution_path = str(agenthub.get("execution_path") or "").strip()
        if effective_kind in {"local", "local_fallback"} or execution_path == "local_fallback":
            return {
                "classification": "fallback_complete"
                if bool(run.get("exit_code") == 0 and answer_quality.get("assistant_text_present"))
                else "fallback_error",
                "reason": str(agenthub.get("fallback_reason") or "").strip() or "local_fallback_route",
                "inferred": False,
            }
        if bool(codex.get("web_search_call_seen")):
            return {
                "classification": "native_complete"
                if bool(answer_quality.get("assistant_text_present") and not agenthub.get("continuation_pending"))
                else "native_degraded",
                "reason": str(agenthub.get("turn_search_phase") or "").strip() or "provider_native_item_seen",
                "inferred": False,
            }
        return {
            "classification": "provider_error_without_search",
            "reason": str(agenthub.get("protocol_path_reason") or agenthub.get("protocol_path_kind") or "").strip()
            or "no_native_dispatch_marker",
            "inferred": False,
        }
    if system == "codex":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        if bool(codex.get("web_search_call_seen")):
            return {
                "classification": "native_complete"
                if bool(answer_quality.get("assistant_text_present"))
                else "native_degraded",
                "reason": "codex_native_item_seen",
                "inferred": False,
            }
        return {
            "classification": "provider_error_without_search",
            "reason": "no_codex_native_web_search_marker",
            "inferred": False,
        }
    claude = dict(parity_evidence.get("claude_comparable") or {})
    web_search_requests = _to_int(claude.get("web_search_requests"))
    raw_blocks_available = bool(claude.get("raw_block_markers_available"))
    if web_search_requests > 0:
        if bool(answer_quality.get("assistant_text_present")):
            return {
                "classification": "server_tool_complete",
                "reason": "usage.server_tool_use.web_search_requests > 0"
                if not raw_blocks_available
                else "server_tool_use resolved to final answer",
                "inferred": not raw_blocks_available,
            }
        return {
            "classification": "server_tool_interrupted",
            "reason": "server_tool_use signaled without usable final answer",
            "inferred": not raw_blocks_available,
        }
    return {
        "classification": "provider_error_without_search",
        "reason": "no_claude_server_tool_web_search_evidence",
        "inferred": False,
    }


__all__ = [
    "build_agenthub_parity_evidence",
    "build_claude_parity_evidence",
    "build_codex_parity_evidence",
    "build_observable_execution_path",
    "build_parity_evidence",
    "build_request_contract",
    "classify_outcome",
]
