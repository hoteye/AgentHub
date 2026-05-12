from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    title: str
    prompt: str
    expected_visible_tools: tuple[str, ...]
    evidence_expectations: tuple[str, ...]
    lifecycle_expectations: tuple[str, ...] = ()
    result_contract_expectations: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    title: str
    family: str
    comparison_labels: tuple[str, ...]
    supported_lanes: tuple[str, ...]
    steps_by_lane: dict[str, tuple[StepSpec, ...]]
    supported_conclusions: tuple[str, ...]
    unsupported_conclusions: tuple[str, ...]
    blocked_assumptions: tuple[str, ...] = ()


def case_specs(*, task_b_blocked_assumptions: tuple[str, ...]) -> tuple[CaseSpec, ...]:
    case_a_prompt_codex = (
        "Use spawn_agent for one bounded read-only side task. Have the child inspect the current repo root and "
        "return the two most relevant top-level entries for understanding this workspace. Do not edit files. "
        "Return the child findings in Chinese."
    )
    case_a_prompt_claude = (
        "Use Agent once for one bounded read-only side task. Have the child inspect the current repo root and "
        "return the two most relevant top-level entries for understanding this workspace. Do not edit files. "
        "Return the child findings in Chinese."
    )
    case_b_prompt_codex = (
        "Start one background child with spawn_agent for a read-only repo scan. Do not wait immediately. "
        "After the child is running, later join it with wait only when you need the final result."
    )
    case_b_prompt_claude = (
        "Use Agent with run_in_background=true for a read-only repo scan. Do not poll. "
        "Continue normally and rely on the completion notification before consuming the result."
    )
    case_c_prompt_codex = (
        "Continue the existing delegated child with send_input. Ask it to narrow the prior findings down to the "
        "single most relevant path and one sentence of rationale."
    )
    case_c_prompt_claude = (
        "Continue the existing delegated child with SendMessage. Ask it to narrow the prior findings down to the "
        "single most relevant path and one sentence of rationale."
    )
    case_d_prompt_codex = (
        "Stop or close the delegated child only if it is no longer needed. Use close_agent rather than waiting for "
        "synthetic completion."
    )
    case_d_prompt_claude = (
        "If the background Agent exposes a task_id that can actually be stopped, use TaskStop(task_id). "
        "If that task id is not available to the model, record the path as unsupported instead of inventing a close step."
    )
    case_e_prompt_generic = (
        "Use the AgentHub control-plane tools to inspect delegated workflow state with agent_workflow and, only if "
        "a recoverable child exists, test recover_agent as a control-plane action. Do not count this as Codex or Claude parity."
    )
    return (
        CaseSpec(
            case_id="case_a_one_shot_read_only",
            title="Case A: one-shot bounded read-only side task",
            family="spawn_entry",
            comparison_labels=("Codex-comparable", "Claude-comparable", "common-bounded-delegation"),
            supported_lanes=("agenthub_codex_openai", "codex_ref", "agenthub_claude_code", "claude_code_ref"),
            steps_by_lane={
                "agenthub_codex_openai": (
                    StepSpec(
                        step_id="a1",
                        title="Launch bounded read-only child",
                        prompt=case_a_prompt_codex,
                        expected_visible_tools=("spawn_agent",),
                        evidence_expectations=(
                            "spawn tool call is visible in the transcript or structured items",
                            "child answer is bounded, read-only, and useful to the main task",
                        ),
                        lifecycle_expectations=("one child identity created",),
                        result_contract_expectations=(
                            "result_contract.status eventually indicates completion",
                            "result_contract.summary or artifact describes the child repo scan result",
                        ),
                    ),
                ),
                "codex_ref": (
                    StepSpec(
                        step_id="a1",
                        title="Launch bounded read-only child",
                        prompt=case_a_prompt_codex,
                        expected_visible_tools=("spawn_agent",),
                        evidence_expectations=(
                            "spawn_agent tool use is visible",
                            "final answer incorporates the child result rather than a local-only guess",
                        ),
                        lifecycle_expectations=("explicit child id is observable",),
                    ),
                ),
                "agenthub_claude_code": (
                    StepSpec(
                        step_id="a1",
                        title="Launch bounded read-only child through Claude-style projection",
                        prompt=case_a_prompt_claude,
                        expected_visible_tools=("Agent",),
                        evidence_expectations=("Agent tool use is visible", "child answer is bounded and read-only"),
                        lifecycle_expectations=("one child identity is created behind the projection",),
                        result_contract_expectations=(
                            "canonical child result must map back to the same delegated session identity",
                        ),
                    ),
                ),
                "claude_code_ref": (
                    StepSpec(
                        step_id="a1",
                        title="Launch bounded read-only child through Agent",
                        prompt=case_a_prompt_claude,
                        expected_visible_tools=("Agent",),
                        evidence_expectations=("Agent tool use is visible", "final answer uses the child output"),
                    ),
                ),
            },
            supported_conclusions=(
                "Both references and both AgentHub parity projections can represent a one-shot bounded read-only side task.",
            ),
            unsupported_conclusions=(
                "This case does not prove background-notification parity or close semantics.",
            ),
        ),
        CaseSpec(
            case_id="case_b_background_join",
            title="Case B: background child and later completion consumption",
            family="background_completion",
            comparison_labels=("Codex-comparable", "Claude-comparable", "lifecycle-parity"),
            supported_lanes=("agenthub_codex_openai", "codex_ref", "agenthub_claude_code", "claude_code_ref"),
            steps_by_lane={
                "agenthub_codex_openai": (
                    StepSpec(
                        step_id="b1",
                        title="Launch background child",
                        prompt=case_b_prompt_codex,
                        expected_visible_tools=("spawn_agent", "wait"),
                        evidence_expectations=(
                            "spawn_agent launches a background child rather than completing inline",
                            "later join point is explicit instead of busy waiting",
                        ),
                        lifecycle_expectations=(
                            "background child stays pending until joined",
                            "wait is used only at an explicit dependency point",
                        ),
                        result_contract_expectations=(
                            "pending result contract stays pending before join",
                            "joined result contract becomes terminal without synthetic completion",
                        ),
                    ),
                ),
                "codex_ref": (
                    StepSpec(
                        step_id="b1",
                        title="Launch background child and later wait",
                        prompt=case_b_prompt_codex,
                        expected_visible_tools=("spawn_agent", "wait"),
                        evidence_expectations=(
                            "spawn_agent creates a child id",
                            "wait joins a real child result at the later dependency point",
                        ),
                        lifecycle_expectations=("Codex wait may accept ids[]; record if only one id is used here.",),
                    ),
                ),
                "agenthub_claude_code": (
                    StepSpec(
                        step_id="b1",
                        title="Launch background child through Agent projection",
                        prompt=case_b_prompt_claude,
                        expected_visible_tools=("Agent",),
                        evidence_expectations=(
                            "Agent background launch is visible",
                            "later completion arrives by notification or equivalent projection, not fake polling",
                        ),
                        lifecycle_expectations=(
                            "background completion path should bind back to the same canonical child session",
                        ),
                        result_contract_expectations=("result_contract should stay pending until the child finishes",),
                    ),
                ),
                "claude_code_ref": (
                    StepSpec(
                        step_id="b1",
                        title="Launch background child through Agent(run_in_background=true)",
                        prompt=case_b_prompt_claude,
                        expected_visible_tools=("Agent",),
                        evidence_expectations=(
                            "run_in_background path is used",
                            "completion is observed via notification, not a model-visible wait tool",
                        ),
                    ),
                ),
            },
            supported_conclusions=(
                "Codex explicit wait and Claude notification-driven background completion are both represented in the bundle as different but valid join paths.",
            ),
            unsupported_conclusions=("This case does not claim Codex multi-id wait parity for AgentHub.",),
            blocked_assumptions=task_b_blocked_assumptions,
        ),
        CaseSpec(
            case_id="case_c_follow_up_existing_child",
            title="Case C: follow-up on existing child",
            family="child_continuation",
            comparison_labels=("Codex-comparable", "Claude-comparable", "continuation-parity"),
            supported_lanes=("agenthub_codex_openai", "codex_ref", "agenthub_claude_code", "claude_code_ref"),
            steps_by_lane={
                "agenthub_codex_openai": (
                    StepSpec(
                        step_id="c1",
                        title="Continue existing child",
                        prompt=case_c_prompt_codex,
                        expected_visible_tools=("send_input",),
                        evidence_expectations=(
                            "send_input targets an existing child identity",
                            "follow-up answer reflects the new constraint rather than a new child launch",
                        ),
                        lifecycle_expectations=("child identity stays stable across follow-up input",),
                        result_contract_expectations=(
                            "pending_input_count or equivalent bookkeeping increments without forking child identity",
                        ),
                    ),
                ),
                "codex_ref": (
                    StepSpec(
                        step_id="c1",
                        title="Continue existing child with send_input",
                        prompt=case_c_prompt_codex,
                        expected_visible_tools=("send_input",),
                        evidence_expectations=("send_input is visible", "child continuation preserves the same agent id"),
                    ),
                ),
                "agenthub_claude_code": (
                    StepSpec(
                        step_id="c1",
                        title="Continue existing child with SendMessage",
                        prompt=case_c_prompt_claude,
                        expected_visible_tools=("SendMessage",),
                        evidence_expectations=("SendMessage is visible", "no fake resume_agent tool is exposed in this lane"),
                        lifecycle_expectations=("SendMessage must resolve to the same canonical delegated child session",),
                    ),
                ),
                "claude_code_ref": (
                    StepSpec(
                        step_id="c1",
                        title="Continue existing child with SendMessage",
                        prompt=case_c_prompt_claude,
                        expected_visible_tools=("SendMessage",),
                        evidence_expectations=(
                            "SendMessage targets the prior agent id or name",
                            "background resume, if needed, happens through the SendMessage path rather than a separate tool",
                        ),
                    ),
                ),
            },
            supported_conclusions=(
                "Codex send_input and Claude SendMessage are treated as the real visible continuation surfaces instead of forcing false symmetry.",
            ),
            unsupported_conclusions=("This case does not claim a dedicated Claude-visible resume_agent tool.",),
            blocked_assumptions=task_b_blocked_assumptions,
        ),
        CaseSpec(
            case_id="case_d_stop_or_close_surface",
            title="Case D: stop or close where the surface really exists",
            family="termination_control",
            comparison_labels=("Codex-comparable", "Claude-conditional", "unsupported-path-accounting"),
            supported_lanes=("agenthub_codex_openai", "codex_ref", "claude_code_ref"),
            steps_by_lane={
                "agenthub_codex_openai": (
                    StepSpec(
                        step_id="d1",
                        title="Close child via explicit control-plane tool",
                        prompt=case_d_prompt_codex,
                        expected_visible_tools=("close_agent",),
                        evidence_expectations=(
                            "close_agent is visible and used instead of synthetic completion",
                            "terminal state records a control-plane close outcome",
                        ),
                        lifecycle_expectations=("close path is distinct from wait/adopt",),
                        result_contract_expectations=("close does not masquerade as a completed child result",),
                    ),
                ),
                "codex_ref": (
                    StepSpec(
                        step_id="d1",
                        title="Close child via close_agent",
                        prompt=case_d_prompt_codex,
                        expected_visible_tools=("close_agent",),
                        evidence_expectations=("close_agent is visible", "agent status changes because shutdown was requested"),
                    ),
                ),
                "claude_code_ref": (
                    StepSpec(
                        step_id="d1",
                        title="Stop background task only if a task_id is surfaced",
                        prompt=case_d_prompt_claude,
                        expected_visible_tools=("TaskStop",),
                        evidence_expectations=(
                            "TaskStop(task_id) is only attempted when the task id is genuinely available",
                            "unsupported stop path is recorded explicitly if the task id is not available to the model",
                        ),
                        notes=("Claude stop parity is conditional by source design; do not coerce this into a close_agent claim.",),
                    ),
                ),
            },
            supported_conclusions=(
                "Codex explicit close is a first-class parity target.",
                "Claude stop remains conditional on genuine task_id visibility.",
            ),
            unsupported_conclusions=(
                "AgentHub claude_code currently has no TaskStop projection and must record that as unsupported capability, not as a hidden pass.",
            ),
            blocked_assumptions=task_b_blocked_assumptions,
        ),
        CaseSpec(
            case_id="case_e_agenthub_control_plane",
            title="Case E: AgentHub-only control-plane evidence",
            family="agenthub_only_extensions",
            comparison_labels=("AgentHub-only-control-plane",),
            supported_lanes=("agenthub_generic_chat",),
            steps_by_lane={
                "agenthub_generic_chat": (
                    StepSpec(
                        step_id="e1",
                        title="Inspect workflow and recovery control plane",
                        prompt=case_e_prompt_generic,
                        expected_visible_tools=("agent_workflow", "recover_agent"),
                        evidence_expectations=(
                            "agent_workflow captures non-blocking workflow state without claiming Codex or Claude parity",
                            "recover_agent is treated as a control-plane action, not a synthetic child completion",
                        ),
                        lifecycle_expectations=("workflow snapshots do not mutate adoption state on their own",),
                        result_contract_expectations=(
                            "recover_agent accepted or rejected status remains distinct from result adoption",
                        ),
                    ),
                ),
            },
            supported_conclusions=("AgentHub control-plane extensions are documented separately from parity claims.",),
            unsupported_conclusions=("This case must not be counted as a Codex or Claude regression.",),
            blocked_assumptions=task_b_blocked_assumptions,
        ),
    )


def selected_cases(
    case_ids: list[str] | None,
    *,
    case_specs_fn,
) -> list[CaseSpec]:
    if not case_ids:
        return list(case_specs_fn())
    wanted = {str(item or "").strip() for item in case_ids if str(item or "").strip()}
    return [case for case in case_specs_fn() if case.case_id in wanted]


def selected_lanes(
    lane_ids: list[str] | None,
    *,
    all_lanes: tuple[str, ...],
) -> list[str]:
    if not lane_ids:
        return list(all_lanes)
    wanted = [str(item or "").strip() for item in lane_ids if str(item or "").strip()]
    return [lane for lane in all_lanes if lane in wanted]


__all__ = [
    "CaseSpec",
    "StepSpec",
    "case_specs",
    "selected_cases",
    "selected_lanes",
]
