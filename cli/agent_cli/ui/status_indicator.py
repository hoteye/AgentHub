from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, pi
import random
from time import monotonic

from rich.style import Style as RichStyle
from rich.text import Text

from cli.agent_cli.ui.presentation import MessageCatalog, default_messages
from cli.agent_cli.ui.theme import CliTheme, default_theme

ANIMATION_INTERVAL_SECONDS = 0.032

_SHIMMER_PADDING = 10
_SHIMMER_SWEEP_SECONDS = 2.0
_SHIMMER_BAND_HALF_WIDTH = 5.0
_ENHANCED_PULSE_FRAMES = ("•", "●", "•", "◦")
_ENHANCED_PULSE_FRAME_SECONDS = 0.18
_ENHANCED_LONG_RUNNING_HINT_DELAY_SECONDS = 4.0
_ENHANCED_LONG_RUNNING_HINT_TEXT = "still working"
_IDLE_CAT_RIGHT = "~=(^.^)=3"
_IDLE_CAT_LEFT = "3=(^.^)=~"
_IDLE_STEP_INTERVAL_RANGE = (0.08, 0.34)
_IDLE_PAUSE_CHANCE = 0.18
_IDLE_PAUSE_RANGE = (0.18, 0.95)
_IDLE_TURN_CHANCE = 0.24
_IDLE_STEP_SIZE_CHOICES = (1, 1, 1, 2, 2, 3)


def fmt_elapsed_compact(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def build_status_indicator_text(
    header: str,
    *,
    width: int,
    started_at: float | None,
    theme: CliTheme | None = None,
    messages: MessageCatalog | None = None,
    enhanced: bool = False,
    show_interrupt_hint: bool = True,
    inline_message: str | None = None,
    now: float | None = None,
) -> Text:
    current_theme = theme or default_theme()
    current_messages = messages or default_messages()
    current_time = monotonic() if now is None else float(now)
    label = str(header or "").strip() or current_messages.text("status.working")
    elapsed_duration = 0.0 if started_at is None else max(0.0, current_time - float(started_at))
    elapsed_seconds = int(elapsed_duration)

    text = Text(no_wrap=True, overflow="ellipsis", end="")
    text.append(
        _status_indicator_symbol(elapsed_duration, enhanced=enhanced),
        style=_spinner_style(
            current_time,
            elapsed_duration=elapsed_duration,
            enhanced=enhanced,
            theme=current_theme,
        ),
    )
    text.append(" ")
    text += shimmer_text(label, now=current_time, theme=current_theme)
    text.append(" ")

    meta_style = RichStyle(color=current_theme.text_dim, dim=True)
    key_style = RichStyle(color=current_theme.text_primary)
    pretty_elapsed = fmt_elapsed_compact(elapsed_seconds)
    if show_interrupt_hint:
        text.append(f"({pretty_elapsed} • ", style=meta_style)
        text.append("esc", style=key_style)
        text.append(f" {current_messages.text('status.interrupt_suffix')})", style=meta_style)
    else:
        text.append(f"({pretty_elapsed})", style=meta_style)

    message = str(inline_message or "").strip()
    if enhanced and not message and elapsed_duration >= _ENHANCED_LONG_RUNNING_HINT_DELAY_SECONDS:
        message = current_messages.text("status.still_working") or _ENHANCED_LONG_RUNNING_HINT_TEXT
    if message:
        text.append(" · ", style=meta_style)
        text.append(message, style=meta_style)

    text.truncate(max(1, int(width or 0)), overflow="ellipsis", pad=False)
    return text


@dataclass(slots=True)
class IdleCatAnimator:
    rng: random.Random = field(default_factory=random.Random)
    position: int | None = None
    direction: int = 1
    next_move_at: float | None = None
    pause_until: float | None = None
    interaction_until: float | None = None
    interaction_direction: int = 1
    _runway_width: int = 0

    @property
    def cat_width(self) -> int:
        return max(len(_IDLE_CAT_RIGHT), len(_IDLE_CAT_LEFT))

    def observe_mouse(
        self,
        *,
        x: int,
        width: int,
        now: float | None = None,
    ) -> bool:
        current_time = monotonic() if now is None else float(now)
        total_width = max(1, int(width or 0))
        self._runway_width = max(0, total_width - self.cat_width)
        if self.position is None:
            return False
        clamped_x = max(0, min(total_width - 1, int(x)))
        cat_left = max(0, min(self._runway_width, int(self.position)))
        cat_right = min(total_width - 1, cat_left + self.cat_width - 1)
        if clamped_x < cat_left or clamped_x > cat_right:
            return False

        cat_midpoint = cat_left + (self.cat_width // 2)
        self.interaction_direction = 1 if clamped_x <= cat_midpoint else -1
        self.direction = self.interaction_direction
        self.interaction_until = current_time + self.rng.uniform(0.45, 1.05)
        self.pause_until = None
        self.next_move_at = current_time + 0.03
        return True

    def render(self, *, width: int, theme: CliTheme | None = None, now: float | None = None) -> Text:
        current_theme = theme or default_theme()
        current_time = monotonic() if now is None else float(now)
        total_width = max(1, int(width or 0))
        runway_width = max(0, total_width - self.cat_width)
        self._advance(now=current_time, runway_width=runway_width)

        cat = (_IDLE_CAT_RIGHT if self.direction >= 0 else _IDLE_CAT_LEFT).ljust(self.cat_width)
        lane = f"{' ' * self.position}{cat}{' ' * max(0, runway_width - self.position)}"
        text = Text(no_wrap=True, overflow="ellipsis", end="")
        text.append(lane, style=RichStyle(color=current_theme.text_secondary, bold=True))
        text.truncate(total_width, overflow="ellipsis", pad=False)
        return text

    def _advance(self, *, now: float, runway_width: int) -> None:
        self._runway_width = max(0, int(runway_width))
        if self.position is None:
            self.position = self.rng.randint(0, self._runway_width) if self._runway_width else 0
            self.direction = self.rng.choice((-1, 1))
            self.next_move_at = now + self._random_step_interval(chasing=False)
            return

        self.position = max(0, min(self._runway_width, int(self.position)))
        if self.next_move_at is None:
            self.next_move_at = now + self._random_step_interval(chasing=False)
            return

        steps = 0
        while now >= self.next_move_at and steps < 128:
            self.pause_until = None
            interacting = self._interaction_active(now)
            self._step_once(interacting=interacting)
            self.next_move_at += self._random_step_interval(chasing=interacting)
            if not interacting and self.rng.random() < _IDLE_PAUSE_CHANCE:
                pause_duration = self._random_pause()
                self.pause_until = self.next_move_at + pause_duration
                self.next_move_at += pause_duration
            steps += 1
        if steps >= 128:
            self.next_move_at = now + self._random_step_interval(chasing=self._interaction_active(now))
            self.pause_until = None

    def _step_once(self, *, interacting: bool) -> None:
        if self._runway_width <= 0:
            self.position = 0
            self.direction = self.rng.choice((-1, 1))
            return

        if interacting:
            step_size = self.rng.choice((2, 3, 4, 4, 5))
            candidate = int(self.position) + self.interaction_direction * step_size
            if candidate < 0:
                self.position = min(self._runway_width, -candidate)
                self.direction = 1
                self.interaction_direction = 1
                return
            if candidate > self._runway_width:
                self.position = max(0, self._runway_width - (candidate - self._runway_width))
                self.direction = -1
                self.interaction_direction = -1
                return
            self.position = candidate
            return

        if self.position <= 0:
            self.direction = 1
        elif self.position >= self._runway_width:
            self.direction = -1
        elif self.rng.random() < _IDLE_TURN_CHANCE:
            self.direction *= -1

        step_size = self.rng.choice(_IDLE_STEP_SIZE_CHOICES)
        candidate = int(self.position) + self.direction * step_size
        if candidate < 0:
            self.position = min(self._runway_width, -candidate)
            self.direction = 1
            return
        if candidate > self._runway_width:
            self.position = max(0, self._runway_width - (candidate - self._runway_width))
            self.direction = -1
            return
        self.position = candidate

    def _interaction_active(self, now: float) -> bool:
        return self.interaction_until is not None and now <= self.interaction_until

    def _random_step_interval(self, *, chasing: bool) -> float:
        interval = self.rng.uniform(*_IDLE_STEP_INTERVAL_RANGE)
        return max(0.04, interval * 0.55) if chasing else interval

    def _random_pause(self) -> float:
        return self.rng.uniform(*_IDLE_PAUSE_RANGE)


def build_idle_status_text(
    *,
    width: int,
    animator: IdleCatAnimator | None = None,
    theme: CliTheme | None = None,
    now: float | None = None,
) -> Text:
    current_animator = animator or IdleCatAnimator()
    return current_animator.render(width=width, theme=theme, now=now)


def shimmer_text(text: str, *, now: float | None = None, theme: CliTheme | None = None) -> Text:
    current_theme = theme or default_theme()
    current_time = monotonic() if now is None else float(now)
    chars = list(str(text or ""))
    if not chars:
        return Text()

    output = Text(end="")
    position = _shimmer_position(len(chars), current_time)
    for index, char in enumerate(chars):
        output.append(char, style=_shimmer_style(index, position, theme=current_theme))
    return output


def _status_indicator_symbol(elapsed_duration: float, *, enhanced: bool) -> str:
    if not enhanced:
        return "•"
    index = int(elapsed_duration / _ENHANCED_PULSE_FRAME_SECONDS) % len(_ENHANCED_PULSE_FRAMES)
    return _ENHANCED_PULSE_FRAMES[index]


def _spinner_style(now: float, *, elapsed_duration: float, enhanced: bool, theme: CliTheme) -> RichStyle:
    if enhanced:
        return _pulse_style(elapsed_duration, theme=theme)
    return _shimmer_style(0, _shimmer_position(1, now), theme=theme)


def _pulse_style(elapsed_duration: float, *, theme: CliTheme) -> RichStyle:
    frame_index = int(elapsed_duration / _ENHANCED_PULSE_FRAME_SECONDS) % len(_ENHANCED_PULSE_FRAMES)
    if frame_index == 1:
        return RichStyle(color=theme.text_primary, bold=True)
    if frame_index == 3:
        return RichStyle(color=theme.text_dim, dim=True)
    return RichStyle(color=theme.text_secondary, bold=True)


def _shimmer_position(char_count: int, now: float) -> float:
    period = max(1, int(char_count)) + _SHIMMER_PADDING * 2
    return (now % _SHIMMER_SWEEP_SECONDS) / _SHIMMER_SWEEP_SECONDS * period


def _shimmer_style(index: int, position: float, *, theme: CliTheme) -> RichStyle:
    padded_index = index + _SHIMMER_PADDING
    distance = abs(float(padded_index) - float(position))
    if distance <= _SHIMMER_BAND_HALF_WIDTH:
        angle = pi * (distance / _SHIMMER_BAND_HALF_WIDTH)
        intensity = 0.5 * (1.0 + cos(angle))
    else:
        intensity = 0.0
    color = _blend_hex(theme.app_bg, theme.text_secondary, max(0.0, min(1.0, intensity * 0.9)))
    return RichStyle(color=color, bold=True)


def _blend_hex(fg: str, bg: str, alpha: float) -> str:
    fg_rgb = _hex_to_rgb(fg)
    bg_rgb = _hex_to_rgb(bg)
    mixed = tuple(
        int(fg_channel * alpha + bg_channel * (1.0 - alpha))
        for fg_channel, bg_channel in zip(fg_rgb, bg_rgb, strict=True)
    )
    return _rgb_to_hex(mixed)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        raise ValueError(f"Expected 6-digit hex color, got {value!r}")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
