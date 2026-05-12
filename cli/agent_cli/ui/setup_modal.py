from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import Key, MouseDown
from textual.widgets import Button, Input, Select, Static

from cli.agent_cli.ui.presentation import PresentationSettings, default_messages
from cli.agent_cli.ui.setup_modal_provider_helpers import (  # re-exported for public API
    default_setup_provider_options,
    normalize_provider_details,
    normalized_setup_provider_options,
    setup_command_from_payload,
    setup_provider_details_for_app,
    setup_provider_options_for_app,
)

__all__ = [
    "SetupOverlay",
    "present_setup_overlay",
    "default_setup_provider_options",
    "normalized_setup_provider_options",
    "normalize_provider_details",
    "setup_provider_options_for_app",
    "setup_provider_details_for_app",
    "setup_command_from_payload",
]


class SetupOverlay(Static):
    can_focus = False

    ROOT_ID = "setup_overlay"
    PANEL_ID = "setup_overlay_panel"
    TITLE_ID = "setup_overlay_title"
    SUBTITLE_ID = "setup_overlay_subtitle"
    PROVIDER_LABEL_ID = "setup_provider_label"
    PROVIDER_SELECT_ID = "setup_provider_select"
    BASE_URL_LABEL_ID = "setup_base_url_label"
    BASE_URL_INPUT_ID = "setup_base_url_input"
    API_KEY_LABEL_ID = "setup_api_key_label"
    API_KEY_INPUT_ID = "setup_api_key_input"
    FOCUS_HINT_ID = "setup_focus_hint"
    NOTICE_ID = "setup_notice"
    SUBMIT_BUTTON_ID = "setup_submit_button"
    CANCEL_BUTTON_ID = "setup_cancel_button"

    def __init__(
        self,
        *,
        on_submit: Callable[[dict[str, str]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        presentation: PresentationSettings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("", id=self.ROOT_ID, **kwargs)
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._presentation = presentation
        self._messages = presentation.messages if presentation is not None else default_messages()
        self._provider_options = default_setup_provider_options()
        self._provider_details: dict[str, dict[str, Any]] = {}
        self.styles.display = "none"

    @property
    def is_active(self) -> bool:
        return str(self.styles.display) != "none"

    def compose(self) -> ComposeResult:
        with Vertical(id=self.PANEL_ID):
            yield Static(self._t("setup.title"), id=self.TITLE_ID)
            yield Static(self._t("setup.subtitle"), id=self.SUBTITLE_ID)
            yield Static(self._t("setup.focus_hint"), id=self.FOCUS_HINT_ID)
            yield Static(self._t("setup.label.provider"), id=self.PROVIDER_LABEL_ID)
            yield Select(
                [(provider, provider) for provider in self._provider_options],
                prompt=self._t("setup.provider_prompt"),
                allow_blank=False,
                value=self._provider_options[0],
                id=self.PROVIDER_SELECT_ID,
            )
            yield Static(self._t("setup.label.uri"), id=self.BASE_URL_LABEL_ID)
            yield Input(
                placeholder=self._t("setup.base_url_placeholder"),
                id=self.BASE_URL_INPUT_ID,
            )
            yield Static(self._t("setup.label.key"), id=self.API_KEY_LABEL_ID)
            yield Input(
                placeholder=self._t("setup.api_key_placeholder"),
                password=True,
                id=self.API_KEY_INPUT_ID,
            )
            yield Static("", id=self.NOTICE_ID)
            with Horizontal(id="setup_overlay_actions"):
                yield Button(
                    self._t("setup.save_button"), id=self.SUBMIT_BUTTON_ID, variant="primary"
                )
                yield Button(self._t("setup.cancel_button"), id=self.CANCEL_BUTTON_ID)

    def _t(self, key: str, **kwargs: object) -> str:
        return self._messages.text(key, **kwargs)

    def set_presentation(self, presentation: PresentationSettings | None) -> None:
        self._presentation = presentation
        self._messages = presentation.messages if presentation is not None else default_messages()
        self._refresh_localized_text()

    def _refresh_localized_text(self) -> None:
        for widget_id, key in (
            (self.TITLE_ID, "setup.title"),
            (self.SUBTITLE_ID, "setup.subtitle"),
            (self.FOCUS_HINT_ID, "setup.focus_hint"),
            (self.PROVIDER_LABEL_ID, "setup.label.provider"),
            (self.BASE_URL_LABEL_ID, "setup.label.uri"),
            (self.API_KEY_LABEL_ID, "setup.label.key"),
        ):
            try:
                self.query_one(f"#{widget_id}", Static).update(self._t(key))
            except Exception:
                pass
        try:
            self.query_one(f"#{self.PROVIDER_SELECT_ID}", Select).prompt = self._t(
                "setup.provider_prompt"
            )
        except Exception:
            pass
        self._refresh_provider_fields()
        for input_id, key in (
            (self.BASE_URL_INPUT_ID, "setup.base_url_placeholder"),
            (self.API_KEY_INPUT_ID, "setup.api_key_placeholder"),
        ):
            try:
                self.query_one(f"#{input_id}", Input).placeholder = self._t(key)
            except Exception:
                pass
        for button_id, key in (
            (self.SUBMIT_BUTTON_ID, "setup.save_button"),
            (self.CANCEL_BUTTON_ID, "setup.cancel_button"),
        ):
            try:
                self.query_one(f"#{button_id}", Button).label = self._t(key)
            except Exception:
                pass

    def set_handlers(
        self,
        *,
        on_submit: Callable[[dict[str, str]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_cancel = on_cancel

    def set_provider_options(self, provider_options: list[str] | tuple[str, ...]) -> None:
        self._provider_options = normalized_setup_provider_options(provider_options)
        try:
            provider_select = self.query_one(f"#{self.PROVIDER_SELECT_ID}", Select)
        except Exception:
            return
        current_value = str(getattr(provider_select, "value", "") or "").strip()
        provider_select.set_options([(provider, provider) for provider in self._provider_options])
        provider_select.value = (
            current_value if current_value in self._provider_options else self._provider_options[0]
        )

    def set_provider_details(self, provider_details: dict[str, dict[str, Any]] | None) -> None:
        self._provider_details = normalize_provider_details(provider_details or {})
        self._refresh_provider_fields()

    def activate(self, payload: dict[str, Any] | None = None) -> None:
        values = dict(payload or {})
        self.set_provider_options(values.get("provider_options") or self._provider_options)
        self.styles.display = "block"
        self._set_provider_value(str(values.get("provider") or "openai").strip() or "openai")
        self._refresh_provider_fields()
        payload_base_url = str(values.get("base_url") or "").strip()
        if payload_base_url:
            self._set_input_value(self.BASE_URL_INPUT_ID, payload_base_url)
        self._set_notice("")
        self.focus_provider()

    def deactivate(self) -> None:
        self.styles.display = "none"
        self._set_notice("")

    def focus_input(self, input_id: str) -> None:
        try:
            self.query_one(f"#{input_id}", Input).focus()
        except Exception:
            self.focus()

    def focus_provider(self) -> None:
        try:
            self.query_one(f"#{self.PROVIDER_SELECT_ID}", Select).focus()
        except Exception:
            self.focus()

    def on_key(self, event: Key) -> None:
        if str(self.styles.display) == "none":
            return
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.cancel()

    def on_mouse_down(self, event: MouseDown) -> None:
        if not self.is_active:
            return
        widget = getattr(event, "widget", None)
        while widget is not None and widget is not self:
            if isinstance(widget, Button | Input | Select):
                widget.focus()
                return
            widget = getattr(widget, "parent", None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = str(getattr(getattr(event, "button", None), "id", "") or "").strip()
        if button_id == self.SUBMIT_BUTTON_ID:
            self.submit()
            return
        if button_id == self.CANCEL_BUTTON_ID:
            self.cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_id = str(getattr(getattr(event, "input", None), "id", "") or "").strip()
        if input_id == self.BASE_URL_INPUT_ID:
            self.focus_input(self.API_KEY_INPUT_ID)
            return
        if input_id == self.API_KEY_INPUT_ID:
            self.submit()

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = str(getattr(getattr(event, "select", None), "id", "") or "").strip()
        if select_id == self.PROVIDER_SELECT_ID:
            self._refresh_provider_fields()

    def submit(self) -> None:
        payload = self._payload()
        missing: list[str] = []
        if not payload["provider"]:
            missing.append("provider")
        if not payload["api_key"]:
            missing.append("api_key")
        if missing:
            self._set_notice(
                self._t(
                    "setup.missing_notice", fields=", ".join(self._missing_field_names(missing))
                )
            )
            return
        self.deactivate()
        if callable(self._on_submit):
            self._on_submit(payload)

    def cancel(self) -> None:
        self.deactivate()
        if callable(self._on_cancel):
            self._on_cancel()

    def _payload(self) -> dict[str, str]:
        return {
            "provider": self._provider_value(),
            "base_url": self._input_value(self.BASE_URL_INPUT_ID),
            "api_key": self._input_value(self.API_KEY_INPUT_ID),
        }

    def _missing_field_names(self, fields: list[str]) -> list[str]:
        labels = {
            "provider": self._t("setup.field.provider"),
            "api_key": self._t("setup.field.api_key"),
        }
        return [labels.get(field, field) for field in fields]

    def _provider_value(self) -> str:
        try:
            value = self.query_one(f"#{self.PROVIDER_SELECT_ID}", Select).value
        except Exception:
            return ""
        return str(value or "").strip()

    def _set_provider_value(self, value: str) -> None:
        provider = str(value or "").strip()
        options = normalized_setup_provider_options([provider, *self._provider_options])
        self.set_provider_options(options)
        try:
            self.query_one(f"#{self.PROVIDER_SELECT_ID}", Select).value = (
                provider if provider in options else options[0]
            )
        except Exception:
            return

    def _provider_detail(self, provider: str | None = None) -> dict[str, Any]:
        normalized = str(provider or self._provider_value() or "").strip()
        if not normalized:
            return {}
        return dict(self._provider_details.get(normalized.lower()) or {})

    def _refresh_provider_fields(self) -> None:
        if not self.is_mounted:
            return
        detail = self._provider_detail()
        self._set_input_value(self.BASE_URL_INPUT_ID, str(detail.get("base_url") or "").strip())
        self._set_input_value(self.API_KEY_INPUT_ID, str(detail.get("api_key") or "").strip())

    def _input_value(self, input_id: str) -> str:
        try:
            return str(self.query_one(f"#{input_id}", Input).value or "").strip()
        except Exception:
            return ""

    def _set_input_value(self, input_id: str, value: str) -> None:
        try:
            self.query_one(f"#{input_id}", Input).value = str(value or "")
        except Exception:
            return

    def _set_notice(self, text: str) -> None:
        try:
            self.query_one(f"#{self.NOTICE_ID}", Static).update(str(text or ""))
        except Exception:
            return


def _resolve_setup_overlay(
    *,
    app: Any,
    on_submit: Callable[[dict[str, str]], None] | None,
    on_cancel: Callable[[], None] | None,
) -> SetupOverlay | None:
    presentation = getattr(app, "_presentation", None)
    overlay = getattr(app, "_setup_overlay", None)
    if isinstance(overlay, SetupOverlay):
        overlay.set_presentation(presentation)
        overlay.set_handlers(on_submit=on_submit, on_cancel=on_cancel)
        return overlay
    try:
        overlay = app.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay)
    except NoMatches:
        overlay = SetupOverlay(
            on_submit=on_submit,
            on_cancel=on_cancel,
            presentation=presentation,
        )
        try:
            app.mount(overlay)
        except Exception:
            return None
    except Exception:
        return None
    overlay.set_presentation(presentation)
    overlay.set_handlers(on_submit=on_submit, on_cancel=on_cancel)
    app._setup_overlay = overlay
    return overlay


def present_setup_overlay(
    *,
    app: Any,
    payload: dict[str, Any] | None,
    on_submit: Callable[[dict[str, str]], None],
    on_cancel: Callable[[], None],
    provider_options: list[str] | tuple[str, ...] | None = None,
) -> bool:
    overlay = _resolve_setup_overlay(
        app=app,
        on_submit=on_submit,
        on_cancel=on_cancel,
    )
    if overlay is None:
        return False
    try:
        overlay.set_provider_details(setup_provider_details_for_app(app))
        overlay.set_provider_options(provider_options or setup_provider_options_for_app(app))
        overlay.activate(payload)
    except Exception:
        return False
    return True
