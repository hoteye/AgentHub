from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

from cli.agent_cli.providers.adapters import openai_responses_input_runtime
from cli.agent_cli.workspace_context import render_workspace_reference_context_item_message

_WORKSPACE_HEADER_PREFIXES = (
    "# AENGTHUB.md instructions for ",
    "# AGENTS.md instructions for ",
)
_REFERENCE_WORKSPACE_HEADER_PREFIX = "# AGENTS.md instructions for "
_WORKSPACE_HEADER_LINE_PATTERN = re.compile(r"(?m)^# (?:AENGTHUB|AGENTS)\.md instructions for (?P<path>.+)$")
_REFERENCE_ONLY_WORKSPACE_BLOCK_TITLES = frozenset(
    {
        "## Active Workspace",
        "## Workspace Defaults",
    }
)
_REFERENCE_ONLY_WORKSPACE_SECTION_TITLES = frozenset(
    {
        "## Skills",
    }
)
_GENERATED_SKILLS_INTRO_PREFIX = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file."


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip()
            if item_type in {"input_text", "text", "output_text"}:
                text = str(item.get("text") or "")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "")


def message_input_blocks(role: str, content: Any) -> List[Dict[str, Any]]:
    normalized_role = str(role or "user").strip().lower() or "user"
    default_type = "output_text" if normalized_role == "assistant" else "input_text"
    if isinstance(content, list):
        blocks: List[Dict[str, Any]] = []
        for entry in content:
            if isinstance(entry, dict):
                entry_type = str(entry.get("type") or "").strip()
                if entry_type:
                    blocks.append(dict(entry))
                    continue
                text = str(entry.get("text") or "").strip()
                if text:
                    blocks.append({"type": default_type, "text": text})
                continue
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    blocks.append({"type": default_type, "text": text})
        return blocks
    if isinstance(content, dict):
        entry_type = str(content.get("type") or "").strip()
        if entry_type:
            return [dict(content)]
        text = str(content.get("text") or "").strip()
        if text:
            return [{"type": default_type, "text": text}]
        return []
    text = content_text(content).strip()
    if not text:
        return []
    return [{"type": default_type, "text": text}]


def typed_message_input_item(role: str, content: Any) -> Dict[str, Any] | None:
    normalized_role = str(role or "user").strip().lower() or "user"
    blocks = message_input_blocks(normalized_role, content)
    if not blocks:
        return None
    return {
        "type": "message",
        "role": normalized_role,
        "content": blocks,
    }


def _canonicalize_reference_workspace_headers(text: str, *, default_cwd: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return normalized

    def _replace(match: re.Match[str]) -> str:
        path = str(match.group("path") or "").strip() or str(default_cwd or "").strip() or "-"
        return f"{_REFERENCE_WORKSPACE_HEADER_PREFIX}{path}"

    return _WORKSPACE_HEADER_LINE_PATTERN.sub(_replace, normalized)


def _strip_reference_only_workspace_sections(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return ""
    filtered: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped in _REFERENCE_ONLY_WORKSPACE_BLOCK_TITLES:
            index += 1
            while index < len(lines):
                current = lines[index]
                current_stripped = current.strip()
                if not current_stripped:
                    index += 1
                    break
                if current.startswith("## "):
                    break
                if current_stripped.startswith("- ") or current.startswith((" ", "\t")):
                    index += 1
                    continue
                break
            while filtered and not filtered[-1].strip():
                filtered.pop()
            continue
        if stripped in _REFERENCE_ONLY_WORKSPACE_SECTION_TITLES and _looks_like_generated_skills_section(
            lines,
            index,
        ):
            index += 1
            while index < len(lines):
                current = lines[index]
                if current.startswith("## "):
                    break
                index += 1
            while filtered and not filtered[-1].strip():
                filtered.pop()
            continue
        filtered.append(line)
        index += 1
    return "\n".join(filtered).strip()


def _looks_like_generated_skills_section(lines: List[str], section_index: int) -> bool:
    index = section_index + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return False
    return lines[index].strip().startswith(_GENERATED_SKILLS_INTRO_PREFIX)


def workspace_context_message_text(payload: Dict[str, Any], *, reference_parity: bool) -> str:
    rendered = render_workspace_reference_context_item_message(payload) or ""
    if not reference_parity:
        return rendered
    cwd = str(payload.get("path") or "").strip() or "-"
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    instructions_text = str(metadata.get("instructions_excerpt") or "").strip()
    if not instructions_text:
        return _canonicalize_reference_workspace_headers(rendered, default_cwd=cwd)
    instructions_text = _canonicalize_reference_workspace_headers(
        instructions_text,
        default_cwd=cwd,
    )
    instructions_text = _strip_reference_only_workspace_sections(instructions_text)
    if not instructions_text:
        return ""
    if _WORKSPACE_HEADER_LINE_PATTERN.search(instructions_text):
        return instructions_text
    return f"{_REFERENCE_WORKSPACE_HEADER_PREFIX}{cwd}\n\n<INSTRUCTIONS>\n{instructions_text}\n</INSTRUCTIONS>"


def is_workspace_context_message(item: Dict[str, Any]) -> bool:
    if str(item.get("type") or "").strip() != "message":
        return False
    if str(item.get("role") or "").strip().lower() != "user":
        return False
    text = content_text(item.get("content"))
    return bool(
        text
        and (
            any(prefix in text for prefix in _WORKSPACE_HEADER_PREFIXES)
            or "REFERENCE_CONTEXT_BASELINE:" in text
            or "REFERENCE_CONTEXT_UPDATE:" in text
        )
    )


def is_environment_context_message(item: Dict[str, Any]) -> bool:
    if str(item.get("type") or "").strip() != "message":
        return False
    if str(item.get("role") or "").strip().lower() != "user":
        return False
    return "<environment_context>" in content_text(item.get("content"))


def reference_environment_context_text(text: str) -> str:
    lines = str(text or "").splitlines()
    filtered: List[str] = []
    skipping_block: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<network "):
            skipping_block = "network"
            continue
        if stripped == "<subagents>":
            skipping_block = "subagents"
            continue
        if skipping_block:
            if (
                (skipping_block == "network" and stripped == "</network>")
                or (skipping_block == "subagents" and stripped == "</subagents>")
            ):
                skipping_block = None
            continue
        if stripped.startswith("<shell>") and stripped.endswith("</shell>"):
            shell_text = stripped[len("<shell>") : -len("</shell>")].strip()
            shell_name = shell_text.replace("\\", "/").rsplit("/", 1)[-1].strip() or shell_text
            indent = line[: len(line) - len(line.lstrip())]
            filtered.append(f"{indent}<shell>{shell_name}</shell>")
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def reference_environment_context_message(item: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(item)
    content = copied.get("content")
    if not isinstance(content, list):
        return copied
    normalized_content: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_copy = dict(block)
        if str(block_copy.get("type") or "").strip() == "input_text":
            block_copy["text"] = reference_environment_context_text(str(block_copy.get("text") or ""))
        normalized_content.append(block_copy)
    copied["content"] = normalized_content
    return copied


def merge_user_message_blocks(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target_content = target.get("content")
    if not isinstance(target_content, list):
        target_content = []
        target["content"] = target_content
    for block in list(source.get("content") or []):
        if isinstance(block, dict):
            target_content.append(dict(block))


def normalize_input_items(
    input_items: List[Dict[str, Any]],
    *,
    reference_parity: bool = False,
    typed_message_input_item_fn: Callable[[str, Any], Dict[str, Any] | None] = typed_message_input_item,
    workspace_context_message_text_fn: Callable[[Dict[str, Any], bool], str] = lambda payload, flag: workspace_context_message_text(payload, reference_parity=flag),  # noqa: E731
    is_workspace_context_message_fn: Callable[[Dict[str, Any]], bool] = is_workspace_context_message,
    is_environment_context_message_fn: Callable[[Dict[str, Any]], bool] = is_environment_context_message,
    reference_environment_context_message_fn: Callable[[Dict[str, Any]], Dict[str, Any]] = reference_environment_context_message,
    merge_user_message_blocks_fn: Callable[[Dict[str, Any], Dict[str, Any]], None] = merge_user_message_blocks,
) -> List[Dict[str, Any]]:
    return openai_responses_input_runtime.normalize_input_items(
        input_items,
        reference_parity=reference_parity,
        normalize_single_input_item_fn=lambda raw, parity: openai_responses_input_runtime.normalize_single_input_item(
            raw,
            reference_parity=parity,
            typed_message_input_item_fn=typed_message_input_item_fn,
            workspace_context_message_text_fn=workspace_context_message_text_fn,
        ),
        is_workspace_context_message_fn=is_workspace_context_message_fn,
        is_environment_context_message_fn=is_environment_context_message_fn,
        reference_environment_context_message_fn=reference_environment_context_message_fn,
        merge_user_message_blocks_fn=merge_user_message_blocks_fn,
    )
