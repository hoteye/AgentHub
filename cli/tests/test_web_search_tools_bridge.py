from __future__ import annotations

import unittest

from shared.document_tools.web_search_tools import WebSearchTools

class WebSearchToolsStructuredResultTest(unittest.TestCase):
    def test_web_search_result_emits_structured_item_events(self) -> None:
        tools = WebSearchTools()
        tools.web_search = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "ok": True,
            "query": "weather",
            "count": 2,
            "results": [{"title": "A"}, {"title": "B"}],
        }

        result = tools.web_search_result("weather", limit=2, domains=["example.com"], recency_days=3, market="us")

        self.assertEqual(result.assistant_text, "Search the web.")
        self.assertEqual(result.tool_events[0].name, "web_search")
        self.assertEqual(result.tool_events[0].summary, "web results=2")
        self.assertEqual(result.item_events[-1]["item"]["tool"], "web_search")
        self.assertEqual(result.item_events[-1]["item"]["arguments"]["query"], "weather")
        self.assertEqual(result.item_events[-1]["item"]["arguments"]["domains"], ["example.com"])

    def test_page_navigation_results_emit_structured_item_events(self) -> None:
        tools = WebSearchTools()
        tools.web_fetch = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "ok": True,
            "url": "https://example.com",
            "title": "Example",
        }
        tools.open = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "ok": True,
            "ref_id": "page_1",
            "title": "Example",
        }
        tools.click = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "ok": True,
            "ref_id": "page_2",
            "clicked_link_id": 3,
        }
        tools.find = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "ok": True,
            "ref_id": "page_2",
            "count": 4,
            "matches": [{"line": 8, "text": "needle"}],
        }

        fetch_result = tools.web_fetch_result("https://example.com", max_chars=400)
        open_result = tools.open_result("page_1", line=10)
        click_result = tools.click_result("page_1", id=3)
        find_result = tools.find_result("page_2", pattern="needle")

        self.assertEqual(fetch_result.item_events[-1]["item"]["tool"], "web_fetch")
        self.assertEqual(fetch_result.item_events[-1]["item"]["arguments"]["url"], "https://example.com")
        self.assertEqual(open_result.item_events[-1]["item"]["tool"], "open")
        self.assertEqual(open_result.item_events[-1]["item"]["arguments"]["line"], 10)
        self.assertEqual(click_result.item_events[-1]["item"]["tool"], "click")
        self.assertEqual(click_result.item_events[-1]["item"]["arguments"]["id"], 3)
        self.assertEqual(find_result.item_events[-1]["item"]["tool"], "find")
        self.assertEqual(find_result.item_events[-1]["item"]["result"]["structured_content"]["count"], 4)
