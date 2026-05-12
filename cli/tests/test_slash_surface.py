from __future__ import annotations

from cli.agent_cli.slash_surface import normalize_command_text


def test_model_default_stays_positional_when_reasoning_effort_is_explicit() -> None:
    assert (
        normalize_command_text("/model default --reasoning-effort default")
        == "/model default --reasoning-effort default"
    )


def test_model_compact_surface_keeps_model_reasoning_and_write_scope() -> None:
    assert normalize_command_text("/model gpt_54 high user") == "/model gpt_54 --reasoning-effort high --write user"


def test_model_reasoning_only_short_form_normalizes_without_fake_model() -> None:
    assert normalize_command_text("/model high user") == "/model --reasoning-effort high --write user"
