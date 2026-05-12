from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Optional

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, ToolEvent


def reference_aligned_current_dir_command(host_platform: HostPlatform) -> str:
    del host_platform
    return "/list_dir . --limit 50 --depth 1"


def protocol_path_payload(
    *,
    kind: str,
    source: str,
    provider_used: bool,
    parity_evaluable: bool,
    reason: str,
) -> Dict[str, Any]:
    return {
        "protocol_path": {
            "kind": str(kind or "").strip(),
            "source": str(source or "").strip(),
            "provider_used": bool(provider_used),
            "parity_evaluable": bool(parity_evaluable),
            "reason": str(reason or "").strip(),
        }
    }


def intent_with_protocol_path(
    intent: AgentIntent,
    *,
    kind: str,
    source: str,
    provider_used: bool,
    parity_evaluable: bool,
    reason: str,
) -> AgentIntent:
    diagnostics = dict(intent.protocol_diagnostics or {})
    diagnostics.update(
        protocol_path_payload(
            kind=kind,
            source=source,
            provider_used=provider_used,
            parity_evaluable=parity_evaluable,
            reason=reason,
        )
    )
    intent.protocol_diagnostics = diagnostics
    return intent


def match_shell_intent(
    *,
    text: str,
    normalized: str,
    host_platform: HostPlatform,
    list_dir_keys: tuple[str, ...],
    pwd_keys: tuple[str, ...],
    python_version_keys: tuple[str, ...],
) -> Optional[AgentIntent]:
    if any(key in normalized for key in list_dir_keys):
        return AgentIntent(
            assistant_text="识别为列出当前工作区文件，准备读取文件列表。",
            command_text=reference_aligned_current_dir_command(host_platform),
            status_hint="tool",
        )
    if normalized == "pwd" or any(key in normalized for key in pwd_keys):
        return AgentIntent(
            assistant_text="识别为查看当前工作目录，准备执行。",
            command_text=host_platform.shell_command(host_platform.print_working_dir_command),
            status_hint="tool",
        )
    if any(key in normalized for key in python_version_keys):
        return AgentIntent(
            assistant_text="识别为查看 Python 版本，准备执行。",
            command_text=host_platform.shell_command(host_platform.python_version_command),
            status_hint="tool",
        )
    return None


_WEATHER_QUERY_MARKERS = (
    "天气",
    "weather",
    "气温",
    "温度",
    "降雨",
    "降雪",
    "风力",
    "预报",
    "台风",
)

_WEATHER_TEXT_MARKERS = (
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


def _looks_like_weather_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _WEATHER_QUERY_MARKERS)


def _looks_like_weather_text(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _WEATHER_TEXT_MARKERS)


def _collapse_spaces(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(text or "").strip())
    return collapsed.strip()


def _first_sentence(text: str) -> str:
    normalized = _collapse_spaces(text)
    if not normalized:
        return ""
    parts = re.split(r"[。！？!?；;]", normalized)
    first = str(parts[0] if parts else normalized).strip()
    return first or normalized


def _weather_summary_from_results(results: List[Dict[str, Any]]) -> str:
    highlights: List[str] = []
    references: List[str] = []
    seen_highlights: set[str] = set()
    seen_refs: set[str] = set()

    for item in list(results or []):
        if not isinstance(item, dict):
            continue
        title = _collapse_spaces(str(item.get("title") or ""))
        snippet = _collapse_spaces(str(item.get("snippet") or ""))
        source_text = f"{title} {snippet}".strip()
        if not _looks_like_weather_text(source_text):
            continue

        sentence = _first_sentence(snippet or title)
        if sentence and sentence not in seen_highlights:
            highlights.append(sentence)
            seen_highlights.add(sentence)

        url = str(item.get("url") or "").strip()
        if title and url:
            ref = f"{title} | {url}"
            if ref not in seen_refs:
                references.append(ref)
                seen_refs.add(ref)

        if len(highlights) >= 2 and len(references) >= 2:
            break

    if not highlights:
        return ""

    lines = ["根据检索结果，天气要点如下（以气象台实时发布为准）："]
    for idx, highlight in enumerate(highlights[:2], start=1):
        lines.append(f"{idx}. {highlight}")
    if references:
        lines.append("来源：")
        for ref in references[:2]:
            lines.append(ref)
    return "\n".join(lines).strip()


def summarize_live_web_result(query: str, event: ToolEvent) -> str:
    payload = event.payload or {}
    if not event.ok:
        return f"联网查询失败：{payload.get('error') or event.summary}"
    results = payload.get("results") or []
    if not results:
        return f"我先搜索了“{query}”，但当前没有拿到可用结果。"
    if _looks_like_weather_query(query):
        weather_summary = _weather_summary_from_results(results)
        if weather_summary:
            return weather_summary
    lines = [f"我先搜索了“{query}”，目前拿到这些来源："]
    for item in results[:3]:
        title = str(item.get("title") or item.get("source_domain") or "").strip()
        url = str(item.get("url") or "").strip()
        if title and url:
            lines.append(f"{int(item.get('rank') or 0)}. {title} | {url}")
        elif title:
            lines.append(f"{int(item.get('rank') or 0)}. {title}")
    if len(results) > 3:
        lines.append(f"还有 {len(results) - 3} 条结果，可继续展开。")
    return "\n".join(lines)
