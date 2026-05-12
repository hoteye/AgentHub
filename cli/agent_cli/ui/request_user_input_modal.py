from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.text import Text
from textual.css.query import NoMatches
from textual.events import Key
from textual.widgets import Static

from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_response,
)
from cli.agent_cli.ui.presentation import PresentationSettings, default_messages
from cli.agent_cli.ui.request_user_input_state_runtime import (
    OTHER_OPTION_VALUE,
    PHASE_QUESTIONS,
    PHASE_REVIEW,
    RequestUserInputSpec,
    RequestUserInputState,
    active_question,
    all_questions_answered,
    parse_request_user_input_spec,
    request_user_input_initial_state,
    response_payload,
    review_actions,
    review_answer_rows,
    selected_option_value_for_question,
    with_cursor_delta,
    with_move_next,
    with_move_previous,
    with_notice,
    with_other_text_backspace,
    with_other_text_append,
    with_return_to_unanswered,
    with_selected_current_option,
)
from cli.agent_cli.ui.theme import CliTheme, default_theme


class RequestUserInputOverlay(Static):
    can_focus = True

    ROOT_ID = "request_user_input_overlay"
    PANEL_ID = "request_user_input_panel"

    def __init__(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
        on_submit: Callable[[dict[str, Any]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("", id=self.ROOT_ID, **kwargs)
        self._theme = theme or (presentation.theme if presentation is not None else default_theme())
        self._messages = default_messages() if presentation is None else presentation.messages
        self._state: RequestUserInputState | None = None
        self._spec: RequestUserInputSpec | None = None
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self.styles.display = "none"

    @property
    def is_active(self) -> bool:
        return self._state is not None and self._spec is not None

    def set_handlers(
        self,
        *,
        on_submit: Callable[[dict[str, Any]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_cancel = on_cancel

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
        spec = parse_request_user_input_spec(payload)
        self._spec = spec
        self._state = request_user_input_initial_state(spec)
        self.styles.display = "block"
        self.focus()
        self.refresh(repaint=True, layout=True)

    def deactivate(self) -> None:
        self._state = None
        self._spec = None
        self.styles.display = "none"
        self.refresh(repaint=True, layout=True)

    def submit_current_response(self) -> None:
        state = self._state
        if state is None:
            return
        if not all_questions_answered(state):
            self._state = with_notice(
                state,
                self._messages.text("rui.notice_missing_answers"),
            )
            self.refresh(repaint=True, layout=False)
            return
        payload = normalize_request_user_input_response(
            response_payload(state),
            question_ids={question.question_id for question in state.spec.questions},
        )
        self.deactivate()
        if callable(self._on_submit):
            self._on_submit(payload)

    def cancel(self) -> None:
        self.deactivate()
        if callable(self._on_cancel):
            self._on_cancel()

    def on_key(self, event: Key) -> None:
        if not self.is_active:
            return
        assert self._state is not None
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.cancel()
            return
        if event.key in {"up", "ctrl+p"}:
            event.stop()
            event.prevent_default()
            self._state = with_cursor_delta(self._state, -1)
            self.refresh(repaint=True, layout=False)
            return
        if event.key in {"down", "ctrl+n"}:
            event.stop()
            event.prevent_default()
            self._state = with_cursor_delta(self._state, 1)
            self.refresh(repaint=True, layout=False)
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            if self._state.phase == PHASE_QUESTIONS:
                self._state = with_move_next(self._state)
                self._state = with_cursor_delta(self._state, 0)
            else:
                self._state = with_cursor_delta(self._state, 1)
            self.refresh(repaint=True, layout=False)
            return
        if event.key == "shift+tab":
            event.stop()
            event.prevent_default()
            if self._state.phase == PHASE_QUESTIONS:
                self._state = with_move_previous(self._state)
                self._state = with_cursor_delta(self._state, 0)
            else:
                self._state = with_cursor_delta(self._state, -1)
            self.refresh(repaint=True, layout=False)
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self._handle_enter()
            self.refresh(repaint=True, layout=False)
            return
        if event.key == "backspace":
            event.stop()
            event.prevent_default()
            self._state = with_other_text_backspace(self._state)
            self.refresh(repaint=True, layout=False)
            return
        if self._should_capture_text_input(event):
            event.stop()
            event.prevent_default()
            self._state = with_other_text_append(self._state, str(event.character or ""))
            self.refresh(repaint=True, layout=False)

    def _handle_enter(self) -> None:
        assert self._state is not None
        if self._state.phase == PHASE_QUESTIONS:
            self._state = with_selected_current_option(self._state)
            return
        action = review_actions()[self._state.cursor_index]
        if action == "Submit answers":
            self.submit_current_response()
            return
        if action == "Edit answers":
            self._state = with_return_to_unanswered(self._state)
            return
        self.cancel()

    def _should_capture_text_input(self, event: Key) -> bool:
        if self._state is None or self._state.phase != PHASE_QUESTIONS:
            return False
        character = str(event.character or "")
        if not character:
            return False
        if len(character) != 1:
            return False
        if ord(character) < 32:
            return False
        question = active_question(self._state)
        selected = selected_option_value_for_question(self._state, question.question_id)
        return selected == OTHER_OPTION_VALUE

    def render(self) -> Text:
        if not self.is_active:
            return Text("")
        assert self._state is not None
        if self._state.phase == PHASE_REVIEW:
            return self._render_review(self._state)
        return self._render_question(self._state)

    def _render_question(self, state: RequestUserInputState) -> Text:
        question = active_question(state)
        result = Text()
        result.append(self._messages.text("rui.title"), style=self._theme.accent_primary)
        result.append("\n")
        result.append(
            self._messages.text(
                "rui.question_progress",
                current=state.question_index + 1,
                total=len(state.spec.questions),
            ),
            style=self._theme.text_muted,
        )
        result.append("\n")
        result.append(f"[{question.header}] ", style=self._theme.accent_primary_soft)
        result.append(question.prompt, style=self._theme.text_primary)
        result.append("\n\n")
        selected = selected_option_value_for_question(state, question.question_id)
        for index, option in enumerate(question.options):
            pointer = ">" if state.cursor_index == index else " "
            chosen = selected == option.value
            marker = "[x]" if chosen else "[ ]"
            option_style = self._theme.text_primary if chosen else self._theme.text_secondary
            result.append(f"{pointer} {marker} {option.label}\n", style=option_style)
            result.append(f"    {option.description}\n", style=self._theme.text_muted)
            if option.value == OTHER_OPTION_VALUE and selected == OTHER_OPTION_VALUE:
                other_text = state.other_text(question.question_id)
                prompt = other_text if other_text else self._messages.text("rui.other_placeholder")
                prompt_style = self._theme.text_primary if other_text else self._theme.text_dim
                result.append(f"    {self._messages.text('rui.other_prefix')}{prompt}\n", style=prompt_style)
        result.append("\n")
        result.append(self._messages.text("rui.help_line_question"), style=self._theme.text_dim)
        if state.notice:
            result.append("\n")
            result.append(state.notice, style=self._theme.accent_warning)
        return result

    def _render_review(self, state: RequestUserInputState) -> Text:
        result = Text()
        result.append(self._messages.text("rui.review_title"), style=self._theme.accent_primary)
        result.append("\n")
        result.append(self._messages.text("rui.review_subtitle"), style=self._theme.text_muted)
        result.append("\n\n")
        for prompt, answer in review_answer_rows(state):
            result.append(f"- {prompt}\n", style=self._theme.text_secondary)
            answer_style = self._theme.text_primary if answer != "<unanswered>" else self._theme.accent_warning
            result.append(f"  -> {answer}\n", style=answer_style)
        result.append("\n")
        actions = review_actions()
        for index, action in enumerate(actions):
            pointer = ">" if index == state.cursor_index else " "
            style = self._theme.accent_primary if index == state.cursor_index else self._theme.text_secondary
            result.append(f"{pointer} {action}\n", style=style)
        result.append("\n")
        result.append(self._messages.text("rui.help_line_review"), style=self._theme.text_dim)
        if state.notice:
            result.append("\n")
            result.append(state.notice, style=self._theme.accent_warning)
        return result


def _resolve_request_user_input_overlay(
    *,
    app: Any,
    on_submit: Callable[[dict[str, Any]], None] | None,
    on_cancel: Callable[[], None] | None,
) -> RequestUserInputOverlay | None:
    overlay = getattr(app, "_request_user_input_overlay", None)
    if isinstance(overlay, RequestUserInputOverlay):
        overlay.set_handlers(on_submit=on_submit, on_cancel=on_cancel)
        return overlay
    try:
        overlay = app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)
    except NoMatches:
        overlay = RequestUserInputOverlay(
            presentation=getattr(app, "_presentation", None),
            on_submit=on_submit,
            on_cancel=on_cancel,
        )
        try:
            app.mount(overlay)
        except Exception:
            return None
    except Exception:
        return None
    overlay.set_handlers(on_submit=on_submit, on_cancel=on_cancel)
    setattr(app, "_request_user_input_overlay", overlay)
    return overlay


def present_request_user_input(
    *,
    app: Any,
    payload: dict[str, Any],
    on_submit: Callable[[dict[str, Any]], None],
    on_cancel: Callable[[], None],
) -> bool:
    overlay = _resolve_request_user_input_overlay(
        app=app,
        on_submit=on_submit,
        on_cancel=on_cancel,
    )
    if overlay is None:
        return False
    try:
        overlay.activate(dict(payload or {}))
    except Exception:
        return False
    return True
