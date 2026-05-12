from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.text import Text
from textual.css.query import NoMatches
from textual.events import Key
from textual.widgets import Static

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.ui.approval_modal_options_helpers import (
    ApprovalOptionSpec,
    approval_option_specs,
    format_additional_permissions_rule,
)
from cli.agent_cli.ui.presentation import PresentationSettings, default_messages
from cli.agent_cli.ui.theme import CliTheme, default_theme


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _copy_mapping_list(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(value or []):
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _starts_with(value: Any, prefix: str) -> bool:
    return _normalized_text(value).lower().startswith(prefix.lower())


def _humanize_token(value: Any) -> str:
    return _normalized_text(value).replace("_", " ")


def _browser_action_label(payload: dict[str, Any]) -> str:
    action_kind = _normalized_text(payload.get("browser_action_kind"))
    command = _normalized_text(payload.get("browser_command"))
    if action_kind:
        return _humanize_token(action_kind)
    if command:
        return _humanize_token(command)
    return ""


def _title_for_payload(payload: dict[str, Any]) -> str:
    action_type = _normalized_text(payload.get("action_type"))
    if action_type == "shell_command":
        return "Would you like to run the following command?"
    if action_type == "apply_patch":
        return "Would you like to make the following edits?"
    if _starts_with(action_type, "browser."):
        browser_host = _normalized_text(payload.get("browser_host"))
        if browser_host:
            return f'Do you want to approve browser access to "{browser_host}"?'
        browser_action = _browser_action_label(payload)
        if browser_action:
            return f'Do you want to approve browser action "{browser_action}"?'
        return "Do you want to approve this browser action?"
    if action_type == "background_teammate":
        return "Approve background teammate live workspace run?"
    return "Do you want to approve this action?"


def _detail_lines(payload: dict[str, Any]) -> list[str]:
    action_type = _normalized_text(payload.get("action_type"))
    lines: list[str] = []
    summary = _normalized_text(payload.get("summary"))
    if action_type not in {"shell_command", "apply_patch"} and summary:
        lines.append(f"Summary: {summary}")
    reason = _normalized_text(payload.get("reason"))
    if reason:
        lines.append(f"Reason: {reason}")
    permission_rule = format_additional_permissions_rule(
        _copy_mapping(payload.get("additional_permissions")) or None
    )
    if permission_rule:
        lines.append(f"Permission rule: {permission_rule}")
    if action_type == "shell_command":
        command = _normalized_text(payload.get("command"))
        if command:
            if lines:
                lines.append("")
            lines.append(f"$ {command}")
        return lines
    if action_type == "apply_patch":
        file_count = payload.get("file_count")
        if file_count not in ("", None):
            lines.append(f"Files: {int(file_count or 0)}")
        changes = _copy_mapping_list(payload.get("changes"))
        for item in changes[:6]:
            change_type = _normalized_text(item.get("change_type") or "update")
            path = _normalized_text(item.get("path"))
            moved_from = _normalized_text(item.get("moved_from"))
            line = f"{change_type} | {path}" if path else change_type
            if moved_from:
                line += f" | from={moved_from}"
            lines.append(line)
        return lines
    if _starts_with(action_type, "browser."):
        browser_action = _browser_action_label(payload)
        if browser_action:
            lines.append(f"Browser action: {browser_action}")
        browser_host = _normalized_text(payload.get("browser_host"))
        if browser_host:
            lines.append(f"Host: {browser_host}")
        browser_url = _normalized_text(payload.get("browser_url"))
        if browser_url:
            lines.append(f"URL: {browser_url}")
        browser_transport = _normalized_text(payload.get("browser_transport"))
        if browser_transport:
            lines.append(f"Transport: {browser_transport}")
        browser_target_id = _normalized_text(payload.get("browser_target_id"))
        if browser_target_id:
            lines.append(f"Target: {browser_target_id}")
        browser_ref = _normalized_text(payload.get("browser_ref"))
        if browser_ref:
            lines.append(f"Ref: {browser_ref}")
        browser_method = _normalized_text(payload.get("browser_method"))
        if browser_method:
            lines.append(f"Method: {browser_method}")
        browser_path = _normalized_text(payload.get("browser_path"))
        if browser_path:
            lines.append(f"Path: {browser_path}")
        browser_action_class = _humanize_token(payload.get("browser_action_class"))
        if browser_action_class:
            lines.append(f"Risk class: {browser_action_class}")
        approval_policy = _normalized_text(payload.get("approval_policy"))
        if approval_policy:
            lines.append(f"Approval policy: {approval_policy}")
        audit_stage = _humanize_token(payload.get("audit_stage"))
        if audit_stage:
            lines.append(f"Audit stage: {audit_stage}")
        return lines
    task = _normalized_text(payload.get("task"))
    if task:
        lines.append(f"Task: {task}")
    provider = _normalized_text(payload.get("provider"))
    model = _normalized_text(payload.get("model"))
    if provider or model:
        lines.append("Model: " + " / ".join(item for item in (provider, model) if item))
    sandbox_mode = _normalized_text(payload.get("sandbox_mode"))
    if sandbox_mode:
        lines.append(f"Sandbox: {sandbox_mode}")
    cwd = _normalized_text(payload.get("cwd"))
    if cwd:
        lines.append(f"CWD: {cwd}")
    allowed_paths = [
        _normalized_text(item)
        for item in list(payload.get("allowed_paths") or [])
        if _normalized_text(item)
    ]
    if allowed_paths:
        lines.append("Allowed paths: " + ", ".join(allowed_paths))
    blocked_paths = [
        _normalized_text(item)
        for item in list(payload.get("blocked_paths") or [])
        if _normalized_text(item)
    ]
    if blocked_paths:
        lines.append("Blocked paths: " + ", ".join(blocked_paths))
    timeout_seconds = payload.get("timeout_seconds")
    if timeout_seconds not in ("", None):
        lines.append(f"Timeout: {timeout_seconds}s")
    return lines


def approval_overlay_text(payload: dict[str, Any], *, selected_index: int = 0) -> Text:
    normalized_payload = dict(payload or {})
    options = approval_option_specs(normalized_payload)
    result = Text()
    result.append(_title_for_payload(normalized_payload), style="bold")
    result.append("\n")
    detail_lines = _detail_lines(normalized_payload)
    if detail_lines:
        result.append("\n")
        for line in detail_lines:
            if line:
                if line.startswith("Reason: "):
                    result.append("Reason: ")
                    result.append(line[len("Reason: ") :], style="italic")
                elif line.startswith("Permission rule: "):
                    result.append("Permission rule: ")
                    result.append(line[len("Permission rule: ") :], style="bold")
                else:
                    result.append(line)
            result.append("\n")
    if detail_lines and detail_lines[-1]:
        result.append("\n")
    for index, option in enumerate(options, start=1):
        pointer = "›" if index - 1 == selected_index else " "
        shortcut_text = "esc" if option.display_shortcut == "escape" else option.display_shortcut
        line = f"{pointer} {index}. {option.label} ({shortcut_text})"
        style = "bold" if index - 1 == selected_index else ""
        result.append(line, style=style)
        result.append("\n")
    if options:
        result.append("\n")
    result.append("Press enter to confirm or esc to cancel")
    return result


class ApprovalOverlay(Static):
    can_focus = True

    ROOT_ID = "approval_overlay"

    def __init__(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
        on_submit: Callable[[str, dict[str, Any]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("", id=self.ROOT_ID, **kwargs)
        self._theme = theme or (presentation.theme if presentation is not None else default_theme())
        self._messages = default_messages() if presentation is None else presentation.messages
        self._payload: dict[str, Any] | None = None
        self._options: list[ApprovalOptionSpec] = []
        self._cursor_index = 0
        self._on_submit = on_submit
        self.styles.display = "none"

    @property
    def is_active(self) -> bool:
        return self._payload is not None

    @property
    def approval_id(self) -> str:
        return _normalized_text((self._payload or {}).get("approval_id"))

    def set_handlers(
        self, *, on_submit: Callable[[str, dict[str, Any]], None] | None = None
    ) -> None:
        self._on_submit = on_submit

    def set_presentation(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
    ) -> None:
        self._theme = theme or (presentation.theme if presentation is not None else self._theme)
        self._messages = default_messages() if presentation is None else presentation.messages
        self.refresh(repaint=True, layout=False)

    def activate(self, payload: dict[str, Any]) -> None:
        normalized = dict(payload or {})
        options = approval_option_specs(normalized)
        if not _normalized_text(normalized.get("approval_id")) or not options:
            raise ValueError("approval overlay requires approval_id and options")
        self._payload = normalized
        self._options = options
        self._cursor_index = 0
        self.styles.display = "block"
        try:
            self.focus()
        except Exception:
            pass
        self.refresh(repaint=True, layout=True)

    def deactivate(self) -> None:
        self._payload = None
        self._options = []
        self._cursor_index = 0
        self.styles.display = "none"
        self.refresh(repaint=True, layout=True)

    def submit_escape(self) -> bool:
        if not self.is_active:
            return False
        for option in self._options:
            if option.display_shortcut == "escape":
                self._submit_option(option)
                return True
        for option in self._options:
            if option.decision_type == approval_contract_runtime.APPROVAL_DECISION_DECLINE:
                self._submit_option(option)
                return True
        return False

    def on_key(self, event: Key) -> None:
        if not self.is_active:
            return
        normalized_key = str(event.key or "").strip().lower()
        if normalized_key == "escape":
            event.stop()
            event.prevent_default()
            self.submit_escape()
            return
        if normalized_key in {"up", "ctrl+p", "shift+tab"}:
            event.stop()
            event.prevent_default()
            self._move_cursor(-1)
            return
        if normalized_key in {"down", "ctrl+n", "tab"}:
            event.stop()
            event.prevent_default()
            self._move_cursor(1)
            return
        if normalized_key == "enter":
            event.stop()
            event.prevent_default()
            self._submit_current()
            return
        for option in self._options:
            if option.matches_key(normalized_key):
                event.stop()
                event.prevent_default()
                self._submit_option(option)
                return

    def _move_cursor(self, delta: int) -> None:
        if not self._options:
            return
        self._cursor_index = (self._cursor_index + int(delta)) % len(self._options)
        self.refresh(repaint=True, layout=False)

    def _submit_current(self) -> None:
        if not self._options:
            return
        self._submit_option(self._options[self._cursor_index])

    def _submit_option(self, option: ApprovalOptionSpec) -> None:
        payload = dict(self._payload or {})
        payload["decision_type"] = option.decision_type
        payload["decision_command"] = option.command
        self.deactivate()
        if callable(self._on_submit):
            self._on_submit(option.command, payload)

    def render(self) -> Text:
        if not self.is_active:
            return Text("")
        assert self._payload is not None
        rendered = approval_overlay_text(self._payload, selected_index=self._cursor_index)
        rendered.stylize(self._theme.text_primary)
        return rendered


def _resolve_approval_overlay(
    *,
    app: Any,
    on_submit: Callable[[str, dict[str, Any]], None] | None,
) -> ApprovalOverlay | None:
    overlay = getattr(app, "_approval_overlay", None)
    if isinstance(overlay, ApprovalOverlay):
        overlay.set_handlers(on_submit=on_submit)
        return overlay
    try:
        overlay = app.query_one(f"#{ApprovalOverlay.ROOT_ID}", ApprovalOverlay)
    except NoMatches:
        overlay = ApprovalOverlay(
            presentation=getattr(app, "_presentation", None),
            on_submit=on_submit,
        )
        try:
            app.mount(overlay)
        except Exception:
            return None
    except Exception:
        return None
    overlay.set_handlers(on_submit=on_submit)
    app._approval_overlay = overlay
    return overlay


def present_approval_overlay(
    *,
    app: Any,
    payload: dict[str, Any],
    on_submit: Callable[[str, dict[str, Any]], None],
) -> bool:
    overlay = _resolve_approval_overlay(
        app=app,
        on_submit=on_submit,
    )
    if overlay is None:
        return False
    try:
        overlay.activate(dict(payload or {}))
    except Exception:
        return False
    return True
