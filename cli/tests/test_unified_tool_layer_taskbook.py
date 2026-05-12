from pathlib import Path
import re


DOC_PATH = Path(__file__).parents[1] / "docs" / "UNIFIED_TOOL_LAYER_TASKBOOK.md"


def _read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_card_three_mentions_resolver_and_backends() -> None:
    text = _read_doc()
    assert "resolve_web_search_capability" in text
    assert "selected_backend" in text
    assert "OpenAI Responses" in text and "type=\"web_search\"" in text
    assert "Anthropic blocks" in text or "Anthropic" in text
    assert "DeepSeek" in text and "local fallback" in text


def test_card_six_mentions_cache_key_and_ttl() -> None:
    text = _read_doc()
    assert "probe cache key" in text
    assert "checked_at" in text
    assert re.search(r"TTL", text, re.IGNORECASE)
    assert "cache hits" in text or "cache state" in text
