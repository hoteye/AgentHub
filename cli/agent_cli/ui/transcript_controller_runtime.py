from __future__ import annotations

from dataclasses import replace
from time import time

from textual.css.query import NoMatches

from cli.agent_cli.ui.prompt_transcript_window_runtime import (
    PromptTranscriptWindowState,
    build_prompt_transcript_window,
)
from cli.agent_cli.ui.transcript_browsing_runtime import (
    TranscriptBrowsingState,
    refresh_transcript_browsing_state,
)
from cli.agent_cli.ui.transcript_controller_viewport_runtime import (
    restore_transcript_viewport,
    transcript_render_width,
    transcript_scroll_offset,
    transcript_should_follow_bottom,
)
from cli.agent_cli.ui.transcript_formatting import (
    merge_exploration_detail_items,
    parse_exploration_detail_item,
    render_exploration_entry_lines,
)
from cli.agent_cli.ui.transcript_history import (
    TranscriptEntry,
    blank_entry,
    final_separator_entry,
    render_transcript_entries,
    render_transcript_visual_entries,
)
from cli.agent_cli.ui.transcript_screen_projection_runtime import entries_for_screen
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from cli.agent_cli.ui.widgets import TranscriptArea


def scope_activity_key(controller, activity_key: str | None) -> str | None:
    key = str(activity_key or "").strip()
    if not key:
        return None
    return f"{controller._active_transcript_turn_key}:{key}"


def scope_transcript_entry(controller, entry: TranscriptEntry) -> TranscriptEntry:
    scoped_key = controller._scope_activity_key(entry.activity_key)
    if scoped_key == entry.activity_key:
        return entry
    return replace(entry, activity_key=scoped_key)


def append_transcript_lines(controller, lines: list[str]) -> None:
    controller._transcript_lines.extend(str(line) for line in lines)
    try:
        controller._sync_transcript()
    except NoMatches:
        return


def append_transcript_entry(
    controller, entry: TranscriptEntry, *, leading_blank: bool = False
) -> None:
    if controller._should_insert_final_separator(entry):
        controller._append_transcript_entry_raw(
            final_separator_entry(controller._final_separator_label()),
            leading_blank=False,
        )
        controller._live_turn_final_separator_emitted = True
    controller._append_transcript_entry_raw(entry, leading_blank=leading_blank)


def append_transcript_entry_raw(
    controller, entry: TranscriptEntry, *, leading_blank: bool = False
) -> None:
    if leading_blank and controller._transcript_entries:
        controller._transcript_entries.append(prepare_transcript_entry(controller, blank_entry()))
    replacement_index = controller._replacement_index_for_entry(entry)
    if replacement_index is not None:
        previous = controller._transcript_entries[replacement_index]
        controller._transcript_entries[replacement_index] = prepare_transcript_entry(
            controller,
            entry,
            previous=previous,
        )
    else:
        prepared_entry = prepare_transcript_entry(controller, entry)
        merged = controller._merge_with_latest_exploration_entry(prepared_entry)
        if merged is None:
            controller._transcript_entries.append(prepared_entry)
        else:
            merge_index, merged_entry = merged
            controller._transcript_entries[merge_index] = merged_entry
    controller._transcript_lines = render_transcript_entries(controller._transcript_entries)
    try:
        controller._sync_transcript()
    except NoMatches:
        return


def replacement_index_for_entry(controller, entry: TranscriptEntry) -> int | None:
    if not entry.activity_key:
        return None
    for index in range(len(controller._transcript_entries) - 1, -1, -1):
        candidate = controller._transcript_entries[index]
        if candidate.activity_key == entry.activity_key:
            return index
    return None


def is_exploration_entry(entry: TranscriptEntry) -> bool:
    if entry.kind != "activity" or not entry.lines:
        return False
    header = str(entry.lines[0] or "").strip()
    return header in {"• Exploring", "• Explored"}


def exploration_detail_items(entry: TranscriptEntry) -> list[tuple[str, str]]:
    if entry.exploration_details:
        return list(entry.exploration_details)
    details: list[tuple[str, str]] = []
    for raw_line in entry.lines[1:]:
        line = str(raw_line or "")
        if line.startswith("  └ "):
            detail_text = line[4:].strip()
        elif line.startswith("    "):
            detail_text = line[4:].strip()
        else:
            detail_text = line.strip()
        detail = parse_exploration_detail_item(detail_text)
        if detail is not None:
            details = merge_exploration_detail_items(details, detail)
    return details


def append_exploration_detail(
    details: list[tuple[str, str]],
    detail: tuple[str, str],
) -> list[tuple[str, str]]:
    return merge_exploration_detail_items(details, detail)


def build_exploration_entry(
    base_entry: TranscriptEntry,
    *,
    details: list[tuple[str, str]],
    status: str,
) -> TranscriptEntry:
    lines = render_exploration_entry_lines(details, status=status)
    return replace(base_entry, lines=lines, status=status, exploration_details=list(details))


def merge_with_latest_exploration_entry(
    controller, entry: TranscriptEntry
) -> tuple[int, TranscriptEntry] | None:
    if not controller._is_exploration_entry(entry):
        return None
    for index in range(len(controller._transcript_entries) - 1, -1, -1):
        candidate = controller._transcript_entries[index]
        if candidate.kind == "blank":
            break
        if not controller._is_exploration_entry(candidate):
            return None
        candidate_details = controller._exploration_detail_items(candidate)
        for detail in controller._exploration_detail_items(entry):
            candidate_details = controller._append_exploration_detail(candidate_details, detail)
        status = entry.status if entry.status != "running" else candidate.status
        merged = controller._build_exploration_entry(
            candidate, details=candidate_details, status=status
        )
        return index, merged
    return None


def prepare_transcript_entry(
    controller,
    entry: TranscriptEntry,
    *,
    previous: TranscriptEntry | None = None,
) -> TranscriptEntry:
    entry_id = str(entry.entry_id or "").strip()
    created_at = float(entry.created_at or 0.0)
    if previous is not None:
        if not entry_id:
            entry_id = str(previous.entry_id or "").strip()
        if not created_at:
            created_at = float(previous.created_at or 0.0)
    if not entry_id:
        serial = int(getattr(controller, "_transcript_entry_serial", 0) or 0) + 1
        controller._transcript_entry_serial = serial
        entry_id = f"entry:{serial}"
    if not created_at:
        created_at = time()
    group_key = (
        str(
            entry.group_key
            or entry.activity_key
            or f"{entry.kind}:{entry.layer}:{entry.render_mode}"
        ).strip()
        or None
    )
    search_text = str(entry.search_text or "").strip() or entry_search_text(entry)
    return replace(
        entry,
        entry_id=entry_id,
        created_at=created_at,
        group_key=group_key,
        search_text=search_text,
        child_entry_ids=tuple(entry.child_entry_ids or ()),
    )


def entry_search_text(entry: TranscriptEntry) -> str:
    parts: list[str] = []
    if entry.raw_content:
        parts.append(str(entry.raw_content))
    if entry.lines:
        parts.extend(str(line) for line in entry.lines)
    return "\n".join(part for part in parts if str(part).strip()).strip()


def snapshot_transcript_entry(entry: TranscriptEntry) -> TranscriptEntry:
    return replace(
        entry,
        lines=list(entry.lines),
        exploration_details=list(entry.exploration_details) if entry.exploration_details else None,
        expanded_lines=list(entry.expanded_lines) if entry.expanded_lines else None,
        child_entry_ids=tuple(entry.child_entry_ids or ()),
    )


def snapshot_transcript_entries(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    return [snapshot_transcript_entry(entry) for entry in list(entries or [])]


def sync_transcript(controller) -> None:
    main_log = controller.query_one("#main_log", TranscriptArea)
    screen_mode = str(getattr(controller, "_screen_mode", "prompt") or "prompt").strip().lower()
    try:
        transcript_log = controller.query_one("#transcript_log", TranscriptVirtualList)
    except NoMatches:
        transcript_log = None
    render_width = controller._transcript_render_width(main_log)
    controller._last_transcript_render_width = render_width
    if screen_mode == "transcript":
        controller._transcript_lines = []
        main_log.load_transcript([])
        snapshot_entries = getattr(controller, "_transcript_screen_snapshot_entries", None) or []
        browsing_state = refresh_transcript_browsing_state(
            snapshot_entries,
            getattr(controller, "_transcript_browsing_state", None),
        )
        controller._transcript_browsing_state = browsing_state
        if transcript_log is not None:
            controller._last_transcript_virtual_width = transcript_render_width(transcript_log)
            transcript_log.load_entries(
                snapshot_entries,
                theme=controller._theme,
                console=controller.console,
            )
            transcript_log.set_highlighted_entry_ids(
                set(browsing_state.match_entry_ids),
                browsing_state.active_match_entry_id,
            )
            if browsing_state.active_match_entry_id:
                transcript_log.scroll_to_entry(browsing_state.active_match_entry_id)
        return
    follow_bottom = True
    preserved_scroll: tuple[int, int] | None = None
    if screen_mode != "transcript":
        force_follow = getattr(main_log, "_force_follow_bottom", False)
        if force_follow:
            follow_bottom = True
            main_log._force_follow_bottom = False
        else:
            follow_bottom = transcript_should_follow_bottom(main_log)
        if not follow_bottom:
            preserved_scroll = transcript_scroll_offset(main_log)
    prompt_entries = entries_for_screen(controller._transcript_entries, screen_mode="prompt")
    prompt_entries = prompt_entries_after_clear_boundary(controller, prompt_entries)
    window_result = build_prompt_transcript_window(
        prompt_entries,
        state=getattr(controller, "_prompt_transcript_window_state", None),
    )
    controller._prompt_transcript_window_state = window_result.state
    render_entries = window_result.entries
    rendered = render_transcript_visual_entries(
        render_entries,
        width=render_width,
        theme=controller._theme,
        console=controller.console,
    )
    controller._transcript_lines = rendered.lines
    main_log.load_transcript(rendered.lines, line_styles=rendered.line_styles)
    if not isinstance(
        getattr(controller, "_transcript_browsing_state", None), TranscriptBrowsingState
    ):
        controller._transcript_browsing_state = TranscriptBrowsingState()
    if screen_mode != "transcript":
        if follow_bottom:
            document_end = main_log.document.end
            main_log.move_cursor(document_end)
        elif preserved_scroll is not None:
            restore_transcript_viewport(
                main_log,
                scroll_x=preserved_scroll[0],
                scroll_y=preserved_scroll[1],
            )


def refresh_transcript_rendering(controller) -> None:
    should_refresh = False
    try:
        main_log = controller.query_one("#main_log", TranscriptArea)
    except NoMatches:
        main_log = None
    if main_log is not None:
        render_width = controller._transcript_render_width(main_log)
        if render_width != controller._last_transcript_render_width:
            should_refresh = True
    screen_mode = str(getattr(controller, "_screen_mode", "prompt") or "prompt").strip().lower()
    try:
        transcript_log = controller.query_one("#transcript_log", TranscriptVirtualList)
    except NoMatches:
        transcript_log = None
    if transcript_log is not None and screen_mode == "transcript":
        render_width = transcript_render_width(transcript_log)
        cached_width = int(getattr(controller, "_last_transcript_virtual_width", 0) or 0)
        if render_width != cached_width:
            controller._last_transcript_virtual_width = render_width
            should_refresh = True
    if should_refresh:
        controller._sync_transcript()


def prompt_entries_after_clear_boundary(
    controller, entries: list[TranscriptEntry]
) -> list[TranscriptEntry]:
    boundary_id = str(
        getattr(controller, "_prompt_transcript_clear_boundary_entry_id", "") or ""
    ).strip()
    if not boundary_id:
        return list(entries or [])
    filtered: list[TranscriptEntry] = []
    passed_boundary = False
    for entry in list(entries or []):
        if passed_boundary:
            filtered.append(entry)
            continue
        entry_ids = [str(entry.entry_id or "").strip()]
        entry_ids.extend(
            str(child_id or "").strip() for child_id in tuple(entry.child_entry_ids or ())
        )
        if boundary_id in entry_ids:
            passed_boundary = True
    if passed_boundary:
        return filtered
    return list(entries or [])


def reset_prompt_window_state(controller) -> None:
    controller._prompt_transcript_window_state = PromptTranscriptWindowState()
