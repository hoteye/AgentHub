from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from cli.agent_cli.ui.transcript_history import TranscriptEntry

logger = logging.getLogger(__name__)

_ESSENTIAL_KINDS = {"user", "assistant", "commentary", "reasoning", "system", "separator"}
_ESSENTIAL_LAYERS = {"final", "commentary", "reasoning", "system", "separator"}
_NOISY_RENDER_MODES = {
    "prompt_tool_group",
    "tool_command",
    "tool_mcp",
    "todo_list",
    "web_search",
}


@dataclass(slots=True)
class _Budget:
    lines: int = 0
    chars: int = 0


def resolve_anchor_turn_index(turns: list[Any], state: Any | None) -> int:
    if not turns:
        return 0
    if state is None:
        return 0
    start_entry_id = str(getattr(state, "start_entry_id", "") or "").strip()
    if start_entry_id:
        for index, turn in enumerate(turns):
            if str(getattr(turn, "start_entry_id", "") or "").strip() == start_entry_id:
                return index
    start_entry_index = max(0, int(getattr(state, "start_entry_index", 0) or 0))
    candidate = 0
    for index, turn in enumerate(turns):
        if int(getattr(turn, "start_entry_index", 0) or 0) <= start_entry_index:
            candidate = index
        else:
            break
    return candidate


def compact_turn_process_noise(turn: Any) -> Any:
    kept_entries: list[TranscriptEntry] = []
    noisy_entries = 0
    for entry in list(getattr(turn, "entries", []) or []):
        if _should_preserve_entry(entry):
            kept_entries.append(entry)
        else:
            noisy_entries += 1
    if noisy_entries <= 0:
        return turn
    summary_entry = TranscriptEntry(
        kind="system",
        layer="system",
        lines=[
            "• Turn activity hidden",
            f"  └ collapsed {noisy_entries} process event{'s' if noisy_entries != 1 else ''}",
        ],
        status="info",
        entry_id=f"prompt-turn-hidden:{getattr(turn, 'start_entry_id', None) or getattr(turn, 'start_entry_index', 0)}:{noisy_entries}",
        group_key="prompt_turn_hidden",
        search_text="Turn activity hidden",
        render_mode="plain",
    )
    if kept_entries:
        insert_at = 1 if kept_entries[0].kind == "user" else 0
        kept_entries = kept_entries[:insert_at] + [summary_entry] + kept_entries[insert_at:]
    else:
        kept_entries = [summary_entry]
    return type(turn)(
        entries=kept_entries,
        start_entry_index=getattr(turn, "start_entry_index", 0),
        start_entry_id=getattr(turn, "start_entry_id", None),
    )


def build_hidden_summary_entry(*, collapsed_turns: int, dropped_turns: int) -> TranscriptEntry:
    lines = ["• Earlier transcript hidden"]
    if collapsed_turns > 0:
        lines.append(f"  └ collapsed {collapsed_turns} older turn{'s' if collapsed_turns != 1 else ''}")
    if dropped_turns > 0:
        lines.append(f"  └ dropped {dropped_turns} older turn{'s' if dropped_turns != 1 else ''} from prompt window")
    lines.append("  └ Ctrl+O view full transcript · Ctrl+L clear")
    return TranscriptEntry(
        kind="system",
        layer="system",
        lines=lines,
        status="info",
        entry_id=f"prompt-hidden:{collapsed_turns}:{dropped_turns}",
        group_key="prompt_hidden_summary",
        search_text="Earlier transcript hidden",
        render_mode="plain",
    )


def entries_for_turns(turns: list[Any]) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []
    for turn in list(turns or []):
        entries.extend(list(getattr(turn, "entries", []) or []))
    return entries


def entry_id(entry: TranscriptEntry | None) -> str | None:
    if entry is None:
        return None
    value = str(entry.entry_id or "").strip()
    return value or None


def limit_entries(
    entries: list[TranscriptEntry],
    *,
    max_lines: int,
    max_chars: int,
) -> list[TranscriptEntry]:
    limited: list[TranscriptEntry] = []
    line_total = 0
    char_total = 0
    for entry in list(entries or []):
        next_lines = entry_line_count(entry)
        next_chars = entry_char_count(entry)
        if limited and (line_total + next_lines > max_lines or char_total + next_chars > max_chars):
            break
        limited.append(entry)
        line_total += next_lines
        char_total += next_chars
    if limited:
        return limited
    fallback = list(entries[:1])
    if fallback:
        entry = fallback[0]
        logger.debug(
            "prompt transcript window kept a single over-budget entry: "
            "entry_id=%s lines=%s chars=%s limits=(%s,%s)",
            entry_id(entry),
            entry_line_count(entry),
            entry_char_count(entry),
            max_lines,
            max_chars,
        )
    return fallback


def budget_for_entries(entries: list[TranscriptEntry]) -> _Budget:
    return _Budget(
        lines=sum(entry_line_count(entry) for entry in list(entries or [])),
        chars=sum(entry_char_count(entry) for entry in list(entries or [])),
    )


def sum_budgets(budgets: list[_Budget]) -> _Budget:
    return _Budget(
        lines=sum(int(budget.lines) for budget in list(budgets or [])),
        chars=sum(int(budget.chars) for budget in list(budgets or [])),
    )


def budget_add(left: _Budget, right: _Budget) -> _Budget:
    return _Budget(lines=int(left.lines) + int(right.lines), chars=int(left.chars) + int(right.chars))


def budget_subtract(left: _Budget, right: _Budget) -> _Budget:
    return _Budget(lines=int(left.lines) - int(right.lines), chars=int(left.chars) - int(right.chars))


def budget_over_limit(budget: _Budget, *, max_lines: int, max_chars: int) -> bool:
    return int(budget.lines) > max_lines or int(budget.chars) > max_chars


def _should_preserve_entry(entry: TranscriptEntry) -> bool:
    if entry.kind in _ESSENTIAL_KINDS:
        return True
    if entry.layer in _ESSENTIAL_LAYERS:
        return True
    status = str(entry.status or "").strip().lower()
    if status in {"error", "failed"}:
        return True
    if entry.render_mode in {"tool_error", "error"}:
        return True
    if entry.kind == "activity" and entry.render_mode not in _NOISY_RENDER_MODES:
        header = str(entry.lines[0] or "").lower() if entry.lines else ""
        if any(token in header for token in ("error", "failed", "denied", "blocked")):
            return True
    return False


def entry_line_count(entry: TranscriptEntry) -> int:
    return len(list(entry.lines or []))


def entry_char_count(entry: TranscriptEntry) -> int:
    return sum(len(str(line or "")) + 1 for line in list(entry.lines or []))
