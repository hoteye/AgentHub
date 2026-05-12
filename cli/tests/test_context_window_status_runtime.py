from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.model_context_window_runtime import (
    configured_model_auto_compact_token_limit,
    configured_model_context_window,
    configured_model_raw_context_window,
)
from cli.agent_cli.providers.config_catalog_types import ProviderConfig
from cli.agent_cli.providers.token_usage_runtime import usage_from_provider_response
from cli.agent_cli.ui.context_window_status_runtime import (
    context_remaining_percent,
    context_usage_status_from_response,
    context_window_footer_text,
    format_tokens_compact,
    format_tokens_footer_brief,
)


def _t(key: str, **kwargs: object) -> str:
    if key == "footer.context_left.detail":
        return f"{kwargs['percent']}% context left · {kwargs['used']}/{kwargs['window']}"
    if key == "footer.context_left.percent":
        return f"{kwargs['percent']}% context left"
    if key == "footer.context_used.tokens":
        return f"{kwargs['tokens']} used"
    return "100% context left"


def test_context_remaining_percent_matches_codex_baseline_formula() -> None:
    assert context_remaining_percent(used_tokens=20_000, context_window=100_000) == 91
    assert context_remaining_percent(used_tokens=1_000, context_window=100_000) == 100
    assert context_remaining_percent(used_tokens=120_000, context_window=100_000) == 0


def test_format_tokens_compact_preserves_significant_trailing_zeroes() -> None:
    assert format_tokens_compact(20_000) == "20K"
    assert format_tokens_compact(100_000) == "100K"
    assert format_tokens_compact(20_000_000) == "20M"


def test_format_tokens_footer_brief_uses_integer_lowercase_suffixes() -> None:
    assert format_tokens_footer_brief(523) == "523"
    assert format_tokens_footer_brief(5_340) == "5k"
    assert format_tokens_footer_brief(20_000_000) == "20m"


def test_context_usage_status_prefers_provider_trace_usage_and_window() -> None:
    response = SimpleNamespace(
        turn_events=[],
        timings={
            "planning_trace": [
                {
                    "usage": {
                        "input_tokens": 18_000,
                        "cached_input_tokens": 3_000,
                        "output_tokens": 2_000,
                        "total_tokens": 20_000,
                    }
                }
            ]
        },
        status={},
    )

    status = context_usage_status_from_response(
        response,
        current_status={"model_context_window": "100000"},
    )

    assert status["context_window_used_tokens"] == "20000"
    assert status["context_window_tokens"] == "100000"
    assert status["context_window_remaining_percent"] == "91"
    assert status["cached_input_tokens"] == "3000"


def test_context_window_footer_uses_percent_then_used_tokens_then_static() -> None:
    assert (
        context_window_footer_text(
            status_data={
                "context_window_remaining_percent": "72",
                "context_window_used_tokens": "20000",
                "context_window_tokens": "100000",
            },
            translate_fn=_t,
        )
        == "72% context left · 20k/100k"
    )
    assert (
        context_window_footer_text(
            status_data={"context_window_remaining_percent": "72"},
            translate_fn=_t,
        )
        == "72% context left"
    )
    assert (
        context_window_footer_text(
            status_data={"context_window_used_tokens": "123456"},
            translate_fn=_t,
        )
        == "123k used"
    )
    assert (
        context_window_footer_text(
            status_data={
                "context_window_used_tokens": "123456",
                "context_window_tokens": "200000",
            },
            translate_fn=_t,
        )
        == "41% context left · 123k/200k"
    )
    assert context_window_footer_text(status_data={}, translate_fn=_t) == ""


def test_provider_usage_extractor_handles_openai_details_shape() -> None:
    response = SimpleNamespace(
        usage={
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 3},
            "total_tokens": 17,
        }
    )

    assert usage_from_provider_response(response) == {
        "input_tokens": 10,
        "cached_input_tokens": 4,
        "output_tokens": 7,
        "reasoning_output_tokens": 3,
        "total_tokens": 17,
    }


def test_model_context_window_supports_codex_style_effective_window() -> None:
    assert (
        configured_model_context_window(
            {
                "context_window": 272_000,
                "max_context_window": 200_000,
                "effective_context_window_percent": 95,
            }
        )
        == 190_000
    )


def test_model_auto_compact_limit_uses_raw_window_and_clamps_configured_limit() -> None:
    raw_model = {
        "context_window": 272_000,
        "effective_context_window_percent": 95,
        "auto_compact_token_limit": 300_000,
    }

    assert configured_model_raw_context_window(raw_model) == 272_000
    assert configured_model_context_window(raw_model) == 258_400
    assert configured_model_auto_compact_token_limit(raw_model) == 244_800


def test_provider_public_summary_exposes_model_context_window() -> None:
    config = ProviderConfig(
        model="gpt-test",
        api_key="key",
        provider_name="openai",
        raw_model={"context_window": 100_000, "effective_context_window_percent": 95},
    )

    assert config.public_summary()["model_context_window"] == 95_000
    assert config.public_summary()["model_raw_context_window"] == 100_000
    assert config.public_summary()["model_auto_compact_token_limit"] == 90_000
