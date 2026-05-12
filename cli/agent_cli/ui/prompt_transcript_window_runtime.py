from __future__ import annotations

from dataclasses import dataclass
import logging

from cli.agent_cli.ui.prompt_transcript_window_helpers_runtime import (
    _Budget,
    budget_add as _budget_add,
    budget_for_entries as _budget_for_entries,
    budget_over_limit as _budget_over_limit,
    budget_subtract as _budget_subtract,
    build_hidden_summary_entry,
    compact_turn_process_noise,
    entries_for_turns as _entries_for_turns,
    entry_id as _entry_id,
    limit_entries as _limit_entries,
    resolve_anchor_turn_index,
    sum_budgets as _sum_budgets,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry

logger = logging.getLogger(__name__)

PROMPT_RECENT_TURNS_ALWAYS_VISIBLE = 6
PROMPT_WINDOW_TARGET_TURNS = 10
PROMPT_TRANSCRIPT_MAX_LINES = 400
PROMPT_TRANSCRIPT_MAX_CHARS = 40000
PROMPT_WINDOW_ADVANCE_STEP_TURNS = 2

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
class PromptTranscriptWindowConfig:
    recent_turns_always_visible: int = PROMPT_RECENT_TURNS_ALWAYS_VISIBLE
    target_turns: int = PROMPT_WINDOW_TARGET_TURNS
    max_lines: int = PROMPT_TRANSCRIPT_MAX_LINES
    max_chars: int = PROMPT_TRANSCRIPT_MAX_CHARS
    advance_step_turns: int = PROMPT_WINDOW_ADVANCE_STEP_TURNS


@dataclass(slots=True)
class PromptTranscriptWindowState:
    start_entry_id: str | None = None
    start_entry_index: int = 0


@dataclass(slots=True)
class PromptTranscriptWindowResult:
    entries: list[TranscriptEntry]
    window_state: PromptTranscriptWindowState
    hidden_summary_entry: TranscriptEntry | None = None
    hidden_summary_turns: int = 0
    dropped_turns: int = 0

    @property
    def state(self) -> PromptTranscriptWindowState:
        return self.window_state


@dataclass(slots=True)
class _PromptTurn:
    entries: list[TranscriptEntry]
    start_entry_index: int
    start_entry_id: str | None


@dataclass(slots=True)
class _VisibleWindow:
    prefix_entries: list[TranscriptEntry]
    turns: list[_PromptTurn]
    collapsed_turns: int
    dropped_turns: int


def build_prompt_transcript_window(
    entries: list[TranscriptEntry],
    *,
    state: PromptTranscriptWindowState | None = None,
    config: PromptTranscriptWindowConfig | None = None,
    recent_turns_always_visible: int | None = None,
    target_turns: int | None = None,
    max_lines: int | None = None,
    max_chars: int | None = None,
    advance_step_turns: int | None = None,
) -> PromptTranscriptWindowResult:
    window_config = _resolve_config(
        config=config,
        recent_turns_always_visible=recent_turns_always_visible,
        target_turns=target_turns,
        max_lines=max_lines,
        max_chars=max_chars,
        advance_step_turns=advance_step_turns,
    )
    current_state = state or PromptTranscriptWindowState()
    prefix_entries, turns = split_prompt_turns(entries)
    if not turns:
        bounded_entries = _limit_entries(
            list(prefix_entries),
            max_lines=window_config.max_lines,
            max_chars=window_config.max_chars,
        )
        return PromptTranscriptWindowResult(
            entries=bounded_entries,
            window_state=_next_state_for_entries(current_state, bounded_entries, default_index=0),
        )

    window = _select_visible_window(turns=turns, prefix_entries=prefix_entries, state=current_state, config=window_config)
    visible_entries = _materialize_window(window)
    hidden_entry = None
    hidden_turns = window.collapsed_turns + window.dropped_turns
    if hidden_turns > 0:
        hidden_entry = build_hidden_summary_entry(
            collapsed_turns=window.collapsed_turns,
            dropped_turns=window.dropped_turns,
        )
        visible_entries = [hidden_entry, *visible_entries]
    next_state = _next_state_for_window(window, current_state)
    return PromptTranscriptWindowResult(
        entries=visible_entries,
        window_state=next_state,
        hidden_summary_entry=hidden_entry,
        hidden_summary_turns=hidden_turns,
        dropped_turns=window.dropped_turns,
    )


def split_prompt_turns(entries: list[TranscriptEntry]) -> tuple[list[TranscriptEntry], list[_PromptTurn]]:
    prefix_entries: list[TranscriptEntry] = []
    turns: list[_PromptTurn] = []
    current_entries: list[TranscriptEntry] = []
    current_start_index = 0
    current_start_id: str | None = None

    for index, entry in enumerate(list(entries or [])):
        if entry.kind == "user":
            if current_entries:
                turns.append(
                    _PromptTurn(
                        entries=list(current_entries),
                        start_entry_index=current_start_index,
                        start_entry_id=current_start_id,
                    )
                )
                current_entries = []
            current_start_index = index
            current_start_id = _entry_id(entry)
            current_entries.append(entry)
            continue
        if current_entries:
            current_entries.append(entry)
        else:
            prefix_entries.append(entry)
    if current_entries:
        turns.append(
            _PromptTurn(
                entries=list(current_entries),
                start_entry_index=current_start_index,
                start_entry_id=current_start_id,
            )
        )
    return prefix_entries, turns


def _resolve_config(
    *,
    config: PromptTranscriptWindowConfig | None,
    recent_turns_always_visible: int | None,
    target_turns: int | None,
    max_lines: int | None,
    max_chars: int | None,
    advance_step_turns: int | None,
) -> PromptTranscriptWindowConfig:
    if config is not None:
        base = PromptTranscriptWindowConfig(
            recent_turns_always_visible=config.recent_turns_always_visible,
            target_turns=config.target_turns,
            max_lines=config.max_lines,
            max_chars=config.max_chars,
            advance_step_turns=config.advance_step_turns,
        )
    else:
        base = PromptTranscriptWindowConfig()
    if recent_turns_always_visible is not None:
        base.recent_turns_always_visible = int(recent_turns_always_visible)
    if target_turns is not None:
        base.target_turns = int(target_turns)
    if max_lines is not None:
        base.max_lines = int(max_lines)
    if max_chars is not None:
        base.max_chars = int(max_chars)
    if advance_step_turns is not None:
        base.advance_step_turns = int(advance_step_turns)
    base.recent_turns_always_visible = max(1, int(base.recent_turns_always_visible or 0))
    base.target_turns = max(base.recent_turns_always_visible, int(base.target_turns or 0))
    base.max_lines = max(1, int(base.max_lines or 0))
    base.max_chars = max(1, int(base.max_chars or 0))
    base.advance_step_turns = max(1, int(base.advance_step_turns or 0))
    return base


def _select_visible_window(
    *,
    turns: list[_PromptTurn],
    prefix_entries: list[TranscriptEntry],
    state: PromptTranscriptWindowState,
    config: PromptTranscriptWindowConfig,
) -> _VisibleWindow:
    desired_start_turn = max(0, len(turns) - config.target_turns)
    anchor_start_turn = resolve_anchor_turn_index(turns, state)
    start_turn = anchor_start_turn
    if desired_start_turn - anchor_start_turn >= config.advance_step_turns:
        start_turn = desired_start_turn
    max_start_for_recent = max(0, len(turns) - config.recent_turns_always_visible)
    start_turn = min(max(start_turn, 0), max_start_for_recent)
    collapsed_turns = start_turn
    dropped_turns = 0
    visible_turns = list(turns[start_turn:])
    visible_prefix_entries = list(prefix_entries) if start_turn == 0 else []
    prefix_budget = _budget_for_entries(visible_prefix_entries)
    turn_budgets = [_budget_for_entries(turn.entries) for turn in visible_turns]
    total_budget = _sum_budgets([prefix_budget, *turn_budgets])

    while True:
        if not _budget_over_limit(total_budget, max_lines=config.max_lines, max_chars=config.max_chars):
            return _VisibleWindow(
                prefix_entries=visible_prefix_entries,
                turns=visible_turns,
                collapsed_turns=collapsed_turns,
                dropped_turns=dropped_turns,
            )
        oldest_removable_turn = len(visible_turns) - config.recent_turns_always_visible
        if oldest_removable_turn <= 0:
            break
        total_budget = _budget_subtract(total_budget, turn_budgets[0])
        visible_turns = visible_turns[1:]
        turn_budgets = turn_budgets[1:]
        visible_prefix_entries = []
        prefix_budget = _Budget()
        dropped_turns += 1

    compacted_turns = [compact_turn_process_noise(turn) for turn in visible_turns]
    compacted_budgets = [_budget_for_entries(turn.entries) for turn in compacted_turns]
    compacted_total_budget = _sum_budgets([prefix_budget, *compacted_budgets])
    if not _budget_over_limit(compacted_total_budget, max_lines=config.max_lines, max_chars=config.max_chars):
        return _VisibleWindow(
            prefix_entries=visible_prefix_entries,
            turns=compacted_turns,
            collapsed_turns=collapsed_turns,
            dropped_turns=dropped_turns,
        )

    progressive_turns = list(visible_turns)
    progressive_budgets = list(turn_budgets)
    progressive_total_budget = total_budget
    for index in range(len(progressive_turns)):
        progressive_turns[index] = compacted_turns[index]
        progressive_total_budget = _budget_add(
            _budget_subtract(progressive_total_budget, progressive_budgets[index]),
            compacted_budgets[index],
        )
        progressive_budgets[index] = compacted_budgets[index]
        if not _budget_over_limit(progressive_total_budget, max_lines=config.max_lines, max_chars=config.max_chars):
            return _VisibleWindow(
                prefix_entries=visible_prefix_entries,
                turns=progressive_turns,
                collapsed_turns=collapsed_turns,
                dropped_turns=dropped_turns,
            )

    if progressive_turns:
        first_turn = progressive_turns[0]
        logger.debug(
            "prompt transcript window preserved an over-budget recent turn after compaction: "
            "start_entry_id=%s start_entry_index=%s visible_turns=%s lines=%s chars=%s limits=(%s,%s)",
            first_turn.start_entry_id,
            first_turn.start_entry_index,
            len(progressive_turns),
            progressive_total_budget.lines,
            progressive_total_budget.chars,
            config.max_lines,
            config.max_chars,
        )

    return _VisibleWindow(
        prefix_entries=visible_prefix_entries,
        turns=progressive_turns,
        collapsed_turns=collapsed_turns,
        dropped_turns=dropped_turns,
    )


def _materialize_window(window: _VisibleWindow) -> list[TranscriptEntry]:
    return list(window.prefix_entries) + _entries_for_turns(window.turns)


def _next_state_for_window(
    window: _VisibleWindow,
    previous_state: PromptTranscriptWindowState,
) -> PromptTranscriptWindowState:
    if window.turns:
        return PromptTranscriptWindowState(
            start_entry_id=window.turns[0].start_entry_id,
            start_entry_index=window.turns[0].start_entry_index,
        )
    return _next_state_for_entries(previous_state, window.prefix_entries, default_index=0)


def _next_state_for_entries(
    previous_state: PromptTranscriptWindowState,
    entries: list[TranscriptEntry],
    *,
    default_index: int,
) -> PromptTranscriptWindowState:
    first_entry = entries[0] if entries else None
    if first_entry is None:
        return PromptTranscriptWindowState(
            start_entry_id=previous_state.start_entry_id,
            start_entry_index=max(0, int(previous_state.start_entry_index or default_index)),
        )
    return PromptTranscriptWindowState(
        start_entry_id=_entry_id(first_entry),
        start_entry_index=max(0, int(default_index)),
    )
