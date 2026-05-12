from __future__ import annotations

from dataclasses import asdict
from typing import Any

try:
    from cli.scripts.previous_response_id_rejection_live_harness_model_helpers import ObservedRequest
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from previous_response_id_rejection_live_harness_model_helpers import ObservedRequest  # type: ignore[no-redef]


def analyze_observed_requests(requests: list[ObservedRequest]) -> dict[str, Any]:
    injected = [item for item in requests if item.injected_rejection]
    first = requests[0] if requests else None
    rejected = injected[0] if injected else None
    replay = None
    post_rejection = None
    if rejected is not None:
        try:
            rejected_index = requests.index(rejected)
        except ValueError:
            rejected_index = -1
        if rejected_index >= 0 and rejected_index + 1 < len(requests):
            post_rejection = requests[rejected_index + 1]
        if (
            post_rejection is not None
            and not post_rejection.previous_response_id
            and "function_call" in post_rejection.input_types
            and "function_call_output" in post_rejection.input_types
        ):
            replay = post_rejection
    reasons: list[str] = []
    if first is None:
        reasons.append("missing_first_request")
    elif first.previous_response_id:
        reasons.append("first_request_unexpected_previous_response_id")
    if rejected is None:
        reasons.append("missing_injected_rejection")
    elif rejected.input_types != ["function_call_output"]:
        reasons.append("rejected_request_input_not_incremental_function_call_output_only")
    if rejected is not None and post_rejection is None:
        reasons.append("missing_post_rejection_request")
    elif post_rejection is not None and post_rejection.previous_response_id:
        reasons.append("post_rejection_request_unexpected_previous_response_id")
    if replay is None:
        reasons.append("missing_direct_full_replay_without_previous_response_id")
    verdict = "pass" if not reasons else "fail"
    return {
        "verdict": verdict,
        "reasons": reasons,
        "request_count": len(requests),
        "first_request": asdict(first) if first is not None else None,
        "rejected_request": asdict(rejected) if rejected is not None else None,
        "post_rejection_request": asdict(post_rejection) if post_rejection is not None else None,
        "full_replay_request": asdict(replay) if replay is not None else None,
    }
