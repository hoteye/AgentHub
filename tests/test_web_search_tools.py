import ssl
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.agent_cli.models import CommandExecutionResult  # noqa: E402
from shared.document_tools.web_search_tools import WebSearchTools  # noqa: E402

_RSS_SAMPLE = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0">
  <channel>
    <title>bing: OpenAI</title>
    <item>
      <title>OpenAI API docs</title>
      <link>https://platform.openai.com/docs/overview</link>
      <description>Official docs for the OpenAI API.</description>
      <pubDate>Wed, 25 Mar 2026 08:11:00 GMT</pubDate>
    </item>
    <item>
      <title>OpenAI GitHub</title>
      <link>https://github.com/openai/openai-python</link>
      <description>Official Python SDK repository.</description>
      <pubDate>Tue, 24 Mar 2026 04:30:00 GMT</pubDate>
    </item>
    <item>
      <title>OpenAI mirror</title>
      <link>https://mirror.example.com/openai-docs</link>
      <description>Unofficial mirror of docs.</description>
      <pubDate>Wed, 25 Mar 2026 09:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Old mirror article</title>
      <link>https://example.org/openai-overview</link>
      <description>Third-party mirror.</description>
      <pubDate>Sat, 01 Mar 2025 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

_RSS_CHINESE_SAMPLE = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0">
  <channel>
    <title>bing: 北京天气</title>
    <item>
      <title>北京天气预报,北京7天天气预报,北京15天天气预报,北京天气查询</title>
      <link>https://www.weather.com.cn/weather/101010100.shtml</link>
      <description>北京天气预报，及时准确发布中央气象台天气信息。</description>
      <pubDate>Thu, 26 Mar 2026 23:48:00 GMT</pubDate>
    </item>
    <item>
      <title>北京旅游：第一次去北京必看攻略</title>
      <link>https://www.zhihu.com/question/123</link>
      <description>北京旅游攻略分享。</description>
      <pubDate>Thu, 26 Mar 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

_HTML_SAMPLE = """
<html>
  <head>
    <title>OpenAI API docs</title>
    <style>.hidden { display: none; }</style>
    <script>console.log("ignore me");</script>
  </head>
  <body>
    <main>
      <h1>Overview</h1>
      <p>The OpenAI API provides access to models.</p>
      <p>Use the Responses API for text and tool calling.</p>
      <p><a href="/docs/quickstart">Quickstart</a></p>
      <p><a href="https://github.com/openai/openai-python">SDK repo</a></p>
    </main>
  </body>
</html>
"""

_HTML_MAIN_SAMPLE = """
<html>
  <head>
    <title>OpenAI API docs</title>
  </head>
  <body>
    <nav>
      <a href="/pricing">Pricing</a>
      <a href="/privacy">Privacy</a>
      <a href="#content">Skip to content</a>
    </nav>
    <main>
      <h1>Overview</h1>
      <p>The OpenAI API provides access to models for text, vision, realtime, and tool use workflows.</p>
      <p>Use the Responses API when you need multi-step orchestration and structured tool calling.</p>
      <p>Authentication is handled with standard API keys and project-based access controls.</p>
      <p>Production integrations should prefer official SDKs and keep request tracing enabled.</p>
      <p>See the <a href="/docs/quickstart">Quickstart</a> guide to build a first request.</p>
      <p>Review the <a href="/docs/responses">Responses API</a> reference for request and response shapes.</p>
      <p>Install from the <a href="https://github.com/openai/openai-python">Python SDK repo</a> when using Python.</p>
    </main>
  </body>
</html>
"""


def _mock_fetch_response(url: str, *, timeout_sec: int = 20) -> dict:
    if url.endswith("/overview"):
        return {
            "text": _HTML_SAMPLE,
            "content_type": "text/html",
            "final_url": "https://platform.openai.com/docs/overview",
        }
    return {
        "text": "<html><head><title>Quickstart</title></head><body><p>Install the SDK first.</p></body></html>",
        "content_type": "text/html",
        "final_url": "https://platform.openai.com/docs/quickstart",
    }


class WebSearchToolsTest(unittest.TestCase):
    def test_web_search_loads_domain_policy_and_recommendations(self) -> None:
        policy_text = """
[search]
allowed_domains = ["openai.com", "github.com"]
denied_domains = ["mirror.example.com"]
preferred_domains = ["github.com"]
official_domains = ["openai.com"]

[[search.domain_recommendations]]
name = "openai"
match = ["openai", "responses api"]
domains = ["openai.com", "github.com"]
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "web_tools.toml"
            policy_path.write_text(policy_text, encoding="utf-8")
            tools = WebSearchTools(policy_path=str(policy_path))
            with patch.object(WebSearchTools, "_fetch_text", return_value=_RSS_SAMPLE):
                payload = tools.web_search("OpenAI Responses API", limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["applied_domains"], ["openai.com", "github.com"])
        self.assertEqual(payload["recommended_domains"], ["openai.com", "github.com"])
        self.assertEqual(payload["official_domains"], ["openai.com"])
        self.assertEqual(payload["preferred_domains"], ["github.com"])
        self.assertEqual(payload["policy_path"], str(policy_path))

    def test_web_search_parses_rss_and_applies_domain_filter(self) -> None:
        tools = WebSearchTools()
        with patch.object(WebSearchTools, "_fetch_text", return_value=_RSS_SAMPLE):
            payload = tools.web_search("OpenAI", domains=["openai.com", "github.com"], limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["engine"], "bing_rss")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["results"][0]["source_domain"], "platform.openai.com")
        self.assertEqual(payload["results"][1]["source_domain"], "github.com")
        self.assertEqual(payload["recommended_domains"], [])
        self.assertEqual(payload["official_domains"], [])
        self.assertEqual(payload["preferred_domains"], [])

    def test_web_search_applies_recency_filter(self) -> None:
        tools = WebSearchTools()

        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                base = datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC)
                return base if tz is None else base.astimezone(tz)

        with (
            patch.object(WebSearchTools, "_fetch_text", return_value=_RSS_SAMPLE),
            patch(
                "shared.document_tools.web_search_tools.datetime",
                _FixedDateTime,
            ),
        ):
            payload = tools.web_search("OpenAI", recency_days=3, limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 3)
        self.assertTrue(all(item["published_at"] for item in payload["results"]))

    def test_web_search_prefers_official_results_in_ranking(self) -> None:
        tools = WebSearchTools()
        with patch.object(WebSearchTools, "_fetch_text", return_value=_RSS_SAMPLE):
            payload = tools.web_search("OpenAI API", limit=4)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["source_domain"], "platform.openai.com")
        self.assertGreater(
            payload["results"][0]["credibility_score"], payload["results"][-1]["credibility_score"]
        )
        self.assertEqual(payload["results"][0]["credibility_label"], "medium")

    def test_web_search_ranking_handles_chinese_query_tokens(self) -> None:
        tools = WebSearchTools()
        with patch.object(WebSearchTools, "_fetch_text", return_value=_RSS_CHINESE_SAMPLE):
            payload = tools.web_search("北京天气怎么样", limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["source_domain"], "www.weather.com.cn")
        self.assertIn("title_match", " ".join(payload["results"][0]["ranking_reasons"]))
        self.assertGreater(
            payload["results"][0]["credibility_score"], payload["results"][1]["credibility_score"]
        )

    def test_web_search_rejects_empty_query(self) -> None:
        tools = WebSearchTools()

        payload = tools.web_search("")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["count"], 0)
        self.assertIn("query is required", payload["error"])

    def test_web_fetch_extracts_title_and_readable_text(self) -> None:
        tools = WebSearchTools()
        with patch.object(
            WebSearchTools,
            "_fetch_response",
            return_value={
                "text": _HTML_SAMPLE,
                "content_type": "text/html",
                "final_url": "https://platform.openai.com/docs/overview",
            },
        ):
            payload = tools.web_fetch("https://platform.openai.com/docs/overview", max_chars=2000)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["title"], "OpenAI API docs")
        self.assertEqual(payload["source_domain"], "platform.openai.com")
        self.assertIn("The OpenAI API provides access to models.", payload["text"])
        self.assertNotIn("ignore me", payload["text"])
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["link_count"], 2)

    def test_open_prefers_main_content_and_filters_navigation_links(self) -> None:
        tools = WebSearchTools()
        with patch.object(
            WebSearchTools,
            "_fetch_response",
            return_value={
                "text": _HTML_MAIN_SAMPLE,
                "content_type": "text/html",
                "final_url": "https://platform.openai.com/docs/overview",
            },
        ):
            payload = tools.open("https://platform.openai.com/docs/overview")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source_scope"], "main")
        self.assertEqual(payload["link_count"], 3)
        self.assertEqual(
            [item["text"] for item in payload["links"]],
            ["Quickstart", "Responses API", "Python SDK repo"],
        )
        self.assertEqual(payload["excerpt_lines"][0]["line"], 1)
        self.assertEqual(payload["excerpt_lines"][0]["text"], "Overview")

    def test_web_fetch_rejects_non_http_url(self) -> None:
        tools = WebSearchTools()

        payload = tools.web_fetch("platform.openai.com/docs/overview")

        self.assertFalse(payload["ok"])
        self.assertIn("http:// or https://", payload["error"])

    def test_open_click_and_find_use_stored_page_references(self) -> None:
        tools = WebSearchTools()

        def _fake_fetch(url: str, *, timeout_sec: int = 20):
            if url.endswith("/overview"):
                return {
                    "text": _HTML_SAMPLE,
                    "content_type": "text/html",
                    "final_url": "https://platform.openai.com/docs/overview",
                }
            return {
                "text": "<html><head><title>Quickstart</title></head><body><p>Install the SDK first.</p></body></html>",
                "content_type": "text/html",
                "final_url": "https://platform.openai.com/docs/quickstart",
            }

        with patch.object(WebSearchTools, "_fetch_response", side_effect=_fake_fetch):
            opened = tools.open("https://platform.openai.com/docs/overview")
            self.assertTrue(opened["ok"])
            self.assertEqual(opened["ref_id"], "page_1")
            self.assertEqual(opened["link_count"], 2)
            self.assertEqual(opened["links"][0]["text"], "Quickstart")

            found = tools.find("page_1", pattern="Responses API")
            self.assertTrue(found["ok"])
            self.assertEqual(found["count"], 1)
            self.assertIn("Responses API", found["matches"][0]["text"])

            clicked = tools.click("page_1", id=1)
            self.assertTrue(clicked["ok"])
            self.assertEqual(clicked["ref_id"], "page_2")
            self.assertIn("Quickstart", clicked["title"])

    def test_web_fetch_reports_underlying_errors(self) -> None:
        tools = WebSearchTools()

        with patch.object(WebSearchTools, "_open_url", side_effect=ValueError("network failure")):
            payload = tools.web_fetch("https://platform.openai.com/docs/overview", max_chars=1000)

        self.assertFalse(payload["ok"])
        self.assertIn("ValueError: network failure", payload["error"])
        self.assertEqual(payload["url"], "https://platform.openai.com/docs/overview")
        self.assertEqual(payload["blocked_reason"], "fetch_failed")
        self.assertIn("web_search", payload["fallback_hint"])

    def test_web_fetch_classifies_tls_eof_errors(self) -> None:
        tools = WebSearchTools()
        exc = URLError(ssl.SSLEOFError(8, "EOF occurred in violation of protocol"))

        with patch.object(WebSearchTools, "_open_url", side_effect=exc):
            payload = tools.web_fetch("https://openai.com/zh-Hans-CN/codex/", max_chars=1000)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "tls_eof")
        self.assertEqual(payload["error_type"], "URLError")
        self.assertIn("Direct page fetch failed", payload["fallback_hint"])

    def test_web_fetch_classifies_cloudflare_challenge(self) -> None:
        tools = WebSearchTools()
        headers = Message()
        headers["server"] = "cloudflare"
        headers["cf-mitigated"] = "challenge"
        exc = HTTPError(
            "https://example.com/protected",
            403,
            "Forbidden",
            headers,
            BytesIO(b"<html>cloudflare challenge</html>"),
        )

        with patch.object(WebSearchTools, "_open_url", side_effect=exc):
            payload = tools.web_fetch("https://example.com/protected", max_chars=1000)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocked_reason"], "cloudflare_challenge")
        self.assertEqual(payload["status_code"], 403)
        self.assertEqual(payload["server"], "cloudflare")
        self.assertEqual(payload["cf_mitigated"], "challenge")

    def test_open_returns_error_for_unknown_ref(self) -> None:
        tools = WebSearchTools()

        payload = tools.open("page_missing")

        self.assertFalse(payload["ok"])
        self.assertIn("unknown ref_id", payload["error"])

    def test_click_reports_error_for_unknown_link_id(self) -> None:
        tools = WebSearchTools()

        with patch.object(WebSearchTools, "_fetch_response", side_effect=_mock_fetch_response):
            opened = tools.open("https://platform.openai.com/docs/overview")
            payload = tools.click(opened["ref_id"], id=999)

        self.assertFalse(payload["ok"])
        self.assertIn("unknown link id", payload["error"])
        self.assertEqual(payload["ref_id"], opened["ref_id"])

    def test_find_requires_pattern(self) -> None:
        tools = WebSearchTools()

        payload = tools.find("page_1", pattern="")

        self.assertFalse(payload["ok"])
        self.assertIn("pattern is required", payload["error"])

    def test_network_unreachable_is_cached_for_fast_followup_failures(self) -> None:
        tools = WebSearchTools()
        attempts: list[str] = []

        def _raise_network_error(*args, **kwargs):
            attempts.append("urlopen")
            raise URLError(OSError(101, "Network is unreachable"))

        with patch(
            "shared.document_tools.web_search_tools.urlopen", side_effect=_raise_network_error
        ):
            first = tools.web_search("北京天气")
            second = tools.web_fetch("https://example.com")

        self.assertFalse(first["ok"])
        self.assertIn("network is unreachable", first["error"].lower())
        self.assertFalse(second["ok"])
        self.assertIn("cached", second["error"].lower())
        self.assertEqual(attempts, ["urlopen"])

    def _assert_structured_result(
        self,
        result: CommandExecutionResult,
        tool_name: str,
        *,
        expected_ok: bool = True,
    ) -> None:
        self.assertIsInstance(result, CommandExecutionResult)
        self.assertGreater(len(result.tool_events), 0)
        self.assertEqual(result.tool_events[0].name, tool_name)
        final_event = result.item_events[-1]
        self.assertEqual(final_event["type"], "item.completed")
        item_payload = final_event["item"]
        self.assertEqual(item_payload["tool"], tool_name)
        self.assertEqual(item_payload["status"], "completed" if expected_ok else "failed")
        if expected_ok:
            self.assertIsNotNone(item_payload["result"])
            self.assertTrue(item_payload["result"].get("structured_content"))
        else:
            self.assertIsNotNone(item_payload["error"])

    def test_web_search_result_exposes_structured_items(self) -> None:
        tools = WebSearchTools()
        payload = {"ok": True, "count": 1, "engine": "bing_rss", "results": [], "query": "foo"}
        with patch.object(WebSearchTools, "web_search", return_value=payload):
            result = tools.web_search_result("foo", limit=1)
        self._assert_structured_result(result, "web_search", expected_ok=True)
        structured = result.item_events[-1]["item"]["result"]["structured_content"]
        self.assertEqual(structured["engine"], "bing_rss")

    def test_web_fetch_result_includes_page_payload(self) -> None:
        tools = WebSearchTools()
        payload = {"ok": True, "url": "https://example.com", "title": "Example"}
        with patch.object(WebSearchTools, "web_fetch", return_value=payload):
            result = tools.web_fetch_result("https://example.com", max_chars=1000)
        self._assert_structured_result(result, "web_fetch", expected_ok=True)
        structured = result.item_events[-1]["item"]["result"]["structured_content"]
        self.assertEqual(structured["url"], "https://example.com")

    def test_open_click_find_result_wraps_payloads(self) -> None:
        tools = WebSearchTools()
        open_payload = {"ok": True, "ref_id": "page_1"}
        click_payload = {"ok": True, "ref_id": "page_2", "source_ref_id": "page_1"}
        find_payload = {"ok": False, "ref_id": "page_2", "error": "not found"}

        with (
            patch.object(WebSearchTools, "open", return_value=open_payload),
            patch.object(WebSearchTools, "click", return_value=click_payload),
            patch.object(WebSearchTools, "find", return_value=find_payload),
        ):
            open_result = tools.open_result("page_1", line=1)
            click_result = tools.click_result("page_1", id=1)
            find_result = tools.find_result("page_1", pattern="term")

        self._assert_structured_result(open_result, "open", expected_ok=True)
        self._assert_structured_result(click_result, "click", expected_ok=True)
        self._assert_structured_result(find_result, "find", expected_ok=False)
        self.assertEqual(find_result.item_events[-1]["item"]["error"]["message"], "not found")
