from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ComposerSnapshot:
    text: str
    cursor_pos: int
    selection_anchor: int | None


def undo(composer) -> None:
    if not composer._undo_stack:
        return
    composer._redo_stack.append(composer._snapshot())
    composer._apply_snapshot(composer._undo_stack.pop())


def redo(composer) -> None:
    if not composer._redo_stack:
        return
    composer._undo_stack.append(composer._snapshot())
    composer._apply_snapshot(composer._redo_stack.pop())


def snapshot(composer) -> ComposerSnapshot:
    return ComposerSnapshot(
        text=composer._text,
        cursor_pos=composer._cursor_pos,
        selection_anchor=composer._selection_anchor,
    )


def push_undo_snapshot(composer) -> None:
    current = composer._snapshot()
    if composer._undo_stack and composer._undo_stack[-1] == current:
        return
    composer._undo_stack.append(current)
    if len(composer._undo_stack) > 200:
        composer._undo_stack = composer._undo_stack[-200:]
    composer._redo_stack = []


def apply_snapshot(composer, snapshot_value: ComposerSnapshot) -> None:
    composer._text = snapshot_value.text
    composer._cursor_pos = snapshot_value.cursor_pos
    composer._selection_anchor = snapshot_value.selection_anchor
    composer._preferred_column = None
    composer._sync()
