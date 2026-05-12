from __future__ import annotations

import re
from typing import Any, Dict, List

_URL_MATCH_PATTERN = re.compile(r"https?://[^\s<>'\"“”‘’]+", flags=re.IGNORECASE)
_URL_HARD_TERMINATOR_PATTERN = re.compile(r"[，。！？；、）】》〉」』”’]")
_URL_WRAPPER_TRIM_CHARS = "()[]{}<>\"'`，。！？；：、,.!?"
_LIVE_WEB_WEATHER_MARKERS = (
    "天气",
    "气温",
    "温度",
    "降雨",
    "下雨",
    "预报",
    "weather",
    "forecast",
)
_LIVE_WEB_TOPIC_MARKERS = (
    "新闻",
    "头条",
    "汇率",
    "股价",
    "价格",
    "油价",
    "金价",
    "比分",
    "赛程",
    "票房",
    "热搜",
    "news",
    "headline",
    "exchange rate",
    "stock price",
    "price",
    "score",
    "schedule",
)
_LIVE_WEB_TEMPORAL_MARKERS = (
    "今天",
    "今日",
    "现在",
    "目前",
    "实时",
    "最新",
    "最近",
    "刚刚",
    "本周",
    "today",
    "now",
    "current",
    "latest",
    "recent",
    "live",
)
_LIVE_WEB_SEARCH_MARKERS = (
    "查一下",
    "查查",
    "查下",
    "搜一下",
    "搜索",
    "搜搜",
    "帮我查",
    "看一下",
    "看看",
    "上网",
    "联网",
    "web_search",
    "search",
    "look up",
)
_ORCHESTRATION_MODE_MARKERS = (
    "任务书模式",
    "taskbook mode",
    "orchestration mode",
    "orchestration/taskbook mode",
    "编排模式",
)
_ORCHESTRATION_EXECUTION_MARKERS = (
    "执行",
    "运行",
    "启动",
    "开始",
    "完成",
    "处理",
    "推进",
    "run",
    "execute",
    "start",
    "handle",
    "perform",
)
_ORCHESTRATION_REQUEST_MARKERS = (
    "请",
    "请帮我",
    "帮我",
    "麻烦你",
    "我想",
    "希望",
    "use ",
    "please ",
)
_ORCHESTRATION_DISCUSSION_MARKERS = (
    "是什么",
    "什么意思",
    "怎么做",
    "如何",
    "讲讲",
    "介绍",
    "解释",
    "区别",
    "原理",
    "can it",
    "how does",
    "what is",
    "why ",
)


def extract_first_url(text: str) -> str | None:
    match = _URL_MATCH_PATTERN.search(str(text or "").strip())
    if not match:
        return None
    candidate = str(match.group(0) or "")
    hard_terminator = _URL_HARD_TERMINATOR_PATTERN.search(candidate)
    if hard_terminator is not None:
        candidate = candidate[: hard_terminator.start()]
    normalized = candidate.strip(_URL_WRAPPER_TRIM_CHARS)
    return normalized or None


def plan_step_names(plan: Dict[str, Any]) -> List[str]:
    return [str(step.get("tool_name") or "").strip() for step in plan.get("steps") or []]


def text_has_any(text: str, keywords: List[str]) -> bool:
    normalized = (text or "").strip().lower()
    return any(keyword in normalized for keyword in keywords)


def looks_like_live_web_query(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if looks_like_file_reference_prompt(text) or looks_like_policy_question(text):
        return False
    if any(marker in normalized for marker in _LIVE_WEB_WEATHER_MARKERS):
        return True
    has_topic = any(marker in normalized for marker in _LIVE_WEB_TOPIC_MARKERS)
    has_temporal = any(marker in normalized for marker in _LIVE_WEB_TEMPORAL_MARKERS)
    has_search_request = any(marker in normalized for marker in _LIVE_WEB_SEARCH_MARKERS)
    return (has_topic and has_temporal) or (has_search_request and has_temporal)


def looks_like_orchestrate_confirm_request(text: str) -> bool:
    normalized = _normalized_space_text(text)
    if not normalized or normalized.startswith("/"):
        return False
    has_mode = any(marker in normalized for marker in _ORCHESTRATION_MODE_MARKERS)
    if not has_mode:
        return False
    has_execution = any(marker in normalized for marker in _ORCHESTRATION_EXECUTION_MARKERS)
    has_request = any(marker in normalized for marker in _ORCHESTRATION_REQUEST_MARKERS)
    if not (has_execution or has_request):
        return False
    if not has_execution:
        return False
    if any(marker in normalized for marker in _ORCHESTRATION_DISCUSSION_MARKERS) and not has_request:
        return False
    return True


def live_web_query_text(text: str) -> str:
    query = str(text or "").strip()
    if not query:
        return ""
    query = re.sub(r"^(请|请你|麻烦你|麻烦)\s*", "", query, flags=re.IGNORECASE)
    query = re.sub(r"^(帮我|给我)\s*", "", query, flags=re.IGNORECASE)
    query = re.sub(r"^(看一下|看看|查一下|查查|查下|搜一下|搜索一下)\s*", "", query, flags=re.IGNORECASE)
    query = re.sub(r"^(请用\s*web_search|用\s*web_search)\s*", "", query, flags=re.IGNORECASE)
    return query.strip(" \t\r\n，。！？,.!?")


def looks_like_policy_question(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "制度",
            "依据",
            "条款",
            "办法",
            "细则",
            "规程",
            "规范",
            "流程",
            "规定",
            "审计整改",
            "管理要求",
        )
    )


def looks_like_confirm_send_request(text: str) -> bool:
    raw = (text or "").strip().lower()
    return text_has_any(
        text,
        ["确认发送", "直接发送", "发送吧", "confirm send", "send now"],
    ) or ("确" in raw and "认" in raw and "发" in raw and "送" in raw)


def looks_like_prepare_send_request(text: str) -> bool:
    raw = (text or "").strip().lower()
    return text_has_any(
        text,
        ["准备发送", "准备好发送", "先准备发送", "不要实际发送", "先别发", "prepare send", "prepare to send"],
    ) or (("准" in raw or "备" in raw) and "发" in raw and "送" in raw) or ("不" in raw and "发" in raw and "送" in raw)


def references_current_conversation(text: str) -> bool:
    raw = (text or "").strip().lower()
    return text_has_any(
        text,
        ["当前会话", "当前聊天", "这个群", "这个会话", "这个聊天", "继续", "确认", "当前", "this chat", "current chat", "continue"],
    ) or ("当" in raw and "前" in raw) or ("这" in raw and "个" in raw) or ("群" in raw)


def looks_like_file_reference_prompt(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    if "@" in raw and ("/" in raw or "\\" in raw):
        return True
    if ('":\\' in raw or ":/" in raw or "\\" in raw or "/" in raw) and any(
        marker in lower
        for marker in (".md", ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".json", ".csv", ".py", ".ps1")
    ):
            return True
    return False


def extract_conversation_name(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    for pattern in (
        r'["\u201c\u201d]([^"\u201c\u201d]{2,128})["\u201c\u201d]',
        r"[']([^']{2,128})[']",
    ):
        match = re.search(pattern, raw)
        if not match:
            continue
        name = str(match.group(1) or "").strip()
        if name:
            return name
    return None


def _normalized_space_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())
