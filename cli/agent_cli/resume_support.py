from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

_GLOBAL_FLAG_OPTIONS = {
    "--headless",
    "--stdin",
    "--json",
    "--jsonl",
    "--serve",
    "--provider-status",
    "--resume-last",
}

_GLOBAL_VALUE_OPTIONS = {
    "--prompt",
    "--resume",
    "--resume-path",
    "--approval-policy",
    "--sandbox-mode",
    "--web-search-mode",
    "--network-access",
    "--lang",
    "--theme",
}


def has_explicit_resume_request(
    *,
    thread_id: str | None = None,
    rollout_path: str | None = None,
    resume_last: bool = False,
) -> bool:
    return bool(
        str(thread_id or "").strip() or str(rollout_path or "").strip() or bool(resume_last)
    )


def resolve_resume_request(
    runtime: Any,
    *,
    thread_id: str | None = None,
    rollout_path: str | None = None,
    resume_last: bool = False,
) -> tuple[str | None, str | None]:
    normalized_thread_id = str(thread_id or "").strip() or None
    normalized_rollout_path = str(rollout_path or "").strip() or None
    if resume_last:
        thread_store = getattr(runtime, "thread_store", None)
        if thread_store is None:
            raise RuntimeError("thread store not configured")
        getter = getattr(thread_store, "get_active_thread_id", None)
        if not callable(getter):
            raise RuntimeError("thread store does not expose active thread lookup")
        active_thread_id = str(getter() or "").strip() or None
        if active_thread_id is None:
            raise ValueError("no active thread to resume")
        return active_thread_id, None
    return normalized_thread_id, normalized_rollout_path


def apply_runtime_resume_request(
    runtime: Any,
    *,
    thread_id: str | None = None,
    rollout_path: str | None = None,
    resume_last: bool = False,
) -> Any:
    resolved_thread_id, resolved_rollout_path = resolve_resume_request(
        runtime,
        thread_id=thread_id,
        rollout_path=rollout_path,
        resume_last=resume_last,
    )
    if resolved_rollout_path:
        return runtime.resume_thread(path=resolved_rollout_path)
    if resolved_thread_id:
        return runtime.resume_thread(resolved_thread_id)
    return None


def _split_global_option_prefix(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    prefix: list[str] = []
    items = list(argv or [])
    index = 0
    while index < len(items):
        token = str(items[index] or "").strip()
        if not token:
            prefix.append(items[index])
            index += 1
            continue
        if token == "--":
            prefix.extend(items[index:])
            return prefix, []
        if token in _GLOBAL_FLAG_OPTIONS:
            prefix.append(items[index])
            index += 1
            continue
        if token in _GLOBAL_VALUE_OPTIONS:
            prefix.append(items[index])
            index += 1
            if index < len(items):
                prefix.append(items[index])
                index += 1
            continue
        if "=" in token and token.split("=", 1)[0] in _GLOBAL_VALUE_OPTIONS:
            prefix.append(items[index])
            index += 1
            continue
        if token.startswith("-"):
            break
        return prefix, items[index:]
    return prefix, items[index:]


def normalize_resume_cli_args(argv: Sequence[str] | None) -> list[str] | None:
    if argv is None:
        return None
    normalized = list(argv)
    if not normalized:
        return normalized
    prefix, remainder = _split_global_option_prefix(normalized)
    if not remainder or str(remainder[0] or "").strip().lower() != "resume":
        return normalized
    remainder = list(remainder[1:])
    thread_id = None
    if remainder and not str(remainder[0] or "").startswith("-"):
        thread_id = str(remainder[0] or "").strip() or None
        remainder = remainder[1:]
    parser = argparse.ArgumentParser(add_help=False, prog="agent_cli resume")
    parser.add_argument("--last", action="store_true")
    parser.add_argument("--path")
    parsed, remainder = parser.parse_known_args(remainder)
    rollout_path = str(parsed.path or "").strip() or None
    resume_last = bool(parsed.last)
    selected = int(bool(thread_id)) + int(bool(rollout_path)) + int(resume_last)
    if selected > 1:
        raise ValueError("resume accepts only one of <thread_id>, --path, or --last")
    if rollout_path:
        return [*prefix, "--resume-path", rollout_path, *remainder]
    if thread_id:
        return [*prefix, "--resume", thread_id, *remainder]
    return [*prefix, "--resume-last", *remainder]
