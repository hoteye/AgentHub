from __future__ import annotations

from typing import Any, Callable


def workflows_result_contract_hint(
    key_values: dict[str, str],
    *,
    normalized_count_fn: Callable[[Any], str],
    count_from_key_values_fn: Callable[[dict[str, str], str], int],
) -> str:
    delegated_returned = count_from_key_values_fn(
        key_values, "delegated_result_returned", normalized_count_fn=normalized_count_fn
    )
    delegated_adopted = count_from_key_values_fn(
        key_values, "delegated_result_adopted", normalized_count_fn=normalized_count_fn
    )
    delegated_review = count_from_key_values_fn(
        key_values, "delegated_result_pending_review", normalized_count_fn=normalized_count_fn
    )
    background_returned = count_from_key_values_fn(
        key_values, "background_result_returned", normalized_count_fn=normalized_count_fn
    )
    background_adopted = count_from_key_values_fn(
        key_values, "background_result_adopted", normalized_count_fn=normalized_count_fn
    )
    background_review = count_from_key_values_fn(
        key_values, "background_result_pending_review", normalized_count_fn=normalized_count_fn
    )
    orchestration_review = count_from_key_values_fn(
        key_values, "orchestration_review_pending", normalized_count_fn=normalized_count_fn
    )
    orchestration_blocked = count_from_key_values_fn(
        key_values, "orchestration_blocked", normalized_count_fn=normalized_count_fn
    )
    action_required = count_from_key_values_fn(
        key_values, "workflow_action_required", normalized_count_fn=normalized_count_fn
    )
    policy_denied = count_from_key_values_fn(
        key_values, "workflow_policy_denied", normalized_count_fn=normalized_count_fn
    )
    policy_rewrite = count_from_key_values_fn(
        key_values, "workflow_policy_rewrite", normalized_count_fn=normalized_count_fn
    )
    policy_checked = count_from_key_values_fn(
        key_values, "workflow_policy_checked", normalized_count_fn=normalized_count_fn
    )

    returned_count = delegated_returned + background_returned
    adopted_count = delegated_adopted + background_adopted
    review_pending_count = delegated_review + background_review + orchestration_review
    hints: list[str] = []
    if returned_count > 0:
        hints.append(f"result returned {returned_count}")
    if adopted_count > 0:
        hints.append(f"result adopted {adopted_count}")
    if review_pending_count > 0:
        hints.append(f"review pending {review_pending_count}")
    if orchestration_blocked > 0:
        hints.append(f"blocked {orchestration_blocked}")
    if action_required > 0:
        hints.append(f"action required {action_required}")
    if policy_denied > 0:
        hints.append(f"policy denied {policy_denied}")
    if policy_rewrite > 0:
        hints.append(f"policy rewrite {policy_rewrite}")
    if policy_checked > 0 and policy_denied <= 0:
        hints.append(f"policy checked {policy_checked}")
    return " · ".join(hints)


def workflows_execution_projection_hint(
    key_values: dict[str, str],
    *,
    normalized_count_fn: Callable[[Any], str],
    count_from_key_values_fn: Callable[[dict[str, str], str], int],
) -> str:
    runs = count_from_key_values_fn(
        key_values, "execution_projection_runs", normalized_count_fn=normalized_count_fn
    )
    running = count_from_key_values_fn(
        key_values, "execution_projection_running", normalized_count_fn=normalized_count_fn
    )
    terminal = count_from_key_values_fn(
        key_values, "execution_projection_terminal", normalized_count_fn=normalized_count_fn
    )
    attention = count_from_key_values_fn(
        key_values, "execution_projection_attention", normalized_count_fn=normalized_count_fn
    )
    hints: list[str] = []
    if attention > 0:
        hints.append(f"exec attention {attention}")
    if running > 0 and attention <= 0:
        hints.append(f"exec running {running}")
    if terminal > 0 and attention <= 0 and running <= 0:
        hints.append(f"exec terminal {terminal}")
    if runs > 0:
        hints.append(f"exec runs {runs}")
    return " · ".join(hints)
