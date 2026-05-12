from __future__ import annotations

import re
from typing import Iterable, Sequence


def extract_header_goal(lines: Sequence[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or "Task objective"
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return "Task objective"


def split_card_blocks(lines: Sequence[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("### "):
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def extract_card_id_and_title(text: str, *, index: int) -> tuple[str, str]:
    normalized = str(text or "").strip()
    match = re.match(r"^(CARD-\d+)\s*[:：-]?\s*(.*)$", normalized, flags=re.IGNORECASE)
    if match:
        card_id = match.group(1).upper()
        title = match.group(2).strip() or card_id
        return card_id, title
    return f"CARD-{index:03d}", normalized or f"CARD-{index:03d}"


def parse_field_lines(lines: Sequence[str], *, split_list_fn) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    key_alias = {
        "owned_files": "owned_files",
        "owned file": "owned_files",
        "acceptance_criteria": "acceptance_criteria",
        "acceptance criteria": "acceptance_criteria",
        "depends_on": "depends_on",
        "depends on": "depends_on",
        "goal": "goal",
    }
    for raw in lines:
        line = str(raw or "").strip()
        if not line.startswith("-"):
            continue
        body = line.lstrip("-").strip()
        if ":" not in body:
            continue
        field_name, raw_value = body.split(":", 1)
        normalized_field = key_alias.get(field_name.strip().lower())
        if not normalized_field:
            continue
        values = split_list_fn(raw_value)
        if values:
            result[normalized_field] = values
    return result


def looks_like_markdown(text: str) -> bool:
    stripped = str(text or "").strip()
    return "### " in stripped or stripped.startswith("# ")


def extract_inline_list(text: str, key: str, *, split_list_fn) -> list[str]:
    regex = re.compile(rf"{re.escape(key)}\s*:\s*(.+)", flags=re.IGNORECASE)
    for line in str(text or "").splitlines():
        match = regex.search(line)
        if match:
            return split_list_fn(match.group(1))
    return []


def split_list(value: str) -> list[str]:
    raw = str(value or "").strip().strip("[]")
    if not raw:
        return []
    chunks = re.split(r"[,;|]", raw)
    items: list[str] = []
    for chunk in chunks:
        token = chunk.strip().strip("`").strip()
        if token:
            items.append(token)
    return items


def extract_path_candidates(text: str) -> list[str]:
    matches = re.findall(
        r"(?:~?[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9_-]{0,8}",
        str(text or ""),
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in matches:
        token = str(raw or "").strip().strip("`").strip("()[]{}<>\"'，。！？,;；")
        if not token or token.lower().startswith(("http://", "https://")):
            continue
        if token in seen:
            continue
        seen.add(token)
        candidates.append(token)
    return candidates


def contains_any(text: str, patterns: Iterable[str], *, contains_pattern_fn) -> bool:
    for pattern in patterns:
        token = str(pattern or "").strip().lower()
        if token and contains_pattern_fn(text, token):
            return True
    return False


def contains_pattern(text: str, token: str, *, ascii_token_boundary_safe_fn) -> bool:
    if not token:
        return False
    if ascii_token_boundary_safe_fn(token):
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text) is not None
    return token in text


def ascii_token_boundary_safe(token: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_- ")
    return all(char in allowed for char in token)
