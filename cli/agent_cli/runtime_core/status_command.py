from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import __version__
from cli.agent_cli.ui.context_window_status_runtime import (
    context_remaining_percent,
    format_tokens_compact,
)
from cli.agent_cli.workspace_context import discover_project_doc_paths

CARD_INNER_WIDTH = 66


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    if text == "-":
        return default
    return text or default


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _compact_path(path: Any) -> str:
    text = _text(path)
    if not text:
        return "<none>"
    try:
        resolved = Path(text).expanduser().resolve(strict=False)
        home = Path.home().resolve(strict=False)
        try:
            relative = resolved.relative_to(home)
        except ValueError:
            return str(resolved)
        return f"~/{relative.as_posix()}"
    except OSError:
        return text


def _permission_label(policy: dict[str, Any]) -> str:
    sandbox = _text(policy.get("sandbox_mode")).lower()
    approval = _text(policy.get("approval_policy")).lower()
    network = _text(policy.get("network_access") or policy.get("network_access_enabled")).lower()
    if sandbox == "danger-full-access":
        label = "Full Access"
    elif sandbox == "workspace-write":
        label = "Workspace Write"
    elif sandbox == "read-only":
        label = "Read Only"
    else:
        label = sandbox or "Unknown"
    details: list[str] = []
    if approval and approval not in {"never", "none"}:
        details.append(f"approval {approval}")
    if network in {"enabled", "true", "1", "yes"}:
        details.append("network enabled")
    elif network in {"disabled", "false", "0", "no"}:
        details.append("network disabled")
    return f"{label} ({', '.join(details)})" if details else label


def _model_line(provider_status: dict[str, Any]) -> str:
    model = _text(
        provider_status.get("provider_model") or provider_status.get("model_key"), default="<none>"
    )
    effort = _text(provider_status.get("provider_reasoning_effort"))
    parts = []
    if effort:
        parts.append(f"reasoning {effort}")
    parts.append("summaries auto")
    return f"{model} ({', '.join(parts)})" if parts else model


def _provider_line(provider_status: dict[str, Any]) -> str:
    provider = _text(
        provider_status.get("provider_public_name")
        or provider_status.get("provider_name")
        or provider_status.get("provider_route_name"),
        default="<none>",
    )
    base_url = _text(provider_status.get("provider_base_url"))
    if base_url:
        return f"{provider} - {base_url}"
    return provider


def _instruction_docs(cwd: Any) -> str:
    try:
        docs = discover_project_doc_paths(cwd)
    except Exception:
        docs = []
    if not docs:
        return "<none>"
    labels: list[str] = []
    cwd_path = Path(str(cwd or Path.cwd())).expanduser().resolve(strict=False)
    for path in docs[:3]:
        try:
            labels.append(Path(path).resolve(strict=False).relative_to(cwd_path).as_posix())
        except (OSError, ValueError):
            labels.append(Path(path).name)
    if len(docs) > 3:
        labels.append(f"+{len(docs) - 3} more")
    return ", ".join(labels)


def _latest_status(runtime: Any) -> dict[str, Any]:
    for turn in reversed(list(getattr(runtime, "history_turns", []) or [])):
        if not isinstance(turn, dict):
            continue
        status = turn.get("status")
        if isinstance(status, dict) and status:
            return dict(status)
    return {}


def _usage_from_turn_events(runtime: Any) -> dict[str, int]:
    for turn in reversed(list(getattr(runtime, "history_turns", []) or [])):
        if not isinstance(turn, dict):
            continue
        for event in reversed(
            [item for item in list(turn.get("turn_events") or []) if isinstance(item, dict)]
        ):
            if str(event.get("type") or "").strip() != "turn.completed":
                continue
            usage = event.get("usage")
            if not isinstance(usage, dict):
                continue
            input_tokens = _int(usage.get("input_tokens"))
            output_tokens = _int(usage.get("output_tokens"))
            total_tokens = _int(usage.get("total_tokens")) or input_tokens + output_tokens
            if total_tokens or input_tokens or output_tokens:
                return {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
    return {}


def _token_usage_line(runtime: Any, latest_status: dict[str, Any]) -> str:
    usage = _usage_from_turn_events(runtime)
    input_tokens = _int(latest_status.get("input_tokens")) or usage.get("input_tokens", 0)
    output_tokens = _int(latest_status.get("output_tokens")) or usage.get("output_tokens", 0)
    total_tokens = (
        _int(latest_status.get("total_tokens"))
        or usage.get("total_tokens", 0)
        or input_tokens + output_tokens
    )
    if total_tokens <= 0:
        return "not available"
    return (
        f"{format_tokens_compact(total_tokens)} total  "
        f"({format_tokens_compact(input_tokens)} input + {format_tokens_compact(output_tokens)} output)"
    )


def _context_window_line(provider_status: dict[str, Any], latest_status: dict[str, Any]) -> str:
    used = _int(
        latest_status.get("context_window_used_tokens") or latest_status.get("total_tokens")
    )
    window = _int(
        latest_status.get("context_window_tokens")
        or latest_status.get("model_context_window")
        or provider_status.get("model_context_window")
        or provider_status.get("provider_model_context_window")
    )
    if window <= 0:
        return "not available"
    percent = _int(latest_status.get("context_window_remaining_percent"))
    if not str(latest_status.get("context_window_remaining_percent") or "").strip():
        computed = context_remaining_percent(used_tokens=used, context_window=window)
        percent = 100 if computed is None else computed
    return f"{percent}% left ({format_tokens_compact(used)} used / {format_tokens_compact(window)})"


def _forked_from(runtime: Any) -> str:
    for attr in ("forked_from_thread_id", "parent_thread_id", "source_thread_id"):
        value = _text(getattr(runtime, attr, ""))
        if value:
            return value
    return "<none>"


def _row(label: str, value: str) -> str:
    return f"  {label:<20} {value}"


def _wrap_line(text: str, *, width: int = CARD_INNER_WIDTH) -> list[str]:
    remaining = str(text or "")
    if not remaining:
        return [""]
    continuation_indent = ""
    if remaining.startswith("  ") and ":" in remaining[:24]:
        continuation_indent = " " * 23
    elif remaining.startswith(" "):
        continuation_indent = " " * (len(remaining) - len(remaining.lstrip(" ")))
    lines: list[str] = []
    while len(remaining) > width:
        split_at = remaining.rfind(" ", 0, width + 1)
        if split_at <= len(continuation_indent):
            split_at = width
        lines.append(remaining[:split_at].rstrip())
        remaining = f"{continuation_indent}{remaining[split_at:].lstrip()}"
    lines.append(remaining)
    return lines


def _box(lines: list[str]) -> str:
    rendered = ["╭" + "─" * CARD_INNER_WIDTH + "╮"]
    for line in lines:
        for wrapped in _wrap_line(line):
            rendered.append(f"│{wrapped:<{CARD_INNER_WIDTH}}│")
    rendered.append("╰" + "─" * CARD_INNER_WIDTH + "╯")
    return "\n".join(rendered)


def status_card_text(runtime: Any) -> str:
    provider_status = dict(getattr(runtime.agent, "provider_status", lambda: {})() or {})
    runtime_policy = dict(runtime.runtime_policy_status() or {})
    latest_status = _latest_status(runtime)
    cwd = getattr(runtime, "cwd", "") or Path.cwd()
    collaboration_mode = _text(
        getattr(runtime, "collaboration_mode", ""), default="default"
    ).title()
    thread_id = _text(getattr(runtime, "thread_id", ""), default="<none>")
    lines = [
        f"  >_ AgentHub (v{__version__})",
        "",
        _row("Model:", _model_line(provider_status)),
        _row("Model provider:", _provider_line(provider_status)),
        _row("Directory:", _compact_path(cwd)),
        _row("Permissions:", _permission_label(runtime_policy)),
        _row("Agents.md:", _instruction_docs(cwd)),
        _row("Collaboration mode:", collaboration_mode),
        _row("Session:", thread_id),
        _row("Forked from:", _forked_from(runtime)),
        "",
        _row("Token usage:", _token_usage_line(runtime, latest_status)),
        _row("Context window:", _context_window_line(provider_status, latest_status)),
        _row("Limits:", "not available for this account"),
    ]
    return _box(lines)
