from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.providers.anthropic_native_web_search_runtime import (
    native_web_search_payload as anthropic_native_web_search_payload,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_native_web_search_runtime import (
    _search_prompt,
    native_web_search_payload,
)
from cli.agent_cli.runtime_core.tool_commands_helpers import handle_web_search
from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
)
from cli.agent_cli.tools_core.tool_capabilities import utc_now_iso, web_search_probe_cache_key
from cli.agent_cli.tools_core.web_tools_runtime import (
    runtime_web_search_route,
    web_fetch,
    web_search,
)


def test_runtime_web_search_route_prefers_anthropic_native_backend() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-test",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        )
    )

    assert route["selected_backend_id"] == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
    assert route["execution_path"] == "anthropic_native"


def test_runtime_web_search_route_prefers_openai_responses_native_backend() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        )
    )

    assert route["selected_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["execution_path"] == "openai_responses_native"
    assert route["effective_backend_kind"] == "provider_native"
    assert route["probe_bypass"] is True
    assert route["probe_bypass_reason"] == "static_rule_hit"
    assert route["probe_lookup_calls"] == 0
    assert route["supported_modes"] == ["disabled", "cached", "live"]
    assert route["default_mode"] == "cached"
    assert route["requested_mode"] == "cached"
    assert route["effective_mode"] == "cached"
    assert route["mode_source"] == "backend_default"
    assert route["mode_binding"] == "explicit_external_web_access"


def test_runtime_web_search_route_promotes_cached_mode_for_danger_full_access() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            raw_provider={"sandbox_mode": "danger-full-access"},
        )
    )

    assert route["selected_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["execution_path"] == "openai_responses_native"
    assert route["default_mode"] == "cached"
    assert route["requested_mode"] == "cached"
    assert route["effective_mode"] == "live"
    assert route["mode_source"] == "backend_default"


def test_runtime_web_search_route_prefers_openai_responses_native_for_provider_alias() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="gpt-5-codex",
            api_key="sk-test",
            provider_name="google_oauth_probe",
            planner_kind="openai_responses",
            wire_api="",
        )
    )

    assert route["selected_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["execution_path"] == "openai_responses_native"


def test_runtime_web_search_route_falls_back_for_deepseek() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="deepseek-chat",
            api_key="sk-test",
            provider_name="deepseek",
            planner_kind="deepseek_chat",
            wire_api="openai_chat",
        )
    )

    assert route["selected_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert route["execution_path"] == "local_fallback"
    assert route["probe_bypass"] is True
    assert route["probe_bypass_reason"] == "static_rule_hit"
    assert route["probe_lookup_calls"] == 0


def test_runtime_web_search_route_probes_cache_on_fallback_path() -> None:
    probe_calls: list[str] = []

    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="custom-chat",
            api_key="sk-test",
            provider_name="custom",
            planner_kind="openai_chat",
            wire_api="openai_chat",
        ),
        probe_cache_lookup=lambda _key: probe_calls.append("called") or None,
    )

    assert route["decision_source"] == "fallback"
    assert route["selected_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert route["probe_bypass"] is False
    assert route["probe_bypass_reason"] == ""
    assert route["probe_lookup_calls"] == 1
    assert probe_calls == ["called"]


def test_runtime_web_search_route_static_rule_bypasses_probe_lookup() -> None:
    probe_calls: list[str] = []

    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        probe_cache_lookup=lambda _key: probe_calls.append("called") or None,
    )

    assert route["decision_source"] == "static_rule"
    assert route["probe_bypass"] is True
    assert route["probe_bypass_reason"] == "static_rule_hit"
    assert route["probe_lookup_calls"] == 0
    assert probe_calls == []


def test_runtime_web_search_route_native_unavailable_falls_back_to_local() -> None:
    route = runtime_web_search_route(
        provider_config=ProviderConfig(
            model="custom-native",
            api_key="sk-test",
            provider_name="custom",
            planner_kind="openai_chat",
            wire_api="openai_chat",
        ),
        resolve_web_search_capability_fn=lambda *_args, **_kwargs: SimpleNamespace(
            selected_backend=BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
            availability="supported",
            confidence="high",
            decision_source="probe_cache",
            reason="probe_report_native_supported",
            checked_at=utc_now_iso(),
            cache_key="custom|custom-native|openai_chat|openai_chat",
            cache_status="supported",
            cache_expires_at=utc_now_iso(),
            cache_source="probe_script",
        ),
        resolve_native_web_search_capability_fn=lambda _config: SimpleNamespace(
            supports_runtime_native=False
        ),
    )

    assert route["selected_backend_id"] == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    assert route["effective_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert route["execution_path"] == "local_fallback"
    assert route["fallback_reason"] == "openai_responses_native_not_available"


def test_web_search_event_payload_includes_route_metadata_for_local_fallback() -> None:
    class _WebTools:
        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            return {"ok": True, "count": 1, "query": query, "source": "local"}

    event = web_search(
        query="北京天气",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="deepseek-chat",
            api_key="sk-test",
            provider_name="deepseek",
            planner_kind="deepseek_chat",
            wire_api="openai_chat",
        ),
    )

    assert event.payload["web_search_route"]["effective_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert event.payload["web_search_route"]["execution_path"] == "local_fallback"
    assert event.payload["web_search_route"]["probe_bypass"] is True
    assert event.payload["web_search_route"]["probe_bypass_reason"] == "static_rule_hit"
    assert event.payload["status"] == "success"
    assert event.payload["result_count"] == 1
    assert event.payload["source_evidence"] == []
    assert event.payload["display_message"] == ""


def test_web_fetch_event_normalizes_backend_exceptions() -> None:
    class _WebTools:
        def web_fetch(self, url, *, max_chars=12000):
            del url, max_chars
            raise OSError("connection closed")

    event = web_fetch(
        url="https://example.com/protected",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
    )

    assert event.ok is False
    assert event.summary == "web fetch failed"
    assert event.payload["url"] == "https://example.com/protected"
    assert event.payload["blocked_reason"] == "fetch_failed"
    assert event.payload["error_type"] == "OSError"
    assert "web_search" in event.payload["fallback_hint"]


def test_web_search_event_payload_uses_openai_native_backend_when_available() -> None:
    local_calls: list[str] = []

    class _WebTools:
        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            del limit, domains, recency_days, market
            local_calls.append(query)
            return {"ok": True, "count": 1, "query": query, "source": "local"}

    event = web_search(
        query="北京天气",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        openai_native_web_search_payload_fn=lambda *_args, **_kwargs: {
            "ok": True,
            "engine": "openai_native_web_search",
            "count": 2,
            "results": [
                {
                    "rank": 1,
                    "title": "A",
                    "url": "https://a.example.com",
                    "snippet": "",
                    "source_domain": "a.example.com",
                },
                {
                    "rank": 2,
                    "title": "B",
                    "url": "https://b.example.com",
                    "snippet": "",
                    "source_domain": "b.example.com",
                },
            ],
            "query": "北京天气",
        },
    )

    assert local_calls == []
    assert event.ok is True
    assert event.payload["engine"] == "openai_native_web_search"
    assert event.payload["status"] == "success"
    assert event.payload["result_count"] == 2
    assert event.payload["source_evidence"] == [
        {"rank": 1, "title": "A", "url": "https://a.example.com", "source_domain": "a.example.com"},
        {"rank": 2, "title": "B", "url": "https://b.example.com", "source_domain": "b.example.com"},
    ]
    assert (
        event.payload["web_search_route"]["effective_backend_id"]
        == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    )
    assert event.payload["web_search_route"]["execution_path"] == "openai_responses_native"


def test_web_search_event_payload_includes_weather_friendly_function_call_output() -> None:
    event = web_search(
        query="北京今天天气怎么样？",
        web_search_tools_factory=lambda: None,
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        openai_native_web_search_payload_fn=lambda *_args, **_kwargs: {
            "ok": True,
            "engine": "openai_native_web_search",
            "count": 2,
            "assistant_text": "搜索已完成。",
            "results": [
                {
                    "rank": 1,
                    "title": "北京今天天气转阴气温下降",
                    "url": "https://news.weather.com.cn/2025/04/4133762.shtml",
                    "snippet": "中国天气网讯 北京今天（4月8日）天气逐渐转阴，傍晚至夜间零星小雨或小雨来扰。",
                    "source_domain": "news.weather.com.cn",
                },
                {
                    "rank": 2,
                    "title": "未来三天北京以晴冷天气为主",
                    "url": "https://news.weather.com.cn/2025/12/4446019.shtml",
                    "snippet": "根据北京市气象台今早发布的最新预报，今天白天，北京晴，偏北风1级转3至4级，阵风6至7级，最高气温6℃。",
                    "source_domain": "news.weather.com.cn",
                },
            ],
            "query": "北京今天天气怎么样？",
        },
    )

    output = str(event.payload.get("function_call_output") or "")
    assert "天气要点如下" in output
    assert "北京今天（4月8日）天气逐渐转阴" in output
    assert "来源：" in output
    assert "https://news.weather.com.cn/2025/04/4133762.shtml" in output


def test_web_search_event_payload_prefers_native_weather_summary_text_when_available() -> None:
    event = web_search(
        query="北京今天天气怎么样？",
        web_search_tools_factory=lambda: None,
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        openai_native_web_search_payload_fn=lambda *_args, **_kwargs: {
            "ok": True,
            "engine": "openai_native_web_search",
            "count": 1,
            "assistant_text": "北京今天天气多云，当前约24°C；今天白天最高25°C，夜间最低14°C。",
            "results": [
                {
                    "rank": 1,
                    "title": "Weather for Beijing, China",
                    "url": "turn0forecast0",
                    "snippet": "",
                    "source_domain": "",
                }
            ],
            "query": "北京今天天气怎么样？",
        },
    )

    output = str(event.payload.get("function_call_output") or "")
    assert output.startswith("北京今天天气多云，当前约24°C；今天白天最高25°C，夜间最低14°C。")
    assert "turn0forecast0" not in output
    assert "天气要点如下" not in output


def test_openai_native_search_prompt_uses_weather_answer_mode_for_weather_query() -> None:
    prompt = _search_prompt(
        query="北京今天天气怎么样？",
        limit=5,
        domains=["weather.com", "weather.cma.cn"],
        recency_days=3,
        market="zh-CN",
    )

    assert "Answer the weather question using the native web_search tool exactly once." in prompt
    assert (
        "You may reformulate the search internally instead of searching the user text literally."
        in prompt
    )
    assert "user_question=北京今天天气怎么样？" in prompt
    assert (
        "constraints=preferred_domains=weather.com, weather.cma.cn ; recency_days=3 ; market=zh-CN"
        in prompt
    )
    assert "Search the web for the query exactly as given." not in prompt


def test_web_search_event_payload_includes_result_list_for_general_query() -> None:
    class _WebTools:
        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            del query, limit, domains, recency_days, market
            return {
                "ok": True,
                "count": 2,
                "results": [
                    {
                        "rank": 1,
                        "title": "Ripgrep Guide",
                        "url": "https://example.com/rg",
                        "snippet": "How to use rg effectively for code search.",
                        "source_domain": "example.com",
                    },
                    {
                        "rank": 2,
                        "title": "Regex search tips",
                        "url": "https://example.com/regex",
                        "snippet": "Examples for filtering files and line numbers.",
                        "source_domain": "example.com",
                    },
                ],
                "query": "rg 命令怎么用？",
            }

    event = web_search(
        query="rg 命令怎么用？",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="deepseek-chat",
            api_key="sk-test",
            provider_name="deepseek",
            planner_kind="deepseek_chat",
            wire_api="openai_chat",
        ),
    )

    output = str(event.payload.get("function_call_output") or "")
    assert "已完成网页搜索" in output
    assert "结果：" in output
    assert "Ripgrep Guide | https://example.com/rg" in output
    assert "How to use rg effectively for code search" in output


def test_handle_web_search_routes_anthropic_via_tool_registry_path() -> None:
    class _Tools:
        def __init__(self) -> None:
            self.last_provider_config = None

        def web_search_result(
            self, query, *, limit=5, domains=None, recency_days=None, market=None
        ):
            self.last_provider_config = self._web_search_provider_config_factory()
            route = runtime_web_search_route(provider_config=self.last_provider_config)
            return CommandExecutionResult(
                assistant_text="Search the web.",
                tool_events=[
                    ToolEvent(
                        name="web_search",
                        ok=True,
                        summary="web results=1",
                        payload={"ok": True, "count": 1, "web_search_route": route},
                    )
                ],
            )

        def web_search(self, *args, **kwargs):
            raise AssertionError("structured runtime path should handle this test")

    class _Runtime:
        def __init__(self) -> None:
            self.tools = _Tools()
            self.agent = SimpleNamespace(
                _planner=SimpleNamespace(
                    config=ProviderConfig(
                        model="claude-sonnet-4-6",
                        api_key="sk-claude",
                        provider_name="anthropic",
                        planner_kind="anthropic_messages",
                        wire_api="anthropic_messages",
                    )
                )
            )

        @staticmethod
        def _parse_args(arg_text: str):
            return [arg_text], {}

        @staticmethod
        def web_search_enabled() -> bool:
            return True

        @staticmethod
        def web_access_allowed() -> bool:
            return True

    runtime = _Runtime()
    result = handle_web_search(
        runtime,
        arg_text="北京天气",
        call_structured=lambda target, method_name, *args, **kwargs: getattr(target, method_name)(
            *args, **kwargs
        ),
        single_event_result=lambda message, event, *, arguments=None: CommandExecutionResult(
            assistant_text=message,
            tool_events=[event],
        ),
        text_only_result=lambda text: CommandExecutionResult(assistant_text=text),
        command_usage_text=lambda name: name,
        error_event=lambda name, summary, **payload: ToolEvent(
            name=name, ok=False, summary=summary, payload=payload
        ),
    )

    assert runtime.tools.last_provider_config is runtime.agent._planner.config
    assert (
        result.tool_events[0].payload["web_search_route"]["effective_backend_id"]
        == BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH
    )


def test_runtime_web_search_route_exposes_probe_cache_provenance() -> None:
    config = ProviderConfig(
        model="custom-1",
        api_key="sk-test",
        provider_name="custom",
        planner_kind="openai_chat",
        wire_api="openai_chat",
    )
    cache_key = web_search_probe_cache_key(
        provider_name=config.provider_name,
        model=config.model,
        wire_api=config.wire_api,
        planner_kind=config.planner_kind,
    )
    cache_entries = {
        cache_key.as_lookup_key(): {
            "selected_backend": BACKEND_LOCAL_WEB_SEARCH,
            "availability": "unknown",
            "confidence": "medium",
            "checked_at": utc_now_iso(),
            "ttl_seconds": 600,
            "probe_status": "unknown",
            "reason": "probe_report_uncertain",
        }
    }
    route = runtime_web_search_route(
        provider_config=config,
        probe_cache_lookup=lambda key: cache_entries.get(key.as_lookup_key()),
    )

    assert route["decision_source"] == "probe_cache"
    assert route["cache_hit"] is True
    assert route["cache_key"] == cache_key.as_lookup_key()
    assert route["cache_status"] == "unknown"
    assert route["cache_expires_at"]
    assert route["cache_source"] == "probe_script"
    assert route["probe_bypass"] is False
    assert route["probe_bypass_reason"] == ""
    assert route["probe_lookup_calls"] == 1


def test_web_search_event_payload_includes_probe_cache_route_fields() -> None:
    class _WebTools:
        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            del limit, domains, recency_days, market
            return {"ok": True, "count": 1, "query": query}

    config = ProviderConfig(
        model="custom-1",
        api_key="sk-test",
        provider_name="custom",
        planner_kind="openai_chat",
        wire_api="openai_chat",
    )
    cache_key = web_search_probe_cache_key(
        provider_name=config.provider_name,
        model=config.model,
        wire_api=config.wire_api,
        planner_kind=config.planner_kind,
    )
    cache_entries = {
        cache_key.as_lookup_key(): {
            "selected_backend": BACKEND_LOCAL_WEB_SEARCH,
            "availability": "unsupported",
            "confidence": "high",
            "checked_at": utc_now_iso(),
            "ttl_seconds": 600,
            "probe_status": "unsupported",
            "reason": "probe_report_native_unsupported",
        }
    }
    event = web_search(
        query="example",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=config,
        probe_cache_lookup=lambda key: cache_entries.get(key.as_lookup_key()),
    )

    route = event.payload["web_search_route"]
    assert route["decision_source"] == "probe_cache"
    assert route["cache_hit"] is True
    assert route["cache_status"] == "unsupported"
    assert route["cache_source"] == "probe_script"
    assert route["probe_bypass"] is False
    assert route["probe_bypass_reason"] == ""
    assert route["probe_lookup_calls"] == 1


def test_web_search_event_payload_normalizes_failure_contract() -> None:
    class _WebTools:
        def web_search(self, query, *, limit=5, domains=None, recency_days=None, market=None):
            del limit, domains, recency_days, market
            return {
                "ok": False,
                "query": query,
                "error": "provider timeout",
                "retryable": True,
            }

    event = web_search(
        query="北京明天天气",
        web_search_tools_factory=lambda: _WebTools(),
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="deepseek-chat",
            api_key="sk-test",
            provider_name="deepseek",
            planner_kind="deepseek_chat",
            wire_api="openai_chat",
        ),
    )

    assert event.ok is False
    assert event.payload["status"] == "error"
    assert event.payload["result_count"] == 0
    assert event.payload["error_code"] == "provider timeout"
    assert event.payload["display_message"] == "provider timeout"
    assert event.payload["retryable"] is True
    assert event.payload["source_evidence"] == []


def test_openai_native_web_search_payload_marks_incomplete_dispatch_without_results() -> None:
    class _FakeResponses:
        def create(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                id="resp_native_incomplete",
                status="incomplete",
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        id="ws_1",
                        action={"type": "search", "query": "北京天气", "queries": ["北京天气"]},
                    )
                ],
                output_text="",
            )

    fake_client = SimpleNamespace(responses=_FakeResponses())
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="responses",
    )

    with (
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.build_openai_client",
            return_value=fake_client,
        ),
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.call_with_provider_retries",
            side_effect=lambda request_fn: request_fn(),
        ),
    ):
        payload = native_web_search_payload(config, query="北京天气", limit=5)

    assert payload["ok"] is False
    assert payload["search_dispatched"] is True
    assert payload["search_results_received"] is False
    assert payload["native_interrupted"] is True
    assert payload["web_search_outcome"] == "native_interrupted"
    assert payload["error_code"] == "native_web_search_incomplete"
    assert payload["retryable"] is True


def test_openai_native_web_search_payload_uses_effective_mode_for_external_web_access() -> None:
    requests: list[dict] = []

    class _FakeResponses:
        def create(self, **kwargs):
            requests.append(dict(kwargs))
            return SimpleNamespace(
                id="resp_native_mode_contract",
                status="completed",
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        id="ws_1",
                        action={"type": "search", "query": "北京天气", "queries": ["北京天气"]},
                    )
                ],
                output_text=(
                    '{"assistant_text":"北京今天晴。","results":[{"title":"北京天气","url":"https://weather.example.com/beijing","snippet":"晴"}]}'
                ),
            )

    fake_client = SimpleNamespace(responses=_FakeResponses())

    with (
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.build_openai_client",
            return_value=fake_client,
        ),
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.call_with_provider_retries",
            side_effect=lambda request_fn: request_fn(),
        ),
    ):
        cached_payload = native_web_search_payload(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"web_search_mode": "cached"},
            ),
            query="北京天气",
            limit=5,
        )
        live_payload = native_web_search_payload(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"web_search_mode": "cached", "sandbox_mode": "danger-full-access"},
            ),
            query="北京天气",
            limit=5,
        )

    assert requests[0]["tools"] == [{"type": "web_search", "external_web_access": False}]
    assert cached_payload["requested_mode"] == "cached"
    assert cached_payload["effective_mode"] == "cached"
    assert cached_payload["external_web_access"] is False
    assert requests[1]["tools"] == [{"type": "web_search", "external_web_access": True}]
    assert live_payload["requested_mode"] == "cached"
    assert live_payload["effective_mode"] == "live"
    assert live_payload["external_web_access"] is True


def test_openai_native_web_search_payload_fails_closed_when_capability_resolution_errors() -> None:
    requests: list[dict] = []

    class _FakeResponses:
        def create(self, **kwargs):
            requests.append(dict(kwargs))
            return SimpleNamespace(
                id="resp_native_mode_contract_error",
                status="completed",
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        id="ws_1",
                        action={"type": "search", "query": "北京天气", "queries": ["北京天气"]},
                    )
                ],
                output_text='{"assistant_text":"北京今天晴。","results":[]}',
            )

    fake_client = SimpleNamespace(responses=_FakeResponses())

    with (
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.build_openai_client",
            return_value=fake_client,
        ),
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.call_with_provider_retries",
            side_effect=lambda request_fn: request_fn(),
        ),
        patch(
            "cli.agent_cli.providers.openai_native_web_search_runtime.resolve_native_web_search_capability",
            side_effect=RuntimeError("boom"),
        ),
    ):
        payload = native_web_search_payload(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
            ),
            query="北京天气",
            limit=5,
        )

    assert requests[0]["tools"] == [{"type": "web_search", "external_web_access": False}]
    assert payload["requested_mode"] == "cached"
    assert payload["effective_mode"] == "cached"
    assert payload["external_web_access"] is False


def test_web_search_event_payload_exposes_provider_error_without_native_marker() -> None:
    event = web_search(
        query="北京今天天气怎么样？",
        web_search_tools_factory=lambda: None,
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        openai_native_web_search_payload_fn=lambda *_args, **_kwargs: {
            "ok": False,
            "engine": "openai_native_web_search",
            "response_status": "completed",
            "error_code": "native_web_search_call_missing",
            "errors": ["response accepted but native web_search_call marker was absent"],
        },
    )

    assert event.ok is False
    assert event.payload["search_dispatched"] is False
    assert event.payload["search_results_received"] is False
    assert event.payload["native_interrupted"] is False
    assert event.payload["web_search_outcome"] == "provider_error_without_search"
    assert (
        event.payload["web_search_route"]["effective_backend_id"]
        == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    )


def test_web_search_event_payload_remaps_effective_backend_after_native_failure_fallback() -> None:
    event = web_search(
        query="北京今天天气怎么样？",
        web_search_tools_factory=lambda: None,
        event_factory=lambda name, ok, summary, payload: ToolEvent(
            name=name, ok=ok, summary=summary, payload=payload
        ),
        provider_config=ProviderConfig(
            model="gpt-5.4",
            api_key="sk-test",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        openai_native_web_search_payload_fn=lambda *_args, **_kwargs: {
            "ok": True,
            "engine": "local_web_search",
            "count": 1,
            "results": [
                {
                    "rank": 1,
                    "title": "北京天气预报",
                    "url": "https://weather.example.com/beijing",
                    "snippet": "今天多云。",
                    "source_domain": "weather.example.com",
                }
            ],
            "fallback_after_native_failure": True,
            "fallback_reason": "openai_native_request_failed",
            "native_request_error": "stream closed before response.completed",
            "native_request_retryable": True,
        },
    )

    assert event.ok is True
    assert event.payload["fallback_after_native_failure"] is True
    assert event.payload["fallback_reason"] == "openai_native_request_failed"
    assert event.payload["web_search_outcome"] == "fallback_after_native_failure"
    assert (
        event.payload["web_search_route"]["selected_backend_id"]
        == BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
    )
    assert event.payload["web_search_route"]["effective_backend_id"] == BACKEND_LOCAL_WEB_SEARCH
    assert event.payload["web_search_route"]["execution_path"] == "local_fallback"


def test_anthropic_native_web_search_payload_marks_orphaned_server_tool_use_as_interrupted() -> (
    None
):
    class _FakeMessages:
        def create(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                id="msg_native_orphaned",
                stop_reason="end_turn",
                content=[
                    SimpleNamespace(
                        type="server_tool_use",
                        id="srvtoolu_1",
                        name="web_search",
                        input={"query": "北京天气"},
                    ),
                    SimpleNamespace(type="text", text="我正在查找结果。"),
                ],
            )

    fake_client = SimpleNamespace(messages=_FakeMessages())
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with patch(
        "cli.agent_cli.providers.anthropic_native_web_search_runtime._build_client",
        return_value=fake_client,
    ):
        payload = anthropic_native_web_search_payload(config, query="北京天气怎么样", limit=5)

    assert payload["ok"] is False
    assert payload["search_dispatched"] is True
    assert payload["search_results_received"] is False
    assert payload["native_interrupted"] is True
    assert payload["web_search_outcome"] == "native_interrupted"
    assert payload["error_code"] == "server_tool_result_missing"
    assert payload["retryable"] is True
    assert payload["response_block_types"] == ["server_tool_use", "text"]


def test_anthropic_native_web_search_payload_retries_transient_provider_errors() -> None:
    attempts = {"count": 0}

    class _FakeMessages:
        def create(self, **kwargs):
            del kwargs
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError(
                    "InternalServerError: Error code: 503 - "
                    "{'error': {'type': 'proxy_unavailable', 'message': 'All accounts are currently unavailable.'}}"
                )
            return SimpleNamespace(
                id="msg_native_retry_ok",
                stop_reason="end_turn",
                content=[
                    SimpleNamespace(
                        type="server_tool_use",
                        id="srvtoolu_1",
                        name="web_search",
                        input={"query": "北京天气"},
                    ),
                    SimpleNamespace(
                        type="web_search_tool_result",
                        content=[
                            {
                                "url": "https://weather.example.com/beijing",
                                "title": "北京天气预报",
                                "content": "今天晴。",
                            }
                        ],
                    ),
                    SimpleNamespace(type="text", text="北京今天晴。"),
                ],
            )

    fake_client = SimpleNamespace(messages=_FakeMessages())
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="sk-claude",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    with (
        patch(
            "cli.agent_cli.providers.anthropic_native_web_search_runtime._build_client",
            return_value=fake_client,
        ),
        patch(
            "cli.agent_cli.providers.openai_client.time.sleep",
            return_value=None,
        ),
        patch(
            "cli.agent_cli.providers.openai_client.random.uniform",
            return_value=0.0,
        ),
    ):
        payload = anthropic_native_web_search_payload(config, query="北京天气怎么样", limit=5)

    assert attempts["count"] == 2
    assert payload["ok"] is True
    assert payload["search_dispatched"] is True
    assert payload["search_results_received"] is True
    assert payload["web_search_outcome"] == "search_results_received"
