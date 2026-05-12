from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any

from textual.css.query import NoMatches

from cli.agent_cli.ui import PromptComposer, SlashCommandPopup, active_prefixed_token, file_query


def file_query_for_app(app: Any) -> str | None:
    composer = app.query_one("#prompt_composer", PromptComposer)
    return file_query(
        composer.text,
        composer.cursor_pos,
        windows_drive_re=app._WINDOWS_DRIVE_RE,
        windows_unc_re=app._WINDOWS_UNC_RE,
    )


def active_prefixed_token_for_app(
    app: Any, prefix: str, *, allow_empty: bool
) -> tuple[str, int, int] | None:
    composer = app.query_one("#prompt_composer", PromptComposer)
    return active_prefixed_token(
        composer.text,
        composer.cursor_pos,
        prefix,
        allow_empty=allow_empty,
    )


def insert_selected_file_reference(app: Any) -> bool:
    active = app._active_prefixed_token("@", allow_empty=True)
    if active is None or not app._file_matches:
        return False
    selected = app._file_matches[app._file_selected_index]
    path_text = str(selected.get("path") or "").strip()
    if not path_text:
        return False
    _, start, end = active
    current = app._current_prompt_text()
    needs_trailing_space = end >= len(current) or not current[end].isspace()
    replacement = app._format_attachment_reference(path_text)
    if needs_trailing_space:
        replacement += " "
    app._set_prompt_text(current[:start] + replacement + current[end:])
    composer = app.query_one("#prompt_composer", PromptComposer)
    composer._cursor_pos = start + len(replacement)
    composer._preferred_column = None
    composer.refresh(repaint=True, layout=False)
    app.dismiss_slash_popup()
    app._focus_input()
    return True


def workspace_files(app: Any) -> list[str]:
    runtime_workspace = Path(
        str(getattr(app.runtime, "cwd", None) or app._workspace_root)
    ).resolve()
    if runtime_workspace != app._workspace_root:
        app._workspace_root = runtime_workspace
        app._workspace_files_cache = None
        app._workspace_files_indexing = False
        app._workspace_files_index_root = None
    cached = app._workspace_files_cache
    if cached is not None:
        return cached

    index_root = getattr(app, "_workspace_files_index_root", None)
    if getattr(app, "_workspace_files_indexing", False) and index_root == app._workspace_root:
        return []

    app._workspace_files_indexing = True
    app._workspace_files_index_root = app._workspace_root

    def _scan_workspace_files(root: Path) -> list[str]:
        files: list[str] = []
        try:
            result = subprocess.run(
                ["rg", "--files"],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if result.returncode == 0:
                files = [
                    line.strip().replace("\\", "/")
                    for line in str(result.stdout or "").splitlines()
                    if line.strip()
                ]
        except Exception:
            files = []
        if not files:
            files = [
                str(path.relative_to(root)).replace("\\", "/")
                for path in root.rglob("*")
                if path.is_file()
            ]
        return sorted(dict.fromkeys(files))

    def _build_index() -> None:
        files = _scan_workspace_files(app._workspace_root)

        def _publish() -> None:
            if getattr(app, "_workspace_files_index_root", None) != app._workspace_root:
                app._workspace_files_indexing = False
                return
            app._workspace_files_cache = files
            app._workspace_files_indexing = False
            if bool(getattr(app, "is_running", False)):
                app._update_completion_popup()

        try:
            app.call_from_thread(_publish)
        except Exception:
            _publish()

    threading.Thread(
        target=_build_index,
        name="agenthub-workspace-file-index",
        daemon=True,
    ).start()
    return []


def refresh_prompt_composer(app: Any) -> None:
    try:
        composer = app.query_one("#prompt_composer", PromptComposer)
        composer_shell = app.query_one("#composer_shell")
        slash_popup = app.query_one("#slash_popup", SlashCommandPopup)
        composer_width = max(
            1,
            getattr(getattr(composer, "content_region", None), "width", 0)
            or getattr(getattr(composer, "region", None), "width", 0)
            or composer.size.width
            or app.size.width,
        )
        composer_height = composer.visible_line_count(composer_width)
        current_composer_height = int(getattr(composer.styles.height, "value", 1) or 1)
        current_shell_height = int(getattr(composer_shell.styles.height, "value", 1) or 1)
        current_popup_height = int(
            getattr(app.query_one("#bottom_dock").styles.height, "value", 3) or 3
        )
        composer.styles.height = composer_height
        composer_shell.styles.height = composer_height
        popup_height = (
            slash_popup.visible_line_count() if slash_popup.styles.display != "none" else 0
        )
        bottom_dock = app.query_one("#bottom_dock")
        bottom_height = composer_height + 2 + popup_height
        bottom_dock.styles.height = bottom_height
        layout_changed = (
            current_composer_height != composer_height
            or current_shell_height != composer_height
            or current_popup_height != bottom_height
        )
        # In a real PTY, repainting parent containers after the composer can
        # clear the prompt line background over the freshly-rendered input.
        # Apply parent layout updates first, then repaint the composer last.
        if layout_changed:
            composer_shell.refresh(repaint=False, layout=True)
            bottom_dock.refresh(repaint=False, layout=True)
            app.refresh(repaint=False, layout=True)
        composer.refresh(repaint=True, layout=False)
    except NoMatches:
        return
