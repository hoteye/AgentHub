from __future__ import annotations

from cli.agent_cli.agent_runtime import summarize_live_web_result
from cli.agent_cli.models import ToolEvent


def test_summarize_live_web_result_weather_query_returns_weather_points() -> None:
    event = ToolEvent(
        name="web_search",
        ok=True,
        summary="web results=2",
        payload={
            "results": [
                {
                    "rank": 1,
                    "title": "北京今天天气转阴气温下降 傍晚至夜间或有小雨来扰-资讯",
                    "url": "https://news.weather.com.cn/2025/04/4133762.shtml",
                    "snippet": "中国天气网讯 北京今天（4月8日）天气逐渐转阴，傍晚至夜间零星小雨或小雨来扰，西部、北部降雨相对较明显。",
                },
                {
                    "rank": 2,
                    "title": "未来三天北京以晴冷天气为主 今日仍有大风需注意防风防寒-资讯",
                    "url": "https://news.weather.com.cn/2025/12/4446019.shtml",
                    "snippet": "根据北京市气象台今早发布的最新预报，今天白天，北京晴，偏北风1级转3至4级，阵风6至7级，最高气温6℃；夜间晴，偏北风3级左右，阵风6至7级，最低气温零下6℃。",
                },
            ]
        },
    )

    text = summarize_live_web_result("北京今天天气怎么样？", event)

    assert "天气要点如下" in text
    assert "北京今天（4月8日）天气逐渐转阴" in text
    assert "来源：" in text
    assert "https://news.weather.com.cn/2025/04/4133762.shtml" in text


def test_summarize_live_web_result_non_weather_query_keeps_source_list_mode() -> None:
    event = ToolEvent(
        name="web_search",
        ok=True,
        summary="web results=1",
        payload={
            "results": [
                {
                    "rank": 1,
                    "title": "Ripgrep guide",
                    "url": "https://example.com/rg",
                    "snippet": "How to use rg effectively.",
                }
            ]
        },
    )

    text = summarize_live_web_result("rg 命令怎么用？", event)

    assert text.startswith("我先搜索了“rg 命令怎么用？”，目前拿到这些来源：")
    assert "Ripgrep guide | https://example.com/rg" in text
