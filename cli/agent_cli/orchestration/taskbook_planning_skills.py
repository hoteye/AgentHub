from __future__ import annotations

import re
from typing import Protocol

from cli.agent_cli.orchestration import taskbook_planner_helpers
from cli.agent_cli.orchestration.taskbook_planning_skill_models import (
    DEFAULT_SCOPE_PLACEHOLDER,
    TaskCardDraftSpec,
)
from cli.agent_cli.orchestration.taskbook_state import TaskCardKind

_VISIBLE_CHILD_COMMON_SCOPE_NAMES = (
    "README",
    "README.md",
    "docs",
    "pyproject.toml",
    "package.json",
    "AGENTS.md",
)


class PlainTextPlanningSkill(Protocol):
    name: str

    def plan(self, text: str, *, objective: str) -> list[TaskCardDraftSpec]: ...


class VisibleChildTabPlanningSkill:
    name = "visible_child_tab_plain_text"

    def plan(self, text: str, *, objective: str) -> list[TaskCardDraftSpec]:
        raw = str(text or "").strip()
        normalized = _matching_text(raw)
        if not _contains_any(
            normalized,
            (
                "visible child tab",
                "visible child",
                "child tab",
                "可见子tab",
                "可见子 tab",
                "子tab",
                "子 tab",
            ),
        ):
            return []
        if not _contains_any(
            normalized, ("split", "拆", "分派", "派发", "dispatch", "并发", "parallel")
        ):
            return []
        scope_segments = _visible_child_scope_segments(raw)
        segments = (
            scope_segments if len(scope_segments) >= 2 else _visible_child_plain_text_segments(raw)
        )
        if len(segments) < 2:
            return []
        drafts: list[TaskCardDraftSpec] = []
        for index, segment in enumerate(segments[:6], start=1):
            target = _visible_child_segment_target(segment)
            owned_files = _visible_child_owned_files(segment, target=target)
            title = f"Read {target}" if target else f"Visible child task {index}"
            goal = f"Read-only research task for visible child tab: {segment.strip()}"
            drafts.append(
                TaskCardDraftSpec(
                    card_id=f"CARD-{index:03d}",
                    title=title[:80] or f"CARD-{index:03d}",
                    goal=goal,
                    owned_files=owned_files or [DEFAULT_SCOPE_PLACEHOLDER],
                    acceptance_criteria=[
                        f"Report concise findings for {target or 'the assigned scope'}."
                    ],
                    depends_on=[],
                    kind=TaskCardKind.READ_ONLY,
                    execution_mode="visible_child_tab",
                    executor_role="scout",
                )
            )
        return drafts


PLAIN_TEXT_PLANNING_SKILLS: tuple[PlainTextPlanningSkill, ...] = (VisibleChildTabPlanningSkill(),)


def plan_plain_text_with_builtin_skills(text: str, *, objective: str) -> list[TaskCardDraftSpec]:
    for skill in PLAIN_TEXT_PLANNING_SKILLS:
        drafts = skill.plan(text, objective=objective)
        if drafts:
            return drafts
    return []


def _matching_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _visible_child_plain_text_segments(text: str) -> list[str]:
    tail = str(text or "").strip()
    for marker in ("：", ":"):
        if marker in tail:
            tail = tail.rsplit(marker, 1)[1].strip()
            break
    normalized = (
        tail.replace("；", "，")
        .replace(";", "，")
        .replace("\n", "，")
        .replace(" and one ", "，one ")
        .replace(" and another ", "，another ")
    )
    chunks = [chunk.strip().strip("，,。.") for chunk in re.split(r"[，,]", normalized)]
    segments: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        target = _visible_child_segment_target(chunk)
        if target or _contains_any(
            chunk.lower(), ("一个", "一项", "one", "first", "second", "另一个", "another")
        ):
            segments.append(chunk)
    return segments


def _visible_child_scope_segments(text: str) -> list[str]:
    scopes = _visible_child_scope_targets(text)
    return [f"read {scope}" for scope in scopes]


def _visible_child_scope_targets(text: str) -> list[str]:
    candidates: list[str] = []
    raw = str(text or "")
    scope_pattern = "|".join(
        [
            *(re.escape(name) for name in _VISIBLE_CHILD_COMMON_SCOPE_NAMES),
            r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+",
            r"[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9_-]{0,8}",
        ]
    )
    for match in re.finditer(
        rf"(?<![A-Za-z0-9_.-])(?:{scope_pattern})(?![A-Za-z0-9_.-])",
        raw,
        flags=re.IGNORECASE,
    ):
        token = match.group(0)
        normalized = token.strip("`\"'()[]{}<>")
        if _scope_token_allowed(normalized):
            _append_unique(candidates, normalized)
    return candidates[:6]


def _append_unique(items: list[str], value: str) -> None:
    normalized = str(value or "").strip()
    if normalized and normalized not in items:
        items.append(normalized)


def _scope_token_allowed(token: str) -> bool:
    normalized = str(token or "").strip()
    if not normalized:
        return False
    lower = normalized.lower()
    if lower in {
        "split",
        "dispatch",
        "parallel",
        "visible",
        "child",
        "tab",
        "tabs",
        "read",
        "inspect",
        "review",
        "research",
        "analyze",
        "master",
        "agenthub",
    }:
        return False
    if lower in {"readme", "docs"}:
        return True
    if "/" in normalized:
        return True
    return "." in normalized


def _visible_child_segment_target(segment: str) -> str:
    text = str(segment or "").strip().strip("。.,，；;")
    text = re.sub(
        r"^(一个|一项|另一个|另外一个|第[一二三四五六]个|one|another|first|second|third|the first|the second)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"^(看|读|读取|检查|调研|研究|分析|read|inspect|review|research|analyze)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = text.strip(" `\"'。.,，；;")
    return text[:80]


def _visible_child_owned_files(segment: str, *, target: str) -> list[str]:
    candidates = taskbook_planner_helpers.extract_path_candidates(segment)
    if candidates:
        return candidates
    target_text = str(target or "").strip()
    if not target_text:
        return []
    tokens = re.findall(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", target_text)
    stopwords = {
        "one",
        "another",
        "first",
        "second",
        "third",
        "read",
        "inspect",
        "review",
        "research",
        "analyze",
        "visible",
        "child",
        "tab",
    }
    owned: list[str] = []
    for token in tokens:
        normalized = token.strip("`\"'()[]{}<>")
        if not normalized or normalized.lower() in stopwords:
            continue
        if normalized not in owned:
            owned.append(normalized)
    return owned


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return taskbook_planner_helpers.contains_any(
        text,
        patterns,
        contains_pattern_fn=_contains_pattern,
    )


def _contains_pattern(text: str, token: str) -> bool:
    return taskbook_planner_helpers.contains_pattern(
        text,
        token,
        ascii_token_boundary_safe_fn=taskbook_planner_helpers.ascii_token_boundary_safe,
    )
