from __future__ import annotations

import re
from typing import Any, Dict, List

_WEATHER_QUERY_MARKERS = (
    "weather",
    "天气",
    "气温",
    "温度",
    "降雨",
    "降雪",
    "风力",
    "预报",
    "台风",
)

_WEATHER_TEXT_MARKERS = (
    "weather",
    "天气",
    "气温",
    "温度",
    "最高气温",
    "最低气温",
    "阵风",
    "多云",
    "晴",
    "阴",
    "雨",
    "雪",
)


def _collapse_spaces(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).strip()


def _first_sentence(text: Any) -> str:
    normalized = _collapse_spaces(text)
    if not normalized:
        return ""
    parts = re.split(r"[。！？!?；;]", normalized)
    first = str(parts[0] if parts else normalized).strip()
    return first or normalized


def _is_http_url(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _looks_like_weather_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _WEATHER_QUERY_MARKERS)


def _looks_like_weather_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _WEATHER_TEXT_MARKERS)


def _weather_function_call_output(query: str, payload: Dict[str, Any]) -> str:
    results = list(payload.get("results") or [])
    summary_text = _collapse_spaces(payload.get("assistant_text") or payload.get("text"))
    highlights: List[str] = []
    references: List[str] = []
    seen_highlights: set[str] = set()
    seen_refs: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        title = _collapse_spaces(item.get("title"))
        snippet = _collapse_spaces(item.get("snippet"))
        source_text = f"{title} {snippet}".strip()
        if not _looks_like_weather_text(source_text):
            continue
        sentence = _first_sentence(snippet) if snippet else ""
        if sentence and sentence not in seen_highlights:
            highlights.append(sentence)
            seen_highlights.add(sentence)
        url = str(item.get("url") or "").strip()
        if title and url and _is_http_url(url):
            ref = f"{title} | {url}"
            if ref not in seen_refs:
                references.append(ref)
                seen_refs.add(ref)
        if len(highlights) >= 2 and len(references) >= 2:
            break
    if _looks_like_weather_text(summary_text):
        lines = [summary_text]
        if references:
            lines.append("来源：")
            lines.extend(references[:2])
        return "\n".join(lines).strip()
    if highlights:
        lines = ["根据本次网页搜索结果，天气要点如下："]
        for index, highlight in enumerate(highlights[:2], start=1):
            lines.append(f"{index}. {highlight}")
        if references:
            lines.append("来源：")
            lines.extend(references[:2])
        return "\n".join(lines).strip()
    if summary_text:
        return summary_text
    return f"已完成天气搜索，但暂未拿到可直接引用的天气摘要：{query}"


def _generic_function_call_output(query: str, payload: Dict[str, Any]) -> str:
    summary_text = _first_sentence(payload.get("assistant_text") or payload.get("text"))
    results = [item for item in list(payload.get("results") or []) if isinstance(item, dict)]
    if not results:
        return summary_text or f"已完成网页搜索：{query}"
    lines: List[str] = []
    if summary_text:
        lines.append(summary_text)
    else:
        lines.append(f"已完成网页搜索：{query}")
    lines.append("结果：")
    for index, item in enumerate(results[:3], start=1):
        title = _collapse_spaces(item.get("title") or item.get("source_domain") or f"result-{index}")
        url = str(item.get("url") or "").strip()
        snippet = _first_sentence(item.get("snippet"))
        if title and url:
            lines.append(f"{index}. {title} | {url}")
        elif title:
            lines.append(f"{index}. {title}")
        if snippet:
            lines.append(snippet)
    return "\n".join(lines).strip()


def web_search_function_call_output(query: str, payload: Dict[str, Any]) -> str:
    if not bool(payload.get("ok")):
        error_text = _collapse_spaces(payload.get("error") or payload.get("text") or payload.get("assistant_text"))
        return error_text or f"网页搜索失败：{query}"
    if _looks_like_weather_query(query):
        return _weather_function_call_output(query, payload)
    return _generic_function_call_output(query, payload)
