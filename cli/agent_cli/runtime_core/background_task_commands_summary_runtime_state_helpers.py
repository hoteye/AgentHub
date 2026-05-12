from __future__ import annotations

import re

_KV_PATTERN = re.compile(r"\|\s*([A-Za-z0-9_]+)=([^|]+)")


def line_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _KV_PATTERN.finditer(str(line or "")):
        key = str(match.group(1) or "").strip().lower()
        value = str(match.group(2) or "").strip().lower()
        if key:
            values[key] = value
    return values


def line_pipe_parts(line: str) -> list[str]:
    return [str(part or "").strip().lower() for part in str(line or "").split("|")]


def delegated_result_state_counts(lines: list[str]) -> tuple[int, int, int]:
    returned = 0
    adopted = 0
    pending_review = 0
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        values = line_key_values(line)
        parts = line_pipe_parts(line)
        status = parts[2] if len(parts) > 2 else values.get("status", "")
        completion = values.get("completion", "") or values.get("completion_state", "")
        result_state = values.get("result_state", "")
        if result_state == "adopted" or completion == "adopted":
            adopted += 1
            continue
        if result_state == "pending_review" or completion in {"ready_to_adopt", "awaiting_join", "pending_review"}:
            pending_review += 1
            continue
        if status == "completed" and completion:
            returned += 1
    return returned, adopted, pending_review


def background_result_state_counts(lines: list[str]) -> tuple[int, int, int]:
    returned = 0
    adopted = 0
    pending_review = 0
    for raw_line in lines:
        line = str(raw_line or "").strip().lower()
        if not line:
            continue
        values = line_key_values(line)
        parts = line_pipe_parts(line)
        status = parts[2] if len(parts) > 2 else values.get("status", "")
        result_state = values.get("result_state", "")
        terminal_state = values.get("terminal_state", "")
        notify = values.get("notify", "")
        review = values.get("review", "") or values.get("final_apply_state", "")
        completion_state = values.get("completion_state", "")
        if result_state == "adopted" or notify == "foreground_adopted":
            adopted += 1
            continue
        if review == "applied":
            adopted += 1
            continue
        if result_state == "pending_review":
            pending_review += 1
            continue
        if completion_state in {"ready_to_adopt", "awaiting_join", "pending_review"}:
            pending_review += 1
            continue
        if review in {"pending", "blocked"}:
            pending_review += 1
            continue
        if status == "completed" or terminal_state == "completed":
            returned += 1
    return returned, adopted, pending_review


def orchestration_state_counts(lines: list[str]) -> tuple[int, int, int, int]:
    ready = 0
    running = 0
    blocked = 0
    review_pending = 0
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        parts = line_pipe_parts(line)
        if not parts:
            continue
        if not parts[0].lstrip("- ").startswith("orchestration"):
            continue
        values = line_key_values(line)
        status = values.get("workflow", "") or (parts[2] if len(parts) > 2 else "")
        phase = values.get("phase", "")
        review_reason = values.get("review_reason", "") or values.get("reason", "")
        latest_acceptance = values.get("latest_acceptance", "")
        current = values.get("current", "")
        acceptance_decision = latest_acceptance.rsplit(":", 1)[-1] if ":" in latest_acceptance else latest_acceptance
        if status == "ready":
            ready += 1
        if status == "running":
            running += 1
        if status == "blocked":
            blocked += 1
        if (
            "review" in phase
            or "review" in review_reason
            or current.endswith(":result_ready")
            or acceptance_decision in {"block", "rework", "reject"}
        ):
            review_pending += 1
    return ready, running, blocked, review_pending


def workflow_policy_surface_counts(lines: list[str]) -> tuple[int, int, int]:
    denied = 0
    rewritten = 0
    checked = 0
    for raw_line in list(lines or []):
        line = str(raw_line or "").strip()
        if not line:
            continue
        values = line_key_values(line)
        if not values:
            continue
        policy_hint = str(
            values.get("policy")
            or values.get("policy_state")
            or values.get("command_policy")
            or ""
        ).strip().lower()
        denied_text = str(values.get("policy_denied") or "").strip().lower()
        rewritten_text = str(values.get("policy_rewrite") or values.get("policy_rewritten") or "").strip().lower()
        if denied_text in {"1", "true", "yes", "on"} or any(token in policy_hint for token in ("denied", "blocked")):
            denied += 1
            continue
        if rewritten_text in {"1", "true", "yes", "on"} or "rewrite" in policy_hint:
            rewritten += 1
            continue
        command_policies_count = str(values.get("command_policies_count") or "").strip().lower()
        command_policies_present = command_policies_count not in {"", "0", "false", "none", "null", "-"}
        if (
            policy_hint
            and any(token in policy_hint for token in ("checked", "allow", "ok", "pass"))
        ) or command_policies_present:
            checked += 1
    return denied, rewritten, checked
