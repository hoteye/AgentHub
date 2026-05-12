from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli.scripts.script_runtime_helpers import resolve_script_provider_home_dir


DEFAULT_AGENTHUB_MAIN = Path(__file__).resolve().parents[2] / "agent_cli" / "__main__.py"
DEFAULT_PROVIDER_HOME = resolve_script_provider_home_dir(cwd=Path(__file__).resolve().parents[2])
DEFAULT_REPORT_ROOT = Path("/tmp/agenthub_web_search_wave02")
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CLAUDE_BIN = "claude"

AGENTHUB_OPENAI_NATIVE_BACKEND = "provider_native_openai_responses_web_search"
AGENTHUB_ANTHROPIC_NATIVE_BACKEND = "provider_native_anthropic_web_search"
AGENTHUB_LOCAL_BACKEND = "local_web_search"
CLAUDE_WEB_SEARCH_SCHEMA = "web_search_20250305"


@dataclass(frozen=True)
class PromptFamily:
    case_id: str
    family: str
    prompt: str
    applicability: tuple[str, ...]
    comparison_labels: tuple[str, ...]


PROMPT_FAMILIES: tuple[PromptFamily, ...] = (
    PromptFamily(
        case_id="weather_live",
        family="weather_volatile_external_fact",
        prompt=(
            "北京明天天气怎么样？请用中文回答，写清楚绝对日期。"
            "如果需要联网查询，优先使用当前会话暴露的规范 web_search 路径。"
        ),
        applicability=("agenthub", "codex", "claude"),
        comparison_labels=("Codex-comparable", "Claude-comparable", "common-three-way"),
    ),
    PromptFamily(
        case_id="current_fact_live",
        family="general_current_fact_lookup",
        prompt=(
            "今天美国现任总统是谁？请只回答当前结论，并写清楚你回答对应的绝对日期。"
            "如果需要联网查询，优先使用当前会话暴露的规范 web_search 路径。"
        ),
        applicability=("agenthub", "codex", "claude"),
        comparison_labels=("Codex-comparable", "Claude-comparable", "common-three-way"),
    ),
    PromptFamily(
        case_id="known_url_read",
        family="known_url_followed_by_read_boundary",
        prompt=(
            "请阅读这个公开页面并总结其中与 GPT-5.4 相关的关键信息："
            "https://platform.openai.com/docs/models"
            "。如果用户已经给出具体 URL，优先直接读取而不是先泛搜。"
        ),
        applicability=("agenthub", "codex"),
        comparison_labels=("Codex-comparable",),
    ),
)


@dataclass
class CommandResult:
    system: str
    exit_code: int | None
    elapsed_seconds: float | None
    timed_out: bool
    command: list[str]
    cwd: str
    stdout_path: str
    stderr_path: str
    skipped: bool = False
    skip_reason: str = ""


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _selected_cases(names: list[str] | None) -> list[PromptFamily]:
    if not names:
        return list(PROMPT_FAMILIES)
    wanted = {str(name or "").strip() for name in names if str(name or "").strip()}
    return [case for case in PROMPT_FAMILIES if case.case_id in wanted]


def _clean_strings(values: Any) -> list[str]:
    return [str(item).strip() for item in list(values or []) if str(item).strip()]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _action_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(items or []):
        item_type = str(item.get("type") or "").strip()
        if item_type not in {"web_search_call", "web_search"}:
            continue
        action = dict(item.get("action") or {})
        row = {
            "item_type": item_type,
            "status": str(item.get("status") or "").strip(),
            "action_type": str(action.get("type") or "").strip(),
            "query": str(action.get("query") or "").strip(),
            "queries": _clean_strings(action.get("queries")),
        }
        signature = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(row)
    return rows


def _response_completed_truth(*, observed: bool | None, inferred: str, source: str) -> dict[str, Any]:
    return {
        "response_completed_seen": observed,
        "inference": str(inferred or "").strip(),
        "source": str(source or "").strip(),
    }


def _effective_web_search_mode_for_turn(mode: str, sandbox_mode: str) -> str:
    requested = str(mode or "").strip().lower()
    if requested not in {"disabled", "cached", "live"}:
        return ""
    sandbox = str(sandbox_mode or "").strip().lower()
    if sandbox == "danger-full-access" and requested != "disabled":
        return "live"
    return requested


def _external_web_access_for_turn(mode: str, sandbox_mode: str) -> bool | None:
    effective_mode = _effective_web_search_mode_for_turn(mode, sandbox_mode)
    if effective_mode == "live":
        return True
    if effective_mode == "cached":
        return False
    return None


def _tool_surface_contract(system: str) -> dict[str, Any]:
    if system == "agenthub":
        return {
            "visible_tool_surface_size": 1,
            "family_inventory": ["web_search(native_if_available)"],
            "source": "AgentHub interaction-profile runtime surface",
        }
    if system == "codex":
        return {
            "visible_tool_surface_size": 1,
            "family_inventory": ["web_search"],
            "source": "codex-rs/core/src/tools/spec.rs",
        }
    return {
        "visible_tool_surface_size": 1,
        "family_inventory": [f"{CLAUDE_WEB_SEARCH_SCHEMA} via local WebSearchTool wrapper"],
        "source": "src/tools/WebSearchTool/WebSearchTool.ts",
    }


def _default_openai_base_url() -> str:
    for key in ("AGENTHUB_OPENAI_BASE_URL", "AGENT_CLI_BASE_URL", "OPENAI_BASE_URL"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _has_weather_like_answer(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    markers = ("天气", "气温", "多云", "晴", "雨", "weather", "temperature", "forecast")
    return any(marker in normalized for marker in markers)


def _has_current_fact_like_answer(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    markers = ("总统", "president", "currently", "现任")
    return any(marker in normalized for marker in markers)


def _has_known_url_read_like_answer(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    markers = ("gpt-5.4", "model", "models", "docs", "文档")
    return any(marker in normalized for marker in markers)


def _answer_quality(case: PromptFamily, assistant_text: str) -> dict[str, Any]:
    text = str(assistant_text or "").strip()
    if case.case_id == "weather_live":
        passed = _has_weather_like_answer(text)
    elif case.case_id == "current_fact_live":
        passed = _has_current_fact_like_answer(text)
    else:
        passed = _has_known_url_read_like_answer(text)
    return {
        "passed": bool(passed),
        "assistant_text_present": bool(text),
        "preview": text[:240],
    }


def _case_request_contract_deltas(case: PromptFamily) -> list[str]:
    deltas = [
        "reasoning_effort is logged as an acceptance variable only and is not upgraded into canonical web_search family semantics.",
        "external_web_access is derived from the sandbox-aware effective web_search mode for the turn, not only from the requested web_search_mode text.",
    ]
    if case.case_id == "known_url_read":
        deltas.append(
            "known_url_read is a Codex-comparable boundary case only; Claude Code reference does not expose Codex-style open/read action parity here."
        )
    return deltas


__all__ = [
    "AGENTHUB_ANTHROPIC_NATIVE_BACKEND",
    "AGENTHUB_LOCAL_BACKEND",
    "AGENTHUB_OPENAI_NATIVE_BACKEND",
    "CLAUDE_WEB_SEARCH_SCHEMA",
    "CommandResult",
    "DEFAULT_AGENTHUB_MAIN",
    "DEFAULT_CLAUDE_BIN",
    "DEFAULT_CODEX_HOME",
    "DEFAULT_PROVIDER_HOME",
    "DEFAULT_REPORT_ROOT",
    "PROMPT_FAMILIES",
    "PromptFamily",
    "_action_rows",
    "_answer_quality",
    "_case_request_contract_deltas",
    "_clean_strings",
    "_default_openai_base_url",
    "_effective_web_search_mode_for_turn",
    "_external_web_access_for_turn",
    "_iso_now",
    "_response_completed_truth",
    "_selected_cases",
    "_to_int",
    "_tool_surface_contract",
]
